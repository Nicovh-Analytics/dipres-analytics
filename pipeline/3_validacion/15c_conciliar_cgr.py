"""
15c_conciliar_cgr.py — Por qué el devengado de DIPRES difiere del de Contraloría
===============================================================================
Usa la respuesta de la CGR a la solicitud por Ley 20.285 (oficio 216260-2026,
raw/externo/cgr/OF216260-2026_ANT-1.xlsx) para descomponer las diferencias
que deja el 15b (VAL-2). El archivo trae, para las partidas consultadas:

  hoja "2"           devengado vigente en SICOGEN por partida y año
  hoja "2.2 Detalle" por subtítulo: devengado bruto, transferencias
                     internas eliminadas y neto
  hoja "Hoja1 (2)"   cada transferencia interna que la CGR elimina, todas
                     las partidas, 2017-2025

Del lado del dataset (miles, diciembre, subtítulos 21-34):
  bruto = suma de cruce_programa (sin consolidar)
  neto  = cruce_partida (consolidado dentro de la partida)
  eliminado = bruto − neto

A) Descomposición, por partida·año·moneda respondida:
     dataset − CGR = subt. 30 sin registro en el dataset
                   + subt. 32 (préstamos)
                   + transferencias eliminadas (DIPRES elimina distinto)
                   + otros subtítulos (lo que no se explica)
   Los Gobiernos Regionales (partida 88 en la respuesta) se suman a Interior,
   como los presenta el IGFE de 2022; esos casos se marcan como perímetro.
B) Transferencias eliminadas, todas las partidas: lo que elimina la CGR
   (Hoja1) contra lo que elimina DIPRES.
C) Cada diferencia de VAL-2 (devengado, 15b) contra lo anterior: se explica
   por la respuesta de la CGR (A), solo por las transferencias (B), o no.

Controles: ❌ si el desglose de la CGR no suma su propio total (hoja 2) o si
el neto del dataset no es el que usó el 15b; ⚠ por cada criterio que explica
una diferencia (hallazgo de la fuente) y si queda una parte sin explicar.

Salidas (reports/):
  conciliacion_cgr.csv                 una fila por caso, con los componentes
  conciliacion_cgr_transferencias.csv  eliminado CGR vs DIPRES por partida·año
  conciliacion_cgr_val2.csv            cada diferencia de VAL-2 y su explicación

Uso:
    python pipeline/3_validacion/15c_conciliar_cgr.py
"""

import numpy as np
import pandas as pd

from dipres.config import DIRS
from dipres.dominio import MES_A_NUM
from dipres.hallazgos import Registro

DIR_CGR = DIRS.get("externo", DIRS["raw"] / "externo") / "cgr"
RESPUESTA = DIR_CGR / "OF216260-2026_ANT-1.xlsx"
REP = DIRS["reportes"]
GASTOS = range(21, 35)          # sin saldo final de caja
MONEDA = {"CLP": "PESOS", "USD": "DOLARES"}
ESCALA_15B = {"PESOS": 1_000, "DOLARES": 1}    # 15b: millones de $ / miles de US$
GORE_CGR, INTERIOR = 88, 5      # la respuesta separa los GORE; el IGFE los suma
GORE_DATASET = 31               # desde 2023: la CGR los toma de la información regional
TOL = 2_000                     # miles: 2 millones de $ o 2 millones de US$
COMPONENTES = ["subt30_sin_registro", "subt32_prestamos", "transferencias",
               "otros_subtitulos"]


# =====================================================
# Lectura
# =====================================================
def respuesta_detalle() -> pd.DataFrame:
    """Hoja 2.2: una fila por año·moneda·partida·subtítulo, en miles."""
    d = pd.read_excel(RESPUESTA, "2.2 Detalle")
    d.columns = ["partida", "nombre", "subt", "concepto", "p_bruto", "p_tr",
                 "p_neto", "cgr_bruto", "cgr_tr", "cgr_neto", "anio", "moneda"]
    d["moneda"] = d.moneda.map(MONEDA)
    d = d[d.subt.isin(GASTOS)].copy()
    perimetro = d.partida == GORE_CGR
    d.loc[perimetro, "partida"] = INTERIOR
    d["perimetro"] = perimetro
    return (d.groupby(["anio", "moneda", "partida", "subt"], as_index=False)
             .agg(cgr_bruto=("cgr_bruto", "sum"), cgr_tr=("cgr_tr", "sum"),
                  cgr_neto=("cgr_neto", "sum"), perimetro=("perimetro", "any")))


