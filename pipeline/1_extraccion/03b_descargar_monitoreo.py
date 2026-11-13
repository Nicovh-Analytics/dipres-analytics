"""
03b_descargar_monitoreo.py — Bases de monitoreo de programas sociales (BIPS)
============================================================================
Baja las bases de monitoreo de la oferta pública que publica el Ministerio
de Desarrollo Social y Familia en su portal CKAN (Banco Integrado de
Programas Sociales, proceso conjunto SES-DIPRES), con sus diccionarios.

Las deja en raw/externo/bips/ con nombre normalizado:
    base_<año>.xlsx          (año de la base tal como la nombra el portal)
    diccionario_<año>.<ext>

Selección de recursos: datasets "Proceso de monitoreo…" (no CASEN), formato
Excel o CSV, un año 2010-2029 en el nombre del recurso o del dataset, y "diccionario" o "base"/"monitoreo" en el
texto. Si dos recursos caen en el mismo destino, se queda el primero y se
avisa. Antes de bajar, revisar la selección con --lista.

Uso:
    python pipeline/1_extraccion/03b_descargar_monitoreo.py --lista
    python pipeline/1_extraccion/03b_descargar_monitoreo.py --si
    python pipeline/1_extraccion/03b_descargar_monitoreo.py --si --revisar-contenido
"""

import argparse
import re
from pathlib import Path

from dipres.config import DIRS
from dipres.descarga import (LogDescarga, buscar_ckan, ejecutar_tareas,
                             imprimir_conteo)
from dipres.hallazgos import Registro

CKAN_MDSF = "https://bid-ckan.ministeriodesarrollosocial.gob.cl/api/3/action"
QUERIES = ["monitoreo", "programas sociales", "oferta programática"]
DESTINO = DIRS.get("externo", DIRS["raw"] / "externo") / "bips"
LOG = DIRS["logs"] / "_log_monitoreo.json"
FORMATOS = {"xlsx", "xls", "csv"}
RX_ANIO = re.compile(r"(?<!\d)(20[12]\d)(?!\d)")


def es_monitoreo(ds: dict) -> bool:
    t = (ds.get("title") or "").lower()
    return "monitoreo" in t and "casen" not in t


def clasificar(ds: dict, rec: dict) -> tuple[str, int, str] | None:
    """(tipo, año, extensión) de un recurso, o None si no es base ni
    diccionario de monitoreo. Solo datasets del proceso de monitoreo: el
    portal también publica CASEN, cuyos libros de códigos calzan con
    "base" y un año."""
    if not es_monitoreo(ds):
        return None
    fmt = (rec.get("format") or "").lower().strip(".")
    url = rec.get("url") or ""
    ext = fmt if fmt in FORMATOS else Path(url.split("?")[0]).suffix.lower().strip(".")
    if ext not in FORMATOS:
        return None
    texto = " ".join([rec.get("name") or "", rec.get("description") or "",
                      ds.get("title") or "", url]).lower()
    m = RX_ANIO.search(rec.get("name") or "") or RX_ANIO.search(ds.get("title") or "")
    if not m:
        return None
    if "diccionario" in texto:
        tipo = "diccionario"
    elif "base" in texto or "monitoreo" in texto:
        tipo = "base"
    else:
        return None
    return tipo, int(m.group(1)), ext


def tareas_monitoreo() -> tuple[list[tuple[Path, str, str]], list[str]]:
    datasets = buscar_ckan(QUERIES, filtro=es_monitoreo, base_url=CKAN_MDSF)
    tareas, avisos, vistos = [], [], {}
    for ds in sorted(datasets, key=lambda d: d.get("title") or ""):
        for rec in ds.get("resources", []):
            c = clasificar(ds, rec)
            if c is None:
                continue
            tipo, anio, ext = c
            destino = DESTINO / (f"base_{anio}.xlsx" if tipo == "base" and ext != "csv"
                                 else f"{tipo}_{anio}.{ext}")
            if destino in vistos:
                avisos.append(f"{destino.name}: ya asignado a «{vistos[destino]}»; "
                              f"se omite «{rec.get('name')}» ({ds.get('title')})")
                continue
            vistos[destino] = rec.get("name")
            tareas.append((destino, rec["url"], ds.get("title") or ""))
    return sorted(tareas), avisos


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lista", action="store_true", help="mostrar la selección y salir")
    ap.add_argument("--si", action="store_true", help="no pedir confirmación")
    ap.add_argument("--revisar-contenido", action="store_true",
                    help="volver a bajar los existentes y comparar SHA-256")
    args = ap.parse_args()

    reg = Registro("descarga_monitoreo", salida_dir=DIRS["reportes"])
    tareas, avisos = tareas_monitoreo()
    print(f"\nPortal MDSF: {len(tareas)} recursos seleccionados → {DESTINO}")
    for destino, url, titulo in tareas:
        marca = "✓" if destino.exists() else "·"
        print(f"  {marca} {destino.name:24} {titulo[:45]:45} {url}")
    for a in avisos:
        reg.warn("seleccion", a, patron="recurso duplicado para un mismo destino")
    if not tareas:
        reg.error("seleccion", "el portal no devolvió bases ni diccionarios de monitoreo")
        reg.emitir()
        return
    if args.lista:
        return
    if not args.si and input("\n¿Descargar? [s/N] ").strip().lower() != "s":
        return

    n = ejecutar_tareas(tareas, LogDescarga(LOG), base=DESTINO.parent,
                        revisar_contenido=args.revisar_contenido)
    imprimir_conteo(n)
    bases = sorted(int(d.stem.split("_")[1]) for d, _, _ in tareas
                   if d.name.startswith("base_") and d.exists())
    if n["errores"]:
        reg.error("descarga", f"{n['errores']} recursos no se pudieron bajar")
    if n.get("cambiados"):
        reg.warn("contenido", f"{n['cambiados']} archivos cambiaron en el portal "
                              f"(anterior en _versiones/)")
    reg.ok("descarga", f"bases disponibles: {', '.join(map(str, bases))}")
    reg.emitir()


if __name__ == "__main__":
    main()