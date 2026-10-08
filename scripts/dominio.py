"""
dominio.py — Conocimiento del presupuesto público chileno
==========================================================
Single source of truth para las reglas de negocio.
Si una regla cambia (ej: un subtítulo se reclasifica),
se corrige acá y todo el pipeline queda consistente.

Referencia normativa: DS 854/2004 Ministerio de Hacienda
(Clasificador Presupuestario) y DL 1.263 (Administración
Financiera del Estado).

Uso:
    from dominio import MESES, NIVELES, keys_de_nivel, tipo_flujo
"""

# =====================================================
# TIEMPO
# =====================================================
MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

MES_A_NUM = {m: i + 1 for i, m in enumerate(MESES)}
NUM_A_MES = {i + 1: m for i, m in enumerate(MESES)}

# Mapeo desde el nombre de carpeta ("01", "1") al nombre del mes
CARPETA_A_MES = {}
for i, m in enumerate(MESES, start=1):
    CARPETA_A_MES[f"{i:02d}"] = m   # "01"
    CARPETA_A_MES[str(i)] = m       # "1"


# =====================================================
# JERARQUÍA INSTITUCIONAL
# =====================================================
# Partida  → Ministerio o poder del Estado
# Capítulo → Servicio dentro del ministerio
# Programa → Unidad de gestión dentro del servicio
NIVELES = ["nacional", "partida", "capitulo", "programa"]

# Los archivos NO son tres niveles de detalle del mismo dato:
# son tres niveles de CONSOLIDACIÓN contable.
#   nacional → elimina transferencias entre ministerios
#   partida  → elimina transferencias entre capítulos del mismo ministerio
#   capitulo/programa → datos brutos
NIVELES_CONSOLIDADOS = ["nacional", "partida"]
NIVELES_BRUTOS = ["capitulo", "programa"]


def keys_de_nivel(nivel: str) -> list[str]:
    """
    Columnas que identifican unívocamente una fila en cada nivel.
    Usadas para merge, deduplicación y validación de coherencia.
    """
    base = ["Año", "Mes", "Moneda"]
    if nivel == "nacional":
        return base + ["Subtítulo"]
    if nivel == "partida":
        return base + ["Partida", "Subtítulo"]
    if nivel == "capitulo":
        return base + ["Partida", "Capítulo", "Subtítulo"]
    if nivel == "programa":
        return base + ["Partida", "Capítulo", "Programa",
                       "Subtítulo", "Item", "Asignación"]
    raise ValueError(f"Nivel desconocido: {nivel}")


def columnas_jerarquicas(nivel: str) -> list[str]:
    """Solo las columnas de jerarquía institucional/económica."""
    return [k for k in keys_de_nivel(nivel)
            if k not in ("Año", "Mes", "Moneda")]


# =====================================================
# CLASIFICACIÓN ECONÓMICA (DS 854)
# =====================================================
# Subtítulo → Item → Asignación → Sub-Asignación
# La ley se aprueba a nivel de Subtítulo; el desglose inferior
# es obligatorio para la EJECUCIÓN, no necesariamente para la ley.

SUBTITULOS_INGRESO = range(1, 16)    # 01–15
SUBTITULOS_GASTO = range(21, 36)     # 21–35

NOMBRES_SUBTITULO = {
    1:  "Impuestos",
    3:  "Tributos sobre el uso de bienes y la realización de actividades",
    4:  "Imposiciones previsionales",
    5:  "Transferencias corrientes",
    6:  "Rentas de la propiedad",
    7:  "Ingresos de operación",
    8:  "Otros ingresos corrientes",
    9:  "Aporte fiscal",
    10: "Venta de activos no financieros",
    11: "Venta de activos financieros",
    12: "Recuperación de préstamos",
    13: "Transferencias para gastos de capital",
    14: "Endeudamiento",
    15: "Saldo inicial de caja",
    21: "Gastos en personal",
    22: "Bienes y servicios de consumo",
    23: "Prestaciones de seguridad social",
    24: "Transferencias corrientes",
    25: "Íntegros al fisco",
    26: "Otros gastos corrientes",
    27: "Aporte fiscal libre",
    28: "Aporte fiscal para servicio de la deuda",
    29: "Adquisición de activos no financieros",
    30: "Adquisición de activos financieros",
    31: "Iniciativas de inversión",
    32: "Préstamos",
    33: "Transferencias de capital",
    34: "Servicio de la deuda",
    35: "Saldo final de caja",
}

# Subtítulos que representan movimientos ENTRE entidades del Estado.
# Son los que se eliminan al consolidar hacia niveles superiores,
# y por eso aparecen en pares ingreso/gasto con montos espejo.
SUBTITULOS_TRANSFERENCIA = {5, 9, 13, 24, 27, 28, 33}

