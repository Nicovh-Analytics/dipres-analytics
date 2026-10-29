"""
11b_tope_endeudamiento.py — Endeudamiento ejecutado vs tope del Art. 3
=======================================================================
El Art. 3 de cada Ley de Presupuestos autoriza al Presidente a contraer
obligaciones hasta un monto en US$ (inciso 1, el que "se incluye en los
Ingresos Generales de la Nación") más un monto adicional (inciso 2).

No entra en el cómputo del margen:
  - la deuda contraída bajo la autorización y amortizada en el mismo
    ejercicio;
  - la contraída para prepagar deuda de ejercicios anteriores, deducidas
    las amortizaciones incluidas en la ley;
  - la contraída para pagar bonos de reconocimiento (D.L. 3.500), que tiene
    su propia autorización, fuera de los límites (inciso 5°, hasta US$1.000
    millones en 2017-2018). Se lee como tope_reconocimiento y la usa
    18d_margen_endeudamiento.py; este script no la suma al tope.

Con datos presupuestarios no se puede reconstruir ese cómputo exacto (hace
falta el detalle de cada emisión y su destino). Se acota por dos lados:

  bruto  = subtítulo 14 ejecutado (Tesoro Público, partida 50)
           → cota SUPERIOR del endeudamiento computable
  neto   = bruto − amortizaciones ejecutadas (34.01 + 34.02, partida 50)
           → cota INFERIOR: descuenta todas las amortizaciones, más de lo
             que permite la ley

  bruto ≤ tope            → DENTRO   (cumple aun sin descontar nada)
  neto  > tope            → SOBRE    (excede aun descontando de más):
                             revisar leyes que modificaron el tope
  neto ≤ tope < bruto     → INDETERMINADO con estos datos

Los pesos se pasan a US$ con el dólar observado promedio del año
(dominio.TC_OBSERVADO): aproximación, cada emisión ocurre a su fecha.

El tope se lee del texto de la ley (12_descarga_normativa.py). Las leyes
que lo modificaron durante el año no están en ese texto: se agregan a mano
en TOPE_AJUSTES (un año) o TOPE_PLURIANUAL (bolsa para varios años, p. ej.
Ley 21.288), con su fuente.

Uso:
    python pipeline/4_analisis/11b_tope_endeudamiento.py
"""

import re

import pandas as pd

from dipres.config import DIRS
from dipres.dominio import MES_A_NUM, NUM_A_MES, TC_OBSERVADO, tipo_cambio
from dipres.hallazgos import Registro
from dipres.utils import leer_csv_robusto

ANIO_EN_CURSO = 2026
PARTIDA_TESORO = 50
SUB_ENDEUDAMIENTO = 14
SUB_SERVICIO_DEUDA = 34
ITEMS_AMORTIZACION = {1: "Amortización deuda interna",
                      2: "Amortización deuda externa"}

DIR_TEXTO = DIRS.get("normativa", DIRS["base"] / "normativa") / "texto"

# Modificaciones legales al tope durante el año, en miles de US$.
# {año: [(monto, "ley y fuente"), ...]}. Llenar solo con fuente verificada.
TOPE_AJUSTES: dict[int, list[tuple[float, str]]] = {
    # Autorización aparte del Art. 3, solo para 2020. Cuadra con el "margen
    # de endeudamiento anual de US$13.000 millones" informado en mayo 2020:
    # 8.000 + 500 (Art. 3) + 4.000 (esta ley) + 500 (bonos de reconocimiento)
    2020: [(4_000_000, "Ley 21.225, art. quinto (D.O. 02-04-2020): hasta "
                       "US$4.000 millones durante 2020")],
}

