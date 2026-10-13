"""
16_modificaciones.py — Ley inicial → ley vigente
=================================================
¿Cuánto del presupuesto se modifica durante el año, dónde, y se apega
a lo que la ley permite modificar sin pasar por el Congreso?

Base: ley_inicial validada contra la ley (scripts 14 y 15).
Corte: último mes disponible de cada año (vigente al cierre). Un año
sin diciembre (2026) se marca incompleto y no entra en la recurrencia.

Salidas en DIRS["reportes"]:
  modificaciones_detalle.csv     RESPALDO GENERAL: cada año × moneda ×
                                 partida × subtítulo, sin agregar. Ningún
                                 aumento se compensa con una rebaja, así
                                 que un neteo casual o por error queda a
                                 la vista.
  modificaciones_resumen.csv     bruto (aumentos y rebajas) y neto por año
  modificaciones_recurrencia.csv partida × subtítulo sobre el umbral de
                                 materialidad, y en cuántos años
  modificaciones_art4.csv        prueba del artículo 4 de cada ley

Artículo 4 (texto 2017-2026, verificado en cada ley):
  inc. 1  Solo por ley puede aumentar la SUMA del valor neto de gastos
          corrientes: subs 21, 22, 23, 24, 26 (+ 25 Íntegros hasta 2020),
          en moneda nacional y en dólares por separado.
  inc. 2  Excepciones: excedibles (art. 28 DL 1.263), glosa 01 Operaciones
          Complementarias, mayores saldos iniciales de caja (salvo Tesoro),
          venta de activos financieros, ingresos propios, fondos
          concursables, art. 21 DL 1.263.
  inc. 3  La SUMA de subs 29, 31 y 33 puede subir hasta 10%; más allá,
          solo si se financia con reasignaciones desde el inc. 1, mayores
          saldos de caja (salvo Tesoro), venta de activos, fondos
          concursables o recuperación de anticipos.

Lo que los datos NO pueden ver: leyes dictadas durante el año (reajuste,
leyes COVID) y gastos excedibles. Por eso el resultado nunca es
"incumple": es "se apega", "explicable por excepciones medibles" o
"requiere respaldo legal" (hay que ir a buscar la ley que lo autorizó).

Uso:
    python 16_modificaciones.py
    python 16_modificaciones.py --umbral-pct 10 --umbral-monto 1000000
"""

import argparse

import numpy as np
import pandas as pd

from dipres.config import DIRS
from dipres.dominio import MES_A_NUM
from dipres.hallazgos import Registro
from dipres.utils import leer_csv_robusto

SALIDA = DIRS["reportes"]

# Umbrales de materialidad (ajustables por CLI). Montos en miles.
UMBRAL_PCT = 10.0
UMBRAL_MONTO = {"PESOS": 1_000_000,   # $1.000 millones
                "DOLARES": 1_000}      # US$1 millón

# Transferencias del Tesoro a las partidas: aparecen como gasto en el
# Tesoro (27/28) y como ingreso en cada partida (09). Se conservan en el
# detalle, pero se excluyen de los totales para no contarlas dos veces.
DOBLE_CONTEO = {"INGRESOS": {9}, "GASTOS": {27, 28}}

# Movimientos que la ley permite o que son mecánicos: se conservan en todo,
# pero la lectura de recurrencia se centra en lo "operativo".
#   caja        saldos iniciales/finales (arrastre del año anterior)
#   financiero  venta/compra de activos financieros, servicio de la deuda
#               (usualmente excedible, art. 28 DL 1.263)
#   aporte      aporte fiscal del Tesoro (09 / 27 / 28)
TIPO_POR_SUB = {15: "caja", 35: "caja", 11: "financiero", 30: "financiero",
                34: "financiero", 9: "aporte", 27: "aporte", 28: "aporte"}

ART4_CORRIENTE = {21, 22, 23, 24, 26}
ART4_CAPITAL = {29, 31, 33}
ART4_MARGEN_CAPITAL = 0.10


