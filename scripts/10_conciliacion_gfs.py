"""
10_conciliacion_gfs.py — Conciliación clasificador ↔ GFS
=========================================================
Produce tres salidas:

  (5) Tabla antes/después: agregado según clasificador vs según GFS,
      año por año, con prueba del signo repetida en ambos perímetros.

  (6) Conciliación en forma de estado: saldo según clasificador →
      ajustes con fundamento → saldo según GFS → extrapresupuestario
      → cifra oficial DIPRES.

  (7) Documentación de la brecha remanente.

Requiere el parche GFS aplicado en dominio.py.

Uso:
    python 10_conciliacion_gfs.py
"""

import pandas as pd
from scipy.stats import binomtest

from config import DIRS
from dominio import (MES_A_NUM, SUBTITULOS_INGRESO, AJUSTES_INGRESO_GFS,
                     es_ingreso_gfs, gfs_verificado, nombre_subtitulo)
from hallazgos import Registro

ANIO_EN_CURSO = 2026

# Cifra oficial para contrastar (IFP 4T2024, en millones de pesos)
REFERENCIA_OFICIAL = {2024: 67_283_221}

MILES_A_MILLONES = 1_000


# =====================================================
def cargar_cierres() -> pd.DataFrame:
    """Una fila por Año × Subtítulo con el cierre de cada año."""
    df, _ = leer = None, None
    df, _ = __import__("utils").leer_csv_robusto(
        str(DIRS["consolidado"] / "cruce_nacional.csv"))

    df = df[df["Año"] < ANIO_EN_CURSO].copy()
    df["MesNum"] = df["Mes"].map(MES_A_NUM)
    df["Sub"] = df["Subtítulo"].astype(int)

    # Cierre = último mes disponible de cada año
    idx = df.groupby("Año")["MesNum"].transform("max") == df["MesNum"]
    c = df[idx].copy()

    # Ambas monedas: DIPRES reporta el consolidado
    c = c[c["Sub"].isin(SUBTITULOS_INGRESO)].copy()
    c["error"] = c["ejecucion_acumulada"] - c["ley_inicial"]
    return c


