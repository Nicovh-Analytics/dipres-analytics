"""
10_conciliacion_gfs.py — Conciliación clasificador ↔ GFS ↔ cifra oficial
=========================================================================
Produce tres salidas:

  (1) Tipo de cambio: supuesto del presupuesto vs observado, por año.

  (2) Conciliación en forma de estado, para cada año con cifra oficial:
      saldo según clasificador → ajustes con fundamento → saldo según GFS
      → brecha remanente → cifra oficial DIPRES.
      La parte en dólares se convierte con el dólar OBSERVADO (es
      ejecución). Se informa además la brecha con el SUPUESTO y el tipo
      de cambio que la cerraría, para separar efecto cambiario de
      operaciones fuera del dataset.

  (3) Composición del ajuste, cada moneda en su unidad.

La comparación ley vs ejecución (antes/después del perímetro y prueba del
signo) vive en 18_ingresos.py.

Requiere TC_SUPUESTO y TC_OBSERVADO llenos en dominio.py.

Uso:
    python pipeline/4_analisis/10_conciliacion_gfs.py
"""

import pandas as pd

from dipres.config import DIRS
from dipres.dominio import (AJUSTES_INGRESO_GFS, MES_A_NUM, SUBTITULOS_INGRESO,
                     desvio_tipo_cambio, es_ingreso_gfs, gfs_verificado,
                     nombre_subtitulo, tipo_cambio)
from dipres.hallazgos import Registro
from dipres.utils import leer_csv_robusto

ANIO_EN_CURSO = 2026

# Cifra oficial para contrastar (IFP 4T2024, en millones de pesos)
REFERENCIA_OFICIAL = {2024: 67_283_221}

MILES_A_MILLONES = 1_000


# =====================================================
def cargar_cierres() -> pd.DataFrame:
    """Una fila por Año × Moneda × Subtítulo de ingreso, al cierre del año."""
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_nacional.csv"))

    df = df[df["Año"] < ANIO_EN_CURSO].copy()
    df["MesNum"] = df["Mes"].map(MES_A_NUM)
    df["Sub"] = df["Subtítulo"].astype(int)
    df["Moneda"] = df["Moneda"].str.upper()

    # Cierre = último mes disponible de cada año
    idx = df.groupby("Año")["MesNum"].transform("max") == df["MesNum"]
    return df[idx & df["Sub"].isin(SUBTITULOS_INGRESO)].copy()


def por_moneda(d: pd.DataFrame) -> tuple[float, float]:
    """(miles de pesos, miles de dólares) de ejecucion_acumulada."""
    s = d.groupby("Moneda")["ejecucion_acumulada"].sum()
    return float(s.get("PESOS", 0)), float(s.get("DOLARES", 0))


def en_millones(pesos: float, usd: float, tc: float) -> float:
    """Miles de pesos + miles de dólares × tc → millones de pesos."""
    return (pesos + usd * tc) / MILES_A_MILLONES


