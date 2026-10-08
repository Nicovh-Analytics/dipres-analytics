"""
12_descargar_normativa.py — Corpus normativo presupuestario
============================================================
Descarga las normas que definen el criterio de cumplimiento y
extrae los artículos relevantes.

Estrategia de obtención, en orden:
  1. LeyChile XML  → texto estructurado, sin parsear PDF
  2. LeyChile HTML → fallback si el XML falla
  3. PDF           → solo para normas que no estén en LeyChile

Salida en DIRS["normativa"]:
  raw/<slug>.xml|.html|.pdf   respaldo íntegro, nunca se modifica
  texto/<slug>.txt            texto plano extraído
  articulos/<slug>.json       artículos clave aislados

El CSV de criterios NO lo genera este script: se arma leyendo
los artículos extraídos. Interpretar articulado no se automatiza
de forma confiable.

Uso:
    python 12_descargar_normativa.py
    python 12_descargar_normativa.py --solo 2024
"""

import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from config import DIRS, HTTP
from hallazgos import Registro
from normativa import (ARTICULOS_CLAVE, DECRETOS_MODIFICACIONES,
                       LEYES_PRESUPUESTO, PERMANENTES, normas_pendientes)

# LeyChile entrega el texto de la norma como XML
LEYCHILE_XML = "https://www.leychile.cl/Consulta/obtxml?opt=7&idNorma={id}"
LEYCHILE_HTML = "https://www.bcn.cl/leychile/navegar?idNorma={id}"

BASE = DIRS.get("normativa", DIRS["base"] / "normativa")
DIR_RAW = BASE / "raw"
DIR_TEXTO = BASE / "texto"
DIR_ARTICULOS = BASE / "articulos"


# =====================================================
# Descarga
# =====================================================
def obtener(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=HTTP["headers"], timeout=HTTP["timeout"])
        r.raise_for_status()
        return r.content if len(r.content) > 500 else None
    except Exception:
        return None


def descargar_norma(id_norma: int, slug: str, reg: Registro) -> Path | None:
    """Intenta XML y cae a HTML. Devuelve la ruta del archivo crudo."""
    for ext, url in (("xml", LEYCHILE_XML), ("html", LEYCHILE_HTML)):
        destino = DIR_RAW / f"{slug}.{ext}"
        if destino.exists() and destino.stat().st_size > 500:
            return destino

        contenido = obtener(url.format(id=id_norma))
        if contenido:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(contenido)
            reg.ok("descarga", f"{slug} ({ext}, {len(contenido):,} bytes)")
            time.sleep(HTTP["pausa_entre_descargas"])
            return destino

    reg.error("descarga", f"{slug}: falló XML y HTML (idNorma={id_norma})")
    return None


# =====================================================
# Extracción de texto
# =====================================================
def texto_desde_xml(ruta: Path) -> str:
    """LeyChile anida el articulado en nodos <Texto>."""
    try:
        raiz = ET.parse(ruta).getroot()
    except ET.ParseError:
        return ""
    # itertext() recorre todo el árbol sin depender del esquema exacto
    partes = (t.strip() for t in raiz.itertext())
    return "\n".join(p for p in partes if p)


def texto_desde_html(ruta: Path) -> str:
    html = ruta.read_text(encoding="utf-8", errors="ignore")
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>|</p>|</div>", "\n", html, flags=re.I)
    texto = re.sub(r"<[^>]+>", " ", html)
    texto = (texto.replace("&nbsp;", " ").replace("&aacute;", "á")
                  .replace("&eacute;", "é").replace("&iacute;", "í")
                  .replace("&oacute;", "ó").replace("&uacute;", "ú")
                  .replace("&ntilde;", "ñ").replace("&amp;", "&"))
    return re.sub(r"[ \t]{2,}", " ", texto)


