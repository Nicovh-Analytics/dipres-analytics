"""
17_ejecucion.py — Ley vigente → ejecución
==========================================
¿Se gasta lo que se autoriza? ¿Y cuándo?

Base: cruce_partida, todos los meses. Criterio: la ley vigente al cierre
es el máximo autorizado; la ejecución acumulada a diciembre es lo gastado.

Tres señales por año × moneda × partida × subtítulo (gastos):
  subejecución     ejecutado < vigente por sobre el umbral
  sobreejecución   ejecutado > vigente > 0 (solo legal si es excedible)
  sin ley          ejecutado > 0 con vigente 0: no hay línea que exceder
                   (filas origen=solo_ejecucion del cruce); va aparte
                   para no inflar la sobreejecución
  concentración    % del gasto del año ejecutado en diciembre

Más un control de calidad del dato: ejecucion_acumulada debería ser la
suma de ejecucion_mes. Donde no lo es, se registra (no se corrige).

Salidas en DIRS["reportes"]:
  ejecucion_detalle.csv      RESPALDO GENERAL: cada año × moneda × partida
                             × subtítulo, ingresos y gastos, sin agregar
  ejecucion_resumen.csv      por año: no ejecutado y sobreejecutado por
                             separado (bruto) y neto
  ejecucion_recurrencia.csv  señales que se repiten en varios años
  ejecucion_calidad.csv      líneas donde acumulada ≠ Σ mensual

Uso:
    python 17_ejecucion.py
    python 17_ejecucion.py --umbral-pct 10 --umbral-conc 25
"""

import argparse

import numpy as np
import pandas as pd

from dipres.config import DIRS
from dipres.dominio import MES_A_NUM
from dipres.hallazgos import Registro
from dipres.utils import leer_csv_robusto

SALIDA = DIRS["reportes"]
CLAVE = ["anio", "moneda", "partida", "subtitulo"]

UMBRAL_PCT = 10.0       # subejecución: ejecuta menos del 90% de lo vigente
UMBRAL_CONC = 25.0      # concentración: ≥25% del año en diciembre (3x lo parejo)
UMBRAL_MONTO = {"PESOS": 1_000_000, "DOLARES": 1_000}   # miles
TOL_SOBRE = {"PESOS": 1_000, "DOLARES": 1}              # ruido de redondeo

# Igual que en 16_modificaciones.py
TIPO_POR_SUB = {15: "caja", 35: "caja", 11: "financiero", 30: "financiero",
                34: "financiero", 9: "aporte", 27: "aporte", 28: "aporte"}
DOBLE_CONTEO = {"INGRESOS": {9}, "GASTOS": {27, 28}}


# =====================================================
# Carga
# =====================================================
def cargar() -> pd.DataFrame:
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_partida.csv"))
    df = df.rename(columns={"Año": "anio", "Moneda": "moneda",
                            "Partida": "partida", "Subtítulo": "subtitulo",
                            "Nombre Partida": "nombre_partida",
                            "Nombre Subtítulo": "nombre_subtitulo"})
    df["mes"] = df["Mes"].map(MES_A_NUM)
    df["subtitulo"] = df["subtitulo"].astype(int)
    num = ["ley_vigente", "ejecucion_mes", "ejecucion_acumulada"]
    nombres = (df.groupby(CLAVE)[["nombre_partida", "nombre_subtitulo"]]
                 .first().reset_index())
    m = (df.groupby(CLAVE + ["mes"], as_index=False)[num].sum()
           .merge(nombres, on=CLAVE))
    return m.sort_values(CLAVE + ["mes"]).reset_index(drop=True)


# =====================================================
# Calidad del dato
# =====================================================
def calidad(m: pd.DataFrame) -> pd.DataFrame:
    """
    ejecucion_acumulada del último mes vs Σ ejecucion_mes publicados.
    Una diferencia puede venir de meses no publicados para esa línea
    (aparece a mitad de año) o de un registro inconsistente en la fuente.
    """
    g = m.groupby(CLAVE)
    c = pd.DataFrame({
        "meses_publicados": g.mes.nunique(),
        "primer_mes": g.mes.min(), "ultimo_mes": g.mes.max(),
        "suma_mensual": g.ejecucion_mes.sum(),
        "acumulada_final": g.ejecucion_acumulada.last(),
    }).reset_index()
    c["diferencia"] = c.acumulada_final - c.suma_mensual
    tol = c.moneda.map(TOL_SOBRE)
    c = c[c.diferencia.abs() > tol].copy()
    c["posible_causa"] = np.where(
        c.primer_mes > 1, "línea publicada desde mitad de año",
        np.where(c.meses_publicados < c.ultimo_mes, "meses faltantes",
                 "inconsistencia en la fuente"))
    return c