# Pares espejo: (subtítulo ingreso, subtítulo gasto)
PARES_TRANSFERENCIA = [
    (5, 24),    # Transferencias corrientes
    (13, 33),   # Transferencias de capital
    (9, 27),    # Aporte fiscal / Aporte fiscal libre
]

# Subtítulos contables, no flujos reales de caja
SUBTITULOS_SALDO = {15, 35}


def tipo_flujo(subtitulo) -> str:
    """Clasifica un subtítulo como Ingreso o Gasto."""
    s = int(subtitulo)
    if s in SUBTITULOS_INGRESO:
        return "Ingreso"
    if s in SUBTITULOS_GASTO:
        return "Gasto"
    return "Desconocido"


def es_transferencia(subtitulo) -> bool:
    """True si el subtítulo es un movimiento entre entidades del Estado."""
    return int(subtitulo) in SUBTITULOS_TRANSFERENCIA


def nombre_subtitulo(subtitulo) -> str:
    return NOMBRES_SUBTITULO.get(int(subtitulo), f"Subtítulo {subtitulo}")


# =====================================================
# CAMPOS DE MONTO
# =====================================================
# Stock: valor a un punto del tiempo, NO se suma entre meses
CAMPOS_STOCK = ["ley_inicial", "ley_vigente", "ejecucion_acumulada"]

# Flujo: variación del período, SÍ se suma entre meses
CAMPOS_FLUJO = ["ejecucion_mes"]

CAMPOS_MONTO = CAMPOS_STOCK + CAMPOS_FLUJO

# Unidad de los datos publicados por DIPRES
UNIDAD = "miles"  # miles de pesos (M$) o miles de dólares (MUS$)
FACTOR_A_PESOS = 1_000


# =====================================================
# NORMALIZACIÓN DE COLUMNAS
# =====================================================
# Variantes encontradas en los CSVs fuente entre 2017 y 2026.
# DIPRES no mantiene consistencia de tildes ni mayúsculas.
ALIAS_COLUMNAS = {
    # Jerarquía institucional
    "partida": "Partida",
    "capítulo": "Capítulo", "capitulo": "Capítulo",
    "programa": "Programa",
    # Clasificación económica
    "subtítulo": "Subtítulo", "subtitulo": "Subtítulo",
    "ítem": "Item", "item": "Item",
    "asignación": "Asignación", "asignacion": "Asignación",
    "sub-asignación": "Sub-Asignación", "sub-asignacion": "Sub-Asignación",
    # Nombres descriptivos
    "nombre partida": "Nombre Partida",
    "nombre capítulo": "Nombre Capítulo", "nombre capitulo": "Nombre Capítulo",
    "nombre programa": "Nombre Programa",
    "nombre subtítulo": "Nombre Subtítulo", "nombre subtitulo": "Nombre Subtítulo",
    "nombre ítem": "Nombre Item", "nombre item": "Nombre Item",
    "nombre asignación": "Nombre Asignación",
    "nombre asignacion": "Nombre Asignación",
    "nombre sub-asignación": "Nombre Sub-Asignación",
    "nombre sub-asignacion": "Nombre Sub-Asignación",
    # Contexto
    "año": "Año", "ano": "Año",
    "mes": "Mes",
    "moneda": "Moneda",
}

# Patrones regex de columnas con el mes embebido en el nombre
PATRONES_MONTO = {
    r"Ejecución de \w+":        "ejecucion_mes",
    r"Ejecución a \w+":         "ejecucion_acumulada",
    r"Monto Ley Inicial":       "ley_inicial",
    r"Monto Ley Vigente a \w+": "ley_vigente",
}


# =====================================================
# INICIATIVAS DE INVERSIÓN (dataset aparte)
# =====================================================
# Estructura distinta: jerarquía geográfica + proyecto individual
COLUMNAS_INVERSION_GEO = [
    "Región Destino", "Nombre Región Destino",
    "Provincia Destino", "Nombre Provincia Destino",
    "Comuna Destino", "Nombre Comuna Destino",
]

COLUMNAS_INVERSION_PROYECTO = ["Código BIP", "Nombre Proyecto"]

CAMPOS_MONTO_INVERSION = [
    "Suma de Monto Identificado Ley de Pptos.",
    "Suma de Monto Devengado Ley de Pptos.",
]

# =====================================================
# CONCORDANCIA CLASIFICADOR PRESUPUESTARIO ↔ GFS
# =====================================================
# El clasificador (DS 854) y el Estado de Operaciones de Gobierno
# (MEFP 2001/2014) NO son el mismo marco. DIPRES construye el
# segundo reclasificando partidas del primero.
#
# Categorías del Estado de Operaciones:
#   INGRESO     → transacción que aumenta el patrimonio neto
#   GASTO       → transacción que lo disminuye
#   ANAF        → Adquisición Neta de Activos No Financieros
#   ANAFIN      → Adquisición Neta de Activos Financieros (financiamiento)
#   PASIVOS     → Pasivos Netos Incurridos (financiamiento)
#   ELIMINADO   → transferencia interna, se cancela al consolidar
#   NO_TRANS    → no es transacción (saldo contable de apertura/cierre)
 
