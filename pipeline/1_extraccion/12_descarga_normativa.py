"""
12_descargar_normativa.py — Corpus normativo presupuestario
============================================================
Descarga las normas que definen el criterio de cumplimiento y
extrae los artículos relevantes.

Estrategia de obtención, en orden:
  1. LeyChile XML  → texto estructurado, sin parsear PDF
  2. LeyChile HTML → fallback si el XML falla
  3. PDF           → solo para normas que no estén en LeyChile

Excepción — Leyes de Presupuestos: el XML de LeyChile es el RESUMEN
publicado en el Diario Oficial (DL 1.263, art. 20) y las tablas de los
artículos 1 y 2 vienen como imagen. Por eso, además del XML, se baja la
ley completa desde la Dipres (PDF, un archivo por año), donde esas
tablas vienen como texto y se incluye el detalle por partida, capítulo
y programa. Se guardan ambas versiones: XML para el articulado limpio,
PDF de la Dipres para las cifras.

Salida en DIRS["normativa"]:
  raw/<slug>.xml|.html|.pdf   respaldo íntegro, nunca se modifica
  texto/<slug>.txt            texto plano extraído
  articulos/<slug>.json       artículos clave aislados
  (Dipres: slug = ley_presupuestos_<año>_dipres; su texto y artículos
   salen solo de las primeras DIPRES_PAGINAS_ARTICULADO páginas)

El CSV de criterios NO lo genera este script: se arma leyendo
los artículos extraídos. Interpretar articulado no se automatiza
de forma confiable.

Uso:
    python pipeline/1_extraccion/12_descarga_normativa.py
    python pipeline/1_extraccion/12_descarga_normativa.py --solo 2024
    python pipeline/1_extraccion/12_descarga_normativa.py --sin-dipres
"""

import argparse
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from itertools import islice
from pathlib import Path
from urllib.parse import urljoin

import requests

from dipres.config import DIRS, HTTP
from dipres.hallazgos import Registro
from dipres.normativa import (ARTICULOS_CLAVE, DECRETOS_MODIFICACIONES,
                       LEYES_PRESUPUESTO, PERMANENTES, normas_pendientes)

# LeyChile entrega el texto de la norma como XML
LEYCHILE_XML = "https://www.leychile.cl/Consulta/obtxml?opt=7&idNorma={id}"
LEYCHILE_HTML = "https://www.bcn.cl/leychile/navegar?idNorma={id}"

