from pathlib import Path
from io import StringIO
import re
import pandas as pd
from config import DIRS
from dominio import NIVELES

BASE_RAW = DIRS["base"]
BASE_CLEAN = DIRS["clean"]
FAMILIAS = ["ley", "ejecucion"]

# Solo "programa" trae un campo de texto libre (Nombre Asignación) con riesgo
# real de delimitador incrustado, confirmado en ambas familias hoy.
NIVELES_CON_RIESGO_DELIMITADOR = {"programa"}
CAMPO_LIBRE_POR_NIVEL = {"programa": "Nombre Asignación"}


def detectar_encoding(ruta: Path) -> str | None:
    for enc in ["utf-8-sig", "latin-1"]:
        try:
            with open(ruta, encoding=enc) as f:
                f.readline()
            return enc
        except UnicodeDecodeError:
            continue
    return None


def normalizar_columna(col: str) -> str:
    c = re.sub(r"\s+", " ", col.strip())
    if re.search(r"^monto\s+ley\s+vigente\s+a\s+", c, re.IGNORECASE):
        return "Monto Ley Vigente"
    if re.search(r"^ejecuci[oó]n\s+de\s+", c, re.IGNORECASE):
        return "Ejecución del Mes"
    if re.search(r"^ejecuci[oó]n\s+a\s+", c, re.IGNORECASE):
        return "Ejecución Acumulada"
    return c

def normalizar_monto(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(
        serie.astype(str)
             .str.replace(".", "", regex=False)
             .str.replace(",", ".", regex=False)
             .replace({"nan": None, "": None}),
        errors="coerce"
    )

def reparar_linea(linea: str, n_esperado: int, n_campos_izq: int, n_campos_der: int = 2) -> str | None:
    campos = linea.rstrip("\r\n").split(";")
    if len(campos) == n_esperado:
        return linea.rstrip("\r\n") + "\n"
    if len(campos) < n_esperado:
        return None
    bloque_izq = campos[:n_campos_izq]
    bloque_der = campos[-n_campos_der:]
    bloque_medio = campos[n_campos_izq: len(campos) - n_campos_der]
    campo_fusionado = ";".join(bloque_medio).replace('"', '""')
    campos_reparados = bloque_izq + [f'"{campo_fusionado}"'] + bloque_der
    if len(campos_reparados) != n_esperado:
        return None
    return ";".join(campos_reparados) + "\n"


def leer_csv_robusto(ruta: Path, nivel: str) -> tuple[pd.DataFrame | None, dict, str | None]:
    log = {"archivo": str(ruta), "encoding": None, "lineas_reparadas": 0,
           "lineas_no_reparables": [], "error": None}

    encoding = detectar_encoding(ruta)
    if encoding is None:
        log["error"] = "No se pudo determinar encoding"
        return None, log, None
    log["encoding"] = encoding

    with open(ruta, encoding=encoding) as f:
        lineas = f.readlines()
    if not lineas:
        log["error"] = "Archivo vacío"
        return None, log, None

    header = lineas[0]
    columnas = [c.strip() for c in header.rstrip("\r\n").rstrip(";").split(";")]
    n_esperado = len(columnas)


    aplica_reparacion = nivel in NIVELES_CON_RIESGO_DELIMITADOR
    n_campos_izq = None
    if aplica_reparacion:
        campo_libre = CAMPO_LIBRE_POR_NIVEL[nivel]
        if campo_libre not in columnas:
            log["error"] = f"Columna '{campo_libre}' no encontrada en el header"
            return None, log, None
        n_campos_izq = columnas.index(campo_libre)

    lineas_reparadas = [header.rstrip("\r\n") + "\n"]
    for i, linea in enumerate(lineas[1:], start=2):
        if not linea.strip():
            continue
        campos_linea = linea.rstrip("\r\n").split(";")
        n_campos_linea = len(campos_linea)

        if n_campos_linea == n_esperado:
            lineas_reparadas.append(linea.rstrip("\r\n") + "\n")

        elif n_campos_linea == n_esperado + 1 and campos_linea[-1] == "":
            # Trailing delimiter huérfano: un ";" de más al final con nada después.
            # La fila es válida, solo se descarta el campo fantasma vacío.
            lineas_reparadas.append(";".join(campos_linea[:n_esperado]) + "\n")
            log["lineas_trailing_benigno"] = log.get("lineas_trailing_benigno", 0) + 1

        elif aplica_reparacion:
            reparada = reparar_linea(linea, n_esperado, n_campos_izq)
            if reparada is not None:
                lineas_reparadas.append(reparada)
                log["lineas_reparadas"] += 1
            else:
                log["lineas_no_reparables"].append(i)

        else:
            log["lineas_no_reparables"].append(i)


    contenido = "".join(lineas_reparadas)
    try:
        df = pd.read_csv(StringIO(contenido), sep=";", quotechar='"', dtype_backend="numpy_nullable")
    except Exception as e:
        log["error"] = f"Error tras procesamiento: {e}"
        return None, log, contenido

    df.columns = [normalizar_columna(c) for c in df.columns]
    columnas_monto = [c for c in df.columns if c.startswith(("Monto", "Ejecución", "Presupuesto"))]
    for col in columnas_monto:
        df[col] = normalizar_monto(df[col])
    return df, log, contenido


def guardar_csv_limpio(ruta_original: Path, contenido: str, familia: str, nivel: str):
    ruta_relativa = ruta_original.relative_to(BASE_RAW)
    ruta_destino = BASE_CLEAN / ruta_relativa
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_destino, "w", encoding="utf-8-sig") as f:
        f.write(contenido)


