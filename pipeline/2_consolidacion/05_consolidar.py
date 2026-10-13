"""
05b_consolidar.py — Crudos → consolidados y cruces
===================================================
Reconstruye el paso que generaba processed/consolidado/ (corrida del
08-09-2026, cuyo código no quedó en el repo):

  ley_<nivel>.csv        todos los meses de raw/ley, montos numéricos
  ejecucion_<nivel>.csv  todos los meses de raw/ejecucion
  cruce_<nivel>.csv      ley + ejecución por claves de dominio.keys_de_nivel

Regla del cruce original (verificada: reproduce cruce_nacional y
cruce_partida idénticos): left join desde la ley, nombres de la ley,
ejecución faltante = 0, pct = round(acumulada / vigente × 100, 2) y 0 si
la vigente es 0. Ese left join descartaba en silencio la ejecución sin
línea de ley. Aquí el cruce es OUTER y la columna `origen` lo deja a la
vista: ambos | solo_ley | solo_ejecucion. Quitando solo_ejecucion se
obtiene el cruce original.

Lectura de crudos (correcciones respecto del 05):
  - encoding: se decodifica el archivo COMPLETO (utf-8-sig → cp1252 →
    latin-1), no solo la primera línea
  - montos: se leen como texto y se convierten con el formato chileno
    (1.234.567 / -307.991); nunca pasan por float antes de quitar puntos
  - delimitador final sobrante (ley 2017): se descarta el campo vacío
  - ";" dentro de un nombre: los campos sobrantes se asignan a la columna
    "Nombre ..." donde la fila resultante queda válida (códigos numéricos
    o vacíos, montos con formato de monto). Si no hay exactamente una
    asignación válida, la fila NO se carga y queda registrada
  - programa/ejecución: Sub-Asignación se colapsa (suma) antes del cruce;
    ejecucion_programa.csv la conserva
  - ley: línea repetida (mismas claves y nombres) donde una copia trae
    EXACTAMENTE el doble de la otra → se descarta la doble y se registra
    (error de la fuente visto en ley 2020-01 y en 2017; ver _log). Claves
    repetidas con nombres distintos son líneas reales y se mantienen

Se procesa mes a mes y se escribe en modo append: memoria acotada aunque
ejecucion_programa pese ~900 MB.

Uso:
    python pipeline/2_consolidacion/05_consolidar.py --salida D:\\dipres-datos\\processed\\consolidado_nuevo
    python pipeline/2_consolidacion/05_consolidar.py --salida D:\\dipres-datos\\processed\\consolidado_nuevo --niveles nacional partida
    python pipeline/2_consolidacion/05_consolidar.py --salida D:\\dipres-datos\\processed\\consolidado_nuevo --verificar D:\\dipres-datos\\processed\\consolidado

--verificar compara contra los consolidados de referencia: familias
idénticas, y cruce sin solo_ejecucion idéntico al de referencia.
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from dipres.config import DIRS
from dipres.dominio import CARPETA_A_MES, NIVELES, keys_de_nivel
from dipres.hallazgos import Registro

FAMILIAS = ("ley", "ejecucion")
ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")   # latin-1 nunca falla: último
SEP = ";"

# Columnas de monto: el nombre trae el mes embebido
MONTOS = [
    (re.compile(r"^monto\s+ley\s+inicial", re.I), "ley_inicial"),
    (re.compile(r"^monto\s+ley\s+vigente", re.I), "ley_vigente"),
    (re.compile(r"^ejecuci[oó]n\s+de\s", re.I), "ejecucion_mes"),
    (re.compile(r"^ejecuci[oó]n\s+a\s", re.I), "ejecucion_acumulada"),
]
MONTO_FAMILIA = {"ley": ["ley_inicial", "ley_vigente"],
                 "ejecucion": ["ejecucion_mes", "ejecucion_acumulada"]}
CODIGOS = ["Año", "Partida", "Capítulo", "Programa", "Subtítulo", "Item",
           "Asignación", "Sub-Asignación"]
# Variantes de encabezado vistas en la fuente
ALIAS = {"ítem": "Item", "item": "Item", "nombre ítem": "Nombre Item",
         "nombre item": "Nombre Item", "capitulo": "Capítulo",
         "subtitulo": "Subtítulo", "asignacion": "Asignación",
         "ano": "Año", "nombre capitulo": "Nombre Capítulo",
         "nombre subtitulo": "Nombre Subtítulo",
         "nombre asignacion": "Nombre Asignación"}

RE_MONTO_TXT = re.compile(r"^-?\d{1,3}(?:\.\d{3})*(?:,\d+)?$|^-?\d+(?:,\d+)?$")
RE_CODIGO_TXT = re.compile(r"^\d*$")


# =====================================================
# Lectura de un crudo
# =====================================================
def decodificar(ruta: Path) -> tuple[str, str]:
    datos = ruta.read_bytes()
    for enc in ENCODINGS:
        try:
            return datos.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError("sin encoding válido")   # inalcanzable con latin-1


def normalizar_columna(col: str) -> str:
    c = re.sub(r"\s+", " ", col.strip())
    for patron, nombre in MONTOS:
        if patron.search(c):
            return nombre
    return ALIAS.get(c.lower(), c)


def _fila_valida(campos: list[str], tipos: list[str]) -> bool:
    for v, t in zip(campos, tipos):
        v = v.strip()
        if t == "monto" and v and not RE_MONTO_TXT.match(v):
            return False
        if t == "codigo" and not RE_CODIGO_TXT.match(v):
            return False
    return True


def reparar(campos: list[str], columnas: list[str], tipos: list[str]):
    """
    Devuelve (campos reparados, columna que absorbió el texto) o (None, motivo).
    Prueba poner los campos sobrantes en cada columna "Nombre ...".
    """
    n, extra = len(columnas), len(campos) - len(columnas)
    if extra == 1 and campos[-1] == "":
        return campos[:n], "delimitador final"
    if extra <= 0:
        return None, f"{len(campos)} campos, se esperaban {n}"
    validas = []
    for i, col in enumerate(columnas):
        if not col.startswith("Nombre"):
            continue
        cand = campos[:i] + [SEP.join(campos[i:i + extra + 1])] + campos[i + extra + 1:]
        if _fila_valida(cand, tipos):
            validas.append((cand, col))
    if len(validas) == 1:
        return validas[0]
    return None, (f"{extra} campos de más; {len(validas)} reparaciones "
                  f"posibles (se exige una)")


def leer_crudo(ruta: Path, familia: str, log: dict,
               anio: str | None = None, mes: str | None = None) -> pd.DataFrame | None:
    try:
        texto, enc = decodificar(ruta)
    except Exception as e:
        log["error"] = str(e)
        return None
    lineas = texto.splitlines()
    if not lineas:
        log["error"] = "archivo vacío"
        return None
    columnas = [normalizar_columna(c) for c in lineas[0].rstrip(SEP).split(SEP)]
    tipos = ["monto" if c in MONTO_FAMILIA[familia] else
             "codigo" if c in CODIGOS else "texto" for c in columnas]
    log.update(encoding=enc, filas=0, delimitador_final=0, reparadas=0,
               no_reparables=[])

    filas = []
    for k, linea in enumerate(lineas[1:], start=2):
        if not linea.strip():
            continue
        campos = linea.split(SEP)
        if len(campos) != len(columnas):
            campos, motivo = reparar(campos, columnas, tipos)
            if campos is None:
                log["no_reparables"].append({"linea": k, "motivo": motivo})
                continue
            if motivo == "delimitador final":
                log["delimitador_final"] += 1
            else:
                log["reparadas"] += 1
        filas.append(campos)
    log["filas"] = len(filas)

    df = pd.DataFrame(filas, columns=columnas, dtype=str)
    for c in columnas:
        if c in MONTO_FAMILIA[familia]:
            df[c] = pd.to_numeric(df[c].str.strip().str.replace(".", "", regex=False)
                                  .str.replace(",", ".", regex=False)
                                  .replace("", np.nan), errors="coerce")
        elif c in CODIGOS:
            df[c] = pd.to_numeric(df[c].str.strip().replace("", np.nan), errors="coerce")
        else:
            df[c] = df[c].str.strip().replace("", np.nan)
    # Año y Mes salen de la CARPETA (raw/<familia>/<año>/<mes>/), no de la
    # columna: la fuente trae "junio" en minúscula en ley 2017-2023 y eso
    # rompía el cruce. Se registra cuando la columna no coincide.
    if anio is not None and mes is not None and "Mes" in df and "Año" in df:
        mes_ok = CARPETA_A_MES[mes]
        col = df["Mes"].dropna().unique().tolist()
        if col != [mes_ok]:
            log["mes_columna"] = col
        if df["Año"].dropna().unique().tolist() != [int(anio)]:
            log["anio_columna"] = df["Año"].dropna().unique().tolist()
        df["Año"], df["Mes"] = int(anio), mes_ok
    if "Moneda" in df:
        df["Moneda"] = df["Moneda"].str.upper()
    malos = sum(df[c].isna().sum() for c in MONTO_FAMILIA[familia] if c in df)
    if malos:
        log["montos_vacios"] = int(malos)
    return df


def quitar_duplicado_doble(df: pd.DataFrame, nivel: str, log: dict) -> pd.DataFrame:
    """Ley: de un par de líneas idénticas en claves y nombres donde una
    trae el doble de ley_inicial (y de ley_vigente) que la otra, se
    descarta la doble. Tolerancia: 1 (miles)."""
    grupo = keys_de_nivel(nivel) + [c for c in df.columns if c.startswith("Nombre")]
    grupo = [c for c in grupo if c in df.columns]
    g = df.groupby(grupo, dropna=False, sort=False)
    n = g["ley_inicial"].transform("size")
    if not (n == 2).any():
        return df
    cond = n == 2
    for col in MONTO_FAMILIA["ley"]:
        mn, mx = g[col].transform("min"), g[col].transform("max")
        cond &= ((mx - 2 * mn).abs() <= 1) & (df[col] == mx)
    ini_min = g["ley_inicial"].transform("min")
    cond &= ini_min > 0          # el doble se reconoce en un monto positivo
    if cond.any():
        caidas = df.loc[cond, grupo + ["ley_inicial"]]
        log["duplicado_doble"] = caidas.astype(str).to_dict("records")
    return df[~cond]


# =====================================================
# Cruce
# =====================================================
def colapsar_subasignacion(e: pd.DataFrame, claves: list[str]) -> pd.DataFrame:
    if "Sub-Asignación" not in e.columns:
        return e
    nombres = [c for c in e.columns if c.startswith("Nombre")
               and c != "Nombre Sub-Asignación"]
    agg = {**{c: "sum" for c in MONTO_FAMILIA["ejecucion"]},
           **{c: "first" for c in nombres}}
    return e.groupby(claves, dropna=False, sort=False, as_index=False).agg(agg)


def cruzar(ley: pd.DataFrame, ejec: pd.DataFrame, nivel: str) -> pd.DataFrame:
    claves = keys_de_nivel(nivel)
    ejec = colapsar_subasignacion(ejec, claves)
    nombres = [c for c in ley.columns if c.startswith("Nombre")]
    nombres += [c for c in ejec.columns if c.startswith("Nombre")
                and c not in nombres and c != "Nombre Sub-Asignación"]
    m = ley.merge(ejec, on=claves, how="outer", suffixes=("", "_ej"),
                  indicator=True, sort=False)
    # Nombres de la ley; en filas sin ley, los de la ejecución
    for c in nombres:
        if f"{c}_ej" in m.columns:
            m[c] = m[c].fillna(m[f"{c}_ej"])
        elif c not in m.columns:
            m[c] = np.nan
    montos = MONTO_FAMILIA["ley"] + MONTO_FAMILIA["ejecucion"]
    m[montos] = m[montos].fillna(0.0)
    m["pct_ejecucion"] = np.where(
        m.ley_vigente != 0,
        (m.ejecucion_acumulada / m.ley_vigente.where(m.ley_vigente != 0) * 100).round(2),
        0.0)
    m["origen"] = m["_merge"].map({"both": "ambos", "left_only": "solo_ley",
                                   "right_only": "solo_ejecucion"}).astype(str)
    return m[claves + nombres + montos + ["pct_ejecucion", "origen"]]


# =====================================================
# Orquestación: mes a mes, en append
# =====================================================
def meses_disponibles(nivel: str) -> list[tuple[str, str]]:
    meses = set()
    for fam in FAMILIAS:
        for f in DIRS[fam].glob(f"*/*/{nivel}.csv"):
            meses.add((f.parent.parent.name, f.parent.name))
    return sorted(meses)


def anexar(df: pd.DataFrame, ruta: Path, primero: bool) -> None:
    df.to_csv(ruta, mode="w" if primero else "a", header=primero,
              index=False, encoding="utf-8-sig" if primero else "utf-8")


def consolidar_nivel(nivel: str, salida: Path, reg: Registro) -> dict:
    rutas = {f: salida / f"{f}_{nivel}.csv" for f in (*FAMILIAS, "cruce")}
    primero = {k: True for k in rutas}
    logs, resumen = [], {"meses": 0, "faltantes": []}
    origen_tot = {"ambos": 0, "solo_ley": 0, "solo_ejecucion": 0}

    for anio, mes in meses_disponibles(nivel):
        dfs = {}
        for fam in FAMILIAS:
            ruta = DIRS[fam] / anio / mes / f"{nivel}.csv"
            if not ruta.exists():
                resumen["faltantes"].append(f"{fam}/{anio}/{mes}")
                continue
            log = {"archivo": f"{fam}/{anio}/{mes}/{nivel}.csv"}
            df = leer_crudo(ruta, fam, log, anio, mes)
            if df is not None and fam == "ley":
                df = quitar_duplicado_doble(df, nivel, log)
            logs.append(log)
            if df is not None:
                anexar(df, rutas[fam], primero[fam])
                primero[fam] = False
                dfs[fam] = df
        if len(dfs) == 2:
            c = cruzar(dfs["ley"], dfs["ejecucion"], nivel)
        elif dfs:
            # Mes con una sola familia: todo queda solo_ley o solo_ejecucion
            fam = next(iter(dfs))
            otra = "ejecucion" if fam == "ley" else "ley"
            vacia = pd.DataFrame(columns=keys_de_nivel(nivel) + MONTO_FAMILIA[otra])
            vacia = vacia.astype({c: float for c in vacia.columns
                                  if c not in ("Mes", "Moneda")})
            c = cruzar(dfs.get("ley", vacia), dfs.get("ejecucion", vacia), nivel)
        else:
            continue
        for k, v in c.origen.value_counts().items():
            origen_tot[k] += int(v)
        anexar(c, rutas["cruce"], primero["cruce"])
        primero["cruce"] = False
        resumen["meses"] += 1

    resumen["origen"] = origen_tot
    resumen["reparadas"] = sum(l.get("reparadas", 0) for l in logs)
    resumen["delimitador_final"] = sum(l.get("delimitador_final", 0) for l in logs)
    resumen["no_reparables"] = sum(len(l.get("no_reparables", [])) for l in logs)
    resumen["errores"] = [l for l in logs if l.get("error")]
    resumen["duplicado_doble"] = sum(len(l.get("duplicado_doble", [])) for l in logs)
    resumen["mes_corregido"] = [f"{l['archivo']}: {l['mes_columna']}"
                                for l in logs if "mes_columna" in l]
    resumen["anio_corregido"] = [f"{l['archivo']}: {l['anio_columna']}"
                                 for l in logs if "anio_columna" in l]
    (salida / f"_log_consolidar_{nivel}.json").write_text(
        json.dumps(logs, ensure_ascii=False, indent=1), encoding="utf-8")

    if resumen["no_reparables"]:
        reg.warn("consolidar", f"{nivel}: {resumen['no_reparables']} filas no "
                 f"reparables (ver _log_consolidar_{nivel}.json)",
                 patron="fila cruda no reparable")
    if resumen["duplicado_doble"]:
        reg.warn("consolidar", f"{nivel}: {resumen['duplicado_doble']} líneas de ley "
                 f"duplicadas al doble descartadas (ver _log_consolidar_{nivel}.json)",
                 patron="línea de ley duplicada al doble")
    if origen_tot["solo_ejecucion"]:
        reg.warn("consolidar", f"{nivel}: {origen_tot['solo_ejecucion']} filas de "
                 f"ejecución sin línea de ley", patron="ejecución sin ley")
    for f in resumen["faltantes"]:
        reg.warn("consolidar", f"{nivel}: falta {f}", patron="mes faltante")
    return resumen


# =====================================================
# Verificación contra consolidados de referencia
# =====================================================
def _comparable(df: pd.DataFrame, claves: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if c in CODIGOS or c in MONTO_FAMILIA["ley"] + MONTO_FAMILIA["ejecucion"] \
                + ["pct_ejecucion"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    orden = [c for c in claves + [c for c in df.columns if c not in claves]]
    return (df[orden].sort_values(orden, na_position="first", kind="stable")
              .reset_index(drop=True))


def verificar(nivel: str, salida: Path, referencia: Path) -> None:
    claves = keys_de_nivel(nivel)
    for f in (*FAMILIAS, "cruce"):
        nuevo_p, ref_p = salida / f"{f}_{nivel}.csv", referencia / f"{f}_{nivel}.csv"
        if not ref_p.exists():
            print(f"  · {f}_{nivel}: sin referencia")
            continue
        nuevo = pd.read_csv(nuevo_p, low_memory=False)
        ref = pd.read_csv(ref_p, low_memory=False)
        extra = ""
        k = claves + (["Sub-Asignación"] if "Sub-Asignación" in ref.columns else [])
        # Meses publicados después de la referencia no son una diferencia:
        # se informan aparte y se compara solo el período común
        periodos_ref = set(zip(ref["Año"], ref["Mes"]))
        en_comun = [p in periodos_ref for p in zip(nuevo["Año"], nuevo["Mes"])]
        nuevos = sorted({f"{int(a_)}-{m_}" for (a_, m_), ok in
                         zip(zip(nuevo["Año"], nuevo["Mes"]), en_comun) if not ok})
        if nuevos:
            extra += f" · meses fuera de la referencia (no comparados): {', '.join(nuevos)}"
        nuevo = nuevo[en_comun]
        if f == "cruce":
            n_sol = int((nuevo.origen == "solo_ejecucion").sum())
            nuevo = nuevo[nuevo.origen != "solo_ejecucion"].drop(columns="origen")
            extra = (f" (+{n_sol:,} filas solo_ejecucion que el original "
                     f"descartaba)") + extra
        a, b = _comparable(nuevo, k), _comparable(ref[nuevo.columns.intersection(ref.columns)], k)
        a = a[b.columns]
        if len(a) != len(b):
            print(f"  ✗ {f}_{nivel}: {len(a):,} filas vs {len(b):,} en la referencia{extra}")
            d = pd.concat([a.groupby(["Año", "Mes"]).size().rename("nuevo"),
                           b.groupby(["Año", "Mes"]).size().rename("ref")],
                          axis=1).fillna(0).astype(int)
            d = d[d.nuevo != d.ref]
            print("      Año/Mes que difieren: " + ", ".join(
                f"{int(a_)}-{m_} ({r.nuevo} vs {r.ref})" for (a_, m_), r in d.head(8).iterrows())
                + (" …" if len(d) > 8 else ""))
            continue
        try:
            pd.testing.assert_frame_equal(a, b, check_dtype=False, check_exact=False,
                                          atol=0.5)
            print(f"  ✓ {f}_{nivel}: idéntico ({len(a):,} filas){extra}")
        except AssertionError as e:
            print(f"  ✗ {f}_{nivel}: mismas filas, valores distintos — "
                  f"{str(e).splitlines()[0][:150]}")


# =====================================================
# Main
# =====================================================
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", type=Path, required=True,
                    help="carpeta de salida (usar una nueva para la verificación)")
    ap.add_argument("--niveles", nargs="*", default=NIVELES)
    ap.add_argument("--verificar", type=Path,
                    help="carpeta de referencia (consolidados del 08-09)")
    args = ap.parse_args()

    if args.verificar and args.salida.resolve() == args.verificar.resolve():
        raise SystemExit("--salida y --verificar no pueden ser la misma carpeta")
    args.salida.mkdir(parents=True, exist_ok=True)
    reg = Registro("consolidar", salida_dir=DIRS["reportes"])

    print("=" * 78)
    print("  CONSOLIDAR CRUDOS → ley / ejecucion / cruce")
    print("=" * 78)
    for nivel in args.niveles:
        r = consolidar_nivel(nivel, args.salida, reg)
        o = r["origen"]
        print(f"\n  {nivel}: {r['meses']} meses · cruce: {o['ambos']:,} ambos, "
              f"{o['solo_ley']:,} solo ley, {o['solo_ejecucion']:,} solo ejecución")
        print(f"    reparadas {r['reparadas']:,} · delimitador final "
              f"{r['delimitador_final']:,} · no reparables {r['no_reparables']:,}"
              + (f" · faltan {len(r['faltantes'])} archivos" if r["faltantes"] else ""))
        if r["mes_corregido"]:
            print(f"    Mes tomado de la carpeta en {len(r['mes_corregido'])} archivos "
                  f"(la columna decía otra cosa), p. ej. {r['mes_corregido'][0]}")
        if r["anio_corregido"]:
            print(f"    ⚠ Año de la columna ≠ carpeta en {len(r['anio_corregido'])} "
                  f"archivos, p. ej. {r['anio_corregido'][0]}")
        if args.verificar:
            verificar(nivel, args.salida, args.verificar)
    reg.emitir()