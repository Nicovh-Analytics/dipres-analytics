"""
02_descargar.py — Descarga de ley y ejecución mensual DIPRES (datos.gob.cl)
============================================================================
Clasifica cada dataset por su cobertura temporal, resuelve la variante
"Total efectiva" cuando existen varias (Ley Regular / FET / Total) y
descarga con reintentos, validación de tamaño y log resumible.

Destino: DIRS["ley"] y DIRS["ejecucion"] / <año> / <mes> / <nivel>.csv

Los datasets que no encajan en el patrón mensual (trimestrales legado,
informes desagregados, iniciativas de inversión, sin clasificar) NO se
descargan: se listan en LOGS["no_procesado"] para revisión manual.
Iniciativas de inversión → 03_descargar_inv.py.

Uso:
    python 02_descargar.py                    # pregunta antes de bajar
    python 02_descargar.py --si               # sin preguntar
    python 02_descargar.py --revisar-tamano   # re-baja archivos cortados
    python 02_descargar.py --sobrescribir     # vuelve a bajar todo
"""

import argparse
import json
import re
from collections import defaultdict

from config import DIRS, LOGS
from descarga import (LogDescarga, buscar_ckan, ejecutar_tareas,
                      imprimir_conteo)

QUERIES = [
    "Ejecución Presupuestaria Gobierno Central",
    "Ley de Presupuestos Inicial y Vigente",
]

MESES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}
RX_PERIODO = re.compile(r"\ba\s+(" + "|".join(MESES) + r")\s+de\s+(\d{4})\b")
VARIANTES = ["ley regular", "total", "fet incendios", "fet covid-19", "fet covid"]
NIVELES = ["nacional", "partida", "capitulo", "programa"]


# =====================================================
# Clasificación
# =====================================================
def es_dipres(ds: dict) -> bool:
    org = ((ds.get("organization") or {}).get("title") or "").lower()
    return "presupuesto" in org or "direcci" in org


def clasificar_dataset(titulo: str, formatos: set[str]) -> str:
    tl = titulo.lower()
    if "CSV" not in formatos:
        return "sin_csv"
    if "iniciativas de inversion" in tl or "iniciativas de inversión" in tl:
        return "iniciativas_inversion"
    if "trimestre" in tl:
        return "trimestral_legado"
    if "informes desagregados" in tl:
        return "informes_desagregados_legado"
    if not RX_PERIODO.search(tl):
        return "sin_clasificar"
    return ("mensual_con_variante" if any(v in tl for v in VARIANTES)
            else "mensual_sin_variante")


def extraer_tipo(titulo: str) -> str | None:
    tl = titulo.lower()
    if "ejecuci" in tl:
        return "ejecucion"
    if "ley de presupuestos" in tl:
        return "ley"
    return None


def agrupar_y_elegir(datasets: list[dict]) -> tuple[dict, dict]:
    """{(tipo, año, mes): dataset} eligiendo 'Total' si hay variantes."""
    por_periodo = defaultdict(list)
    no_procesados = defaultdict(list)

    for ds in datasets:
        titulo = ds.get("title", "")
        formatos = {r.get("format", "").upper() for r in ds.get("resources", [])}
        grupo = clasificar_dataset(titulo, formatos)
        if not grupo.startswith("mensual"):
            no_procesados[grupo].append(titulo)
            continue

        tipo = extraer_tipo(titulo)
        m = RX_PERIODO.search(titulo.lower())
        if not tipo or not m:
            no_procesados["sin_tipo_o_periodo"].append(titulo)
            continue
        por_periodo[(tipo, m.group(2), MESES[m.group(1)])].append((titulo, ds))

    elegidos = {}
    for clave, candidatos in por_periodo.items():
        if len(candidatos) == 1:
            elegidos[clave] = candidatos[0][1]
            continue
        total = next((ds for t, ds in candidatos if "total" in t.lower()), None)
        if total:
            elegidos[clave] = total
        else:
            no_procesados["con_variante_sin_total"].extend(t for t, _ in candidatos)

    return elegidos, no_procesados


def nivel_recurso(nombre: str) -> str | None:
    n = nombre.lower().replace("í", "i")
    return next((nv for nv in NIVELES if nv in n), None)


def armar_tareas(elegidos: dict) -> list:
    tareas = []
    for (tipo, anio, mes), ds in sorted(elegidos.items()):
        vistos = set()
        for r in ds.get("resources", []):
            if r.get("format", "").upper() != "CSV":
                continue
            nivel = nivel_recurso(r.get("name", ""))
            if nivel is None:          # diccionario u otro
                continue
            if nivel in vistos:        # dos recursos al mismo nivel: avisar
                print(f"   ⚠ {tipo} {anio}-{mes}: más de un CSV de nivel "
                      f"'{nivel}', se usa el primero")
                continue
            vistos.add(nivel)
            tareas.append((DIRS[tipo] / anio / mes / f"{nivel}.csv",
                           r.get("url", ""), ds.get("title", "")))
    return tareas


# =====================================================
# Reporte
# =====================================================
def imprimir_resumen(elegidos: dict, no_procesados: dict) -> None:
    print(f"\n{'=' * 70}\nRESUMEN DE CLASIFICACIÓN\n{'=' * 70}")
    for tipo in ("ley", "ejecucion"):
        periodos = sorted(k for k in elegidos if k[0] == tipo)
        if periodos:
            print(f"\n  {tipo.upper()}: {len(periodos)} períodos "
                  f"({periodos[0][1]}-{periodos[0][2]} → "
                  f"{periodos[-1][1]}-{periodos[-1][2]})")
    if no_procesados:
        print("\n  ⚠ No incorporados automáticamente (requieren revisión):")
        for grupo, titulos in no_procesados.items():
            print(f"    {grupo}: {len(titulos)} datasets")


def guardar_no_procesados(no_procesados: dict) -> None:
    if not no_procesados:
        return
    ruta = LOGS["no_procesado"]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(no_procesados, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"\n💾 No procesados guardados en: {ruta}")


# =====================================================
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--si", action="store_true", help="no preguntar")
    ap.add_argument("--sobrescribir", action="store_true")
    ap.add_argument("--revisar-tamano", action="store_true",
                    help="comparar archivos existentes con el tamaño remoto")
    args = ap.parse_args()

    print("=" * 70)
    print("  DESCARGA DIPRES — SERIE 'TOTAL EFECTIVA' CONTINUA")
    print("=" * 70)
    print(f"\nDestino: {DIRS['raw']}\n")

    print("🔍 Buscando datasets en CKAN...")
    datasets = buscar_ckan(QUERIES, filtro=es_dipres)
    print(f"📊 Datasets DIPRES únicos: {len(datasets)}")

    elegidos, no_procesados = agrupar_y_elegir(datasets)
    imprimir_resumen(elegidos, no_procesados)
    guardar_no_procesados(no_procesados)
    tareas = armar_tareas(elegidos)

    print(f"\n{'=' * 70}")
    if not args.si and input(f"¿Procesar {len(tareas)} archivos? (s/n): "
                             ).strip().lower() != "s":
        raise SystemExit("Cancelado, nada descargado.")

    n = ejecutar_tareas(tareas, LogDescarga(LOGS["descarga"]), DIRS["raw"],
                        args.sobrescribir, args.revisar_tamano)

    print(f"\n{'=' * 70}\nDESCARGA COMPLETA\n{'=' * 70}")
    imprimir_conteo(n)