# =====================================================
# ORQUESTACIÓN — recorre familia × nivel, limpia y consolida
# =====================================================
resumen_global = []

for familia in FAMILIAS:
    for nivel in NIVELES:
        carpeta = BASE_RAW / familia
        archivos = sorted(carpeta.rglob(f"{nivel}.csv"))
        if not archivos:
            continue

        dataframes = []
        logs = []

        for archivo in archivos:
            df, log, contenido = leer_csv_robusto(archivo, nivel)
            año = archivo.parent.parent.name
            mes = archivo.parent.name

            if df is not None:
                df["año_proceso"] = año
                df["mes_proceso"] = mes
                dataframes.append(df)
                if contenido is not None:
                    guardar_csv_limpio(archivo, contenido, familia, nivel)

            logs.append(log)

        df_logs = pd.DataFrame(logs)
        n_error = df_logs["error"].notna().sum()
        n_reparadas = df_logs["lineas_reparadas"].sum()
        n_no_reparables = df_logs["lineas_no_reparables"].apply(len).sum()

        resumen_global.append({
            "familia": familia, "nivel": nivel,
            "archivos": len(archivos), "cargados": len(dataframes),
            "con_error": n_error, "lineas_reparadas": n_reparadas,
            "lineas_no_reparables": n_no_reparables,
        })

        if dataframes:
            df_consolidado = pd.concat(dataframes, ignore_index=True)
            ruta_parquet = BASE_CLEAN / f"{familia}_{nivel}_consolidado.parquet"
            df_consolidado.to_parquet(ruta_parquet, index=False)
            print(f"✅ {familia}/{nivel}: {df_consolidado.shape} -> {ruta_parquet.name}")
        else:
            print(f"⚠️ {familia}/{nivel}: ningún archivo se pudo cargar")

print("\n" + "=" * 70)
print(pd.DataFrame(resumen_global).to_string(index=False))

from pathlib import Path

carpeta = Path(r"D:\dipres-datos") / "ley"
tipos_por_archivo = {}

for archivo in sorted(carpeta.rglob("programa.csv")):
    df, log, _ = leer_csv_robusto(archivo, "programa")
    if df is not None and "Monto Ley Vigente" in df.columns:
        tipos_por_archivo[str(archivo)] = str(df["Monto Ley Vigente"].dtype)

from collections import Counter
print(Counter(tipos_por_archivo.values()))

# Mostrar ejemplos de cada tipo distinto
tipos_unicos = set(tipos_por_archivo.values())
for t in tipos_unicos:
    ejemplo = next(a for a, dt in tipos_por_archivo.items() if dt == t)
    print(f"\n{t}: {ejemplo}")