"""
09_contribucion_sesgo.py — ¿Quién explica el sesgo agregado?
=============================================================
El script anterior midió el error en porcentaje por subtítulo.
Un porcentaje alto sobre una base chica pesa poco en pesos.

Acá se mide la CONTRIBUCIÓN ABSOLUTA: cuántos pesos del error
total aporta cada subtítulo, y qué porcentaje del sesgo agregado
representa.

Pregunta: ¿las partidas que no se proyectan explican el 14,8%
de subestimación agregada, o el sesgo está repartido?

Uso:
    python 09_contribucion_sesgo.py
"""

import pandas as pd

from config import DIRS
from dominio import (MES_A_NUM, SUBTITULOS_INGRESO, SUBTITULOS_SALDO,
                     nombre_subtitulo)
from utils import leer_csv_robusto

ANIO_EN_CURSO = 2026

# Subtítulos que SÍ se proyectan con modelos (DIPRES publica metodología)
PROYECTADOS = {1}          # Impuestos

# Partidas cuyo monto depende de operaciones discrecionales del año,
# no de un pronóstico: se consignan por convención, no por estimación
NO_PROYECTADOS = {6, 11, 12, 13, 14}
# 06 Rentas de la propiedad · 11 Venta activos financieros
# 12 Recuperación de préstamos · 13 Transf. para gastos de capital
# 14 Endeudamiento


def clasificar(sub: int) -> str:
    if sub in PROYECTADOS:
        return "Proyectado"
    if sub in NO_PROYECTADOS:
        return "No proyectado"
    return "Mixto"


# =====================================================
def cargar_cierres() -> pd.DataFrame:
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_nacional.csv"))
    df = df[(df["Moneda"] == "PESOS") & (df["Año"] < ANIO_EN_CURSO)].copy()
    df["MesNum"] = df["Mes"].map(MES_A_NUM)

    idx = df.groupby("Año")["MesNum"].transform("max") == df["MesNum"]
    cierres = df[idx].copy()
    cierres["Sub"] = cierres["Subtítulo"].astype(int)

    # Ingresos, sin saldos de caja (partidas contables, no flujos)
    cierres = cierres[
        cierres["Sub"].isin(SUBTITULOS_INGRESO)
        & ~cierres["Sub"].isin(SUBTITULOS_SALDO)
    ].copy()

    cierres["error"] = cierres["ejecucion_acumulada"] - cierres["ley_inicial"]
    cierres["grupo"] = cierres["Sub"].map(clasificar)
    return cierres


# =====================================================
if __name__ == "__main__":
    c = cargar_cierres()

    error_total = c["error"].sum()
    ley_total = c["ley_inicial"].sum()

    print("=" * 74)
    print("  CONTRIBUCIÓN AL SESGO AGREGADO (2017–2025, PESOS)")
    print("=" * 74)
    print(f"\n  Proyectado total : {ley_total:>20,.0f} M$")
    print(f"  Error total      : {error_total:>20,.0f} M$  "
          f"({error_total/ley_total*100:+.1f}%)")

    # ── Por subtítulo ──
    por_sub = (
        c.groupby("Sub")
        .agg(ley=("ley_inicial", "sum"),
             error=("error", "sum"))
        .assign(
            error_pct_propio=lambda d: d["error"] / d["ley"] * 100,
            contrib_pct=lambda d: d["error"] / error_total * 100,
            peso_en_ley=lambda d: d["ley"] / ley_total * 100,
        )
        .sort_values("contrib_pct", ascending=False)
    )

    print(f"\n{'─'*74}")
    print("Por subtítulo — ordenado por aporte al error total\n")
    print(f"{'Subtítulo':<36}{'% de la ley':>12}{'Error propio':>14}{'Aporte':>12}")
    for sub, r in por_sub.iterrows():
        print(f"{nombre_subtitulo(sub)[:34]:<36}"
              f"{r['peso_en_ley']:>11.1f}%"
              f"{r['error_pct_propio']:>13.1f}%"
              f"{r['contrib_pct']:>11.1f}%")

    # ── Por grupo ──
    por_grupo = (
        c.groupby("grupo")
        .agg(ley=("ley_inicial", "sum"), error=("error", "sum"))
        .assign(
            error_pct_propio=lambda d: d["error"] / d["ley"] * 100,
            contrib_pct=lambda d: d["error"] / error_total * 100,
            peso_en_ley=lambda d: d["ley"] / ley_total * 100,
        )
        .sort_values("contrib_pct", ascending=False)
    )

    print(f"\n{'─'*74}")
    print("Agrupado\n")
    print(f"{'Grupo':<20}{'% de la ley':>14}{'Error propio':>16}{'Aporte al error':>18}")
    for g, r in por_grupo.iterrows():
        print(f"{g:<20}{r['peso_en_ley']:>13.1f}%"
              f"{r['error_pct_propio']:>15.1f}%"
              f"{r['contrib_pct']:>17.1f}%")

    # ── Contrafactual: ¿qué pasa si solo miramos lo proyectado? ──
    proj = c[c["grupo"] == "Proyectado"]
    sesgo_proj = proj["error"].sum() / proj["ley_inicial"].sum() * 100

    sin_noproj = c[c["grupo"] != "No proyectado"]
    sesgo_sin = sin_noproj["error"].sum() / sin_noproj["ley_inicial"].sum() * 100

    print(f"\n{'─'*74}")
    print("Contrafactual\n")
    print(f"  Sesgo agregado (todos los ingresos)      : {error_total/ley_total*100:+6.1f}%")
    print(f"  Sesgo excluyendo partidas no proyectadas : {sesgo_sin:+6.1f}%")
    print(f"  Sesgo solo en Impuestos                  : {sesgo_proj:+6.1f}%")

    # ── Serie anual del grupo proyectado ──
    anual = (
        proj.groupby("Año")
        .agg(ley=("ley_inicial", "sum"), ejec=("ejecucion_acumulada", "sum"))
        .assign(error_pct=lambda d: (d["ejec"] - d["ley"]) / d["ley"] * 100)
    )
    print(f"\n{'─'*74}")
    print("Impuestos — error de proyección año a año\n")
    for anio, r in anual.iterrows():
        barra = "█" * int(abs(r["error_pct"]))
        signo = "▼" if r["error_pct"] < 0 else "▲"
        print(f"  {anio}  {r['error_pct']:>6.1f}% {signo} {barra}")
    print(f"\n  Media: {anual['error_pct'].mean():+.1f}%  ·  "
          f"Mediana: {anual['error_pct'].median():+.1f}%  ·  "
          f"Sin 2020: {anual.drop(2020, errors='ignore')['error_pct'].mean():+.1f}%")