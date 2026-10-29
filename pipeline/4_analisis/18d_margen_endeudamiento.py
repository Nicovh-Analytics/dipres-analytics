"""
18d_margen_endeudamiento.py — Uso estimado del margen de endeudamiento (Art. 3)
===============================================================================
Estima cuánto del tope del Art. 3 de cada Ley de Presupuestos se usó, con el
detalle de emisiones de los reportes de deuda (11c) en vez del subtítulo 14.
Mejora la cota del 11b (bruto vs neto) en tres puntos:

  1. Mide los bonos a valor nominal (lo que la ley limita), no lo recibido en
     caja: el subt. 14 incluye el premio o descuento de colocación.
  2. Descuenta los prepagos de deuda de ejercicios anteriores (inciso 4°),
     con el anexo de prepagos de los reportes de deuda, y los bonos que se
     emitieron y vencieron el mismo año (amortizados dentro del ejercicio,
     también inciso 4°: p. ej. tres BTP cero cupón emitidos el 07-01-2025 y
     vencidos entre agosto y noviembre de 2025).
  3. Considera la autorización aparte para pagar bonos de reconocimiento
     (inciso 5°), que no se imputa al tope.

Cómputo:
  base  = bonos emitidos (US$, valor nominal) − prepagos del año
          − bonos emitidos y vencidos en el mismo año
  alto  = base + residuo en dólares del cruce con el subt. 14 (cota de los
          créditos con organismos, que no son bonos; incluye también premio)
  tope  = inciso 1 + inciso 2 (+ ajustes legales del 11b)
  tope ampliado = tope + autorización de bonos de reconocimiento

  alto ≤ tope            → DENTRO
  base > tope ampliado   → SOBRE (aun suponiendo que se usó toda la
                           autorización de bonos de reconocimiento)
  otro caso              → INDETERMINADO con datos públicos

Lo que no se puede medir con datos públicos y queda fuera:
  - la deuda contraída y amortizada dentro del mismo año que no aparece en
    ningún reporte (emitida y vencida entre dos de ellos): tampoco está en
    los bonos del 11c, así que ambos lados la omiten;
  - cuánto se usó de verdad de la autorización de bonos de reconocimiento;
  - el tipo de cambio de cada operación (se usa el promedio del periodo).
El cómputo oficial se pidió por Ley 20.285 (docs/consultas_transparencia.md).

Los bonos locales de 2024 y 2025 no se pueden separar por año (ver 11c): esos
dos años se evalúan juntos contra la suma de sus topes.

Salida en DIRS["reportes"]:
  margen_endeudamiento.csv   ventana: tope, bonos, prepagos, base, rango, lectura

Uso:
    python pipeline/4_analisis/18d_margen_endeudamiento.py
"""

import importlib.util
from pathlib import Path

import pandas as pd

from dipres.config import DIRS
from dipres.hallazgos import Registro

REP = DIRS["reportes"]
MM = 1e3                # miles de US$ → millones de US$


