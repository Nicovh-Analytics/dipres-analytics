"""
Descarga DIPRES — versión consolidada
======================================
Clasifica cada dataset por su cobertura temporal, resuelve la variante
"Total efectiva" cuando existen múltiples (Ley Regular / FET / Total),
y descarga con reintentos, validación de contenido y log resumible.

Los datasets que no encajan en el patrón mensual (trimestrales legado,
informes desagregados, iniciativas de inversión, sin clasificar) NO se
descargan automáticamente: se listan en _catalogo_no_procesado.json
para revisión manual.
"""

import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

# =====================================================
# CONFIGURACIÓN
# =====================================================
DATOS_DIR = Path(r"D:\dipres-datos")
CKAN_BASE = "https://datos.gob.cl/api/3/action"
LOG_FILE = DATOS_DIR / "_log_descarga.json"
NO_PROCESADOS_FILE = DATOS_DIR / "_catalogo_no_procesado.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv, application/csv, text/plain, */*",
}

MESES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}
VARIANTES = ["ley regular", "total", "fet incendios", "fet covid-19", "fet covid"]


# =====================================================
# PASO 1 — Buscar datasets en CKAN
# =====================================================
def buscar_datasets() -> list[dict]:
    print("🔍 Buscando datasets en CKAN API...")
    queries = [
        "Ejecución Presupuestaria Gobierno Central",
        "Ley de Presupuestos Inicial y Vigente",
    ]
    datasets_raw = {}

    for q in queries:
        offset = 0
        while True:
            try:
                resp = requests.get(
                    f"{CKAN_BASE}/package_search",
                    params={"q": q, "rows": 100, "start": offset},
                    headers=HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()["result"]
                results = data["results"]
                if not results:
                    break
                for ds in results:
                    datasets_raw[ds["id"]] = ds
                offset += len(results)
                if offset >= data["count"]:
                    break
            except Exception as e:
                print(f"   ⚠ Error consultando '{q}' (offset={offset}): {e}")
                break

    print(f"📊 Total datasets únicos encontrados: {len(datasets_raw)}")
    return list(datasets_raw.values())


# =====================================================
# PASO 2 — Clasificación por cobertura temporal / formato
# =====================================================
def clasificar_dataset(titulo: str, formatos_disponibles: set[str]) -> str:
    tl = titulo.lower()
    if "CSV" not in formatos_disponibles:
        return "sin_csv"
    if "iniciativas de inversion" in tl or "iniciativas de inversión" in tl:
        return "iniciativas_inversion"
    if "trimestre" in tl:
        return "trimestral_legado"
    if "informes desagregados" in tl:
        return "informes_desagregados_legado"
    if not re.search(r"\ba\s+(" + "|".join(MESES) + r")\s+de\s+(\d{4})\b", tl):
        return "sin_clasificar"
    tiene_variante = any(v in tl for v in VARIANTES)
    return "mensual_con_variante" if tiene_variante else "mensual_sin_variante"


def extraer_tipo(titulo: str) -> str | None:
    tl = titulo.lower()
    if "ejecuci" in tl:
        return "ejecucion"
    if "ley de presupuestos" in tl:
        return "ley"
    return None


def extraer_periodo(titulo: str) -> tuple[str, str] | None:
    m = re.search(r"\ba\s+(" + "|".join(MESES) + r")\s+de\s+(\d{4})\b", titulo.lower())
    return (MESES[m.group(1)], m.group(2)) if m else None  # (mes, año)


# =====================================================
# PASO 3 — Agrupar por (tipo, año, mes) y elegir el "Total efectivo"
# =====================================================
def agrupar_y_elegir(datasets_crudos: list[dict]) -> tuple[dict, dict]:
    por_periodo = defaultdict(list)
    no_procesados = defaultdict(list)

    for ds in datasets_crudos:
        titulo = ds.get("title", "")
        org = (ds.get("organization", {}) or {}).get("title", "") or ""
        if "presupuesto" not in org.lower() and "direcci" not in org.lower():
            continue

        formatos = set(r.get("format", "").upper() for r in ds.get("resources", []))
        grupo = clasificar_dataset(titulo, formatos)

        if grupo not in ("mensual_con_variante", "mensual_sin_variante"):
            no_procesados[grupo].append(titulo)
            continue

        tipo = extraer_tipo(titulo)
        periodo = extraer_periodo(titulo)
        if not tipo or not periodo:
            no_procesados["sin_tipo_o_periodo"].append(titulo)
            continue

        mes, año = periodo
        por_periodo[(tipo, año, mes)].append((titulo, ds))

    periodos_elegidos = {}
    for clave, candidatos in por_periodo.items():
        if len(candidatos) == 1:
            periodos_elegidos[clave] = candidatos[0][1]
            continue

        elegido = next((ds for t, ds in candidatos if "total" in t.lower()), None)
        if elegido:
            periodos_elegidos[clave] = elegido
        else:
            no_procesados["con_variante_sin_total"].extend(t for t, _ in candidatos)

    return periodos_elegidos, no_procesados


# =====================================================
# PASO 4 — Extraer recursos CSV del dataset elegido
# =====================================================
def extraer_recursos(dataset: dict) -> list[dict]:
    recursos = []
    for r in dataset.get("resources", []):
        if r.get("format", "").upper() != "CSV":
            continue
        nombre = r.get("name", "").lower()

        if "nacional" in nombre:
            nivel = "nacional"
        elif "partida" in nombre:
            nivel = "partida"
        elif "capítulo" in nombre or "capitulo" in nombre:
            nivel = "capitulo"
        elif "programa" in nombre:
            nivel = "programa"
        elif "diccionario" in nombre:
            nivel = "diccionario"
        else:
            nivel = "otro"

        recursos.append({"nivel": nivel, "url": r.get("url", "")})
    return recursos


# =====================================================
# PASO 5 — Descarga robusta: reintentos + validación + limpieza
# =====================================================
def descargar_archivo(url: str, ruta_destino: Path, max_reintentos: int = 3) -> tuple[bool, str | None]:
    for intento in range(1, max_reintentos + 1):
        try:
            with requests.get(url, headers=HEADERS, timeout=60, stream=True) as resp:
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "").lower()
                if "text/html" in content_type or "application/json" in content_type:
                    return False, f"Content-Type inesperado: {content_type}"

                ruta_destino.parent.mkdir(parents=True, exist_ok=True)
                with open(ruta_destino, "wb") as f_out:
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f_out.write(chunk)

            if ruta_destino.exists() and ruta_destino.stat().st_size > 0:
                return True, None
            if ruta_destino.exists():
                ruta_destino.unlink()

        except Exception as e:
            if intento < max_reintentos:
                time.sleep(2 ** intento)
            else:
                if ruta_destino.exists():
                    ruta_destino.unlink()
                return False, str(e)

    return False, "Reintentos agotados"