def texto_desde_pdf(ruta: Path) -> str:
    """Solo para normas que no estén en LeyChile. Requiere pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        return "\n".join(p.extract_text() or "" for p in PdfReader(ruta).pages)
    except Exception:
        return ""


EXTRACTORES = {".xml": texto_desde_xml, ".html": texto_desde_html,
               ".pdf": texto_desde_pdf}


# =====================================================
# Aislamiento de artículos
# =====================================================
# "Artículo 4.-" / "Artículo 4º" / "ARTICULO 4" — el articulado
# chileno usa varias formas, incluso dentro del mismo documento.
RE_ARTICULO = re.compile(
    r"Art[íi]culo\s+(\d+)\s*[.ºª°\-–]*", re.IGNORECASE)


def partir_en_articulos(texto: str) -> dict[int, str]:
    """
    Corta el texto en artículos. Un solo barrido con finditer:
    cada artículo va desde su encabezado hasta el siguiente.
    """
    marcas = [(m.start(), int(m.group(1))) for m in RE_ARTICULO.finditer(texto)]
    if not marcas:
        return {}

    arts: dict[int, str] = {}
    for i, (pos, num) in enumerate(marcas):
        fin = marcas[i + 1][0] if i + 1 < len(marcas) else len(texto)
        cuerpo = texto[pos:fin].strip()
        # Nos quedamos con la aparición más larga: las referencias
        # cruzadas ("conforme al artículo 26") generan falsos cortes
        if num not in arts or len(cuerpo) > len(arts[num]):
            arts[num] = cuerpo
    return arts


def procesar(ruta_raw: Path, slug: str, reg: Registro) -> dict | None:
    extractor = EXTRACTORES.get(ruta_raw.suffix.lower())
    if not extractor:
        reg.warn("extraccion", f"{slug}: formato no soportado {ruta_raw.suffix}")
        return None

    texto = extractor(ruta_raw)
    if len(texto) < 1000:
        reg.warn("extraccion", f"{slug}: texto muy corto ({len(texto)} chars)",
                 patron="extracción vacía o fallida")
        return None

    DIR_TEXTO.mkdir(parents=True, exist_ok=True)
    (DIR_TEXTO / f"{slug}.txt").write_text(texto, encoding="utf-8")

    arts = partir_en_articulos(texto)
    clave = {n: arts[n] for n in ARTICULOS_CLAVE if n in arts}

    DIR_ARTICULOS.mkdir(parents=True, exist_ok=True)
    (DIR_ARTICULOS / f"{slug}.json").write_text(
        json.dumps({"slug": slug, "n_articulos": len(arts), "clave": clave},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    faltan = [n for n in ARTICULOS_CLAVE if n not in arts]
    if faltan:
        reg.warn("articulos", f"{slug}: no se ubicaron los artículos {faltan}",
                 patron="artículo clave ausente")
    else:
        reg.ok("articulos", f"{slug}: {len(arts)} artículos, todos los clave")

    return {"slug": slug, "chars": len(texto), "articulos": len(arts),
            "clave_ok": len(clave)}


# =====================================================
# Main
# =====================================================
def corpus(solo_anio: int | None = None) -> list[tuple[int, str]]:
    """Devuelve [(id_norma, slug)] de lo que tiene id registrado."""
    items = []
    if solo_anio is None:
        for k, v in PERMANENTES.items():
            if v["id_norma"]:
                items.append((v["id_norma"], k))
    for anio, v in LEYES_PRESUPUESTO.items():
        if v["id_norma"] and (solo_anio is None or anio == solo_anio):
            items.append((v["id_norma"], f"ley_presupuestos_{anio}"))
    for anio, v in DECRETOS_MODIFICACIONES.items():
        if v["id_norma"] and (solo_anio is None or anio == solo_anio):
            items.append((v["id_norma"], f"decreto_modificaciones_{anio}"))
    return items


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", type=int, help="procesar un solo año")
    args = ap.parse_args()

    reg = Registro("normativa", salida_dir=DIRS["reportes"])
    for d in (DIR_RAW, DIR_TEXTO, DIR_ARTICULOS):
        d.mkdir(parents=True, exist_ok=True)

    objetivo = corpus(args.solo)
    print(f"Corpus con idNorma registrado: {len(objetivo)} normas\n")

    resultados = []
    for id_norma, slug in objetivo:
        print(f"→ {slug}")
        raw = descargar_norma(id_norma, slug, reg)
        if raw:
            r = procesar(raw, slug, reg)
            if r:
                resultados.append(r)
                print(f"  {r['chars']:,} chars · {r['articulos']} artículos · "
                      f"{r['clave_ok']}/{len(ARTICULOS_CLAVE)} clave")

    pendientes = normas_pendientes()
    if pendientes:
        print(f"\n{'─' * 60}")
        print(f"Sin idNorma en el registro ({len(pendientes)}):")
        for p in pendientes:
            print(f"  {p}")
        print("\nBuscar en https://www.bcn.cl/leychile y completar normativa.py")
        reg.warn("registro", f"{len(pendientes)} normas sin idNorma")

    print(f"\nRespaldo:  {DIR_RAW}")
    print(f"Texto:     {DIR_TEXTO}")
    print(f"Artículos: {DIR_ARTICULOS}")
    reg.emitir()