def respuesta_totales() -> pd.DataFrame:
    """Hoja 2: devengado vigente por partida·año (bloques CLP y USD). La hoja
    trae después una tabla de presupuesto actualizado, que aquí se salta."""
    raw = pd.read_excel(RESPUESTA, "2", header=None)
    filas, moneda, anios, devengado = [], None, None, False
    for _, r in raw.iterrows():
        vals = [v for v in r.tolist() if pd.notna(v)]
        texto = " ".join(map(str, vals))
        if "Estado Comparativo" in texto:
            devengado = "devengado" in texto.lower()
            moneda = anios = None
        elif not devengado:
            continue
        elif "CLP" in texto.split() or "USD" in texto.split():
            moneda = MONEDA["CLP" if "CLP" in texto.split() else "USD"]
        elif vals and str(vals[0]).startswith("Cód"):
            anios = [int(v) for v in vals[2:]]
        elif moneda and anios and vals and isinstance(vals[0], (int, float)) \
                and len(vals) == len(anios) + 2:
            for a, v in zip(anios, vals[2:]):
                if v:
                    filas.append({"anio": a, "moneda": moneda,
                                  "partida": int(vals[0]), "cgr_total": float(v)})
    return pd.DataFrame(filas)


def transferencias_cgr() -> pd.DataFrame:
    """Hoja1 (2): lo que la CGR elimina por partida·año·moneda (miles)."""
    h = pd.read_excel(RESPUESTA, "Hoja1 (2)")
    h.columns = [str(c).strip() for c in h.columns]
    h["moneda"] = h["Moneda"].map(MONEDA)
    return (h.groupby(["Año", "moneda", "Partida"])["Ejecución (miles)"].sum()
             .rename("cgr_eliminado").rename_axis(["anio", "moneda", "partida"]))


def dataset_por_subtitulo() -> pd.DataFrame:
    """Bruto (programa) y neto (partida) a diciembre, por subtítulo, en miles."""
    def leer(nivel):
        c = pd.read_csv(DIRS["consolidado"] / f"cruce_{nivel}.csv",
                        encoding="utf-8-sig", low_memory=False,
                        usecols=["Año", "Mes", "Moneda", "Partida", "Subtítulo",
                                 "ejecucion_acumulada"])
        c = c[(c.Mes.map(MES_A_NUM) == 12) & c["Subtítulo"].isin(GASTOS)]
        c["Moneda"] = c.Moneda.str.upper()
        return (c.groupby(["Año", "Moneda", "Partida", "Subtítulo"])
                 .ejecucion_acumulada.sum())
    out = pd.concat([leer("programa").rename("ds_bruto"),
                     leer("partida").rename("ds_neto")], axis=1).fillna(0)
    out.index.names = ["anio", "moneda", "partida", "subt"]
    return out.reset_index()


# =====================================================
# A) Descomposición de los casos respondidos
# =====================================================
def descomponer(cgr: pd.DataFrame, ds: pd.DataFrame) -> pd.DataFrame:
    casos = cgr[["anio", "moneda", "partida"]].drop_duplicates()
    ds = ds.merge(casos, on=["anio", "moneda", "partida"])
    # Outer y con ceros: un subtítulo que solo tiene un lado es justamente
    # lo que se busca (el NaN no puede quedar fuera de las sumas)
    m = cgr.merge(ds, on=["anio", "moneda", "partida", "subt"], how="outer")
    m = m.fillna({c: 0 for c in ["cgr_bruto", "cgr_tr", "cgr_neto",
                                 "ds_bruto", "ds_neto"]})
    m["perimetro"] = m.perimetro.astype("boolean").fillna(False).astype(bool)
    m["ds_tr"] = m.ds_bruto - m.ds_neto
    m["d_bruto"] = m.ds_bruto - m.cgr_bruto
    m["d_tr"] = -(m.ds_tr - m.cgr_tr)          # eliminar más baja el neto
    m["d_neto"] = m.ds_neto - m.cgr_neto

    def comp(g):
        s30 = g[(g.subt == 30) & (g.ds_bruto == 0)].d_bruto.sum()
        s32 = g[g.subt == 32].d_bruto.sum()
        otros = g[~g.subt.isin([30, 32])].d_bruto.sum() \
            + g[(g.subt == 30) & (g.ds_bruto != 0)].d_bruto.sum()
        return pd.Series({
            "cgr_neto": g.cgr_neto.sum(), "dataset_neto": g.ds_neto.sum(),
            "diferencia": g.d_neto.sum(), "subt30_sin_registro": s30,
            "subt32_prestamos": s32, "transferencias": g.d_tr.sum(),
            "otros_subtitulos": otros, "perimetro_gore": bool(g.perimetro.any())})
    return (m.groupby(["anio", "moneda", "partida"]).apply(comp, include_groups=False)
             .reset_index())


