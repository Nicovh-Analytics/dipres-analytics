"""
config.py — Rutas y parámetros del pipeline
============================================
Single source of truth para TODO lo que depende del entorno.
Ningún otro script debe hardcodear una ruta.

Estructura:
    repo (Git)   → scripts, docs, notebooks
    DIPRES_HOME  → datos, fuera de Git

Uso:
    from dipres.config import DIRS
    ruta = DIRS["consolidado"] / "cruce_partida.csv"
"""

import os
from pathlib import Path

# =====================================================
# RAÍCES
# =====================================================
# El repo es donde vive este archivo:  repo/dipres/config.py
REPO_DIR = Path(__file__).resolve().parent.parent

# Los datos viven fuera del repo. Sobrescribible por entorno:
#     set DIPRES_HOME=E:\otro\path
BASE_DIR = Path(os.environ.get("DIPRES_HOME", r"D:\data\dipres-datos"))

# =====================================================
# DIRECTORIOS
# =====================================================
DIRS = {
    "repo":         REPO_DIR,
    "scripts":      REPO_DIR / "pipeline",
    "docs":         REPO_DIR / "docs",

    "base":         BASE_DIR,

    # Crudo — inmutable, nunca se regenera ni se edita
    "raw":          BASE_DIR / "raw",
    "ejecucion":    BASE_DIR / "raw" / "ejecucion",
    "ley":          BASE_DIR / "raw" / "ley",
    "inversion":    BASE_DIR / "raw" / "inversion",
    "normativa":    BASE_DIR / "raw" / "normativa",

    # Derivado — regenerable corriendo el pipeline
    "processed":    BASE_DIR / "processed",
    "consolidado":  BASE_DIR / "processed" / "consolidado",
    "clean":        BASE_DIR / "processed" / "clean",

    # Salidas y metadata
    "reportes":     BASE_DIR / "reports",
    "logs":         BASE_DIR / "logs",
    "exploracion":  BASE_DIR / "exploracion",
}


def asegurar_dirs(*claves):
    """Crea los directorios indicados. Sin argumentos, todos."""
    for k in (claves or DIRS.keys()):
        DIRS[k].mkdir(parents=True, exist_ok=True)


# =====================================================
# LOGS Y CATÁLOGOS
# =====================================================
LOGS = {
    "descarga":     DIRS["logs"] / "_log_descarga.json",
    "inversion":    DIRS["logs"] / "_log_inversion.json",
    "catalogo":     DIRS["logs"] / "_datasets_encontrados.json",
    "no_procesado": DIRS["logs"] / "_catalogo_no_procesado.json",
}

# =====================================================
# FUENTES EXTERNAS
# =====================================================
CKAN = {
    "base_url": "https://datos.gob.cl/api/3/action",
    "rows_por_pagina": 100,
    "max_por_termino": 200,
    "queries": [
        "presupuesto",
        "ejecución presupuestaria",
        "gasto público",
        "ley de presupuestos",
        "DIPRES",
    ],
}

LEYCHILE = {
    "xml":  "https://www.leychile.cl/Consulta/obtxml?opt=7&idNorma={id}",
    "html": "https://www.bcn.cl/leychile/navegar?idNorma={id}",
}

HTTP = {
    "headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/csv, application/csv, application/json, text/xml, */*",
    },
    "timeout": 120,
    "max_reintentos": 3,
    "pausa_entre_descargas": 2,
}

# =====================================================
# LECTURA DE ARCHIVOS
# =====================================================
IO = {
    # latin-1 nunca falla al decodificar: va último, como fallback
    "encodings": ["utf-8-sig", "utf-8", "cp1252", "latin-1"],
    "separadores": [";", ",", "\t"],
    # Secuencias que delatan un encoding mal elegido
    "marcadores_mojibake": ["Ã±", "Ã³", "Ã­", "Ã¡", "Ã©", "Ãº", "ï»¿", "Â"],
    "bytes_muestra": 8192,
}

# =====================================================
# TOLERANCIAS DE VALIDACIÓN
# =====================================================
TOLERANCIAS = {
    "monto": 1,              # diferencia máxima aceptable (miles)
    "porcentaje": 0.1,       # en porcentajes recalculados
    "meses_pegados": 3,      # meses iguales para marcar "dato pegado"
    "ratio_merge": 1.05,     # dispara alerta de producto cartesiano
}