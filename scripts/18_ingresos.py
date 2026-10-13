"""
18_ingresos.py — ¿Se proyecta bien lo que entra?
=================================================
Formaliza el hallazgo de ingresos: el agregado ingenuo (Σ subtítulos
01-15) parece subestimar sistemáticamente, pero mezcla pronósticos con
autorizaciones de financiamiento y partidas contables. Separados según
la lógica GFS (FMI), el pronóstico real (impuestos) casi no tiene sesgo.

Base: cruce_nacional (consolidado: el aporte fiscal 09 ya no está),
diciembre de cada año completo, pesos y dólares por separado (sin tipo
de cambio: cada moneda se analiza en la suya).

Error de proyección = (ejecutado − inicial) / inicial
  > 0  entró más de lo proyectado (subestimación)
  < 0  entró menos (sobreestimación)

Prueba del signo: bajo H0 (sin sesgo) cada año sub o sobreestima con
p = 0,5. Binomial exacta, dos colas, sin dependencias externas.

Clasificación: toda viene de dominio.py (CONCORDANCIA_GFS y
NATURALEZA_INGRESO). Este script no define reglas propias.

Salidas en DIRS["reportes"]:
  ingresos_detalle.csv       RESPALDO GENERAL: año × moneda × subtítulo
  ingresos_concordancia.csv  copia de la clasificación usada (dominio)
  ingresos_agregados.csv     ingenuo vs GFS vs pronóstico vs impuestos
  ingresos_prueba_signo.csv  prueba del signo por subtítulo y agregado
  ingresos_contribucion.csv  aporte EN PESOS de cada subtítulo al error
                             total (antes 09_contribucion_sesgo.py): un %
                             alto sobre una base chica pesa poco en pesos

Uso:
    python 18_ingresos.py
"""

from math import comb

import numpy as np
import pandas as pd

from config import DIRS
from dominio import (CONCORDANCIA_GFS, MES_A_NUM, NAT_CONTABLE, NAT_INTERNA,
                     NAT_PRONOSTICO, NATURALEZA_INGRESO, es_ingreso_gfs,
                     nombre_subtitulo, subtitulos_con_naturaleza)
from hallazgos import Registro
from utils import leer_csv_robusto

SALIDA = DIRS["reportes"]

# Clasificación desde dominio: una sola fuente para todo el pipeline
CONCORDANCIA = pd.DataFrame([
    {"subtitulo": sub, "nombre": nombre_subtitulo(sub),
     "categoria_gfs": CONCORDANCIA_GFS.get(sub, (None, False))[0],
     "gfs_verificado": CONCORDANCIA_GFS.get(sub, (None, False))[1],
     "naturaleza": nat, "naturaleza_verificada": ver, "fundamento": fund}
    for sub, (nat, ver, fund) in sorted(NATURALEZA_INGRESO.items())])

INGENUO = set(range(1, 16))
GFS_INGRESOS = {s for s in INGENUO if es_ingreso_gfs(s)}
PRONOSTICO = subtitulos_con_naturaleza(NAT_PRONOSTICO)
# Para la contribución: lo contable y lo interno no son flujos proyectables
SIN_CONTRIBUCION = subtitulos_con_naturaleza(NAT_CONTABLE) | \
    subtitulos_con_naturaleza(NAT_INTERNA)


