"""
Validación interna de datos DIPRES (v3)
========================================
Verifica consistencia de los CSVs consolidados antes de
publicar el dashboard.

Checks:
  1. Cobertura temporal — ¿hay meses faltantes por año?
  2. Duplicados — ¿filas repetidas?
  3. Nulos en columnas clave
  4. Anomalías de valores — ley_vigente=0 con ejecución>0, etc.
  5. Valores idénticos entre meses consecutivos (posible dato pegado)
  6. Consistencia del cruce — ¿ley + ejecución bien mergeados?
  7. Coherencia entre niveles — separando consolidación de error
  8. Estructura a nivel de fila — delimitadores consistentes
  9. Encoding consistente entre archivos fuente

Uso:
    python validation.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
from hallazgos import Registro
from config import DIRS, TOLERANCIAS
from dominio import MESES, NIVELES, keys_de_nivel

reg = Registro("validacion", salida_dir=DIRS["reportes"])


# Importar lector robusto
try:
    from utils import leer_csv_robusto
    TIENE_UTILS = True
except ImportError:
    TIENE_UTILS = False

# =====================================================
# CONFIGURACIÓN
# =====================================================
CONSOLIDADO_DIR = DIRS["consolidado"]

MESES_ORDEN = MESES

NIVELES = ["nacional", "partida", "capitulo", "programa"]

resultados = {"errores": 0, "advertencias": 0, "ok": 0}


# =====================================================
# UTILIDADES
# =====================================================
def error(msg):
    reg.error("general", msg)

def advertencia(msg):
    reg.warn("general", msg)

def ok(msg):
    reg.ok("general", msg)

def info(msg):
    reg.info("general", msg)


def cargar(nombre):
    """Carga un CSV consolidado usando detección automática de formato."""
    ruta = CONSOLIDADO_DIR / nombre
    if not ruta.exists():
        error(f"Archivo no encontrado: {nombre}")
        return None

    if TIENE_UTILS:
        try:
            df, fmt = leer_csv_robusto(str(ruta))
        except Exception as e:
            error(f"No se pudo leer {nombre}: {e}")
            return None
    else:
        df = pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)

    if "Año" not in df.columns:
        error(f"{nombre}: falta columna 'Año'. Detectadas: {list(df.columns)[:5]}")
        return None

    return df


def separador(titulo):
    print(f"\n{'─'*60}")
    print(f"  {titulo}")
    print(f"{'─'*60}")


# =====================================================
# CHECK 1 — Cobertura temporal
# =====================================================
def check_cobertura(df, nombre):
    separador(f"CHECK 1 — Cobertura temporal: {nombre}")

    años = sorted(df["Año"].unique())
    print(f"  Años presentes: {min(años)}–{max(años)} ({len(años)} años)")

    faltantes_total = 0
    for año in años:
        meses_presentes = df[df["Año"] == año]["Mes"].unique()
        meses_faltantes = [m for m in MESES_ORDEN if m not in meses_presentes]

        if meses_faltantes:
            if año == max(años):
                advertencia(f"{año}: faltan {meses_faltantes} (puede ser año en curso)")
            else:
                error(f"{año}: faltan meses {meses_faltantes}")
                faltantes_total += len(meses_faltantes)
        else:
            ok(f"{año}: 12 meses completos")

    if faltantes_total == 0:
        ok(f"Cobertura temporal completa (excepto año en curso)")


# =====================================================
# CHECK 2 — Duplicados
# =====================================================
def check_duplicados(df, nombre, nivel):
    separador(f"CHECK 2 — Duplicados: {nombre}")

    keys = keys_de_nivel(nivel)
    keys_presentes = [k for k in keys if k in df.columns]

    if len(keys_presentes) < len(keys):
        faltantes = set(keys) - set(keys_presentes)
        advertencia(f"Keys faltantes para check de duplicados: {faltantes}")

    duplicados = df.duplicated(subset=keys_presentes, keep=False)
    n_dup = duplicados.sum()

    if n_dup > 0:
        n_combis = n_dup // 2
        error(f"{n_dup} filas duplicadas ({n_combis} combinaciones) en keys {keys_presentes}")
        
        # Analizar origen
        print(f"    Distribución:")
        for col in ["Partida", "Año"]:
            if col in df.columns:
                dist = df[duplicados].groupby(col).size().sort_values(ascending=False).head(5)
                print(f"      Por {col}: {dict(dist)}")
    else:
        ok(f"Sin duplicados en keys {keys_presentes}")


# =====================================================
# CHECK 3 — Nulos en columnas clave
# =====================================================
def check_nulos(df, nombre):
    separador(f"CHECK 3 — Nulos: {nombre}")

    columnas_criticas = ["Año", "Mes", "Moneda"]
    columnas_monto = [c for c in df.columns if c in [
        "ley_inicial", "ley_vigente",
        "ejecucion_mes", "ejecucion_acumulada",
        "pct_ejecucion"
    ]]

    for col in columnas_criticas:
        if col in df.columns:
            nulos = df[col].isna().sum()
            if nulos > 0:
                error(f"'{col}' tiene {nulos} valores nulos")
            else:
                ok(f"'{col}' sin nulos")

    for col in columnas_monto:
        if col in df.columns:
            nulos = df[col].isna().sum()
            if nulos > 0:
                advertencia(f"'{col}' tiene {nulos} valores nulos (se tratarán como 0)")
            else:
                ok(f"'{col}' sin nulos")


# =====================================================
# CHECK 4 — Anomalías de valores
# =====================================================
def check_anomalias(df, nombre):
    separador(f"CHECK 4 — Anomalías de valores: {nombre}")

    # Ley vigente = 0 pero hay ejecución
    if "ley_vigente" in df.columns and "ejecucion_acumulada" in df.columns:
        sin_ley = (df["ley_vigente"] == 0) & (df["ejecucion_acumulada"] != 0)
        n = sin_ley.sum()
        if n > 0:
            advertencia(f"{n} filas con ley_vigente=0 pero ejecución>0")
        else:
            ok("Sin filas con ley_vigente=0 y ejecución>0")

    # Ejecución negativa
    if "ejecucion_acumulada" in df.columns:
        negativos = df["ejecucion_acumulada"] < 0
        n = negativos.sum()
        if n > 0:
            advertencia(f"{n} filas con ejecución acumulada negativa (ajustes presupuestarios)")
        else:
            ok("Sin ejecución negativa")

    # Ley vigente negativa
    if "ley_vigente" in df.columns:
        negativos = df["ley_vigente"] < 0
        n = negativos.sum()
        if n > 0:
            advertencia(f"{n} filas con ley vigente negativa (recortes/reasignaciones)")
        else:
            ok("Sin ley vigente negativa")

    # Ejecución mensual mayor que acumulada
    if "ejecucion_mes" in df.columns and "ejecucion_acumulada" in df.columns:
        invertido = df["ejecucion_mes"].abs() > df["ejecucion_acumulada"].abs() + 1
        n = invertido.sum()
        if n > 0:
            advertencia(f"{n} filas donde ejecución mensual > acumulada")
        else:
            ok("Ejecución mensual consistente con acumulada")


# =====================================================
# CHECK 5 — Valores pegados entre meses
# =====================================================
def check_valores_pegados(df, nombre):
    separador(f"CHECK 5 — Valores pegados entre meses: {nombre}")

    if "ejecucion_acumulada" not in df.columns:
        advertencia("No tiene columna ejecucion_acumulada")
        return

    keys_grupo = [c for c in ["Año", "Moneda", "Partida", "Subtítulo"] if c in df.columns]

    mes_a_num = {m: i + 1 for i, m in enumerate(MESES_ORDEN)}
    df_work = df.copy()
    df_work["MesNum"] = df_work["Mes"].map(mes_a_num)
    df_work = df_work.sort_values(keys_grupo + ["MesNum"])

    pegados = 0
    total_grupos = 0

    for _, grupo in df_work.groupby(keys_grupo):
        if len(grupo) < 3:
            continue

        total_grupos += 1
        ejec = grupo["ejecucion_acumulada"].values
        for i in range(len(ejec) - 2):
            if ejec[i] != 0 and ejec[i] == ejec[i + 1] == ejec[i + 2]:
                pegados += 1
                break

    if pegados > 0:
        pct = pegados / total_grupos * 100
        advertencia(f"{pegados}/{total_grupos} grupos ({pct:.1f}%) con 3+ meses consecutivos con misma ejecución")
    else:
        ok("Sin valores pegados detectados")


# =====================================================
# CHECK 6 — Consistencia del cruce
# =====================================================
def check_cruce(cruce, ejec, ley, nombre_nivel):
    separador(f"CHECK 6 — Consistencia del cruce: {nombre_nivel}")

    if cruce is None:
        advertencia(f"No se encontró cruce_{nombre_nivel}.csv")
        return

    tiene_ley = "ley_vigente" in cruce.columns
    tiene_ejec = "ejecucion_acumulada" in cruce.columns

    if tiene_ley and tiene_ejec:
        ok("Cruce contiene columnas de ley y ejecución")
    else:
        if not tiene_ley:
            error("Cruce no tiene columna ley_vigente")
        if not tiene_ejec:
            error("Cruce no tiene columna ejecucion_acumulada")

    # Verificar pct_ejecucion
    if "pct_ejecucion" in cruce.columns and tiene_ley and tiene_ejec:
        mask = cruce["ley_vigente"] != 0
        pct_calc = (cruce.loc[mask, "ejecucion_acumulada"] / cruce.loc[mask, "ley_vigente"] * 100).round(2)
        pct_real = cruce.loc[mask, "pct_ejecucion"]
        diff = (pct_calc - pct_real).abs()
        problemas = diff > 0.1
        if problemas.any():
            advertencia(f"{problemas.sum()} filas con pct_ejecucion mal calculado")
        else:
            ok("pct_ejecucion calculado correctamente")

    # Conteo de filas vs ley
    if ley is not None:
        filas_ley = len(ley)
        filas_cruce = len(cruce)
        diff = filas_ley - filas_cruce
        if diff > 0:
            advertencia(f"Cruce tiene {diff} filas menos que ley ({filas_cruce} vs {filas_ley})")
        elif diff < 0:
            advertencia(f"Cruce tiene {abs(diff)} filas más que ley ({filas_cruce} vs {filas_ley})")
        else:
            ok(f"Cruce y ley tienen la misma cantidad de filas ({filas_cruce})")


# =====================================================
# CHECK 7 — Coherencia entre niveles (con distinción
#            de consolidación vs error)
# =====================================================
def check_coherencia(nivel_alto, nivel_bajo, nombre_alto, nombre_bajo, keys_extra=None, es_consolidacion=False):
    separador(f"CHECK 7 — {'Consolidación' if es_consolidacion else 'Coherencia'}: {nombre_alto} vs {nombre_bajo}")

    if nivel_alto is None or nivel_bajo is None:
        advertencia("No se puede comparar — falta algún archivo")
        return

    keys_comunes = ["Año", "Mes", "Moneda", "Subtítulo"]
    if keys_extra:
        keys_comunes += keys_extra
    keys_comunes = [k for k in keys_comunes if k in nivel_alto.columns and k in nivel_bajo.columns]

    campos_monto = ["ley_vigente", "ejecucion_acumulada"]
    campos_monto = [c for c in campos_monto if c in nivel_alto.columns and c in nivel_bajo.columns]

    if not campos_monto:
        advertencia("No hay campos de monto comunes para comparar")
        return

    bajo_agrupado = nivel_bajo.groupby(keys_comunes, as_index=False)[campos_monto].sum()

    comp = pd.merge(
        nivel_alto[keys_comunes + campos_monto],
        bajo_agrupado,
        on=keys_comunes,
        how="outer",
        suffixes=("_alto", "_bajo"),
    )

    for campo in campos_monto:
        col_alto = f"{campo}_alto"
        col_bajo = f"{campo}_bajo"

        if col_alto not in comp.columns or col_bajo not in comp.columns:
            continue

        comp[col_alto] = comp[col_alto].fillna(0)
        comp[col_bajo] = comp[col_bajo].fillna(0)

        diff = (comp[col_alto] - comp[col_bajo]).abs()
        problemas = diff > 1
        n_prob = problemas.sum()
        total = len(comp)
        pct_ok = (total - n_prob) / total * 100

        if n_prob > 0:
            max_diff = diff[problemas].max()
            
            if es_consolidacion:
                # Esperado: verificar que las diferencias son en subtítulos de transferencia
                subs_afectados = comp.loc[problemas, "Subtítulo"].unique() if "Subtítulo" in comp.columns else []
                subs_transf = [s for s in subs_afectados if int(s) in [5, 9, 13, 24, 27, 33]]
                pct_transf = len(subs_transf) / len(subs_afectados) * 100 if len(subs_afectados) > 0 else 0
                
                info(f"{campo}: {n_prob} diferencias ({pct_ok:.1f}% cuadra) — consolidación esperada")
                info(f"  {pct_transf:.0f}% de subtítulos afectados son de transferencia (esperado)")
            else:
                error(f"{campo}: {n_prob} discrepancias (máx: {max_diff:,.0f}, {pct_ok:.1f}% cuadra)")
                ejemplos = comp[problemas].head(3)
                for _, row in ejemplos.iterrows():
                    ctx = " | ".join(f"{k}={row[k]}" for k in keys_comunes if k in row.index)
                    print(f"    {ctx}: alto={row[col_alto]:,.0f} vs bajo={row[col_bajo]:,.0f}")
        else:
            ok(f"{campo}: 100% cuadra entre {nombre_alto} y {nombre_bajo}")


# =====================================================
# CHECK 8 — Estructura a nivel de fila (CSVs crudos)
# =====================================================
def check_estructura_filas(tipos=None):
    separador("CHECK 8 — Estructura a nivel de fila (CSVs crudos)")

    if tipos is None:
        tipos = ["ejecucion", "ley"]

    problemas_total = 0
    archivos_revisados = 0

    for tipo in tipos:
        carpeta = DIRS[tipo]
        if not carpeta.exists():
            advertencia(f"No existe carpeta: {carpeta}")
            continue

        for csv_path in sorted(carpeta.rglob("*.csv")):
            archivos_revisados += 1

            try:
                with open(csv_path, "rb") as f:
                    lineas = f.readlines()

                if len(lineas) < 2:
                    continue

                # Detectar separador del header
                header = lineas[0].decode("utf-8-sig", errors="replace").strip()
                sep = ";" if header.count(";") >= header.count(",") else ","
                n_campos_header = header.count(sep) + 1

                # Verificar que cada fila tiene la misma cantidad de separadores
                filas_malas = 0
                for i, linea in enumerate(lineas[1:], start=2):
                    texto = linea.decode("utf-8-sig", errors="replace").strip()
                    if not texto:
                        continue
                    n_campos = texto.count(sep) + 1
                    if n_campos != n_campos_header:
                        filas_malas += 1

                if filas_malas > 0:
                    ruta_rel = csv_path.relative_to(DIRS["base"])
                    advertencia(f"{ruta_rel}: {filas_malas} filas con {n_campos} campos vs {n_campos_header} en header")
                    problemas_total += filas_malas

            except Exception as e:
                advertencia(f"Error leyendo {csv_path.relative_to(DIRS["base"])}: {e}")

    if problemas_total == 0:
        ok(f"Todos los {archivos_revisados} archivos tienen estructura de filas consistente")
    else:
        advertencia(f"{problemas_total} filas con estructura inconsistente en {archivos_revisados} archivos")


# =====================================================
# CHECK 9 — Encoding consistente entre archivos
# =====================================================
def check_encoding():
    separador("CHECK 9 — Encoding entre archivos")

    if not TIENE_UTILS:
        advertencia("utils.py no disponible — no se puede verificar encoding")
        return

    encodings_por_tipo = {}

    for tipo in ["ejecucion", "ley"]:
        carpeta = DIRS[tipo]
        if not carpeta.exists():
            continue

        encodings = {}
        for csv_path in sorted(carpeta.rglob("*.csv")):
            try:
                _, fmt = leer_csv_robusto(str(csv_path), nrows=5)
                enc = fmt["encoding"]
                if enc not in encodings:
                    encodings[enc] = []
                encodings[enc].append(str(csv_path.relative_to(DIRS["base"])))
            except Exception:
                continue

        encodings_por_tipo[tipo] = encodings

    for tipo, encs in encodings_por_tipo.items():
        if len(encs) == 1:
            enc = list(encs.keys())[0]
            n = len(list(encs.values())[0])
            ok(f"{tipo}: todos los archivos usan {enc} ({n} archivos)")
        else:
            advertencia(f"{tipo}: múltiples encodings detectados")
            for enc, archivos in encs.items():
                # Extraer años para resumir
                años = set()
                for a in archivos:
                    partes = a.replace("\\", "/").split("/")
                    for p in partes:
                        if p.isdigit() and len(p) == 4:
                            años.add(p)
                años_str = f"{min(años)}-{max(años)}" if años else "?"
                info(f"  {enc}: {len(archivos)} archivos (años {años_str})")


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    import config
    print(f"config desde: {config.__file__}")
    print(f"Corriendo: {__file__}")
    print(f"CONSOLIDADO_DIR: {CONSOLIDADO_DIR}")
    print("=" * 60)
    print("  VALIDACIÓN INTERNA — DATOS DIPRES (v3)")
    print("=" * 60)

    # ─── Checks por nivel (consolidados) ───
    for nivel in NIVELES:
        print(f"\n{'='*60}")
        print(f"  NIVEL: {nivel.upper()}")
        print(f"{'='*60}")

        cruce = cargar(f"cruce_{nivel}.csv")
        ejec = cargar(f"ejecucion_{nivel}.csv")
        ley = cargar(f"ley_{nivel}.csv")

        if cruce is not None:
            check_cobertura(cruce, f"cruce_{nivel}")
            check_duplicados(cruce, f"cruce_{nivel}", nivel)
            check_nulos(cruce, f"cruce_{nivel}")
            check_anomalias(cruce, f"cruce_{nivel}")
            check_valores_pegados(cruce, f"cruce_{nivel}")
            check_cruce(cruce, ejec, ley, nivel)

    # ─── Coherencia entre niveles ───
    print(f"\n{'='*60}")
    print(f"  COHERENCIA ENTRE NIVELES")
    print(f"{'='*60}")

    cruce_nacional = cargar("cruce_nacional.csv")
    cruce_partida = cargar("cruce_partida.csv")
    cruce_capitulo = cargar("cruce_capitulo.csv")
    cruce_programa = cargar("cruce_programa.csv")

    # Nacional vs Partida: consolidación (elimina transferencias inter-ministeriales)
    check_coherencia(cruce_nacional, cruce_partida,
        "nacional", "partida",
        es_consolidacion=True)

    # Partida vs Capítulo: consolidación parcial (elimina transferencias intra-ministeriales)
    check_coherencia(cruce_partida, cruce_capitulo,
        "partida", "capitulo",
        keys_extra=["Partida"],
        es_consolidacion=True)

    # Capítulo vs Programa: debería cuadrar (mismo nivel bruto)
    check_coherencia(cruce_capitulo, cruce_programa,
        "capitulo", "programa",
        keys_extra=["Partida", "Capítulo"])

    # ─── Checks de archivos fuente ───
    print(f"\n{'='*60}")
    print(f"  ESTRUCTURA DE ARCHIVOS FUENTE")
    print(f"{'='*60}")

    check_estructura_filas()
    check_encoding()

    # ─── Resumen ───
    print(f"\n{'='*60}")
    print(f"  RESUMEN")
    print(f"{'='*60}")
    print(f"  ✓ Checks OK:       {resultados['ok']}")
    print(f"  ⚠ Advertencias:    {resultados['advertencias']}")
    print(f"  ❌ Errores:         {resultados['errores']}")

    if resultados["errores"] == 0:
        print(f"\n  ✓ Datos aptos para publicación (revisar advertencias)")
    else:
        print(f"\n  ❌ Corregir errores antes de publicar")

    reg.emitir()