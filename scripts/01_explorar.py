"""
Fase 1 — Exploración de fuentes de datos presupuestarios (Robusto y Paginado)
=============================================================================
Requisitos: pip install requests pandas

Objetivo:
  - Mapear datasets en la API CKAN de datos.gob.cl con paginación completa.
  - Sondear disponibilidad de endpoints en presupuestoabierto.gob.cl.
  - Inspeccionar muestras de CSVs remotos sin riesgo de descalce de separador.
  - Guardar catálogo en CSV y JSON para documentación de fuentes.
"""

from io import StringIO
import json
from pathlib import Path
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# =====================================================
# RUTA MADRE Y SUBDIRECTORIOS DEL PROYECTO
# =====================================================
# =====================================================
# RUTA MADRE Y SUBDIRECTORIOS DEL PROYECTO
# =====================================================
BASE_DIR = Path(r"D:\dipres-datos")

# Carpetas del pipeline
OUTPUT_DIR = BASE_DIR / "exploracion"        # Fase 1: CKAN y muestras
CONSOLIDADO_DIR = BASE_DIR / "consolidado"   # Cruces y catalogos
DATOS_LIMPIOS_DIR = BASE_DIR / "clean"       # Salida de limpieza

# Crear automáticamente los directorios base si no existen
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CONSOLIDADO_DIR.mkdir(parents=True, exist_ok=True)

# API CKAN
CKAN_BASE = "https://datos.gob.cl/api/3/action"

# Headers de navegador estándar para prevenir bloqueos por WAF/Cloudflare
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
}

def separador(titulo: str):
    print(f"\n{'='*70}\n  {titulo}\n{'='*70}\n")