# =====================================================
# 1. Respaldo general (anual)
# =====================================================
def detalle(m: pd.DataFrame, umbral_pct: float, umbral_conc: float) -> pd.DataFrame:
    ult = m.groupby("anio").mes.transform("max")
    cierre = m[m.mes == ult].copy()          # mes de corte del año
    cierre["anio_completo"] = cierre.mes == 12

    # Gasto de diciembre = acumulada dic − acumulada nov. Si la línea no
    # tiene noviembre, se usa el ejecucion_mes publicado.
    piv = m.pivot_table(index=CLAVE, columns="mes",
                        values="ejecucion_acumulada", aggfunc="sum")
    dic = piv.get(12)
    nov = piv.get(11)
    ejec_dic = (dic - nov) if dic is not None and nov is not None else None
    if ejec_dic is not None:
        pub = m[m.mes == 12].set_index(CLAVE).ejecucion_mes
        ejec_dic = ejec_dic.fillna(pub)
    d = cierre.set_index(CLAVE)
    d["ejec_dic"] = ejec_dic if ejec_dic is not None else np.nan
    d = d.reset_index()

    d = d.rename(columns={"ley_vigente": "vigente",
                          "ejecucion_acumulada": "ejecutado",
                          "mes": "mes_corte"})
    d = d.drop(columns="ejecucion_mes")
    d["seccion"] = np.where(d.subtitulo < 21, "INGRESOS", "GASTOS")
    d["tipo"] = d.subtitulo.map(TIPO_POR_SUB).fillna("operativo")
    d["doble_conteo"] = [s in DOBLE_CONTEO[sec]
                         for s, sec in zip(d.subtitulo, d.seccion)]
    d["saldo"] = d.vigente - d.ejecutado      # + no ejecutado / − sobre
    with np.errstate(divide="ignore", invalid="ignore"):
        d["pct_ejecucion"] = np.where(d.vigente != 0,
                                      100 * d.ejecutado / d.vigente, np.nan)
        d["pct_en_diciembre"] = np.where(d.ejecutado > 0,
                                         100 * d.ejec_dic / d.ejecutado, np.nan)

    monto = d.moneda.map(UMBRAL_MONTO)
    gasto = (d.seccion == "GASTOS") & d.anio_completo
    d["subejecucion"] = gasto & (d.saldo >= monto) & (
        d.pct_ejecucion <= 100 - umbral_pct)
    tol = d.moneda.map(TOL_SOBRE)
    d["sin_ley"] = gasto & (d.vigente == 0) & (d.ejecutado > tol)
    d["sobreejecucion"] = gasto & (d.vigente != 0) & (-d.saldo > tol)
    d["concentracion_dic"] = gasto & (d.ejec_dic >= monto) & (
        d.pct_en_diciembre >= umbral_conc)
    return d


# =====================================================
# 2. Resumen
# =====================================================
def resumen(d: pd.DataFrame) -> pd.DataFrame:
    x = d[~d.doble_conteo].copy()
    # Lo ejecutado sin línea de ley no es sobreejecución: se separa
    sin = (x.vigente == 0) & (x.ejecutado > 0)
    x["ejec_sin_ley"] = np.where(sin, x.ejecutado, 0.0)
    x.loc[sin, "saldo"] = 0.0
    g = x.groupby(["anio", "anio_completo", "moneda", "seccion"])
    r = g.agg(vigente=("vigente", "sum"), ejecutado=("ejecutado", "sum"),
              ejec_dic=("ejec_dic", "sum"),
              no_ejecutado=("saldo", lambda s: s[s > 0].sum()),
              sobreejecutado=("saldo", lambda s: -s[s < 0].sum()),
              ejecutado_sin_ley=("ejec_sin_ley", "sum"),
              lineas_sub=("subejecucion", "sum"),
              lineas_sobre=("sobreejecucion", "sum"),
              lineas_sin_ley=("sin_ley", "sum"),
              lineas_conc=("concentracion_dic", "sum")).reset_index()
    r["pct_ejecucion"] = 100 * r.ejecutado / r.vigente
    r["pct_en_diciembre"] = 100 * r.ejec_dic / r.ejecutado
    # El neto (vigente − ejecutado) esconde las sobreejecuciones
    r["neto"] = r.no_ejecutado - r.sobreejecutado
    return r


# =====================================================
# 3. Recurrencia
# =====================================================
def recurrencia(d: pd.DataFrame) -> pd.DataFrame:
    x = d[d.anio_completo & (d.seccion == "GASTOS")]
    n = x.anio.nunique()
    filas = []
    for senal in ("subejecucion", "sobreejecucion", "concentracion_dic"):
        s = x[x[senal]]
        if s.empty:
            continue
        r = (s.groupby(["moneda", "partida", "subtitulo", "tipo"])
               .agg(nombre_partida=("nombre_partida", "first"),
                    nombre_subtitulo=("nombre_subtitulo", "first"),
                    anios_senal=("anio", "nunique"),
                    anios=("anio", lambda a: ",".join(map(str, sorted(a)))),
                    saldo_total=("saldo", "sum"),
                    pct_ejec_mediana=("pct_ejecucion", "median"),
                    pct_dic_mediana=("pct_en_diciembre", "median"))
               .reset_index())
        r.insert(0, "senal", senal)
        r["de_anios"] = n
        filas.append(r)
    out = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
    return out.sort_values(["senal", "anios_senal"], ascending=[True, False])


