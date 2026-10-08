"""
Descarga de Iniciativas de Inversión — DIPRES
===============================================
Busca, inspecciona y descarga los datasets de ejecución
presupuestaria de iniciativas de inversión desde datos.gob.cl.

Estos datasets incluyen desagregación por localización geográfica
(región/comuna) que los datos de ejecución regular no tienen.

Uso:
    python 02_descargar_inversion.py
"""

import json
import re
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

# =====================================================
# CONFIGURACIÓN
# =====================================================
DATOS_DIR = Path(r"D:\dipres-datos")
INVERSION_DIR = DATOS_DIR / "inversion"
INVERSION_DIR.mkdir(parents=True, exist_ok=True)

CKAN_BASE = "https://datos.gob.cl/api/3/action"
LOG_FILE = DATOS_DIR / "_log_inversion.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv, application/csv, text/plain, */*",
}


# =====================================================
# PASO 1 — Buscar datasets de inversión en CKAN
# =====================================================
def buscar_datasets_inversion() -> list[dict]:
    print("🔍 Buscando datasets de Iniciativas de Inversión...")
    
    datasets = {}
    offset = 0
    
    while True:
        try:
            resp = requests.get(
                f"{CKAN_BASE}/package_search",
                params={
                    "q": "Iniciativas de Inversión",
                    "rows": 100,
                    "start": offset,
                },
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()["result"]
            results = data["results"]
            
            if not results:
                break
            
            for ds in results:
                titulo = ds.get("title", "")
                if "iniciativa" in titulo.lower() and "inversión" in titulo.lower():
                    datasets[ds["id"]] = ds
            
            offset += len(results)
            if offset >= data["count"]:
                break
                
        except Exception as e:
            print(f"  ⚠ Error: {e}")
            break
    
    print(f"  Encontrados: {len(datasets)} datasets de inversión")
    return list(datasets.values())


# =====================================================
# PASO 2 — Clasificar datasets (Total vs Ley Regular vs FET)
# =====================================================
def clasificar_datasets(datasets: list[dict]) -> dict:
    """
    Clasifica por año y variante.
    Prioriza la variante "Total" sobre Ley Regular y FET.
    """
    por_año = {}
    
    for ds in datasets:
        titulo = ds.get("title", "")
        
        # Extraer año
        match_año = re.search(r"(\d{4})", titulo)
        if not match_año:
            continue
        año = match_año.group(1)
        
        # Determinar variante
        titulo_lower = titulo.lower()
        if "total" in titulo_lower:
            variante = "total"
        elif "ley regular" in titulo_lower:
            variante = "ley_regular"
        elif "fet" in titulo_lower:
            variante = "fet"
        else:
            variante = "total"  # datasets antiguos sin variante = total
        
        if año not in por_año:
            por_año[año] = {}
        por_año[año][variante] = ds
    
    # Elegir variante Total cuando existe
    elegidos = {}
    for año, variantes in sorted(por_año.items()):
        if "total" in variantes:
            elegidos[año] = variantes["total"]
            print(f"  {año}: usando variante Total")
        elif "ley_regular" in variantes:
            elegidos[año] = variantes["ley_regular"]
            print(f"  {año}: usando Ley Regular (no hay Total)")
        else:
            primera = list(variantes.values())[0]
            elegidos[año] = primera
            print(f"  {año}: usando {list(variantes.keys())[0]}")
    
    return elegidos


# =====================================================
# PASO 3 — Inspeccionar estructura de un CSV de muestra
# =====================================================
def inspeccionar_muestra(url: str, nombre: str = "muestra") -> pd.DataFrame | None:
    """Descarga las primeras 100 filas de un CSV para ver su estructura."""
    print(f"\n🔍 Inspeccionando: {nombre}")
    print(f"   URL: {url[:80]}...")
    
    try:
        with requests.get(url, headers=HEADERS, timeout=30, stream=True) as resp:
            resp.raise_for_status()
            lineas = []
            for i, linea in enumerate(resp.iter_lines()):
                if i >= 105:
                    break
                lineas.append(linea)
        
        contenido = b"\n".join(lineas)
        
        # Decodificar
        for enc in ["utf-8-sig", "latin-1", "utf-8"]:
            try:
                texto = contenido.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            print("  ❌ No se pudo decodificar")
            return None
        
        # Detectar separador
        primera = texto.splitlines()[0] if texto.splitlines() else ""
        sep = ";" if primera.count(";") >= primera.count(",") else ","
        
        df = pd.read_csv(
            StringIO(texto),
            nrows=100,
            sep=sep,
            index_col=False,
            on_bad_lines="skip",
        )
        
        print(f"   Encoding: {enc} | Separador: '{sep}'")
        print(f"   Dimensiones: {df.shape}")
        print(f"\n   Columnas ({len(df.columns)}):")
        for col in df.columns:
            ejemplo = df[col].dropna().iloc[0] if not df[col].dropna().empty else "VACÍO"
            print(f"     {col:<40s} | {str(df[col].dtype):<10s} | Ej: {str(ejemplo)[:40]}")
        
        # Buscar columnas geográficas
        geo_cols = [c for c in df.columns if any(
            term in c.lower() for term in ["region", "región", "comuna", "localiz", "ubicac", "geo"]
        )]
        if geo_cols:
            print(f"\n   📍 Columnas geográficas detectadas: {geo_cols}")
            for gc in geo_cols:
                vals = df[gc].dropna().unique()[:10]
                print(f"      {gc}: {list(vals)}")
        else:
            print(f"\n   ⚠ No se detectaron columnas geográficas explícitas")
        
        return df
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


# =====================================================
# PASO 4 — Descargar archivos
# =====================================================
def descargar_archivo(url: str, ruta: Path, max_reintentos: int = 3) -> tuple[bool, str]:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    
    for intento in range(max_reintentos):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=120, stream=True)
            resp.raise_for_status()
            
            with open(ruta, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            if ruta.stat().st_size < 100:
                return False, f"Archivo muy pequeño ({ruta.stat().st_size} bytes)"
            
            return True, ""
            
        except Exception as e:
            if intento < max_reintentos - 1:
                time.sleep(2 ** intento)
            else:
                if ruta.exists():
                    ruta.unlink()
                return False, str(e)
    
    return False, "Reintentos agotados"


def descargar_todos(elegidos: dict, sobrescribir: bool = False):
    log = {}
    if LOG_FILE.exists():
        with open(LOG_FILE, encoding="utf-8") as f:
            log = json.load(f)
    
    tareas = []
    
    for año, ds in elegidos.items():
        recursos = ds.get("resources", [])
        for r in recursos:
            formato = r.get("format", "").upper()
            if formato != "CSV":
                continue
            
            url = r.get("url", "")
            nombre_recurso = r.get("name", "").lower()
            
            # Clasificar por nivel/tipo
            if "diccionario" in nombre_recurso:
                nivel = "diccionario"
            elif "programa" in nombre_recurso:
                nivel = "programa"
            elif "capítulo" in nombre_recurso or "capitulo" in nombre_recurso:
                nivel = "capitulo"
            elif "partida" in nombre_recurso:
                nivel = "partida"
            elif "nacional" in nombre_recurso:
                nivel = "nacional"
            else:
                nivel = "detalle"
            
            ruta = INVERSION_DIR / año / f"{nivel}.csv"
            tareas.append((ruta, url, ds.get("title", "")))
    
    total = len(tareas)
    descargados = saltados = errores = 0
    print(f"\n📥 {total} archivos a descargar")
    
    for i, (ruta, url, titulo) in enumerate(tareas, start=1):
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
            "dataset": titulo,
        }
        
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        
        time.sleep(0.3)
    
    return descargados, saltados, errores


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  DESCARGA — INICIATIVAS DE INVERSIÓN DIPRES")
    print("=" * 70)
    print(f"\nDestino: {INVERSION_DIR.resolve()}\n")
    
    # 1. Buscar
    datasets = buscar_datasets_inversion()
    
    if not datasets:
        print("❌ No se encontraron datasets")
        raise SystemExit
    
    # 2. Clasificar y elegir variante Total
    print(f"\n📋 Clasificando por año y variante:")
    elegidos = clasificar_datasets(datasets)
    
    # 3. Inspeccionar muestra del primer CSV encontrado
    print(f"\n{'='*70}")
    print("  INSPECCIÓN DE ESTRUCTURA")
    print(f"{'='*70}")
    
    for año, ds in sorted(elegidos.items()):
        for r in ds.get("resources", []):
            if r.get("format", "").upper() == "CSV":
                inspeccionar_muestra(r["url"], f"inversion_{año}")
                break
        break  # solo inspeccionar el primero
    
    # 4. Preguntar antes de descargar
    print(f"\n{'='*70}")
    respuesta = input(f"¿Descargar {len(elegidos)} datasets de inversión? (s/n): ").strip().lower()
    
    if respuesta != "s":
        print("Cancelado.")
        raise SystemExit
    
    # 5. Descargar
    desc, salt, err = descargar_todos(elegidos)
    
    print(f"\n{'='*70}")
    print(f"  DESCARGA COMPLETA")
    print(f"{'='*70}")
    print(f"  ✅ Descargados: {desc}")
    print(f"  ⏭  Ya existían: {salt}")
    print(f"  ❌ Errores:     {err}")
    print(f"\n  Archivos en: {INVERSION_DIR.resolve()}")

