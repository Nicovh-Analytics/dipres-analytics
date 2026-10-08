"""
normativa.py — Corpus normativo presupuestario
===============================================
Single source of truth del marco legal que "marca la cancha".

Cada norma se identifica por su idNorma en LeyChile (BCN), que es
la fuente autoritativa y entrega texto estructurado (no PDF).

Para encontrar un idNorma faltante:
    https://www.bcn.cl/leychile  → buscar la norma → el id aparece
    en la URL como ?idNorma=XXXXXXX

Artículos relevantes para el análisis presupuestario:
  Art. 1  — montos aprobados por partida y subtítulo
  Art. 3  — autorización máxima de endeudamiento (en USD)
  Art. 4  — subtítulos protegidos y excepciones al tope
  Art. 32 — gastos excedibles
"""

# =====================================================
# NORMAS PERMANENTES
# =====================================================
PERMANENTES = {
    "ds_854": {
        "id_norma": 233184,
        "titulo": "DS 854/2004 — Determina clasificaciones presupuestarias",
        "rol": "clasificador",
    },
    "dl_1263": {
        "id_norma": None,   # PENDIENTE: buscar en LeyChile
        "titulo": "DL 1.263/1975 — Administración Financiera del Estado",
        "rol": "marco",
        "nota": "Art. 26 (modificaciones), 28 (gastos excedibles), 70 (decretos)",
    },
}

# =====================================================
# LEYES DE PRESUPUESTOS POR AÑO
# =====================================================
# Confirmados hasta ahora; completar los faltantes desde LeyChile.
LEYES_PRESUPUESTO = {
    2017: {"ley": "20.981", "id_norma": None},
    2018: {"ley": "21.053", "id_norma": None},
    2019: {"ley": "21.125", "id_norma": None},
    2020: {"ley": "21.192", "id_norma": None},
    2021: {"ley": "21.289", "id_norma": None},
    2022: {"ley": "21.395", "id_norma": None},
    2023: {"ley": "21.516", "id_norma": None},
    2024: {"ley": "21.640", "id_norma": 1199318},   # confirmado
    2025: {"ley": "21.722", "id_norma": None},
    2026: {"ley": None,     "id_norma": None},
}

# =====================================================
# DECRETOS ANUALES DE MODIFICACIONES PRESUPUESTARIAS
# =====================================================
# Se dictan en enero del año que regulan.
DECRETOS_MODIFICACIONES = {
    2024: {"decreto": "2273", "id_norma": 1200224},  # confirmado, 17-ene-2024
    # completar el resto
}

# =====================================================
# ARTÍCULOS A EXTRAER
# =====================================================
# Patrón: el articulado de la Ley de Presupuestos mantiene
# numeración estable entre años, pero conviene verificar.
ARTICULOS_CLAVE = {
    1:  "Montos aprobados (ingresos y gastos por subtítulo)",
    3:  "Autorización máxima de endeudamiento",
    4:  "Subtítulos protegidos y excepciones al tope",
    32: "Gastos excedibles",
}

# Subtítulos cuyo régimen define cada artículo.
# Fuente: Ley 21.640 art. 3 y 4. VERIFICAR año por año —
# la redacción puede cambiar.
REGIMEN_POR_SUBTITULO = {
    21: {"regimen": "protegido",   "articulo": 4, "detalle": "requiere ley para incrementarse"},
    22: {"regimen": "protegido",   "articulo": 4, "detalle": "requiere ley para incrementarse"},
    23: {"regimen": "protegido",   "articulo": 4, "detalle": "requiere ley para incrementarse"},
    29: {"regimen": "margen_10",   "articulo": 4, "detalle": "hasta 10% sin ley"},
    31: {"regimen": "margen_10",   "articulo": 4, "detalle": "hasta 10% sin ley"},
    33: {"regimen": "margen_10",   "articulo": 4, "detalle": "hasta 10% sin ley"},
    11: {"regimen": "exceptuado",  "articulo": 4, "detalle": "inc. 2: venta de activos financieros"},
    15: {"regimen": "exceptuado",  "articulo": 4, "detalle": "inc. 2: mayores saldos iniciales de caja"},
    14: {"regimen": "tope_usd",    "articulo": 3, "detalle": "tope en dólares, no en pesos"},
    34: {"regimen": "restringido", "articulo": None,
         "detalle": "decreto anual: sin traspasos desde Aporte Fiscal Servicio Deuda"},
}

# Tope de endeudamiento por año, en miles de USD (art. 3).
# Completar leyendo el artículo 3 de cada ley.
TOPE_ENDEUDAMIENTO_USD = {
    2024: 16_500_000,   # US$16.500 millones (reducido desde 21.000 por el Congreso)
}


def regimen(subtitulo) -> dict | None:
    return REGIMEN_POR_SUBTITULO.get(int(subtitulo))


def normas_pendientes() -> list[str]:
    """Qué falta completar en el registro."""
    faltan = []
    for k, v in PERMANENTES.items():
        if v["id_norma"] is None:
            faltan.append(f"permanente/{k}")
    for anio, v in LEYES_PRESUPUESTO.items():
        if v["id_norma"] is None:
            faltan.append(f"ley/{anio} ({v['ley'] or 'sin número'})")
    for anio, v in DECRETOS_MODIFICACIONES.items():
        if v["id_norma"] is None:
            faltan.append(f"decreto/{anio}")
    return faltan