def parte_a(reg: Registro) -> pd.DataFrame | None:
    cgr = respuesta_detalle()
    tot = respuesta_totales()
    ds = dataset_por_subtitulo()

    # Control 1: el desglose de la CGR suma su propio total
    suma = cgr.groupby(["anio", "moneda", "partida"]).cgr_neto.sum()
    for r in tot.itertuples():
        s = suma.get((r.anio, r.moneda, r.partida))
        if s is None:
            reg.warn("respuesta_cgr", f"{r.anio}/{r.moneda}/{r.partida:02d}: la CGR "
                                      f"informa el total pero no su desglose",
                     anio=r.anio, patron="total sin desglose")
        elif abs(s - r.cgr_total) > TOL:
            reg.error("respuesta_cgr", f"{r.anio}/{r.moneda}/{r.partida:02d}: el "
                                       f"desglose ({s:,.0f}) no suma el total de la "
                                       f"CGR ({r.cgr_total:,.0f})", anio=r.anio)
    t = descomponer(cgr, ds)

    # Control 2: el neto del dataset es el mismo que comparó el 15b
    try:
        v = pd.read_csv(REP / "validacion_cgr.csv")
        v = v[(v.concepto == "devengado") & v.partida.notna()]
        v = v.assign(partida=v.partida.astype(int),
                     dataset_15b=v.dataset * v.moneda.map(ESCALA_15B),
                     cgr_igfe=v.cgr * v.moneda.map(ESCALA_15B))
        t = t.merge(v[["anio", "moneda", "partida", "dataset_15b", "cgr_igfe"]],
                    on=["anio", "moneda", "partida"], how="left")
        malos = t[(t.dataset_neto - t.dataset_15b).abs() > TOL]
        for r in malos.itertuples():
            reg.error("dataset", f"{r.anio}/{r.moneda}/{r.partida:02d}: el neto "
                                 f"({r.dataset_neto:,.0f}) no es el del 15b "
                                 f"({r.dataset_15b:,.0f})", anio=r.anio)
    except FileNotFoundError:
        reg.warn("dataset", "falta validacion_cgr.csv: correr 15b antes")

    t["sin_explicar"] = t.otros_subtitulos
    # Explicado si lo que queda no pasa de TOL ni del 1% de la diferencia
    t["explicada"] = t.sin_explicar.abs() <= np.maximum(TOL, 0.01 * t.diferencia.abs())
    t.to_csv(REP / "conciliacion_cgr.csv", index=False, encoding="utf-8-sig")

    nombres = {"subt30_sin_registro": "subt. 30 sin registro en el dataset",
               "subt32_prestamos": "subt. 32 (préstamos) con otro valor",
               "transferencias": "DIPRES elimina otras transferencias internas"}
    for col, texto in nombres.items():
        x = t[t[col].abs() > TOL]
        if len(x):
            reg.warn("criterio", f"{texto}: {len(x)} casos, "
                                 f"{x[col].sum() / 1000:,.0f} millones en total",
                     patron=texto)
    per = t[t.perimetro_gore]
    for r in per.itertuples():
        reg.warn("criterio", f"{r.anio}/{r.partida:02d}: la CGR suma los Gobiernos "
                             f"Regionales por lo que gastan; el dataset, por lo que "
                             f"se les transfiere", anio=r.anio,
                 patron="perímetro de los Gobiernos Regionales")
    resto = t[~t.perimetro_gore]
    sin = resto[~resto.explicada]
    ok = len(resto) - len(sin)
    reg.ok("conciliacion", f"{ok} de {len(resto)} casos respondidos se explican "
                           f"completos por los criterios")
    for r in sin.itertuples():
        reg.warn("conciliacion", f"{r.anio}/{r.moneda}/{r.partida:02d}: "
                                 f"{r.sin_explicar:,.0f} miles sin explicar",
                 anio=r.anio, patron="diferencia sin explicar")

    print("\nA) Descomposición dataset − CGR (miles):")
    cols = ["anio", "moneda", "partida", "diferencia"] + COMPONENTES + ["perimetro_gore"]
    print(t[cols].round(0).to_string(index=False))
    return t