# =====================================================
if __name__ == "__main__":
    reg = Registro("conciliacion_gfs", salida_dir=DIRS["reportes"])
    c = cargar_cierres()

    # ── (1) Tipo de cambio ───────────────────────────
    print("=" * 78)
    print("  (1)  TIPO DE CAMBIO: SUPUESTO DEL PRESUPUESTO vs OBSERVADO ($/US$)")
    print("=" * 78)
    tc = desvio_tipo_cambio()
    if tc.empty:
        print("\n  Sin datos: llenar TC_SUPUESTO y TC_OBSERVADO en dominio.py")
    else:
        print(f"\n{'Año':>6}{'Supuesto':>12}{'Observado':>12}{'Desvío':>10}")
        for _, r in tc.iterrows():
            print(f"{int(r['Año']):>6}{r['supuesto']:>12,.1f}"
                  f"{r['observado']:>12,.1f}{r['desvio_pct']:>+9.1f}%")
        sobre = int((tc["desvio_pct"] > 0).sum())
        print(f"\n  dólar observado sobre el supuesto: {sobre}/{len(tc)} años · "
              f"desvío medio {tc['desvio_pct'].mean():+.1f}% · "
              f"medio absoluto {tc['desvio_pct'].abs().mean():.1f}%")
        tc.round(2).to_csv(DIRS["reportes"] / "tipo_cambio_desvio.csv",
                           index=False)

    # ── (2) Conciliación ─────────────────────────────
    print(f"\n{'=' * 78}")
    print("  (2)  CONCILIACIÓN — EJECUCIÓN DE INGRESOS")
    print("=" * 78)

    conciliaciones = []
    for anio in sorted(REFERENCIA_OFICIAL):
        d = c[c["Año"] == anio]
        if d.empty:
            print(f"\n  {anio}: sin datos de cierre")
            continue
        try:
            tc_obs = tipo_cambio(anio, "observado")
            tc_sup = tipo_cambio(anio, "supuesto")
        except KeyError as e:
            print(f"\n  {anio}: {e.args[0]} — conciliación omitida")
            continue

        base_p, base_u = por_moneda(d)
        base = en_millones(base_p, base_u, tc_obs)

        print(f"\n  Año {anio} — millones de pesos "
              f"(dólares al observado: {tc_obs:,.1f} $/US$)\n")
        print(f"  {'Saldo según clasificador (Σ subt. 01-15)':<52}{base:>17,.0f}")
        print(f"  {'   de ello en dólares (MUS$ ' + f'{base_u/1000:,.0f}' + ')':<52}"
              f"{base_u * tc_obs / MILES_A_MILLONES:>17,.0f}")

        for sub, motivo in AJUSTES_INGRESO_GFS.items():
            p, u = por_moneda(d[d["Sub"] == sub])
            monto = en_millones(p, u, tc_obs)
            if monto == 0:
                continue
            etiqueta = f"  (-) {sub:02d} {nombre_subtitulo(sub)}"
            marca = "" if gfs_verificado(sub) else "  (*)"
            print(f"  {etiqueta:<52}{-monto:>17,.0f}{marca}")
            print(f"       {motivo}")

        gfs_p, gfs_u = por_moneda(d[d["Sub"].map(es_ingreso_gfs)])
        gfs_anio = en_millones(gfs_p, gfs_u, tc_obs)
        oficial = REFERENCIA_OFICIAL[anio]
        brecha = oficial - gfs_anio

        print(f"  {'─' * 69}")
        print(f"  {'= Ingresos según criterio GFS (presupuestario)':<52}{gfs_anio:>17,.0f}")
        print(f"  {'  (+) Brecha remanente':<52}{brecha:>17,.0f}")
        print(f"       No explicada por el dataset — cifra derivada por diferencia")
        print(f"  {'─' * 69}")
        print(f"  {'= Ingresos Gobierno Central Total (DIPRES)':<52}{oficial:>17,.0f}")

        # Sensibilidad al tipo de cambio
        brecha_sup = oficial - en_millones(gfs_p, gfs_u, tc_sup)
        tc_cierra = ((oficial * MILES_A_MILLONES - gfs_p) / gfs_u
                     if gfs_u else float("nan"))
        print(f"\n  Brecha con dólar observado ({tc_obs:,.1f}): "
              f"{brecha / oficial * 100:+.2f}% del oficial")
        print(f"  Brecha con dólar supuesto  ({tc_sup:,.1f}): "
              f"{brecha_sup / oficial * 100:+.2f}% del oficial")
        print(f"  Tipo de cambio que cierra la brecha: {tc_cierra:,.1f} $/US$")

        conciliaciones.append({
            "anio": anio, "clasificador_mm": base, "gfs_mm": gfs_anio,
            "oficial_mm": oficial, "brecha_mm": brecha,
            "tc_observado": tc_obs, "tc_supuesto": tc_sup,
            "brecha_obs_pct": brecha / oficial * 100,
            "brecha_sup_pct": brecha_sup / oficial * 100,
            "tc_que_cierra": tc_cierra})
        reg.info("conciliacion",
                 f"{anio}: clasificador {base:,.0f} → GFS {gfs_anio:,.0f} → "
                 f"oficial {oficial:,.0f} (brecha {brecha/oficial*100:+.2f}% "
                 f"con TC observado {tc_obs:,.1f}; TC que cierra "
                 f"{tc_cierra:,.1f})", anio=anio)

    if conciliaciones:
        pd.DataFrame(conciliaciones).round(4).to_csv(
            DIRS["reportes"] / "conciliacion_ingresos.csv", index=False)

    print(f"\n  (*) correspondencia inferida del MEFP, no confirmada en")
    print(f"      documentación de DIPRES — pendiente de verificar")

    # ── (3) Composición del ajuste ───────────────────
    print(f"\n{'=' * 78}")
    print("  (3)  COMPOSICIÓN DEL AJUSTE (todos los años, cada moneda en su unidad)")
    print("=" * 78)

    aj = c[~c["Sub"].map(es_ingreso_gfs)]
    for moneda, unidad in [("PESOS", "MM$"), ("DOLARES", "MMUS$")]:
        m = aj[aj["Moneda"] == moneda]
        total = m["ejecucion_acumulada"].sum()
        if total == 0:
            continue
        print(f"\n  {moneda}")
        print(f"{'Subtítulo':<44}{'Monto ' + unidad:>16}{'% del ajuste':>14}")
        montos = m.groupby("Sub")["ejecucion_acumulada"].sum()
        # Con montos de signo mixto (p. ej. 11 en dólares, ventas netas
        # negativas) el % del total no tiene sentido: se omite
        con_pct = (montos >= 0).all()
        for sub in AJUSTES_INGRESO_GFS:
            v = montos.get(sub, 0)
            if v == 0:
                continue
            pct = f"{v / total * 100:>13.1f}%" if con_pct else f"{'—':>14}"
            print(f"{sub:02d} {nombre_subtitulo(sub)[:40]:<41}"
                  f"{v / MILES_A_MILLONES:>15,.0f}{pct}")
        if not con_pct:
            print("  (% omitido: hay subtítulos con monto neto negativo)")

    reg.emitir()