# Autorizaciones de leyes especiales con un monto para varios años (bolsa
# común), en miles de US$. Se usan para ver si el exceso sobre el Art. 3
# de esos años cabe en la bolsa.
TOPE_PLURIANUAL: dict[str, tuple[float, list[int]]] = {
    # Art. 6: hasta US$8.000 millones, vigente hasta el 30-06-2022
    "Ley 21.288 (Fondo COVID)": (8_000_000, [2020, 2021, 2022]),
}

_RX_INICIO = re.compile(
    r"Autor[íi]zase\s+al?\s+(?:la\s+)?President[ae]\s+de\s+la\s+Rep[úu]blica"
    r"\s+para\s+contraer\s+obligaciones,\s+en\s+el\s+pa[íi]s", re.I)
_RX_MONTO = re.compile(r"US\$\s*([\d.]+)\s*miles")


# =====================================================
# Tope legal
# =====================================================
def extraer_tope(anio: int) -> tuple[float | None, float | None,
                                      float | None, str]:
    """
    (inciso 1, inciso 2, bonos de reconocimiento, estado) en miles de US$
    desde el texto. El de reconocimiento se busca en la oración del Art. 3
    que menciona los bonos de reconocimiento; si no está, queda en None.
    """
    ruta = DIR_TEXTO / f"ley_presupuestos_{anio}_dipres_completo.txt"
    if not ruta.exists():
        return None, None, None, f"no existe {ruta.name}"
    t = ruta.read_text(encoding="utf-8").replace("�", ".")
    m = _RX_INICIO.search(t)
    if m is None:
        return None, None, None, "no se ubicó el Art. 3"
    bloque = re.sub(r"\s+", " ", t[m.start():m.start() + 1500])
    montos = [float(x.replace(".", "")) for x in _RX_MONTO.findall(bloque)[:2]]
    if len(montos) < 2:
        return None, None, None, f"se leyeron {len(montos)} montos, se esperaban 2"
    # Inciso 5°: el artículo sigue después del bloque de los dos topes
    articulo = re.sub(r"\s+", " ", t[m.start():m.start() + 5000])
    articulo = re.split(r"Art[íi]culo\s+4", articulo)[0]
    reconoc = None
    for oracion in re.split(r"(?<=[a-z\)])\.\s", articulo):
        if "reconocimiento" in oracion.lower():
            r = _RX_MONTO.findall(oracion)
            if r:
                reconoc = float(r[0].replace(".", ""))
                break
    return montos[0], montos[1], reconoc, "ok"


def tabla_topes(anios) -> pd.DataFrame:
    filas = []
    for a in anios:
        i1, i2, rec, estado = extraer_tope(a)
        aj = sum(m for m, _ in TOPE_AJUSTES.get(a, []))
        filas.append({"Año": a, "tope_inciso1": i1, "tope_inciso2": i2,
                      "tope_reconocimiento": rec, "tope_ajustes": aj,
                      "tope_total": (i1 + i2 + aj) if i1 is not None else None,
                      "estado_texto": estado})
    return pd.DataFrame(filas)


# =====================================================
# Ejecución
# =====================================================
def ultimo_mes(df: pd.DataFrame) -> pd.DataFrame:
    """Último mes de cada año, solo años con dólar observado ingresado."""
    df = df[df["Año"].map(lambda a: TC_OBSERVADO.get(int(a)) is not None)]
    df = df.copy()
    df["MesNum"] = df["Mes"].map(MES_A_NUM)
    return df[df.groupby("Año")["MesNum"].transform("max") == df["MesNum"]]


def a_usd(df: pd.DataFrame, col: str) -> pd.Series:
    """Miles de US$: los pesos se dividen por el dólar observado del año."""
    es_pesos = df["Moneda"].str.upper().eq("PESOS")
    tc = df["Año"].map(lambda a: tipo_cambio(a, "observado"))
    return df[col].where(~es_pesos, df[col] / tc)