def crear_sesion_robusta() -> requests.Session:
    session = requests.Session()
    # Estrategia de reintento: hasta 3 veces, esperando 1s, 2s, 4s...
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# =============================================================
# 1. DATOS.GOB.CL — CKAN API CON PAGINACIÓN COMPLETA
# =============================================================
def explorar_ckan(max_por_termino: int = 200) -> dict:
    separador("DATOS.GOB.CL — Búsqueda paginada en API CKAN")

    queries = [
        "presupuesto",
        "ejecución presupuestaria",
        "gasto público",
        "ley de presupuestos",
        "DIPRES",
    ]

    todos_los_datasets = {}

    for q in queries:
        print(f"🔍 Buscando término: '{q}'")
        start = 0
        rows = 50
        total_encontrados_query = 0

        while start < max_por_termino:
            params = {"q": q, "rows": rows, "start": start}
            try:
                resp = requests.get(
                    f"{CKAN_BASE}/package_search",
                    params=params,
                    headers=HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json().get("result", {})
                results = data.get("results", [])
                total_encontrados_query = data.get("count", 0)

                if not results:
                    break

                for ds in results:
                    ds_id = ds["id"]
                    if ds_id not in todos_los_datasets:
                        recursos = []
                        for r in ds.get("resources", []):
                            recursos.append({
                                "nombre": r.get("name", ""),
                                "formato": r.get("format", "").upper(),
                                "url": r.get("url", ""),
                                "tamaño": r.get("size", ""),
                                "descripcion": r.get("description", ""),
                            })

                        todos_los_datasets[ds_id] = {
                            "id": ds_id,
                            "nombre": ds.get("title", ""),
                            "organizacion": ds.get("organization", {}).get(
                                "title", ""
                            ),
                            "descripcion": ds.get("notes", "")[:250].replace(
                                "\n", " "
                            ),
                            "n_recursos": len(recursos),
                            "recursos": recursos,
                        }

                start += rows
                if start >= total_encontrados_query:
                    break

            except Exception as e:
                print(f"   ⚠️ Error consultando '{q}' (start={start}): {e}")
                break

        print(
            f"   → Registros procesados para '{q}': {min(start, total_encontrados_query)} / {total_encontrados_query}"
        )

    print(f"\n📊 Total datasets únicos recolectados: {len(todos_los_datasets)}")

    # 1. Guardar resumen consolidado tabular
    resumen = []
    for ds_id, info in todos_los_datasets.items():
        formatos = ", ".join(
            sorted(
                set(r["formato"] for r in info["recursos"] if r["formato"])
            )
        )
        resumen.append({
            "id": ds_id,
            "nombre": info["nombre"],
            "organizacion": info["organizacion"],
            "n_recursos": info["n_recursos"],
            "formatos": formatos,
            "descripcion": info["descripcion"],
        })

    df_resumen = pd.DataFrame(resumen)
    ruta_csv = OUTPUT_DIR / "ckan_datasets_encontrados.csv"
    df_resumen.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    print(f"💾 Resumen guardado en: {ruta_csv}")

    # 2. Guardar catálogo JSON completo con URLs
    ruta_json = OUTPUT_DIR / "ckan_datasets_detalle.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(todos_los_datasets, f, ensure_ascii=False, indent=2)
    print(f"💾 Catálogo completo guardado en: {ruta_json}")

    return todos_los_datasets


# =============================================================
# 2. INSPECCIÓN ROBUSTA DE MUESTRA CSV
# =============================================================
def inspeccionar_recurso_csv(url: str, nombre: str = "muestra") -> pd.DataFrame | None:
    """
    Descarga una muestra de las primeras 100 líneas de un CSV remoto
    cerrando el socket de conexión de forma determinista con un context manager.
    """
    separador(f"Inspeccionando recurso remoto: {nombre}")
    print(f"URL: {url}")

    contenido_bytes = None

    try:
        # Context manager 'with' para cerrar la conexión HTTP inmediatamente tras el break
        with requests.get(url, headers=HEADERS, timeout=30, stream=True) as resp:
            resp.raise_for_status()
            
            lineas_raw = []
            # Leemos hasta 105 líneas para tener margen de encabezado y muestra
            for i, linea in enumerate(resp.iter_lines()):
                if i >= 105:
                    break
                lineas_raw.append(linea)

            contenido_bytes = b"\n".join(lineas_raw)

    except Exception as e:
        print(f"❌ Error al descargar recurso: {e}")
        return None

    # Intentar decodificación de bytes a texto
    contenido_txt = None
    enc_exitoso = None
    for enc in ["utf-8-sig", "latin-1", "utf-8"]:
        try:
            contenido_txt = contenido_bytes.decode(enc)
            enc_exitoso = enc
            break
        except UnicodeDecodeError:
            continue

    if not contenido_txt:
        print("❌ Error: No se pudo decodificar el contenido del archivo.")
        return None

    # Detección de delimitador predominante
    primera_linea = contenido_txt.splitlines()[0] if contenido_txt.splitlines() else ""
    sep = ";" if primera_linea.count(";") >= primera_linea.count(",") else ","

    try:
        # Sin parámetro 'encoding' porque StringIO ya maneja cadenas decodificadas
        df = pd.read_csv(
            StringIO(contenido_txt),
            nrows=100,
            sep=sep,
            quotechar='"',
            on_bad_lines="skip"
        )
    except Exception as e:
        print(f"❌ Error al cargar muestra con pandas: {e}")
        return None

    print(f"Formato detectado: Encoding={enc_exitoso} | Separador='{sep}'")
    print(f"Dimensiones de la muestra: {df.shape} (filas, columnas)")
    print(f"\nColumnas ({len(df.columns)}):")
    for col in df.columns:
        ejemplo = df[col].dropna().iloc[0] if not df[col].dropna().empty else "VACÍO"
        print(f"  • {col:<30s} | Tipo: {str(df[col].dtype):<10s} | Ej: {ejemplo}")

    ruta_salida = OUTPUT_DIR / f"muestra_{nombre}.csv"
    df.to_csv(ruta_salida, index=False, encoding="utf-8-sig")
    print(f"\n💾 Muestra local guardada en: {ruta_salida}")

    return df


# =============================================================
# 3. PRESUPUESTOABIERTO.GOB.CL — SONDEO DE ACCESIBILIDAD
# =============================================================
def explorar_presupuesto_abierto():
    separador("PRESUPUESTOABIERTO.GOB.CL — Sondeo de accesibilidad")

    urls = [
        "https://presupuestoabierto.gob.cl",
        "https://presupuestoabierto.gob.cl/api",
        "https://presupuestoabierto.gob.cl/datos",
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            tipo_contenido = resp.headers.get("content-type", "N/A")
            print(f"• {url:<45s} → Status: {resp.status_code} | Tipo: {tipo_contenido}")

            if resp.status_code == 200 and "json" in tipo_contenido.lower():
                ruta = OUTPUT_DIR / "presupuestoabierto_api_response.json"
                with open(ruta, "w", encoding="utf-8") as f:
                    json.dump(resp.json(), f, ensure_ascii=False, indent=2)
                print(f"  💾 Respuesta JSON capturada en: {ruta}")

        except Exception as e:
            print(f"• {url:<45s} → ⚠️ Error de conexión: {e}")


# =============================================================
# EJECUCIÓN PRINCIPAL
# =============================================================
if __name__ == "__main__":
    separador("FASE 1: DISCOVERING — CATÁLOGO DE FUENTES DIPRES")
    print(f"Directorio de exportación: {OUTPUT_DIR.resolve()}\n")

    # 1. Búsqueda y catalogación completa en API CKAN
    datasets = explorar_ckan(max_por_termino=150)

    # 2. Sondeo de Presupuesto Abierto
    explorar_presupuesto_abierto()

    # 3. Inspección automática del primer recurso CSV de DIPRES encontrado
    csv_dipres_url = None
    for ds in datasets.values():
        org = ds["organizacion"].lower()
        titulo = ds["nombre"].lower()
        if "dipres" in org or "presupuesto" in titulo:
            for rec in ds["recursos"]:
                if rec["formato"] == "CSV" and rec["url"]:
                    csv_dipres_url = rec["url"]
                    break
        if csv_dipres_url:
            break

    if csv_dipres_url:
        print("\n🔍 Inspeccionando el primer recurso CSV identificado...")
        inspeccionar_recurso_csv(csv_dipres_url, nombre="ejemplo_dipres")
    else:
        print("\nℹ️ No se detectó una URL directa de CSV para inspección inmediata.")

    separador("FASE 1 COMPLETADA CON ÉXITO")
    print(f"Revisa los archivos generados en la carpeta '{OUTPUT_DIR.name}/'.")

carpeta = Path("exploración").resolve()
print(f"Ubicación absoluta: {carpeta}")
print(f"¿Existe realmente?: {carpeta.exists()}")

if carpeta.exists():
    print("\nArchivos dentro de la carpeta:")
    for archivo in carpeta.iterdir():
        print(f"  • {archivo.name}")