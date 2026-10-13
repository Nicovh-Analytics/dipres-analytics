"""
Diccionario temporal de clasificadores presupuestarios
======================================================
Construye un catálogo de todos los códigos usados por año,
identificando cuáles se agregan y cuáles desaparecen entre
períodos.

Salida (DIRS["consolidado"]):
  - diccionario_clasificadores.csv → catálogo completo con vigencia
  - cambios_clasificadores.csv → log de agregaciones y eliminaciones por año

Uso:
    python pipeline/2_consolidacion/07_diccionario.py
"""

import pandas as pd

from dipres.config import DIRS

DATOS_DIR = DIRS["consolidado"]

# Columnas que usan los niveles de abajo: se lee solo esto (el archivo de
# programa es grande)
COLUMNAS = ["Año", "Partida", "Capítulo", "Programa", "Subtítulo", "Item",
            "Asignación", "Nombre Partida", "Nombre Capítulo",
            "Nombre Programa", "Nombre Subtítulo", "Nombre Item",
            "Nombre Asignación"]


def cargar(nombre):
    ruta = DATOS_DIR / nombre
    if not ruta.exists():
        print(f"  ❌ No encontrado: {ruta}")
        return None
    return pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False,
                       usecols=lambda c: c in COLUMNAS)


def construir_diccionario_nivel(df, nivel, campos_codigo, campos_nombre):
    """
    Combinaciones únicas de códigos (con su nombre) por año: primer y
    último año de aparición, y log de códigos agregados/eliminados entre
    años consecutivos.
    """
    codigos = [c for c in campos_codigo if c in df.columns]
    nombres = [c for c in campos_nombre if c in df.columns]

    # Solo filas con todos los códigos informados
    mask = df[codigos].notna().all(axis=1)
    for c in codigos:
        mask &= df[c].astype(str).str.strip() != ""
    unicos = df.loc[mask, ["Año"] + codigos + nombres].drop_duplicates()
    if unicos.empty:
        print(f"  Sin datos para nivel {nivel}")
        return None, None

    ultimo = df["Año"].max()
    grupo = (unicos.groupby(codigos + nombres, dropna=False)
                   .agg(primer_año=("Año", "min"), ultimo_año=("Año", "max"),
                        años_presente=("Año", "nunique"))
                   .reset_index())
    grupo["nivel"] = nivel
    grupo["vigente"] = grupo["ultimo_año"] == ultimo

    print(f"  {nivel}: {len(grupo):,} combinaciones únicas")
    print(f"    Vigentes en {ultimo}: {grupo['vigente'].sum():,}")
    print(f"    Históricas (ya no aparecen): {(~grupo['vigente']).sum():,}")

    # Un nombre por código y año (el primero), para el log
    por_anio = unicos.drop_duplicates(["Año"] + codigos)
    cambios = []
    años = sorted(por_anio["Año"].unique())
    for ant, act in zip(años, años[1:]):
        m = por_anio[por_anio["Año"] == ant].drop(columns="Año").merge(
            por_anio[por_anio["Año"] == act].drop(columns="Año"),
            on=codigos, how="outer", indicator=True,
            suffixes=("_ant", "_act"))
        for lado, tipo, suf in (("right_only", "AGREGADO", "_act"),
                                ("left_only", "ELIMINADO", "_ant")):
            x = m[m["_merge"] == lado]
            if x.empty:
                continue
            x = x[codigos + [n + suf for n in nombres]].copy()
            x.columns = codigos + nombres
            x.insert(0, "nivel", nivel)
            x.insert(0, "tipo_cambio", tipo)
            x.insert(0, "año", act)
            cambios.append(x)
        n_ag = int((m["_merge"] == "right_only").sum())
        n_el = int((m["_merge"] == "left_only").sum())
        if n_ag or n_el:
            print(f"    {ant} → {act}: +{n_ag} agregados, -{n_el} eliminados")

    return grupo, (pd.concat(cambios, ignore_index=True) if cambios else None)


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  DICCIONARIO TEMPORAL DE CLASIFICADORES PRESUPUESTARIOS")
    print("=" * 70)

    # Usar ejecución (tiene mayor completitud en clasificación)
    ejec = cargar("ejecucion_programa.csv")
    if ejec is None:
        raise SystemExit(1)

    print(f"\n  Años disponibles: {sorted(int(a) for a in ejec['Año'].unique())}")
    print(f"  Total filas: {len(ejec):,}")

    resultados_dict = []
    resultados_cambios = []

    # Nivel 1: Subtítulo
    print(f"\n{'─'*70}")
    print(f"  NIVEL: SUBTÍTULO")
    print(f"{'─'*70}")
    d, c = construir_diccionario_nivel(
        ejec, "subtitulo",
        ["Subtítulo"],
        ["Nombre Subtítulo"]
    )
    if d is not None:
        resultados_dict.append(d)
    if c is not None:
        resultados_cambios.append(c)

    # Nivel 2: Item
    print(f"\n{'─'*70}")
    print(f"  NIVEL: ÍTEM")
    print(f"{'─'*70}")
    d, c = construir_diccionario_nivel(
        ejec, "item",
        ["Subtítulo", "Item"],
        ["Nombre Subtítulo", "Nombre Item"]
    )
    if d is not None:
        resultados_dict.append(d)
    if c is not None:
        resultados_cambios.append(c)

    # Nivel 3: Asignación
    print(f"\n{'─'*70}")
    print(f"  NIVEL: ASIGNACIÓN")
    print(f"{'─'*70}")
    d, c = construir_diccionario_nivel(
        ejec, "asignacion",
        ["Subtítulo", "Item", "Asignación"],
        ["Nombre Subtítulo", "Nombre Item", "Nombre Asignación"]
    )
    if d is not None:
        resultados_dict.append(d)
    if c is not None:
        resultados_cambios.append(c)

    # Nivel institucional: Partida
    print(f"\n{'─'*70}")
    print(f"  NIVEL: PARTIDA")
    print(f"{'─'*70}")
    d, c = construir_diccionario_nivel(
        ejec, "partida",
        ["Partida"],
        ["Nombre Partida"]
    )
    if d is not None:
        resultados_dict.append(d)
    if c is not None:
        resultados_cambios.append(c)

    # Nivel institucional: Capítulo
    print(f"\n{'─'*70}")
    print(f"  NIVEL: CAPÍTULO")
    print(f"{'─'*70}")
    d, c = construir_diccionario_nivel(
        ejec, "capitulo",
        ["Partida", "Capítulo"],
        ["Nombre Partida", "Nombre Capítulo"]
    )
    if d is not None:
        resultados_dict.append(d)
    if c is not None:
        resultados_cambios.append(c)

    # Nivel institucional: Programa
    print(f"\n{'─'*70}")
    print(f"  NIVEL: PROGRAMA")
    print(f"{'─'*70}")
    d, c = construir_diccionario_nivel(
        ejec, "programa",
        ["Partida", "Capítulo", "Programa"],
        ["Nombre Partida", "Nombre Capítulo", "Nombre Programa"]
    )
    if d is not None:
        resultados_dict.append(d)
    if c is not None:
        resultados_cambios.append(c)

    # Guardar resultados
    print(f"\n{'='*70}")
    print(f"  GUARDANDO RESULTADOS")
    print(f"{'='*70}")

    if resultados_dict:
        diccionario = pd.concat(resultados_dict, ignore_index=True)
        ruta = DATOS_DIR / "diccionario_clasificadores.csv"
        diccionario.to_csv(ruta, index=False, encoding="utf-8-sig")
        print(f"  💾 {ruta.name}: {len(diccionario):,} entradas")

    if resultados_cambios:
        cambios = pd.concat(resultados_cambios, ignore_index=True)
        cambios = cambios.sort_values(["año", "nivel", "tipo_cambio"])
        ruta = DATOS_DIR / "cambios_clasificadores.csv"
        cambios.to_csv(ruta, index=False, encoding="utf-8-sig")
        print(f"  💾 {ruta.name}: {len(cambios):,} cambios registrados")

    print(f"\n{'='*70}")
    print(f"  DICCIONARIO COMPLETO")
    print(f"{'='*70}")