def serie_anual(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega por año y calcula el error de proyección."""
    return (df.groupby("Año")
              .agg(ley=("ley_inicial", "sum"),
                   ejec=("ejecucion_acumulada", "sum"))
              .assign(error=lambda d: d["ejec"] - d["ley"],
                      error_pct=lambda d: (d["ejec"] - d["ley"]) / d["ley"] * 100))


def signo(errores: pd.Series) -> tuple[int, int, float]:
    """Devuelve (sobreestimó, subestimó, p-valor)."""
    e = errores[errores != 0].dropna()
    sobre, sub = int((e < 0).sum()), int((e > 0).sum())
    p = binomtest(max(sobre, sub), len(e), 0.5, alternative="two-sided").pvalue
    return sobre, sub, p


# =====================================================
if __name__ == "__main__":
    reg = Registro("conciliacion_gfs", salida_dir=DIRS["reportes"])
    c = cargar_cierres()

    clasificador = c
    gfs = c[c["Sub"].map(es_ingreso_gfs)]

    s_clas = serie_anual(clasificador)
    s_gfs = serie_anual(gfs)

    # ── (5) Tabla antes/después ──────────────────────
    print("=" * 78)
    print("  (5)  AGREGADO SEGÚN CLASIFICADOR  vs  SEGÚN GFS")
    print("=" * 78)
    print(f"\n{'Año':>6}{'Clasificador':>14}{'GFS':>14}   {'Δ perímetro':>14}")
    print(f"{'':>6}{'error %':>14}{'error %':>14}")
    for anio in s_clas.index:
        a, b = s_clas.loc[anio, "error_pct"], s_gfs.loc[anio, "error_pct"]
        print(f"{anio:>6}{a:>13.1f}%{b:>13.1f}%   {b - a:>13.1f} pp")

    for nombre, serie in [("Clasificador (01-15)", s_clas), ("GFS (ingresos)", s_gfs)]:
        sobre, sub, p = signo(serie["error"])
        media = serie["error_pct"].mean()
        print(f"\n  {nombre}")
        print(f"    sobreestimó {sobre} · subestimó {sub} · p = {p:.4f}")
        print(f"    error medio {media:+.1f}% · mediana {serie['error_pct'].median():+.1f}%")
        reg.info("prueba_signo", f"{nombre}: {sub}/{sobre+sub} subestima, "
                                 f"p={p:.4f}, error medio {media:+.1f}%")

    # ── (6) Conciliación ─────────────────────────────
    print(f"\n{'=' * 78}")
    print("  (6)  CONCILIACIÓN — EJECUCIÓN DE INGRESOS")
    print("=" * 78)

    for anio in sorted(REFERENCIA_OFICIAL):
        if anio not in s_clas.index:
            continue

        d = c[c["Año"] == anio]
        base = d["ejecucion_acumulada"].sum() / MILES_A_MILLONES

        print(f"\n  Año {anio} — millones de pesos\n")
        print(f"  {'Saldo según clasificador (Σ subt. 01-15)':<52}{base:>17,.0f}")

        for sub, motivo in AJUSTES_INGRESO_GFS.items():
            monto = d.loc[d["Sub"] == sub, "ejecucion_acumulada"].sum() / MILES_A_MILLONES
            if monto == 0:
                continue
            etiqueta = f"  (-) {sub:02d} {nombre_subtitulo(sub)}"
            marca = "" if gfs_verificado(sub) else "  (*)"
            print(f"  {etiqueta:<52}{-monto:>17,.0f}{marca}")
            print(f"       {motivo}")

        gfs_anio = d[d["Sub"].map(es_ingreso_gfs)]["ejecucion_acumulada"].sum() / MILES_A_MILLONES
        print(f"  {'─' * 69}")
        print(f"  {'= Ingresos según criterio GFS (presupuestario)':<52}{gfs_anio:>17,.0f}")

        oficial = REFERENCIA_OFICIAL[anio]
        brecha = oficial - gfs_anio
        print(f"  {'  (+) Operaciones extrapresupuestarias':<52}{brecha:>17,.0f}")
        print(f"       No disponible en el dataset — cifra derivada por diferencia")
        print(f"  {'─' * 69}")
        print(f"  {'= Ingresos Gobierno Central Total (DIPRES)':<52}{oficial:>17,.0f}")
        print(f"\n  Brecha: {brecha/oficial*100:.2f}% del total oficial")

        reg.info("conciliacion",
                 f"{anio}: clasificador {base:,.0f} → GFS {gfs_anio:,.0f} → "
                 f"oficial {oficial:,.0f} (brecha {brecha/oficial*100:.2f}%)",
                 anio=anio)

    print(f"\n  (*) correspondencia inferida del MEFP, no confirmada en")
    print(f"      documentación de DIPRES — pendiente de verificar")

    # ── Composición del ajuste ───────────────────────
    print(f"\n{'=' * 78}")
    print("  COMPOSICIÓN DEL AJUSTE (todos los años)")
    print("=" * 78)
    print(f"\n{'Subtítulo':<44}{'Monto':>16}{'% del ajuste':>14}")

    ajuste_total = c[~c["Sub"].map(es_ingreso_gfs)]["ejecucion_acumulada"].sum()
    for sub in AJUSTES_INGRESO_GFS:
        m = c.loc[c["Sub"] == sub, "ejecucion_acumulada"].sum()
        if m == 0:
            continue
        print(f"{sub:02d} {nombre_subtitulo(sub)[:40]:<41}"
              f"{m/MILES_A_MILLONES:>15,.0f}{m/ajuste_total*100:>13.1f}%")

    reg.emitir()