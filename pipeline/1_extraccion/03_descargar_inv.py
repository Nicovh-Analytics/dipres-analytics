"""
03_descargar_inv.py — Descarga de Iniciativas de Inversión DIPRES
==================================================================
Busca y descarga los datasets de ejecución presupuestaria de iniciativas
de inversión desde datos.gob.cl. Traen desagregación geográfica
(región/comuna) que la ejecución regular no tiene.

Destino: DIRS["inversion"] / <año> / <nivel>.csv

Uso:
    python pipeline/1_extraccion/03_descargar_inv.py                    # pregunta antes de bajar
    python pipeline/1_extraccion/03_descargar_inv.py --si               # sin preguntar
    python pipeline/1_extraccion/03_descargar_inv.py --inspeccionar     # muestra la estructura del
                                                  # primer CSV y termina
    python pipeline/1_extraccion/03_descargar_inv.py --revisar-tamano   # re-baja archivos cortados
"""

import argparse
import re
from io import StringIO

import pandas as pd

from dipres.config import DIRS, IO, LOGS
from dipres.descarga import (SESION, LogDescarga, buscar_ckan, ejecutar_tareas,
                      imprimir_conteo)

QUERIES = ["Iniciativas de Inversión"]
NIVELES = ["programa", "capitulo", "partida", "nacional"]
TERMINOS_GEO = ["region", "región", "comuna", "localiz", "ubicac", "geo"]


# =====================================================
# Selección
# =====================================================
def es_inversion(ds: dict) -> bool:
    t = ds.get("title", "").lower()
    return "iniciativa" in t and "inversión" in t


def variante(titulo: str) -> str:
    t = titulo.lower()
    if "total" in t:
        return "total"
    if "ley regular" in t:
        return "ley_regular"
    if "fet" in t:
        return "fet"
    return "total"   # datasets antiguos sin variante = total


def elegir_por_anio(datasets: list[dict]) -> dict[str, dict]:
    """Un dataset por año, prefiriendo Total > Ley Regular > otra."""
    por_anio: dict[str, dict] = {}
    for ds in datasets:
        m = re.search(r"\b(20\d{2})\b", ds.get("title", ""))
        if m:
            por_anio.setdefault(m.group(1), {})[variante(ds["title"])] = ds

    elegidos = {}
    for anio, vs in sorted(por_anio.items()):
        clave = next((k for k in ("total", "ley_regular") if k in vs),
                     next(iter(vs)))
        elegidos[anio] = vs[clave]
        print(f"  {anio}: variante {clave}")
    return elegidos


def nivel_recurso(nombre: str) -> str:
    n = nombre.lower().replace("í", "i")
    if "diccionario" in n:
        return "diccionario"
    return next((nv for nv in NIVELES if nv in n), "detalle")


def armar_tareas(elegidos: dict) -> list:
    tareas = []
    for anio, ds in elegidos.items():
        usados: dict[str, int] = {}
        for r in ds.get("resources", []):
            if r.get("format", "").upper() != "CSV":
                continue
            nivel = nivel_recurso(r.get("name", ""))
            # Dos recursos al mismo nivel no se pisan: detalle, detalle_2...
            usados[nivel] = usados.get(nivel, 0) + 1
            nombre = nivel if usados[nivel] == 1 else f"{nivel}_{usados[nivel]}"
            tareas.append((DIRS["inversion"] / anio / f"{nombre}.csv",
                           r.get("url", ""), ds.get("title", "")))
    return tareas


# =====================================================
# Inspección (exploratoria)
# =====================================================
def inspeccionar_muestra(url: str, nombre: str, filas: int = 100) -> None:
    print(f"\n🔍 Inspeccionando: {nombre}\n   URL: {url[:80]}...")
    try:
        with SESION.get(url, timeout=30, stream=True) as r:
            r.raise_for_status()
            lineas = [l for _, l in zip(range(filas + 5), r.iter_lines())]
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return

    crudo = b"\n".join(lineas)
    for enc in IO["encodings"]:          # latin-1 va último: nunca falla
        try:
            texto = crudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    primera = texto.splitlines()[0] if texto else ""
    sep = max(IO["separadores"], key=primera.count)
    df = pd.read_csv(StringIO(texto), nrows=filas, sep=sep, index_col=False,
                     on_bad_lines="warn")

    print(f"   Encoding: {enc} | Separador: '{sep}' | Dimensiones: {df.shape}")
    print(f"\n   Columnas ({len(df.columns)}):")
    for col in df.columns:
        v = df[col].dropna()
        ej = str(v.iloc[0])[:40] if not v.empty else "VACÍO"
        print(f"     {col:<40s} | {str(df[col].dtype):<10s} | Ej: {ej}")

    geo = [c for c in df.columns if any(t in c.lower() for t in TERMINOS_GEO)]
    if geo:
        print(f"\n   📍 Columnas geográficas: {geo}")
        for c in geo:
            print(f"      {c}: {list(df[c].dropna().unique()[:10])}")
    else:
        print("\n   ⚠ No se detectaron columnas geográficas explícitas")


# =====================================================
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--si", action="store_true", help="no preguntar")
    ap.add_argument("--sobrescribir", action="store_true")
    ap.add_argument("--revisar-tamano", action="store_true",
                    help="comparar archivos existentes con el tamaño remoto")
    ap.add_argument("--inspeccionar", action="store_true",
                    help="mostrar la estructura del primer CSV y terminar")
    args = ap.parse_args()

    print("=" * 70)
    print("  DESCARGA — INICIATIVAS DE INVERSIÓN DIPRES")
    print("=" * 70)
    print(f"\nDestino: {DIRS['inversion']}\n")

    print("🔍 Buscando datasets de Iniciativas de Inversión...")
    datasets = buscar_ckan(QUERIES, filtro=es_inversion)
    print(f"  Encontrados: {len(datasets)}")
    if not datasets:
        raise SystemExit("❌ No se encontraron datasets")

    print("\n📋 Variante elegida por año:")
    elegidos = elegir_por_anio(datasets)

    if args.inspeccionar:
        anio, ds = next(iter(sorted(elegidos.items())))
        r = next((r for r in ds.get("resources", [])
                  if r.get("format", "").upper() == "CSV"), None)
        if r:
            inspeccionar_muestra(r["url"], f"inversion_{anio}")
        raise SystemExit

    tareas = armar_tareas(elegidos)
    print(f"\n{'=' * 70}")
    if not args.si and input(f"¿Procesar {len(tareas)} archivos de "
                             f"{len(elegidos)} años? (s/n): "
                             ).strip().lower() != "s":
        raise SystemExit("Cancelado.")

    n = ejecutar_tareas(tareas, LogDescarga(LOGS["inversion"]),
                        DIRS["inversion"], args.sobrescribir,
                        args.revisar_tamano)

    print(f"\n{'=' * 70}\n  DESCARGA COMPLETA\n{'=' * 70}")
    imprimir_conteo(n)