def bolsas_plurianuales() -> dict:
    """TOPE_PLURIANUAL del 11b (única fuente), en millones de US$."""
    ruta = Path(__file__).with_name("11b_tope_endeudamiento.py")
    spec = importlib.util.spec_from_file_location("tope11b", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return {ley: (monto / MM, set(anios))
            for ley, (monto, anios) in m.TOPE_PLURIANUAL.items()}


def anios_de(ventana: str) -> list[int]:
    a0, a1 = (int(x) for x in (ventana.split("-") if "-" in ventana
                               else (ventana, ventana)))
    return list(range(a0, a1 + 1))


def lectura(r) -> str:
    if pd.isna(r.tope):
        return "sin tope"
    if r.alto <= r.tope:
        return "DENTRO"
    if r.base > r.tope_ampliado:
        return "SOBRE"
    return "INDETERMINADO"


def main() -> None:
    print("=" * 84)
    print("  MARGEN DE ENDEUDAMIENTO ART. 3 — estimación con el detalle de bonos")
    print("=" * 84)
    tope = pd.read_csv(REP / "tope_endeudamiento.csv").set_index("Año")
    if "tope_reconocimiento" not in tope.columns:
        print("  · tope_endeudamiento.csv sin tope_reconocimiento: correr la "
              "versión actual del 11b")
        return
    emis = pd.read_csv(REP / "deuda_emisiones_usd.csv", encoding="utf-8-sig",
                       parse_dates=["emision", "vencimiento"])
    # Emitidos y vencidos el mismo año: amortizados dentro del ejercicio
    emis["mismo_anio"] = emis.emision.dt.year == emis.vencimiento.dt.year
    pre = (pd.read_csv(REP / "deuda_prepagos.csv", encoding="utf-8-sig")
             .set_index("anio").prepago_musd)
    cruce = pd.read_csv(REP / "deuda_cruce_subt14.csv", encoding="utf-8-sig")
    resid = (cruce[cruce.seccion == "DOLARES"].set_index("ventana")
                  .diferencia.clip(lower=0) / MM)

    filas = []
    for v, g in emis.groupby("ventana"):
        anios = anios_de(v)
        t = tope.reindex(anios)
        tiene_tope = t.tope_total.notna().all()
        # El residuo en dólares está por año en el cruce; se suman los años
        # de la ventana (o la ventana tal cual, si coincide)
        r_usd = (resid.get(v) if v in resid.index
                 else sum(resid.get(str(a), 0) for a in anios))
        filas.append({
            "ventana": v,
            "tope": t.tope_total.sum() / MM if tiene_tope else float("nan"),
            "reconocimiento": t.tope_reconocimiento.fillna(0).sum() / MM,
            "bonos": g.emitido_musd.sum(),
            "mismo_anio": g.loc[g.mismo_anio, "emitido_musd"].sum(),
            "prepagos": sum(pre.get(a, 0) for a in anios),
            "residuo_usd": r_usd,
            "bruto_11b": t.bruto.sum() / MM, "neto_11b": t.neto.sum() / MM,
            "lectura_11b": " / ".join(t.lectura.dropna().astype(str)),
        })
    d = pd.DataFrame(filas)
    d["base"] = d.bonos - d.prepagos - d.mismo_anio
    d["alto"] = d.base + d.residuo_usd
    d["tope_ampliado"] = d.tope + d.reconocimiento
    d["lectura"] = d.apply(lectura, axis=1)
    d["uso_base_pct"] = d.base / d.tope * 100

    # Leyes especiales con bolsa plurianual (p. ej. Ley 21.288, Fondo COVID)
    for ley, (monto, anios) in bolsas_plurianuales().items():
        en = d.ventana.map(lambda v: set(anios_de(v)) <= anios) & \
             (d.lectura == "SOBRE")
        exceso = (d.loc[en, "base"] - d.loc[en, "tope_ampliado"]).sum()
        if en.any() and exceso <= monto:
            d.loc[en, "lectura"] = "SOBRE ART.3, CABE EN LEY"
        if en.any():
            print(f"  {ley}: exceso {exceso:,.0f} vs bolsa {monto:,.0f} → "
                  f"{'cabe' if exceso <= monto else 'NO cabe'}")

    print(f"\n  Millones de US${'':4}{'Tope':>8}{'+Rec.':>7}{'Bonos':>8}"
          f"{'Prepag.':>8}{'Mismo':>7}{'Base':>8}{'Alto':>8}{'Uso':>6}  "
          f"Lectura (antes, 11b)")
    for r in d.itertuples():
        print(f"  {r.ventana:16}{r.tope:>8,.0f}{r.reconocimiento:>7,.0f}"
              f"{r.bonos:>8,.0f}{r.prepagos:>8,.0f}{r.mismo_anio:>7,.0f}"
              f"{r.base:>8,.0f}"
              f"{r.alto:>8,.0f}{r.uso_base_pct:>5.0f}%  {r.lectura} "
              f"({r.lectura_11b})")
    print("\n  Base = bonos a valor nominal − prepagos − emitidos y vencidos el "
          "mismo año (Mismo)")
    print("  Alto = base + residuo en dólares del cruce con el subt. 14 "
          "(cota de créditos)")
    print("  +Rec. = autorización aparte para bonos de reconocimiento "
          "(inciso 5°), no imputable al tope")

    d.round(2).to_csv(REP / "margen_endeudamiento.csv", index=False,
                      encoding="utf-8-sig")
    # Un "SOBRE" es un aviso, no un error de datos: es una estimación y el
    # cómputo oficial se pidió por Ley 20.285
    reg = Registro("margen_endeudamiento", salida_dir=REP, eco=False)
    for r in d.itertuples():
        msg = f"{r.ventana}: {r.lectura} (uso {r.uso_base_pct:.0f}% del tope)"
        if r.lectura == "SOBRE":
            reg.warn("margen", msg, anio=r.ventana,
                     patron="estimación sobre el tope ampliado")
        elif r.lectura in ("INDETERMINADO", "sin tope"):
            reg.info("margen", msg, anio=r.ventana, patron=r.lectura)
        else:
            reg.ok("margen", msg, anio=r.ventana)
    print(f"\n  Salida: {REP / 'margen_endeudamiento.csv'}")
    reg.emitir()


if __name__ == "__main__":
    main()