def endeudamiento_bruto() -> pd.DataFrame:
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_partida.csv"))
    df = df[(df["Partida"] == PARTIDA_TESORO) &
            (df["Subtítulo"].isin([SUB_ENDEUDAMIENTO, SUB_SERVICIO_DEUDA]))]
    df = ultimo_mes(df)
    df["usd"] = a_usd(df, "ejecucion_acumulada")
    p = (df.pivot_table(index=["Año", "MesNum"], columns="Subtítulo",
                        values="usd", aggfunc="sum", fill_value=0)
           .reset_index())
    return p.rename(columns={SUB_ENDEUDAMIENTO: "bruto",
                             SUB_SERVICIO_DEUDA: "servicio_deuda"})


def amortizaciones() -> pd.DataFrame:
    """34.01 + 34.02 de la partida 50, desde cruce_programa (único nivel
    con ítem). Se lee por partes: el archivo es grande."""
    cols = ["Año", "Mes", "Moneda", "Partida", "Subtítulo", "Item",
            "Asignación", "ejecucion_acumulada"]
    partes = []
    for ch in pd.read_csv(DIRS["consolidado"] / "cruce_programa.csv",
                          usecols=cols, chunksize=500_000,
                          encoding="utf-8-sig", low_memory=False):
        partes.append(ch[(ch["Partida"] == PARTIDA_TESORO) &
                         (ch["Subtítulo"] == SUB_SERVICIO_DEUDA) &
                         (ch["Item"].isin(ITEMS_AMORTIZACION))])
    df = ultimo_mes(pd.concat(partes, ignore_index=True))

    # Evitar doble conteo: si un ítem tiene filas por asignación, se suman
    # esas; la fila sin asignación (subtotal) se usa solo si es la única
    claves = ["Año", "Mes", "Moneda", "Item"]
    tiene_asig = df.groupby(claves)["Asignación"].transform(
        lambda s: s.notna().any())
    df = df[df["Asignación"].notna() | ~tiene_asig]

    df["usd"] = a_usd(df, "ejecucion_acumulada")
    p = (df.pivot_table(index="Año", columns="Item", values="usd",
                        aggfunc="sum", fill_value=0)
           .reindex(columns=list(ITEMS_AMORTIZACION), fill_value=0))
    p.columns = [f"amort_{i:02d}" for i in p.columns]
    p["amortizacion"] = p.sum(axis=1)
    return p.reset_index()


def lectura(r) -> str:
    if pd.isna(r["tope_total"]):
        return "sin tope"
    if r["bruto"] <= r["tope_total"]:
        return "DENTRO"
    if r["neto"] > r["tope_total"]:
        return "SOBRE"
    return "INDETERMINADO"


