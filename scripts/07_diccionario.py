"""
Diccionario temporal de clasificadores presupuestarios
======================================================
Construye un catálogo de todos los códigos usados por año,
identificando cuáles se agregan y cuáles desaparecen entre
períodos.

Salida:
  - diccionario_clasificadores.csv → catálogo completo con vigencia
  - cambios_clasificadores.csv → log de agregaciones y eliminaciones por año

Uso:
    python 09_diccionario_clasificadores.py
"""

import pandas as pd
from pathlib import Path

DATOS_DIR = Path("D:/dipres-datos/consolidado")


def cargar(nombre):
    ruta = DATOS_DIR / nombre
    if not ruta.exists():
        print(f"  ❌ No encontrado: {nombre}")
        return None
    return pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)


def construir_diccionario_nivel(df, nivel, campos_codigo, campos_nombre):
    """
    Extrae combinaciones únicas de códigos por año y determina
    primer y último año de aparición.
    """
    # Filtrar solo filas que tengan los campos de código informados
    mask = pd.Series(True, index=df.index)
    for campo in campos_codigo:
        if campo in df.columns:
            mask = mask & df[campo].notna() & (df[campo].astype(str).str.strip() != "")

    df_filtrado = df[mask].copy()

    if len(df_filtrado) == 0:
        print(f"  Sin datos para nivel {nivel}")
        return None, None

    # Campos disponibles
    codigos = [c for c in campos_codigo if c in df_filtrado.columns]
    nombres = [c for c in campos_nombre if c in df_filtrado.columns]

    # Extraer combinaciones únicas por año
    cols = ["Año"] + codigos + nombres
    unicos = df_filtrado[cols].drop_duplicates()

    # Diccionario: primer y último año de cada combinación
    grupo = unicos.groupby(codigos + nombres).agg(
        primer_año=("Año", "min"),
        ultimo_año=("Año", "max"),
        años_presente=("Año", "nunique"),
    ).reset_index()

    grupo["nivel"] = nivel
    grupo["vigente_2026"] = grupo["ultimo_año"] == df["Año"].max()

    print(f"  {nivel}: {len(grupo):,} combinaciones únicas")
    print(f"    Vigentes en {df['Año'].max()}: {grupo['vigente_2026'].sum():,}")
    print(f"    Históricas (ya no aparecen): {(~grupo['vigente_2026']).sum():,}")

    # Log de cambios año a año
    cambios = []
    años = sorted(unicos["Año"].unique())

    for i in range(1, len(años)):
        año_ant = años[i - 1]
        año_act = años[i]

        codigos_ant = set(
            unicos[unicos["Año"] == año_ant][codigos].apply(tuple, axis=1)
        )
        codigos_act = set(
            unicos[unicos["Año"] == año_act][codigos].apply(tuple, axis=1)
        )

        agregados = codigos_act - codigos_ant
        eliminados = codigos_ant - codigos_act

        for cod in agregados:
            fila = {"año": año_act, "tipo_cambio": "AGREGADO", "nivel": nivel}
            for j, c in enumerate(codigos):
                fila[c] = cod[j]
            # Buscar nombre
            match = unicos[(unicos["Año"] == año_act)]
            for j, c in enumerate(codigos):
                match = match[match[c].astype(str) == str(cod[j])]
            if len(match) > 0 and nombres:
                for n in nombres:
                    fila[n] = match[n].values[0]
            cambios.append(fila)

        for cod in eliminados:
            fila = {"año": año_act, "tipo_cambio": "ELIMINADO", "nivel": nivel}
            for j, c in enumerate(codigos):
                fila[c] = cod[j]
            # Buscar nombre del año anterior
            match = unicos[(unicos["Año"] == año_ant)]
            for j, c in enumerate(codigos):
                match = match[match[c].astype(str) == str(cod[j])]
            if len(match) > 0 and nombres:
                for n in nombres:
                    fila[n] = match[n].values[0]
            cambios.append(fila)

        if agregados or eliminados:
            print(f"    {año_ant} → {año_act}: +{len(agregados)} agregados, -{len(eliminados)} eliminados")

    cambios_df = pd.DataFrame(cambios) if cambios else None

    return grupo, cambios_df


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
        exit()

    print(f"\n  Años disponibles: {sorted(ejec['Año'].unique())}")
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