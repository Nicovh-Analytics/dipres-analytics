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
    python 06_validar.py
"""

from collections import Counter

import pandas as pd

from config import DIRS, IO, TOLERANCIAS
from dominio import (MES_A_NUM, MESES, NIVELES, SUBTITULOS_TRANSFERENCIA,
                     keys_de_nivel)
from hallazgos import Registro
from utils import leer_csv_robusto

reg = Registro("validacion", salida_dir=DIRS["reportes"])

CONSOLIDADO_DIR = DIRS["consolidado"]
MESES_ORDEN = MESES

resultados = {"errores": 0, "advertencias": 0, "ok": 0}
_cache: dict[str, pd.DataFrame | None] = {}


# =====================================================
# UTILIDADES
# =====================================================
def error(msg):
    resultados["errores"] += 1
    reg.error("general", msg)

def advertencia(msg):
    resultados["advertencias"] += 1
    reg.warn("general", msg)

def ok(msg):
    resultados["ok"] += 1
    reg.ok("general", msg)

def info(msg):
    reg.info("general", msg)


def cargar(nombre):
    """Carga un CSV consolidado (una sola vez: queda en caché)."""
    if nombre in _cache:
        return _cache[nombre]
    ruta = CONSOLIDADO_DIR / nombre
    df = None
    if not ruta.exists():
        error(f"Archivo no encontrado: {nombre}")
    else:
        try:
            # estricto: un consolidado no debería traer filas mal formadas
            df, _ = leer_csv_robusto(str(ruta), estricto=True)
        except Exception as e:
            error(f"No se pudo leer {nombre}: {e}")
        if df is not None and "Año" not in df.columns:
            error(f"{nombre}: falta columna 'Año'. Detectadas: {list(df.columns)[:5]}")
            df = None
    _cache[nombre] = df
    return df


def contar_filas(nombre, claves=None):
    """Filas de un consolidado sin cargarlo entero. Con `claves`, cuenta
    combinaciones distintas (la ejecución de programa trae Sub-Asignación,
    que el cruce suma en una fila)."""
    ruta = CONSOLIDADO_DIR / nombre
    if not ruta.exists():
        return None
    if claves is None:
        return len(pd.read_csv(ruta, usecols=[0], encoding="utf-8-sig"))
    df = pd.read_csv(ruta, usecols=lambda c: c in claves, encoding="utf-8-sig",
                     low_memory=False)
    return len(df.drop_duplicates())


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
        n_combis = df.loc[duplicados, keys_presentes].drop_duplicates().shape[0]
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
            detalle = ""
            if "origen" in df.columns:
                solo = int((sin_ley & (df["origen"] == "solo_ejecucion")).sum())
                detalle = f" ({solo} sin línea en la ley: origen=solo_ejecucion)"
            advertencia(f"{n} filas con ley_vigente=0 pero ejecución≠0{detalle}")
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
    n_pegue = TOLERANCIAS["meses_pegados"]

    # Agregado por grupo y mes, ordenado; un grupo está "pegado" si tiene
    # n_pegue meses consecutivos con el mismo acumulado distinto de 0
    w = (df.assign(MesNum=df["Mes"].map(MES_A_NUM))
           .groupby(keys_grupo + ["MesNum"], as_index=False)["ejecucion_acumulada"].sum()
           .sort_values(keys_grupo + ["MesNum"]))
    g = w.groupby(keys_grupo)["ejecucion_acumulada"]
    igual = w["ejecucion_acumulada"] != 0
    for k in range(1, n_pegue):
        igual &= w["ejecucion_acumulada"] == g.shift(k)
    tamanos = g.transform("size")
    total_grupos = int(w.loc[tamanos >= n_pegue, keys_grupo].drop_duplicates().shape[0])
    pegados = int(w.loc[igual, keys_grupo].drop_duplicates().shape[0])

    if pegados > 0:
        pct = pegados / total_grupos * 100
        advertencia(f"{pegados}/{total_grupos} grupos ({pct:.1f}%) con {n_pegue}+ meses consecutivos con misma ejecución")
    else:
        ok("Sin valores pegados detectados")


# =====================================================
# CHECK 6 — Consistencia del cruce
# =====================================================
def check_cruce(cruce, n_ejec, n_ley, nombre_nivel):
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

    # Conteo de filas: el cruce es un outer join con columna `origen`
    if "origen" not in cruce.columns:
        advertencia("Cruce sin columna 'origen' (generado antes de 05b): "
                    "no se puede verificar el conteo de filas")
        return
    n = cruce["origen"].value_counts()
    ambos, s_ley, s_ejec = (int(n.get(k, 0)) for k in
                            ("ambos", "solo_ley", "solo_ejecucion"))
    info(f"origen: ambos {ambos:,} · solo_ley {s_ley:,} · solo_ejecucion {s_ejec:,}")
    for n_arch, nombre, esperado in ((n_ley, "ley", ambos + s_ley),
                                     (n_ejec, "ejecución", ambos + s_ejec)):
        if n_arch is None:
            continue
        if n_arch == esperado:
            ok(f"{nombre}: sus {n_arch:,} filas están todas en el cruce")
        else:
            advertencia(f"{nombre}: {n_arch:,} filas en el archivo vs "
                        f"{esperado:,} en el cruce")


def hojas(df):
    """Máscara de filas hoja. La ley a nivel programa trae subtotales:
    fila de subtítulo (Item vacío) e ítem (Asignación vacía) además del
    detalle; sumarlo todo cuenta dos o tres veces lo mismo."""
    base = [c for c in ["Año", "Mes", "Moneda", "Partida", "Capítulo",
                        "Programa", "Subtítulo"] if c in df.columns]
    if "Item" not in df.columns:
        return pd.Series(True, index=df.index)
    # El detalle que convierte una fila en subtotal debe venir de la LEY:
    # filas solo_ejecucion con asignación no cuentan (si no, una línea de
    # ley a nivel ítem se descartaría por tener ejecución desagregada)
    es_ley = (df["origen"] != "solo_ejecucion") if "origen" in df.columns \
        else pd.Series(True, index=df.index)
    item_na = df["Item"].isna()
    tiene_items = (df.assign(_i=df["Item"].where(es_ley))
                     .groupby(base)["_i"].transform("count") > 0)
    sub_total = item_na & tiene_items
    if "Asignación" in df.columns:
        tiene_asig = (df.assign(_a=df["Asignación"].where(es_ley))
                        .groupby(base + ["Item"], dropna=False)["_a"]
                        .transform("count") > 0)
        sub_total |= ~item_na & df["Asignación"].isna() & tiene_asig
    return ~sub_total


# =====================================================
# CHECK 7 — Coherencia entre niveles (con distinción
#            de consolidación vs error)
# =====================================================
def check_coherencia(nivel_alto, nivel_bajo, nombre_alto, nombre_bajo, keys_extra=None, es_consolidacion=False):
    """Las diferencias en subtítulos de transferencia se informan como
    consolidación (transferencias entre unidades que el nivel alto elimina);
    las demás, como error. La ley del nivel bajo se suma solo en sus filas
    hoja (sin subtotales)."""
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

    bajo = nivel_bajo[keys_comunes + campos_monto].copy()
    if "ley_vigente" in campos_monto:
        es_hoja = hojas(nivel_bajo)
        n_sub = int((~es_hoja).sum())
        if n_sub:
            info(f"{nombre_bajo}: {n_sub:,} filas de subtotal excluidas de ley_vigente")
        bajo.loc[~es_hoja, "ley_vigente"] = 0
    bajo_agrupado = bajo.groupby(keys_comunes, as_index=False)[campos_monto].sum()

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
        problemas = diff > TOLERANCIAS["monto"]
        n_prob = problemas.sum()
        total = len(comp)
        pct_ok = (total - n_prob) / total * 100

        if n_prob > 0:
            # Compatible con consolidación: subtítulo de transferencia, o
            # (si el nivel alto consolida) el alto es menor que el bajo:
            # consolidar solo elimina flujos internos, nunca agrega
            transf = comp["Subtítulo"].astype(int).isin(SUBTITULOS_TRANSFERENCIA)
            reduce = comp[col_alto].abs() < comp[col_bajo].abs()
            compatible = problemas & (transf | (reduce if es_consolidacion else False))
            otro = problemas & ~compatible
            if compatible.any():
                por_sub = (comp[compatible].groupby("Subtítulo").size()
                           .sort_values(ascending=False))
                subs = ", ".join(f"{int(k):02d}×{v}" for k, v in por_sub.head(8).items())
                info(f"{campo}: {int(compatible.sum())} diferencias compatibles con "
                     f"consolidación (subtítulo×casos: {subs})")
            if otro.any():
                max_diff = diff[otro].max()
                pct_ok = (total - int(otro.sum())) / total * 100
                error(f"{campo}: {int(otro.sum())} discrepancias no explicadas por "
                      f"consolidación (máx: {max_diff:,.0f}, {pct_ok:.1f}% cuadra)")
                por_mes = (comp[otro].groupby(["Año", "Mes"]).size()
                           .sort_values(ascending=False).head(5))
                print("    Año-Mes con más casos: " + ", ".join(
                    f"{int(a)}-{m}×{n}" for (a, m), n in por_mes.items()))
                por_sub = comp[otro].groupby("Subtítulo").size().sort_values(ascending=False).head(8)
                print("    Subtítulos: " + ", ".join(f"{int(k):02d}×{v}" for k, v in por_sub.items()))
                for _, row in comp[otro].head(3).iterrows():
                    ctx = " | ".join(f"{k}={row[k]}" for k in keys_comunes)
                    print(f"    {ctx}: alto={row[col_alto]:,.0f} vs bajo={row[col_bajo]:,.0f}")
            else:
                ok(f"{campo}: toda diferencia es compatible con consolidación")
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
            if "_versiones" in csv_path.parts:
                continue
            archivos_revisados += 1
            ruta_rel = csv_path.relative_to(DIRS["base"])
            try:
                # Línea a línea: no cargar el archivo entero en memoria
                with open(csv_path, "rb") as f:
                    header = f.readline().decode("utf-8-sig", errors="replace").strip()
                    sep = max(IO["separadores"], key=header.count)
                    n_header = header.count(sep) + 1
                    conteo = Counter()
                    trailing = 0
                    for linea in f:
                        texto = linea.decode("utf-8-sig", errors="replace").rstrip("\r\n")
                        if not texto.strip():
                            continue
                        n = texto.count(sep) + 1
                        if n == n_header:
                            continue
                        if n == n_header + 1 and texto.endswith(sep):
                            trailing += 1      # ";" sobrante al final (ley 2017)
                        else:
                            conteo[n] += 1
            except Exception as e:
                advertencia(f"Error leyendo {ruta_rel}: {e}")
                continue

            if conteo:
                distrib = ", ".join(f"{c}×{n} campos" for n, c in sorted(conteo.items()))
                advertencia(f"{ruta_rel}: {sum(conteo.values())} filas con nº de "
                            f"campos ≠ {n_header} del header ({distrib})")
                problemas_total += sum(conteo.values())
            if trailing:
                info(f"{ruta_rel}: {trailing} filas con delimitador final sobrante")

    if problemas_total == 0:
        ok(f"Todos los {archivos_revisados} archivos tienen estructura de filas consistente")
    else:
        advertencia(f"{problemas_total} filas con estructura inconsistente en {archivos_revisados} archivos")


# =====================================================
# CHECK 9 — Encoding consistente entre archivos
# =====================================================
def check_encoding():
    separador("CHECK 9 — Encoding entre archivos")

    encodings_por_tipo = {}

    for tipo in ["ejecucion", "ley"]:
        carpeta = DIRS[tipo]
        if not carpeta.exists():
            continue

        encodings = {}
        for csv_path in sorted(carpeta.rglob("*.csv")):
            if "_versiones" in csv_path.parts:
                continue
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
        n_ejec = contar_filas(f"ejecucion_{nivel}.csv", keys_de_nivel(nivel))
        n_ley = contar_filas(f"ley_{nivel}.csv")

        if cruce is not None:
            check_cobertura(cruce, f"cruce_{nivel}")
            check_duplicados(cruce, f"cruce_{nivel}", nivel)
            check_nulos(cruce, f"cruce_{nivel}")
            check_anomalias(cruce, f"cruce_{nivel}")
            check_valores_pegados(cruce, f"cruce_{nivel}")
            check_cruce(cruce, n_ejec, n_ley, nivel)

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