# =====================================================
# Carga
# =====================================================
def cierre(nivel: str) -> pd.DataFrame:
    """Último mes de cada año: inicial y vigente al corte."""
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / f"cruce_{nivel}.csv"))
    df["mes_num"] = df["Mes"].map(MES_A_NUM)
    df = df[df.groupby("Año")["mes_num"].transform("max") == df["mes_num"]]
    df = df.rename(columns={"Año": "anio", "Moneda": "moneda",
                            "Partida": "partida", "Subtítulo": "subtitulo",
                            "Nombre Partida": "nombre_partida",
                            "Nombre Subtítulo": "nombre_subtitulo",
                            "Mes": "mes_corte"})
    df["subtitulo"] = df["subtitulo"].astype(int)
    df["seccion"] = np.where(df.subtitulo < 21, "INGRESOS", "GASTOS")
    df["anio_completo"] = df.mes_num == 12
    claves = [c for c in ("anio", "mes_corte", "anio_completo", "moneda",
                          "partida", "nombre_partida", "seccion", "subtitulo",
                          "nombre_subtitulo") if c in df.columns]
    return (df.groupby(claves, as_index=False, dropna=False)
              [["ley_inicial", "ley_vigente"]].sum())


# =====================================================
# 1. Respaldo general
# =====================================================
def detalle(p: pd.DataFrame, umbral_pct: float) -> pd.DataFrame:
    d = p.copy()
    d["delta"] = d.ley_vigente - d.ley_inicial
    with np.errstate(divide="ignore", invalid="ignore"):
        d["pct"] = np.where(d.ley_inicial != 0,
                            100 * d.delta / d.ley_inicial.abs(), np.nan)
    d["signo"] = np.sign(d.delta).map({1: "aumento", -1: "rebaja", 0: "sin cambio"})
    d["nuevo"] = (d.ley_inicial == 0) & (d.ley_vigente != 0)
    d["tipo"] = d.subtitulo.map(TIPO_POR_SUB).fillna("operativo")
    d["doble_conteo"] = [s in DOBLE_CONTEO[sec]
                         for s, sec in zip(d.subtitulo, d.seccion)]
    monto_min = d.moneda.map(UMBRAL_MONTO)
    # Material: supera ambos umbrales. Una línea nueva (inicial 0) no tiene
    # %, así que basta el monto.
    d["material"] = (d.delta.abs() >= monto_min) & (
        d.nuevo | (d.pct.abs() >= umbral_pct))
    return d


# =====================================================
# 2. Resumen bruto / neto
# =====================================================
def resumen(d: pd.DataFrame) -> pd.DataFrame:
    x = d[~d.doble_conteo]
    g = x.groupby(["anio", "anio_completo", "moneda", "seccion"])
    r = g.agg(inicial=("ley_inicial", "sum"), vigente=("ley_vigente", "sum"),
              neto=("delta", "sum"),
              aumentos=("delta", lambda s: s[s > 0].sum()),
              rebajas=("delta", lambda s: -s[s < 0].sum()),
              lineas_material=("material", "sum")).reset_index()
    r["bruto"] = r.aumentos + r.rebajas
    r["neto_pct"] = 100 * r.neto / r.inicial
    r["bruto_pct"] = 100 * r.bruto / r.inicial
    # Cuánto del movimiento bruto desaparece al netear
    r["oculto_por_neteo"] = r.bruto - r.neto.abs()
    return r


# =====================================================
# 3. Recurrencia
# =====================================================
def recurrencia(d: pd.DataFrame) -> pd.DataFrame:
    """Partida × subtítulo material en cuántos años completos."""
    x = d[d.anio_completo & d.material]
    n_anios = d[d.anio_completo].anio.nunique()
    r = (x.groupby(["moneda", "partida", "seccion", "subtitulo", "tipo"])
           .agg(nombre_partida=("nombre_partida", "first"),
                nombre_subtitulo=("nombre_subtitulo", "first"),
                anios_material=("anio", "nunique"),
                anios=("anio", lambda s: ",".join(map(str, sorted(s)))),
                aumentos=("signo", lambda s: (s == "aumento").sum()),
                rebajas=("signo", lambda s: (s == "rebaja").sum()),
                delta_total=("delta", "sum"))
           .reset_index())
    r["de_anios"] = n_anios
    # Mismo sentido casi todos los años = patrón, no evento
    r["sentido"] = np.select(
        [r.aumentos == r.anios_material, r.rebajas == r.anios_material],
        ["siempre aumenta", "siempre baja"], "mixto")
    return r.sort_values(["anios_material", "delta_total"],
                         ascending=[False, False], key=lambda s: s.abs()
                         if s.name == "delta_total" else s)