# =====================================================
# PASO 6 — Orquestar la descarga de todos los períodos
# =====================================================
def descargar_todo(periodos_elegidos: dict, sobrescribir: bool = False):
    log = {}
    if LOG_FILE.exists():
        with open(LOG_FILE, encoding="utf-8") as f:
            log = json.load(f)

    tareas = [
        (DATOS_DIR / tipo / año / mes / f"{r['nivel']}.csv", r["url"], ds.get("title", ""))
        for (tipo, año, mes), ds in periodos_elegidos.items()
        for r in extraer_recursos(ds)
        if r["nivel"] not in ("diccionario", "otro")  # se manejan aparte si se necesitan
    ]

    total = len(tareas)
    descargados = saltados = errores = 0
    print(f"\n📥 {total} archivos a procesar\n")

    for i, (ruta, url, titulo_ds) in enumerate(tareas, start=1):
        if not sobrescribir and ruta.exists() and ruta.stat().st_size > 0:
            saltados += 1
            continue

        print(f"[{i}/{total}] {ruta.relative_to(DATOS_DIR)}")
        ok, motivo = descargar_archivo(url, ruta)

        if ok:
            descargados += 1
            print(f"   ✅ {ruta.stat().st_size:,} bytes")
        else:
            errores += 1
            print(f"   ❌ {motivo}")

        log[str(ruta)] = {
            "ok": ok,
            "motivo_error": motivo,
            "url": url,
            "dataset": titulo_ds,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        DATOS_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

        time.sleep(0.3)

    return descargados, saltados, errores


# =====================================================
# PASO 7 — Reporte y persistencia de no-procesados
# =====================================================
def imprimir_resumen(periodos_elegidos: dict, no_procesados: dict):
    print(f"\n{'='*70}\nRESUMEN DE CLASIFICACIÓN\n{'='*70}")

    for tipo in ("ley", "ejecucion"):
        periodos_tipo = sorted(k for k in periodos_elegidos if k[0] == tipo)
        if not periodos_tipo:
            continue
        etiquetas = [f"{año}-{mes}" for _, año, mes in periodos_tipo]
        print(f"\n  {tipo.upper()}: {len(periodos_tipo)} períodos ({etiquetas[0]} → {etiquetas[-1]})")

    if no_procesados:
        print(f"\n  ⚠️ No incorporados automáticamente (requieren revisión):")
        for grupo, titulos in no_procesados.items():
            print(f"    {grupo}: {len(titulos)} datasets")


def guardar_no_procesados(no_procesados: dict):
    if not no_procesados:
        return
    NO_PROCESADOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NO_PROCESADOS_FILE, "w", encoding="utf-8") as f:
        json.dump(no_procesados, f, ensure_ascii=False, indent=2)
    print(f"\n💾 No procesados guardados en: {NO_PROCESADOS_FILE}")


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  DESCARGA DIPRES — SERIE 'TOTAL EFECTIVA' CONTINUA")
    print("=" * 70)
    print(f"\nDestino: {DATOS_DIR.resolve()}\n")

    datasets_crudos = buscar_datasets()
    periodos_elegidos, no_procesados = agrupar_y_elegir(datasets_crudos)

    imprimir_resumen(periodos_elegidos, no_procesados)
    guardar_no_procesados(no_procesados)

    print(f"\n{'='*70}")
    if input("¿Iniciar descarga? (s/n): ").strip().lower() != "s":
        print("Cancelado, nada descargado.")
        raise SystemExit

    descargados, saltados, errores = descargar_todo(periodos_elegidos)

    print(f"\n{'='*70}\nDESCARGA COMPLETA\n{'='*70}")
    print(f"  ✅ Descargados: {descargados}")
    print(f"  ⏭  Ya existían: {saltados}")
    print(f"  ❌ Errores:     {errores}")

