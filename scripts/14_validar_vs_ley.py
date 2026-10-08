"""
14_validar_vs_ley.py — ley_inicial vs artículo 1 de la ley
===========================================================
Validación contra un TERCERO real: la Ley de Presupuestos
publicada en el Diario Oficial, no un informe de DIPRES.

El artículo 1 publica tres columnas por subtítulo:

    Resumen de las Partidas  →  suma bruta, sin consolidar
    Deducciones               →  eliminaciones de transferencias
    Total                     →  consolidado

Hipótesis:
    Σ cruce_partida[ley_inicial]   = Resumen de las Partidas
    Σ cruce_nacional[ley_inicial]  = Total
    diferencia                     = Deducciones

La referencia vive en docs/art1_ley_presupuestos.csv, transcrita
desde las imágenes del artículo 1 (ver 13_extraer_imagenes_ley.py).
Para agregar un año, se agregan sus filas al CSV — sin tocar código.

Uso:
    python 14_validar_vs_ley.py
    python 14_validar_vs_ley.py --anio 2024
"""

import argparse

import pandas as pd

from config import DIRS, TOLERANCIAS
from dominio import MES_A_NUM
from hallazgos import Registro
from utils import leer_csv_robusto

REFERENCIA = DIRS["docs"] / "art1_ley_presupuestos.csv"

# Columna del artículo 1 que debería reproducir cada nivel
COL_POR_NIVEL = {"partida": "resumen_partidas", "nacional": "total"}


def cierres(nivel: str) -> pd.DataFrame:
    """Último mes de cada año: el presupuesto aprobado."""
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / f"cruce_{nivel}.csv"))
    df["MesNum"] = df["Mes"].map(MES_A_NUM)
    idx = df.groupby(["Año", "Moneda"])["MesNum"].transform("max") == df["MesNum"]
    df = df[idx].copy()
    df["Sub"] = df["Subtítulo"].astype(int)
    return df.groupby(["Año", "Moneda", "Sub"], as_index=False)["ley_inicial"].sum()


def comparar(obs: pd.DataFrame, ref: pd.DataFrame, nivel: str,
             anio: int, moneda: str, reg: Registro) -> dict:
    col = COL_POR_NIVEL[nivel]
    r = ref[(ref.anio == anio) & (ref.moneda == moneda)]
    detalle = r[r.subtitulo != 0]
    subs = detalle.subtitulo.tolist()

    o = obs[(obs["Año"] == anio) & (obs["Moneda"] == moneda)]
    o = o.set_index("Sub")["ley_inicial"]

    comp = detalle.assign(
        dataset=lambda d: d.subtitulo.map(lambda s: float(o.get(s, 0))),
    )
    comp["delta"] = comp.dataset - comp[col]
    cuadran = int((comp.delta.abs() <= TOLERANCIAS["monto"]).sum())

    tot_ref = float(r.loc[r.subtitulo == 0, col].iloc[0])
    tot_obs = float(o.loc[o.index.isin(subs)].sum())
    delta_tot = tot_obs - tot_ref
    ok = abs(delta_tot) <= TOLERANCIAS["monto"] and cuadran == len(comp)

    estado = "✓" if ok else "✗"
    print(f"  {estado} {anio} {moneda:<8} {nivel:<9}"
          f"{cuadran:>3}/{len(comp)} subtítulos · total Δ={delta_tot:>16,.0f}")

    if not ok:
        for _, f in comp[comp.delta.abs() > TOLERANCIAS["monto"]].iterrows():
            print(f"        {f.concepto[:38]:<40}"
                  f"ley={f[col]:>18,.0f}  dataset={f.dataset:>18,.0f}")

    (reg.ok if ok else reg.warn)(
        "art1", f"{anio}/{moneda}/{nivel}: {cuadran}/{len(comp)}, Δ={delta_tot:,.0f}",
        anio=anio)

    return {"anio": anio, "moneda": moneda, "nivel": nivel,
            "cuadran": cuadran, "de": len(comp), "delta": delta_tot, "ok": ok}


def deducciones(p: pd.DataFrame, n: pd.DataFrame, ref: pd.DataFrame,
                anio: int, moneda: str, reg: Registro) -> dict:
    r = ref[(ref.anio == anio) & (ref.moneda == moneda)]
    subs = r[r.subtitulo != 0].subtitulo.tolist()
    esperado = float(r.loc[r.subtitulo == 0, "deducciones"].iloc[0])

    sel = lambda d: d[(d["Año"] == anio) & (d["Moneda"] == moneda)
                      & d["Sub"].isin(subs)]["ley_inicial"].sum()
    obs = float(sel(p) - sel(n))
    delta = obs - esperado
    ok = abs(delta) <= TOLERANCIAS["monto"]

    print(f"  {'✓' if ok else '✗'} {anio} {moneda:<8} deducciones  "
          f"ley={esperado:>16,.0f}  obs={obs:>16,.0f}  Δ={delta:,.0f}")
    (reg.ok if ok else reg.warn)(
        "deducciones", f"{anio}/{moneda}: Δ={delta:,.0f}", anio=anio)
    return {"anio": anio, "moneda": moneda, "ok": ok, "delta": delta}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int)
    args = ap.parse_args()

    reg = Registro("validacion_vs_ley", salida_dir=DIRS["reportes"])
    ref = pd.read_csv(REFERENCIA)
    if args.anio:
        ref = ref[ref.anio == args.anio]

    anios = sorted(ref.anio.unique())
    print("=" * 78)
    print("  LEY_INICIAL vs ARTÍCULO 1 — Ley de Presupuestos (Diario Oficial)")
    print("=" * 78)
    print(f"\n  Años en la referencia: {anios}")

    niveles = {n: cierres(n) for n in COL_POR_NIVEL}

    print(f"\n{'─' * 78}\n  Comparación por nivel\n")
    res = []
    for anio in anios:
        for moneda in sorted(ref[ref.anio == anio].moneda.unique()):
            for nivel, obs in niveles.items():
                res.append(comparar(obs, ref, nivel, anio, moneda, reg))

    print(f"\n{'─' * 78}\n  Deducciones de transferencias\n")
    for anio in anios:
        for moneda in sorted(ref[ref.anio == anio].moneda.unique()):
            deducciones(niveles["partida"], niveles["nacional"],
                        ref, anio, moneda, reg)

    d = pd.DataFrame(res)
    print(f"\n{'─' * 78}")
    print(f"  {d.ok.sum()}/{len(d)} comparaciones cuadran "
          f"({d.cuadran.sum()}/{d['de'].sum()} subtítulos)")

    faltan = [a for a in range(2017, 2027) if a not in anios]
    if faltan:
        print(f"\n  Años sin transcribir: {faltan}")
        print(f"  Agregar filas a {REFERENCIA.name} desde las imágenes del art. 1")

    reg.emitir()