# =====================================================
# Main
# =====================================================
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral-pct", type=float, default=UMBRAL_PCT)
    ap.add_argument("--umbral-conc", type=float, default=UMBRAL_CONC)
    args = ap.parse_args()

    reg = Registro("ejecucion", salida_dir=DIRS["reportes"])
    m = cargar()
    cal = calidad(m)
    det = detalle(m, args.umbral_pct, args.umbral_conc)
    res = resumen(det)
    rec = recurrencia(det)

    SALIDA.mkdir(parents=True, exist_ok=True)
    for nombre, df in (("detalle", det), ("resumen", res),
                       ("recurrencia", rec), ("calidad", cal)):
        df.to_csv(SALIDA / f"ejecucion_{nombre}.csv", index=False,
                  encoding="utf-8")

    print("=" * 78)
    print("  LEY VIGENTE → EJECUCIÓN")
    print("=" * 78)
    print(f"  Subejecución: ejecuta ≤ {100 - args.umbral_pct:g}% y saldo ≥ umbral · "
          f"concentración: ≥ {args.umbral_conc:g}% del año en diciembre")

    print(f"\n{'─' * 78}\n  Calidad: ejecucion_acumulada vs Σ ejecucion_mes\n")
    print(f"  {len(cal):,} líneas no cuadran (de {m.groupby(CLAVE).ngroups:,})")
    for causa, n in cal.posible_causa.value_counts().items():
        print(f"    {n:>6,}  {causa}")
    if (cal.posible_causa == "inconsistencia en la fuente").any():
        reg.warn("calidad", f"{(cal.posible_causa == 'inconsistencia en la fuente').sum()} "
                 f"líneas con acumulada ≠ Σ mensual sin meses faltantes",
                 patron="ejecución acumulada inconsistente")

    print(f"\n{'─' * 78}\n  Gastos en pesos (millones), sin aporte fiscal 27/28\n")
    print(f"  {'Año':<6}{'Vigente':>12}{'Ejecutado':>12}{'%':>7}{'No ejec.':>12}"
          f"{'Sobre':>11}{'Sin ley':>9}{'% dic':>7}{'Sub':>6}{'Sobre':>6}{'Conc':>6}")
    for r in res[(res.moneda == "PESOS") & (res.seccion == "GASTOS")].itertuples():
        print(f"  {r.anio:<6}{r.vigente / 1e3:>12,.0f}{r.ejecutado / 1e3:>12,.0f}"
              f"{r.pct_ejecucion:>7.1f}{r.no_ejecutado / 1e3:>12,.0f}"
              f"{r.sobreejecutado / 1e3:>11,.0f}{r.ejecutado_sin_ley / 1e3:>9,.0f}"
              f"{r.pct_en_diciembre:>7.1f}"
              f"{r.lineas_sub:>6}{r.lineas_sobre:>6}{r.lineas_conc:>6}"
              + ("" if r.anio_completo else "  * incompleto"))

    titulos = {"subejecucion": "Subejecución", "sobreejecucion": "Sobreejecución",
               "concentracion_dic": "Concentración en diciembre"}
    for senal, titulo in titulos.items():
        t = rec[(rec.senal == senal) & (rec.moneda == "PESOS")
                & (rec.tipo == "operativo") & (rec.anios_senal >= 5)]
        print(f"\n{'─' * 78}\n  {titulo} (gastos operativos, pesos) en ≥ 5 años\n")
        for r in t.head(15).itertuples():
            extra = (f"mediana {r.pct_dic_mediana:5.1f}% en dic"
                     if senal == "concentracion_dic"
                     else f"mediana {r.pct_ejec_mediana:5.1f}% ejec · "
                          f"Σ saldo {r.saldo_total / 1e3:>9,.0f}")
            print(f"  {r.anios_senal}/{r.de_anios}  {int(r.partida):02d} "
                  f"{str(r.nombre_partida)[:26]:<27} sub {r.subtitulo:>2} "
                  f"{str(r.nombre_subtitulo)[:22]:<23} {extra}")
        print(f"  ({len(t)} combinaciones)")
        if senal == "sobreejecucion" and len(t):
            reg.warn("ejecucion", f"{len(t)} partida·subtítulo operativos "
                     f"sobreejecutados en ≥5 años", patron="sobreejecución recurrente")

    print("\n  Sobre   = ejecutado sobre un vigente > 0")
    print("  Sin ley = ejecutado en partida·subtítulo con vigente 0 (no es sobreejecución)")
    print(f"\n  Respaldo general: {SALIDA / 'ejecucion_detalle.csv'} ({len(det):,} filas)")
    reg.emitir()