# Ley de Presupuestos COMPLETA, publicada por la Dipres (un PDF por año).
DIPRES_PAGINA = "https://www.dipres.gob.cl/598/w3-propertyvalue-15954.html"
DIPRES_BASE = "https://www.dipres.gob.cl/598/"
# Respaldo observado el 2026-10-08. Solo se usa si la página no entrega el año.
DIPRES_RESPALDO = {
    2017: "articles-158418_doc_pdf.pdf",
    2018: "articles-172496_doc_pdf.pdf",
    2019: "articles-187231_doc_pdf.pdf",
    2020: "articles-202693_doc_pdf.pdf",
    2021: "articles-229524_doc_pdf.pdf",
    2022: "articles-266626_doc_pdf.pdf",
    2023: "articles-316305_doc_pdf.pdf",
    2024: "articles-330063_doc_pdf.pdf",
    2025: "articles-363446_doc_pdf.pdf",
    2026: "articles-406493_doc_pdf.pdf",
}
# Páginas iniciales a extraer: índice + articulado (en la ley 2021 el articulado
# cierra antes de la página 35 del PDF). El detalle por partida (1.000+ páginas)
# se procesa aparte. Verificado solo con la ley 2021.
DIPRES_PAGINAS_ARTICULADO = 60

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
# Descarga — ley completa desde la Dipres
# =====================================================
def enlaces_dipres() -> tuple[dict[int, str], str]:
    """
    ({año: url_pdf}, motivo) leído de la página de la Dipres. Si no se puede,
    el dict va vacío y `motivo` explica por qué (HTTP, tamaño, redirecciones).
    El año se toma del title del propio enlace ("... año 2021"). Un enlace sin
    año identificable se ignora: es preferible caer al respaldo con aviso que
    asignarle un año equivocado en silencio.
    """
    try:
        r = requests.get(DIPRES_PAGINA, headers=HTTP["headers"],
                         timeout=HTTP["timeout"])
    except requests.RequestException as e:
        return {}, f"la petición falló: {type(e).__name__}: {e}"

    # unescape: si el HTML crudo trae "a&ntilde;o", lo deja como "año"
    cuerpo = unescape(r.content.decode("utf-8", errors="replace"))
    info = (f"HTTP {r.status_code}, {len(r.content):,} bytes, "
            f"{r.headers.get('Content-Type', '?')}, "
            f"{len(r.history)} redirecciones, URL final {r.url}")
    if r.status_code != 200:
        return {}, f"respuesta no exitosa ({info})"

    enlaces: dict[int, str] = {}
    for m in re.finditer(r"<a\b[^>]*>", cuerpo, flags=re.I):
        tag = m.group(0)
        href = re.search(r'href=["\']([^"\']*articles-\d+_doc_pdf\.pdf)["\']',
                         tag, re.I)
        anio = re.search(r"title=[\"'][^\"']*a[ñn]o\s+(\d{4})", tag, re.I)
        if href and anio:
            # setdefault: ante un año repetido nos quedamos con el primero
            enlaces.setdefault(int(anio.group(1)),
                               urljoin(DIPRES_PAGINA, href.group(1)))
    if not enlaces:
        n_pdf = len(re.findall(r"articles-\d+_doc_pdf\.pdf", cuerpo))
        inicio = re.sub(r"\s+", " ", cuerpo[:200])
        return {}, (f"llegó HTML pero sin enlaces con año ({info}); "
                    f"menciones de 'articles-N_doc_pdf.pdf': {n_pdf}; "
                    f"inicio: {inicio!r}")
    return enlaces, f"{len(enlaces)} enlaces ({info})"


def _es_pdf(ruta: Path) -> bool:
    with open(ruta, "rb") as f:
        return f.read(5) == b"%PDF-"


def descargar_pdf(url: str, destino: Path, intentos: int = 3) -> tuple[int, str]:
    """
    Baja un PDF grande en streaming (obtener() lo cargaría entero en memoria).
    Escribe a .part y solo renombra si es un PDF completo, de modo que un corte
    nunca deja un archivo a medias con el nombre final. El SHA-256 se calcula en
    la misma pasada. Devuelve (bytes, sha256).
    """
    tmp = destino.with_name(destino.name + ".part")
    for n in range(1, intentos + 1):
        try:
            h, total = hashlib.sha256(), 0
            with requests.get(url, headers=HTTP["headers"],
                              timeout=HTTP["timeout"], stream=True) as r:
                r.raise_for_status()
                esperado = int(r.headers.get("Content-Length") or 0)
                comprimido = bool(r.headers.get("Content-Encoding"))
                with open(tmp, "wb") as f:
                    for trozo in r.iter_content(chunk_size=1 << 20):
                        if trozo:
                            f.write(trozo)
                            h.update(trozo)
                            total += len(trozo)
            if not _es_pdf(tmp):
                raise ValueError("la respuesta no es un PDF (¿página de error?)")
            if esperado and not comprimido and total != esperado:
                raise ValueError(f"descarga incompleta: {total:,} de {esperado:,} bytes")
            tmp.replace(destino)
            return total, h.hexdigest()
        except (requests.RequestException, ValueError, OSError):
            tmp.unlink(missing_ok=True)
            if n == intentos:
                raise
            time.sleep(5 * n)