# =====================================================
# 4. Artículo 4
# =====================================================
def prueba_art4(n: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    """
    A nivel nacional (valor neto = consolidado, como el art. 1). Las
    excepciones medibles son proxies desde los propios datos:
      caja   Δ sub 15 por partida, sin Tesoro (la ley excluye su caja)
      vaf    Δ sub 11 venta de activos financieros (nacional)
      va     Δ sub 10 venta de activos no financieros (solo inc. 3)
    Ingresos propios, excedibles y leyes del año no son medibles aquí.
    """
    filas = []
    nn = n[n.anio_completo]
    for (anio, mon), g in nn.groupby(["anio", "moneda"]):
        corriente = ART4_CORRIENTE | ({25} if anio <= 2020 else set())
        s = g.set_index("subtitulo")[["ley_inicial", "ley_vigente"]]
        s = s.groupby(level=0).sum()

        def delta(subs):
            x = s.loc[s.index.isin(subs)]
            return float(x.ley_inicial.sum()), float((x.ley_vigente - x.ley_inicial).sum())

        ini_a, d_a = delta(corriente)
        ini_b, d_b = delta(ART4_CAPITAL)
        _, d_vaf = delta({11})
        _, d_va = delta({10})
        pp = p[(p.anio == anio) & (p.moneda == mon) & (p.subtitulo == 15)
               & (p.partida != 50)]
        d_caja = float((pp.ley_vigente - pp.ley_inicial).sum())

        exceso_a = max(0.0, d_a)
        exceso_b = max(0.0, d_b - ART4_MARGEN_CAPITAL * ini_b)
        # Excepciones: solo cuentan los aumentos de esas fuentes
        exc = max(0.0, d_caja) + max(0.0, d_vaf)
        exc_b = exc + max(0.0, d_va) + max(0.0, -d_a)  # + reasignación desde inc. 1
        no_expl_a = max(0.0, exceso_a - exc)
        no_expl_b = max(0.0, exceso_b - exc_b)

        def estado(exceso, no_expl):
            if exceso == 0:
                return "se apega"
            if no_expl == 0:
                return "explicable por excepciones medibles"
            return "requiere respaldo legal"

        filas.append({
            "anio": anio, "moneda": mon,
            "corriente_inicial": ini_a, "corriente_delta": d_a,
            "corriente_pct": 100 * d_a / ini_a if ini_a else np.nan,
            "capital_inicial": ini_b, "capital_delta": d_b,
            "capital_pct": 100 * d_b / ini_b if ini_b else np.nan,
            "exc_caja_sin_tesoro": d_caja, "exc_venta_act_financieros": d_vaf,
            "exc_venta_act_no_financieros": d_va,
            "corriente_exceso": exceso_a, "capital_exceso": exceso_b,
            "excepciones_inc1": exc, "excepciones_inc3": exc_b,
            "corriente_no_explicado": no_expl_a,
            "capital_no_explicado": no_expl_b,
            "estado_inc1": estado(exceso_a, no_expl_a),
            "estado_inc3": estado(exceso_b, no_expl_b),
        })
    return pd.DataFrame(filas)


# =====================================================
# Main
# =====================================================
def _mm(x: float, mon: str) -> str:
    """Miles → millones (pesos) o millones (US$)."""
    return f"{x / 1e3:>12,.0f}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral-pct", type=float, default=UMBRAL_PCT)
    ap.add_argument("--umbral-monto", type=float,
                    help="umbral en miles de pesos (dólares: x 1/1000)")
    args = ap.parse_args()
    if args.umbral_monto:
        UMBRAL_MONTO["PESOS"] = args.umbral_monto
        UMBRAL_MONTO["DOLARES"] = args.umbral_monto / 1000

    reg = Registro("modificaciones", salida_dir=DIRS["reportes"])
    p = cierre("partida")
    n = cierre("nacional")

    det = detalle(p, args.umbral_pct)
    res = resumen(det)
    rec = recurrencia(det)
    art4 = prueba_art4(n, p)

    SALIDA.mkdir(parents=True, exist_ok=True)
    for nombre, df in (("detalle", det), ("resumen", res),
                       ("recurrencia", rec), ("art4", art4)):
        df.to_csv(SALIDA / f"modificaciones_{nombre}.csv", index=False,
                  encoding="utf-8")

    incompletos = sorted(int(a) for a in det[~det.anio_completo].anio.unique())
    print("=" * 78)
    print("  LEY INICIAL → VIGENTE")
    print("=" * 78)
    print(f"  Umbral: |Δ| ≥ {args.umbral_pct:g}% y ≥ "
          f"{UMBRAL_MONTO['PESOS']:,.0f} miles $ / "
          f"{UMBRAL_MONTO['DOLARES']:,.0f} miles US$")
    if incompletos:
        print(f"  Años incompletos (fuera de la recurrencia): {incompletos}")

    print(f"\n{'─' * 78}\n  Gastos en pesos (millones), sin aporte fiscal 27/28\n")
    print(f"  {'Año':<6}{'Inicial':>12}{'Neto':>12}{'Aumentos':>12}"
          f"{'Rebajas':>12}{'Neto%':>8}{'Bruto%':>8}{'Oculto':>12}")
    for r in res[(res.moneda == "PESOS") & (res.seccion == "GASTOS")].itertuples():
        marca = "" if r.anio_completo else " *"
        print(f"  {r.anio:<6}{_mm(r.inicial, 'P')}{_mm(r.neto, 'P')}"
              f"{_mm(r.aumentos, 'P')}{_mm(r.rebajas, 'P')}"
              f"{r.neto_pct:>8.1f}{r.bruto_pct:>8.1f}"
              f"{_mm(r.oculto_por_neteo, 'P')}{marca}")

    print(f"\n{'─' * 78}\n  Artículo 4 (nacional)\n")
    for r in art4.itertuples():
        print(f"  {r.anio} {r.moneda:<8} corriente {r.corriente_pct:>+6.1f}% "
              f"→ {r.estado_inc1:<36} capital {r.capital_pct:>+6.1f}% "
              f"→ {r.estado_inc3}")
        if r.corriente_exceso:
            print(f"        inc. 1: exceso {r.corriente_exceso / 1e3:>10,.0f} · "
                  f"excepciones medibles {r.excepciones_inc1 / 1e3:>10,.0f} "
                  f"(caja {r.exc_caja_sin_tesoro / 1e3:,.0f}, "
                  f"venta act. fin. {r.exc_venta_act_financieros / 1e3:,.0f})")
        for inc, est, ne in (("inc. 1", r.estado_inc1, r.corriente_no_explicado),
                             ("inc. 3", r.estado_inc3, r.capital_no_explicado)):
            if est == "requiere respaldo legal":
                reg.warn("art4", f"{r.anio}/{r.moneda} {inc}: "
                         f"{ne / 1e3:,.0f} millones sin excepción medible",
                         anio=r.anio, patron="modificación sin excepción medible")

    print(f"\n{'─' * 78}\n  Recurrencia (gastos operativos, pesos): material en "
          f"≥ 5 años\n  (caja, financiero y aporte fiscal quedan en el CSV)\n")
    top = rec[(rec.anios_material >= 5) & (rec.moneda == "PESOS")
              & (rec.tipo == "operativo") & (rec.seccion == "GASTOS")]
    for r in top.head(25).itertuples():
        print(f"  {r.anios_material}/{r.de_anios}  {int(r.partida):02d} "
              f"{str(r.nombre_partida)[:28]:<29} sub {r.subtitulo:>2} "
              f"{str(r.nombre_subtitulo)[:24]:<25} {r.sentido:<16} "
              f"Σ Δ {r.delta_total / 1e3:>10,.0f}")
    print(f"  ({len(top)} de {len(rec)} combinaciones; lista completa en "
          f"modificaciones_recurrencia.csv)")

    print(f"\n  Respaldo general: {SALIDA / 'modificaciones_detalle.csv'} "
          f"({len(det):,} filas)")
    reg.emitir()