# =====================================================
if __name__ == "__main__":
    sin_tc = sorted(a for a, v in TC_OBSERVADO.items() if v is None)
    if sin_tc:
        print(f"  Años omitidos por falta de TC_OBSERVADO: {sin_tc}\n")
    b = endeudamiento_bruto()
    a = amortizaciones()
    d = b.merge(a, on="Año", how="left").fillna({"amortizacion": 0})
    d["neto"] = d["bruto"] - d["amortizacion"]
    d = d.merge(tabla_topes(d["Año"]), on="Año", how="left")
    d["lectura"] = d.apply(lectura, axis=1)

    # Bolsas plurianuales: exceso sobre el Art. 3 con la cota inferior
    # (neto). Si la suma de excesos cabe en la bolsa, el año queda
    # explicado por esa ley.
    bolsas = []
    for ley, (monto, anios) in TOPE_PLURIANUAL.items():
        en = d["Año"].isin(anios) & (d["lectura"] == "SOBRE")
        exceso = (d.loc[en, "neto"] - d.loc[en, "tope_total"]).sum()
        cabe = exceso <= monto
        if cabe:
            d.loc[en, "lectura"] = "SOBRE ART.3, CABE EN LEY"
        bolsas.append((ley, monto, anios, exceso, cabe))
    d["uso_bruto_pct"] = d["bruto"] / d["tope_total"] * 100
    d["uso_neto_pct"] = d["neto"] / d["tope_total"] * 100

    print("=" * 84)
    print("  ENDEUDAMIENTO EJECUTADO vs TOPE ART. 3 — Tesoro Público, miles de "
          "millones de US$")
    print("=" * 84)
    print(f"\n{'Año':>6}{'Tope':>8}{'Bruto':>8}{'Amort.':>8}{'Neto':>8}"
          f"{'Uso bruto':>11}{'Uso neto':>10}  Lectura")
    mm = 1e6   # miles de US$ → miles de millones
    for _, r in d.iterrows():
        anio = int(r["Año"])
        corte = "" if r["MesNum"] == 12 else f"  (a {NUM_A_MES[int(r['MesNum'])]})"
        tope = f"{r['tope_total'] / mm:>8.1f}" if pd.notna(r["tope_total"]) \
            else f"{'—':>8}"
        print(f"{anio:>6}{tope}{r['bruto'] / mm:>8.1f}"
              f"{r['amortizacion'] / mm:>8.1f}{r['neto'] / mm:>8.1f}"
              f"{r['uso_bruto_pct']:>10.0f}%{r['uso_neto_pct']:>9.0f}%  "
              f"{r['lectura']}{corte}")

    reg = Registro("tope_endeudamiento", salida_dir=DIRS["reportes"], eco=False)

    # Control: las amortizaciones no pueden superar el subtítulo 34
    malo = d[d["amortizacion"] > d["servicio_deuda"] * 1.001]
    if not malo.empty:
        print(f"\n  ⚠ amortización > subtítulo 34 en {malo['Año'].tolist()}: "
              f"revisar el filtro de ítems/asignaciones")
    for _, r in d.iterrows():
        a = int(r["Año"])
        (reg.error if a in set(malo["Año"]) else reg.ok)(
            "amortizaciones", f"{a}: amortizaciones 34.01-34.02 ≤ subt. 34",
            anio=a, patron="amortización > subtítulo 34 (filtro de ítems)")

    # Control: el tope se leyó del texto de cada ley. Sin tope, el año no se
    # evalúa (ni aquí ni en el 18d): es un error de datos, no un hallazgo
    sin = d[d["estado_texto"] != "ok"]
    for _, r in sin.iterrows():
        print(f"\n  ⚠ {int(r['Año'])}: tope no leído — {r['estado_texto']}")
    for _, r in d.iterrows():
        a = int(r["Año"])
        if r["estado_texto"] != "ok":
            reg.error("tope_ley", f"{a}: tope no leído — {r['estado_texto']}",
                      anio=a, patron="tope del art. 3 no leído")
        else:
            reg.ok("tope_ley", f"{a}: tope leído del art. 3", anio=a)
            if pd.isna(r.get("tope_reconocimiento")):
                reg.info("tope_ley", f"{a}: sin autorización de bonos de "
                         f"reconocimiento en el art. 3", anio=a,
                         patron="sin inciso de bonos de reconocimiento")

    print(f"\n  Tope  = inciso 1 + inciso 2 (+ ajustes por ley en TOPE_AJUSTES)")
    print(f"  Bruto = subt. 14 ejecutado → cota superior del endeudamiento computable")
    print(f"  Neto  = bruto − amortizaciones 34.01/34.02 → cota inferior")
    print(f"  SOBRE = excede aun con la cota inferior: revisar leyes modificatorias")

    for ley, monto, anios, exceso, cabe in bolsas:
        print(f"\n  {ley}: bolsa {monto / mm:.1f} para {anios[0]}-{anios[-1]} · "
              f"exceso neto sobre Art. 3 en esos años {exceso / mm:.1f} → "
              f"{'cabe' if cabe else 'NO cabe'}")

    d.round(2).to_csv(DIRS["reportes"] / "tope_endeudamiento.csv", index=False)
    reg.emitir()