def dipres_ley_completa(solo_anio: int | None, reg: Registro,
                        resultados: list) -> None:
    """Baja y procesa la ley completa de la Dipres para cada año registrado."""
    anios = [a for a in sorted(LEYES_PRESUPUESTO) if solo_anio in (None, a)]
    if not anios:
        return

    try:
        import pypdf  # noqa: F401
    except ImportError:
        reg.warn("dipres", "pypdf no instalado: se descargan los PDF pero no "
                           "se extrae texto (pip install pypdf)")

    enlaces, motivo = enlaces_dipres()
    if enlaces:
        print(f"  Dipres: {motivo}")
    else:
        reg.warn("dipres", f"no pude leer la página de la Dipres; uso el respaldo "
                           f"de URLs. Motivo: {motivo}")

    for anio in anios:
        url = enlaces.get(anio)
        if not url and anio in DIPRES_RESPALDO:
            url = urljoin(DIPRES_BASE, DIPRES_RESPALDO[anio])
            if enlaces:
                reg.warn("dipres", f"{anio}: no aparece en la página; uso respaldo")
        if not url:
            reg.error("dipres", f"{anio}: sin URL conocida en la Dipres")
            continue

        slug = f"ley_presupuestos_{anio}_dipres"
        destino = DIR_RAW / f"{slug}.pdf"
        destino.parent.mkdir(parents=True, exist_ok=True)
        print(f"→ {slug}")
        try:
            if destino.exists() and _es_pdf(destino):
                pass  # ya respaldado; el .part garantiza que está completo
            else:
                nbytes, digest = descargar_pdf(url, destino)
                reg.ok("descarga", f"{slug} (pdf, {nbytes:,} bytes, sha256 {digest})")
                time.sleep(HTTP["pausa_entre_descargas"])
        except (requests.RequestException, ValueError, OSError) as e:
            reg.error("descarga", f"{slug}: {e}")
            continue

        r = procesar(destino, slug, reg, max_paginas=DIPRES_PAGINAS_ARTICULADO)
        if r:
            resultados.append(r)
            print(f"  {r['chars']:,} chars · {r['articulos']} artículos · "
                  f"{r['clave_ok']}/{len(ARTICULOS_CLAVE)} clave")
        texto_completo_dipres(destino, slug, reg)


def texto_completo_dipres(pdf: Path, slug: str, reg: Registro) -> None:
    """
    Texto de TODAS las páginas (el detalle por partida viene después del
    articulado), con una marca <<<PAGINA n>>> al final de cada una para
    poder citar la página del PDF en un hallazgo.

    Son 1.000+ páginas por año: se extrae una sola vez y solo se repite si
    el PDF es más nuevo que el texto. Se escribe a .part y se renombra al
    terminar, igual que las descargas, para no dejar un texto a medias.
    """
    destino = DIR_TEXTO / f"{slug}_completo.txt"
    if destino.exists() and destino.stat().st_mtime >= pdf.stat().st_mtime:
        return
    try:
        from pypdf import PdfReader
    except ImportError:
        return  # ya avisado en dipres_ley_completa

    DIR_TEXTO.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".part")
    n = chars = 0
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            for n, pag in enumerate(PdfReader(pdf).pages, start=1):
                t = pag.extract_text() or ""
                f.write(f"{t}\n<<<PAGINA {n}>>>\n")
                chars += len(t)
        tmp.replace(destino)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        reg.warn("extraccion", f"{slug}: falló el texto completo ({e})")
        return
    reg.ok("extraccion", f"{slug}: texto completo, {n} páginas")
    print(f"  completo: {n} páginas · {chars:,} chars")


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


def texto_desde_pdf(ruta: Path, max_paginas: int | None = None) -> str:
    """
    Para normas que no estén en LeyChile y para la ley completa de la Dipres.
    Requiere pypdf. max_paginas limita la lectura a las primeras N páginas
    (None = todas); islice recorre las páginas sin cargarlas todas.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        paginas = islice(PdfReader(ruta).pages, max_paginas)
        return "\n".join(p.extract_text() or "" for p in paginas)
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


def procesar(ruta_raw: Path, slug: str, reg: Registro,
             max_paginas: int | None = None) -> dict | None:
    extractor = EXTRACTORES.get(ruta_raw.suffix.lower())
    if not extractor:
        reg.warn("extraccion", f"{slug}: formato no soportado {ruta_raw.suffix}")
        return None

    # max_paginas solo aplica a PDF (la ley completa de la Dipres tiene 1.000+ páginas)
    if ruta_raw.suffix.lower() == ".pdf":
        texto = extractor(ruta_raw, max_paginas)
    else:
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
    ap.add_argument("--sin-dipres", action="store_true",
                    help="omitir la ley completa de la Dipres")
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

    if not args.sin_dipres:
        print(f"\n{'─' * 60}\nLey completa (Dipres)\n")
        dipres_ley_completa(args.solo, reg, resultados)

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