GFS_INGRESO = "INGRESO"
GFS_GASTO = "GASTO"
GFS_ANAF = "ANAF"
GFS_ANAFIN = "ANAFIN"
GFS_PASIVOS = "PASIVOS"
GFS_ELIMINADO = "ELIMINADO"
GFS_NO_TRANS = "NO_TRANS"
 
# (categoría, verificado_en_fuente)
# verificado=True  → confirmado en documentación oficial de DIPRES
# verificado=False → inferido del MEFP; pendiente de confirmar en el
#                    anexo metodológico de Estadísticas de Finanzas Públicas
CONCORDANCIA_GFS = {
    # ── Ingresos ──
    1:  (GFS_INGRESO,   True),   # Impuestos
    3:  (GFS_INGRESO,   False),  # Tributos sobre uso de bienes (municipal)
    4:  (GFS_INGRESO,   True),   # Imposiciones previsionales → contrib. sociales
    5:  (GFS_INGRESO,   True),   # Transferencias corrientes (si son externas)
    6:  (GFS_INGRESO,   True),   # Rentas de la propiedad
    7:  (GFS_INGRESO,   True),   # Ingresos de operación
    8:  (GFS_INGRESO,   True),   # Otros ingresos corrientes
    9:  (GFS_ELIMINADO, True),   # Aporte fiscal → transferencia interna
    10: (GFS_ANAF,      True),   # Venta activos no financieros → desinversión
    11: (GFS_ANAFIN,    True),   # Venta activos financieros → financiamiento
    12: (GFS_ANAFIN,    True),   # Recuperación de préstamos → financiamiento
    13: (GFS_INGRESO,   False),  # Transf. para gastos de capital
    14: (GFS_PASIVOS,   True),   # Endeudamiento → financiamiento
    15: (GFS_NO_TRANS,  True),   # Saldo inicial de caja
 
    # ── Gastos ──
    21: (GFS_GASTO,     False),  # Gastos en personal → remuneraciones
    22: (GFS_GASTO,     False),  # Bienes y servicios de consumo
    23: (GFS_GASTO,     False),  # Prestaciones de seguridad social
    24: (GFS_GASTO,     False),  # Transferencias corrientes (si externas)
    25: (GFS_GASTO,     False),  # Íntegros al fisco
    26: (GFS_GASTO,     False),  # Otros gastos corrientes
    27: (GFS_ELIMINADO, True),   # Aporte fiscal libre → transferencia interna
    28: (GFS_ELIMINADO, True),   # Aporte fiscal servicio deuda → interna
    29: (GFS_ANAF,      False),  # Adquisición activos no financieros
    30: (GFS_ANAFIN,    False),  # Adquisición activos financieros
    31: (GFS_ANAF,      False),  # Iniciativas de inversión
    32: (GFS_ANAFIN,    False),  # Préstamos
    33: (GFS_GASTO,     False),  # Transferencias de capital
    34: (None,          False),  # Servicio de la deuda — MIXTO:
                                 #   intereses → GASTO
                                 #   amortizaciones → PASIVOS
                                 #   requiere desglose a nivel de ítem
    35: (GFS_NO_TRANS,  True),   # Saldo final de caja
}
 
 
def categoria_gfs(subtitulo) -> str | None:
    """Categoría del Estado de Operaciones para un subtítulo."""
    e = CONCORDANCIA_GFS.get(int(subtitulo))
    return e[0] if e else None
 
 
def gfs_verificado(subtitulo) -> bool:
    """True si la correspondencia está confirmada en fuente oficial."""
    e = CONCORDANCIA_GFS.get(int(subtitulo))
    return e[1] if e else False
 
 
def es_ingreso_gfs(subtitulo) -> bool:
    """True si el subtítulo cuenta como ingreso en el Estado de Operaciones."""
    return categoria_gfs(subtitulo) == GFS_INGRESO
 
 
# Subtítulos que el clasificador rotula como ingreso pero que GFS
# NO cuenta como tal. Son el ajuste de la conciliación.
AJUSTES_INGRESO_GFS = {
    9:  "Transferencia interna (se elimina al consolidar)",
    10: "Desinversión → Adquisición Neta de Activos No Financieros",
    11: "Financiamiento → Adquisición Neta de Activos Financieros",
    12: "Financiamiento → Adquisición Neta de Activos Financieros",
    14: "Financiamiento → Pasivos Netos Incurridos",
    15: "Saldo contable de apertura, no es transacción",
}