def prueba_signo(errores: pd.Series) -> dict:
    """Binomial exacta, dos colas. Ignora errores exactamente 0."""
    e = errores.dropna()
    e = e[e != 0]
    n, k = len(e), int((e > 0).sum())
    if n == 0:
        return {"n": 0, "subestima": 0, "sobreestima": 0, "p_valor": np.nan,
                "error_medio_pct": np.nan, "error_mediano_pct": np.nan}
    cola = sum(comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n
    return {"n": n, "subestima": k, "sobreestima": n - k,
            "p_valor": min(1.0, 2 * cola),
            "error_medio_pct": 100 * e.mean(),
            "error_mediano_pct": 100 * e.median()}


def cargar() -> pd.DataFrame:
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_nacional.csv"))
    df = df.rename(columns={"Año": "anio", "Moneda": "moneda",
                            "Subtítulo": "subtitulo",
                            "Nombre Subtítulo": "nombre_subtitulo"})
    df["mes"] = df["Mes"].map(MES_A_NUM)
    df["subtitulo"] = df["subtitulo"].astype(int)
    df = df[(df.mes == 12) & (df.subtitulo < 21)]   # años completos, ingresos
    return (df.groupby(["anio", "moneda", "subtitulo", "nombre_subtitulo"],
                       as_index=False)
              [["ley_inicial", "ley_vigente", "ejecucion_acumulada"]].sum()
              .rename(columns={"ley_inicial": "inicial", "ley_vigente": "vigente",
                               "ejecucion_acumulada": "ejecutado"}))


def errores(df: pd.DataFrame) -> pd.DataFrame:
    with np.errstate(divide="ignore", invalid="ignore"):
        df["error_vs_inicial"] = np.where(
            df.inicial != 0, (df.ejecutado - df.inicial) / df.inicial.abs(), np.nan)
        df["error_vs_vigente"] = np.where(
            df.vigente != 0, (df.ejecutado - df.vigente) / df.vigente.abs(), np.nan)
    return df


if __name__ == "__main__":
    reg = Registro("ingresos", salida_dir=DIRS["reportes"])
    det = errores(cargar().merge(
        CONCORDANCIA[["subtitulo", "categoria_gfs", "naturaleza"]],
        on="subtitulo", how="left"))
    sin_concordancia = sorted(set(det[det.naturaleza.isna()].subtitulo))
    if sin_concordancia:
        reg.warn("ingresos", f"subtítulos sin concordancia: {sin_concordancia}")

    # Agregados por año: ingenuo (01-15) vs pronóstico (lógica GFS)
    filas = []
    for (anio, mon), g in det.groupby(["anio", "moneda"]):
        for nombre, subs in (("ingenuo_01_15", INGENUO),
                             ("ingreso_gfs", GFS_INGRESOS),
                             ("pronostico", PRONOSTICO),
                             ("impuestos_01", {1})):
            x = g[g.subtitulo.isin(subs)]
            ini, ejec = x.inicial.sum(), x.ejecutado.sum()
            filas.append({"anio": anio, "moneda": mon, "agregado": nombre,
                          "inicial": ini, "vigente": x.vigente.sum(),
                          "ejecutado": ejec,
                          "error_vs_inicial": (ejec - ini) / abs(ini) if ini else np.nan,
                          "peso_en_ingenuo": np.nan})
    agr = pd.DataFrame(filas)
    base = agr[agr.agregado == "ingenuo_01_15"].set_index(["anio", "moneda"]).inicial
    agr["peso_en_ingenuo"] = 100 * agr.inicial / agr.set_index(
        ["anio", "moneda"]).index.map(base)

    # Prueba del signo: por agregado y por subtítulo
    pruebas = []
    for (mon, a), g in agr.groupby(["moneda", "agregado"]):
        pruebas.append({"moneda": mon, "nivel": "agregado", "clave": a,
                        **prueba_signo(g.error_vs_inicial)})
    for (mon, s), g in det.groupby(["moneda", "subtitulo"]):
        pruebas.append({"moneda": mon, "nivel": "subtitulo", "clave": str(s),
                        "nombre": g.nombre_subtitulo.iloc[0],
                        "naturaleza": g.naturaleza.iloc[0],
                        **prueba_signo(g.error_vs_inicial)})
    prs = pd.DataFrame(pruebas)

    # Contribución en pesos al error total (antes 09_contribucion_sesgo)
    x = det[~det.subtitulo.isin(SIN_CONTRIBUCION)].copy()
    x["error"] = x.ejecutado - x.inicial
    con = []
    for mon, g in x.groupby("moneda"):
        tot_err, tot_ley = g.error.sum(), g.inicial.sum()
        for (sub, nat), h in g.groupby(["subtitulo", "naturaleza"]):
            con.append({"moneda": mon, "subtitulo": sub, "naturaleza": nat,
                        "nombre": h.nombre_subtitulo.iloc[0],
                        "inicial": h.inicial.sum(), "error": h.error.sum(),
                        "error_propio_pct": 100 * h.error.sum() / h.inicial.sum()
                        if h.inicial.sum() else np.nan,
                        "aporte_al_error_pct": 100 * h.error.sum() / tot_err,
                        "peso_en_ley_pct": 100 * h.inicial.sum() / tot_ley})
    con = pd.DataFrame(con).sort_values(["moneda", "aporte_al_error_pct"],
                                        ascending=[True, False])

    SALIDA.mkdir(parents=True, exist_ok=True)
    for nombre, df in (("detalle", det), ("concordancia", CONCORDANCIA),
                       ("agregados", agr), ("prueba_signo", prs),
                       ("contribucion", con)):
        df.to_csv(SALIDA / f"ingresos_{nombre}.csv", index=False, encoding="utf-8")

    anios = sorted(det.anio.unique())
    print("=" * 78)
    print("  INGRESOS: PROYECCIÓN (ley inicial) vs RECAUDACIÓN (ejecución dic.)")
    print("=" * 78)
    print(f"  Años completos: {anios[0]}-{anios[-1]} (n={len(anios)}) · "
          f"error = (ejecutado − inicial) / inicial")

    print(f"\n{'─' * 78}\n  Agregados en pesos: lo que cambia al separar\n")
    print(f"  {'Agregado':<18}{'n':>3}{'sub':>5}{'sobre':>6}{'p':>8}"
          f"{'error medio':>13}{'mediano':>10}{'peso':>8}")
    for a in ("ingenuo_01_15", "ingreso_gfs", "pronostico", "impuestos_01"):
        r = prs[(prs.moneda == "PESOS") & (prs.clave == a)].iloc[0]
        peso = agr[(agr.moneda == "PESOS") & (agr.agregado == a)].peso_en_ingenuo.mean()
        print(f"  {a:<18}{r.n:>3}{r.subestima:>5}{r.sobreestima:>6}"
              f"{r.p_valor:>8.4f}{r.error_medio_pct:>+12.1f}%"
              f"{r.error_mediano_pct:>+9.1f}%{peso:>7.0f}%")

    print(f"\n{'─' * 78}\n  Por subtítulo (pesos)\n")
    print(f"  {'Sub':>3} {'Nombre':<34}{'Naturaleza':<15}{'sub/sobre':>10}"
          f"{'p':>8}{'error medio':>13}")
    for r in prs[(prs.moneda == "PESOS") & (prs.nivel == "subtitulo")].itertuples():
        if r.n == 0:
            continue
        print(f"  {int(r.clave):>3} {str(r.nombre)[:33]:<34}{str(r.naturaleza):<15}"
              f"{r.subestima:>4}/{r.sobreestima:<5}{r.p_valor:>8.4f}"
              f"{r.error_medio_pct:>+12.1f}%")

    c = con[con.moneda == "PESOS"]
    print(f"\n{'─' * 78}\n  Contribución EN PESOS al error total, {anios[0]}-{anios[-1]}"
          f" (sin contable ni interna)\n")
    print(f"  {'Sub':>3} {'Nombre':<30}{'Naturaleza':<14}{'% de la ley':>12}"
          f"{'error propio':>14}{'aporte':>9}")
    for r in c.itertuples():
        print(f"  {r.subtitulo:>3} {str(r.nombre)[:29]:<30}{r.naturaleza:<14}"
              f"{r.peso_en_ley_pct:>11.1f}%{r.error_propio_pct:>+13.1f}%"
              f"{r.aporte_al_error_pct:>8.1f}%")
    por_nat = c.groupby("naturaleza")[["inicial", "error"]].sum()
    print("\n  Por naturaleza: " + " · ".join(
        f"{n.lower()} {100 * r.error / c.error.sum():.0f}% del error "
        f"({100 * r.error / r.inicial:+.1f}% propio)" for n, r in por_nat.iterrows()))

    ag = agr[agr.moneda == "PESOS"].pivot(index="anio", columns="agregado", values="inicial")
    peso_imp = 100 * (ag.impuestos_01 / ag.pronostico).mean()
    print(f"\n  Nota: impuestos es ~{peso_imp:.0f}% del agregado de pronóstico, así que")
    print("  su prueba del signo no es evidencia independiente de la de impuestos:")
    print("  muestra que, con el perímetro correcto, el sesgo agregado desaparece.")
    pend = CONCORDANCIA[~CONCORDANCIA.naturaleza_verificada]
    print(f"\n  Naturaleza por verificar (dominio.py): subs {list(pend.subtitulo)}")
    reg.emitir()