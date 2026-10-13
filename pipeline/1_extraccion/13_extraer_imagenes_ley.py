"""
13_extraer_imagenes_ley.py — Imágenes embebidas en LeyChile
============================================================
El artículo 1 de la Ley de Presupuestos —el detalle de ingresos y
gastos que aprueba el Congreso— se publica como imagen JPEG
embebida en base64 dentro del XML, no como texto.

Este script las extrae a archivos para poder leerlas (OCR o a mano).

Estructura en el XML:
    <aem:ArchivoBinario>
      <aem:Nombre>Ley 21640_1.jpeg</aem:Nombre>
      <aem:TipoContenido>image/jpeg</aem:TipoContenido>
      <aem:CantidadBytes>127863</aem:CantidadBytes>
      <aem:DataCodificada>/9j/4AAQ... (con espacios cada 76 chars)
    </aem:ArchivoBinario>

Uso:
    python 13_extraer_imagenes_ley.py
    python 13_extraer_imagenes_ley.py --solo ley_presupuestos_2024
"""

import argparse
import base64
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from dipres.config import DIRS
from dipres.hallazgos import Registro

NS = {"aem": "http://valida.aem.gob.cl"}

DIR_RAW = DIRS["normativa"] / "raw"
DIR_IMG = DIRS["normativa"] / "imagenes"

EXT_POR_TIPO = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}


def slug(nombre: str) -> str:
    """'Ley 21640_1.jpeg' → 'ley_21640_1'"""
    base = Path(nombre).stem
    return re.sub(r"[^\w]+", "_", base).strip("_").lower()


def extraer(ruta_xml: Path, reg: Registro) -> list[dict]:
    """Extrae todos los ArchivoBinario de un XML de LeyChile."""
    try:
        raiz = ET.parse(ruta_xml).getroot()
    except ET.ParseError as e:
        reg.error("xml", f"{ruta_xml.name}: {e}")
        return []

    destino = DIR_IMG / ruta_xml.stem
    resultados = []
    vistos = set()

    for nodo in raiz.iter(f"{{{NS['aem']}}}ArchivoBinario"):
        nombre = (nodo.findtext("aem:Nombre", "", NS) or "").strip()
        tipo = (nodo.findtext("aem:TipoContenido", "", NS) or "").strip()
        declarado = nodo.findtext("aem:CantidadBytes", "", NS) or "0"
        data = nodo.findtext("aem:DataCodificada", "", NS) or ""

        if not data:
            continue

        # El mismo archivo aparece dos veces (.jpeg y .jpg)
        clave = slug(nombre)
        if clave in vistos:
            continue
        vistos.add(clave)

        # El base64 viene partido en líneas de 76 chars: quitar
        # todo lo que no pertenezca al alfabeto base64
        limpio = re.sub(r"[^A-Za-z0-9+/=]", "", data)

        try:
            binario = base64.b64decode(limpio, validate=True)
        except Exception as e:
            reg.error("base64", f"{nombre}: no decodifica ({e})")
            continue

        ext = EXT_POR_TIPO.get(tipo, Path(nombre).suffix or ".bin")
        salida = destino / f"{clave}{ext}"
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_bytes(binario)

        # Verificación de integridad: tamaño declarado vs obtenido
        esperado = int(declarado) if declarado.isdigit() else 0
        coincide = esperado == len(binario)
        if esperado and not coincide:
            reg.warn("integridad",
                     f"{nombre}: {len(binario):,} bytes vs {esperado:,} declarados",
                     patron="tamaño no coincide")
        else:
            reg.ok("extraccion", f"{nombre} → {salida.name} ({len(binario):,} bytes)")

        resultados.append({
            "archivo": salida, "nombre": nombre, "tipo": tipo,
            "bytes": len(binario), "integridad": coincide or not esperado,
        })

    return resultados


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", help="procesar un solo documento por su slug")
    args = ap.parse_args()

    reg = Registro("imagenes_ley", salida_dir=DIRS["reportes"])

    xmls = sorted(DIR_RAW.glob("*.xml"))
    if args.solo:
        xmls = [x for x in xmls if x.stem == args.solo]

    if not xmls:
        print(f"Sin XML en {DIR_RAW}")
        raise SystemExit

    total = 0
    for xml in xmls:
        imgs = extraer(xml, reg)
        if imgs:
            print(f"\n{xml.stem} — {len(imgs)} imagen(es)")
            for i in imgs:
                marca = "" if i["integridad"] else "  ⚠ tamaño no coincide"
                print(f"  {i['archivo'].name:<24} {i['bytes']:>9,} bytes"
                      f"  {i['tipo']}{marca}")
            total += len(imgs)

    print(f"\n{total} imágenes en {DIR_IMG}")
    reg.emitir()