# =====================================================
# EXTENSIÓN — Captura de datos legado (sin procesar aún)
# =====================================================
import unicodedata

LEGADO_DIR = DATOS_DIR / "legado"

def normalizar_texto(t: str) -> str:
    t = t.strip().lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t)


# --- 1. Informes desagregados (2012-2017): trimestral, Pesos/Dólares ---
def extraer_trimestre_moneda(nombre_recurso: str) -> tuple[str, str] | None:
    nt = normalizar_texto(nombre_recurso)

    if "primer" in nt:
        trim = "T1"
    elif "segundo" in nt:
        trim = "T2"
    elif "tercer" in nt:
        trim = "T3"
    elif "cuarto" in nt:
        trim = "T4"
    else:
        return None

    if "dolar" in nt:  # cubre "dólar"/"dolar" ya normalizado sin tilde
        moneda = "dolares"
    elif "peso" in nt:
        moneda = "pesos"
    else:
        return None

    return trim, moneda


def descargar_informes_desagregados(datasets_crudos: list[dict]):
    """
    Descarga los CSV de 'Informes desagregados de Presupuestos' (2012-2017).
    Fusiona recursos de datasets duplicados con el mismo título (mismo año),
    ya que el catálogo trae más de un ds_id para el mismo año con recursos
    distintos y complementarios.
    """
    recursos_por_año = defaultdict(dict)  # año -> {(trim, moneda): url}

    for ds in datasets_crudos:
        titulo = ds.get("title", "")
        if "informes desagregados" not in titulo.lower():
            continue

        m = re.search(r"\b(20\d{2})\b", titulo)
        if not m:
            continue
        año = m.group(1)

        for r in ds.get("resources", []):
            if r.get("format", "").upper() != "CSV":
                continue
            clave = extraer_trimestre_moneda(r.get("name", ""))
            if clave is None:
                continue  # ej. el CSV de "Ley de Presupuestos" embebido en el mismo dataset, se maneja aparte
            recursos_por_año[año][clave] = r.get("url", "")

    total = sum(len(v) for v in recursos_por_año.values())
    print(f"\n📥 Informes desagregados legado: {total} archivos ({len(recursos_por_año)} años)\n")

    descargados = errores = 0
    for año, recursos in sorted(recursos_por_año.items()):
        for (trim, moneda), url in sorted(recursos.items()):
            destino = LEGADO_DIR / "informes_desagregados" / año / f"{trim}_{moneda}.csv"
            if destino.exists() and destino.stat().st_size > 0:
                continue
            print(f"   {destino.relative_to(DATOS_DIR)}")
            ok, motivo = descargar_archivo(url, destino)
            if ok:
                descargados += 1
            else:
                errores += 1
                print(f"      ❌ {motivo}")

    print(f"\n   ✅ {descargados} descargados, ❌ {errores} errores")