# =====================================================
# B) Transferencias eliminadas, todas las partidas
# =====================================================
def parte_b(reg: Registro) -> pd.DataFrame:
    cgr = transferencias_cgr()
    ds = dataset_por_subtitulo()
    ds = ds[ds.anio.isin(cgr.index.get_level_values("anio").unique())]
    dip = (ds.assign(eliminado=ds.ds_bruto - ds.ds_neto)
             .groupby(["anio", "moneda", "partida"]).eliminado.sum()
             .rename("dipres_eliminado"))
    t = pd.concat([cgr, dip], axis=1).fillna(0).reset_index()
    t = t[(t.cgr_eliminado != 0) | (t.dipres_eliminado != 0)]
    t["diferencia"] = t.dipres_eliminado - t.cgr_eliminado
    t.to_csv(REP / "conciliacion_cgr_transferencias.csv", index=False,
             encoding="utf-8-sig")
    dif = t[t.diferencia.abs() > TOL]
    reg.ok("transferencias", f"{len(t) - len(dif)} de {len(t)} partida·año·moneda "
                             f"eliminan lo mismo que la CGR")
    for p, g in dif.groupby("partida"):
        reg.warn("transferencias",
                 f"partida {int(p):02d}: DIPRES elimina distinto que la CGR en "
                 f"{len(g)} años (diferencia total {g.diferencia.sum() / 1000:,.0f} "
                 f"millones)", patron="transferencias eliminadas distintas")
    print("\nB) Transferencias eliminadas: DIPRES − CGR (millones), por partida:")
    print((dif.pivot_table(index="partida", columns="anio", values="diferencia",
                           aggfunc="sum") / 1000).round(0).fillna(0).to_string())
    return t


# =====================================================
# C) Las diferencias de VAL-2, una por una
# =====================================================
def parte_c(reg: Registro, a: pd.DataFrame | None, b: pd.DataFrame) -> None:
    try:
        v = pd.read_csv(REP / "validacion_cgr.csv")
    except FileNotFoundError:
        return
    v = v[(v.concepto == "devengado") & (v.estado == "difiere") & v.partida.notna()]
    v = v.assign(partida=v.partida.astype(int),
                 delta_miles=v.delta * v.moneda.map(ESCALA_15B))
    v = v.merge(b[["anio", "moneda", "partida", "diferencia"]]
                 .rename(columns={"diferencia": "transferencias_b"}),
                on=["anio", "moneda", "partida"], how="left").fillna({"transferencias_b": 0})
    # El 15b redondea a millones (o miles de US$): ±1 de redondeo por lado.
    # Además, hasta 1% de la diferencia: las dos cifras vienen de sumar
    # cientos de asignaciones redondeadas por separado
    tol = np.maximum(TOL + v.moneda.map(ESCALA_15B), 0.01 * v.delta_miles.abs())
    respondidos = set()
    if a is not None:
        resto = a[~a.perimetro_gore & a.explicada]
        respondidos = set(resto[["anio", "moneda", "partida"]].itertuples(index=False, name=None))
        perim = set(a[a.perimetro_gore][["anio", "moneda", "partida"]]
                    .itertuples(index=False, name=None))
    else:
        perim = set()
    def clase(r):
        k = (r.anio, r.moneda, r.partida)
        if k in perim or r.partida == GORE_DATASET:
            return "perímetro Gobiernos Regionales"
        if k in respondidos:
            return "respuesta CGR por subtítulo"
        if abs(r.delta_miles + r.transferencias_b) <= tol[r.Index]:
            return "transferencias eliminadas"
        # Mismo sentido y al menos la mitad: las transferencias explican parte
        if r.delta_miles * r.transferencias_b < 0 \
                and abs(r.transferencias_b) >= 0.5 * abs(r.delta_miles):
            return "transferencias eliminadas, en parte"
        return "sin explicar"
    v["explicacion"] = [clase(r) for r in v.itertuples()]
    v.to_csv(REP / "conciliacion_cgr_val2.csv", index=False, encoding="utf-8-sig")
    n = v.explicacion.value_counts()
    reg.ok("val2", f"{len(v) - int(n.get('sin explicar', 0))} de {len(v)} diferencias "
                   f"de devengado de VAL-2 quedan explicadas")
    sin = v[v.explicacion == "sin explicar"]
    for p, g in sin.groupby("partida"):
        reg.warn("val2", f"partida {p:02d}: {len(g)} diferencias sin explicar "
                         f"({', '.join(map(str, sorted(g.anio)))})",
                 patron="diferencia de VAL-2 sin explicar")
    print("\nC) Diferencias de VAL-2 por explicación:")
    print(n.to_string())
    print("\nSin explicar:")
    print(sin.assign(transferencias_b=(sin.transferencias_b / sin.moneda.map(ESCALA_15B)).round(1))
          [["anio", "moneda", "partida", "nombre", "delta", "transferencias_b"]]
          .to_string(index=False))


def main() -> None:
    reg = Registro("conciliacion_cgr", salida_dir=REP)
    if not RESPUESTA.exists():
        reg.info("respuesta_cgr", f"sin {RESPUESTA.name}: no hay respuesta que conciliar")
        reg.emitir()
        return
    a = parte_a(reg)
    b = parte_b(reg)
    parte_c(reg, a, b)
    reg.emitir()


if __name__ == "__main__":
    main()