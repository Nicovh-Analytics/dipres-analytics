"""
24_monitoreo_programas.py — ¿El gasto de los programas sociales se puede trazar a DIPRES?
========================================================================================
Cruza las bases de monitoreo de programas sociales (SES-DIPRES, publicadas
por el Ministerio de Desarrollo Social; las baja 03b) con la ejecución de
DIPRES (cruce_programa.csv).

A) Cruce por línea, 2018. La base 2018 es la única que publica la
   identificación presupuestaria completa: cada programa informa hasta tres
   fuentes (bloques PARTIDA … SUBTOTAL, PARTIDA_1 … SUBTOTAL_1, …) y en
   cada una el gasto del año, en miles, por subtítulo (24 y 33 abiertos por
   ítem y asignación). La unidad de cruce es la línea presupuestaria; varios
   programas pueden compartir una y se suman. Cada línea que no cuadra se
   clasifica mirando qué tiene DIPRES en ese programa.

B) Cota por capítulo, años sin identificación por línea (2022 en adelante:
   solo partida, capítulo y gasto total en miles de pesos del año
   siguiente). El gasto de los programas se lleva a pesos del año con la UF
   promedio y su suma por capítulo debe quedar bajo el gasto ejecutado del
   capítulo (subtítulos 21 y siguientes, pesos y dólares convertidos).

C) Detalle publicado. Qué identificación presupuestaria trae cada base.

Salidas (reports/):
  monitoreo_cruce_2018.csv       una fila por línea, con resultado y clase
  monitoreo_clases_2018.csv      líneas y gasto por clase y grupo
  monitoreo_resumen_2018.csv     cifras para la síntesis (MON-1)
  monitoreo_cota_capitulo.csv    año × capítulo (MON-2)
  monitoreo_detalle_publicado.csv

Uso:
    python pipeline/4_analisis/24_monitoreo_programas.py
"""

import re

import numpy as np
import pandas as pd

from dipres.config import DIRS
from dipres.dominio import a_pesos
from dipres.hallazgos import Registro

EXTERNO = DIRS.get("externo", DIRS["raw"] / "externo")
BIPS = EXTERNO / "bips"
UF_ANUAL = EXTERNO / "tipo_cambio" / "anual.csv"
REP = DIRS["reportes"]

ANIO_LINEA = 2018
TOL_PCT = 1.0        # una línea es "igual" si difiere menos que esto (% de DIPRES)
TOL_COTA_PCT = 1.0   # holgura de la cota por capítulo
RX_GASTO_SUB = re.compile(r"^GASTO_SUB_(\d\d)(?:_(\d\d))?(?:_(\d))?$")
# "Gasto total ejecutado 2024 (M$2025)" (2023-) o "PRESUPUESTO TOTAL EJECUTADO 2022\n(M$2023)"
RX_GASTO_TOTAL = re.compile(
    r"(?:gasto|presupuesto)\s+total\s+ejecutado\s+(\d{4})\s*\(m\$\s*(\d{4})\)", re.I)
# Programas que son gasto tributario (renuncia a recaudar), no gasto ejecutado
RX_TRIBUTARIO = re.compile(r"franquicia tributaria|cr[eé]dito tributario|exenci[oó]n tributaria", re.I)
CLAVES = ["Partida", "Capítulo", "Programa", "Subtítulo", "Item", "Asignación"]

GRUPOS = {
    "igual": "cuadra",
    "declara el subtítulo completo": "cuadra",
    "excede el ítem, cabe en el subtítulo": "cuadra a nivel subtítulo",
    "menor que DIPRES": "menor que DIPRES",
    "monto excede DIPRES": "excede a DIPRES",
    "suma de programas excede": "excede a DIPRES",
    "asignación inexistente en el programa": "línea mal imputada",
    "subtítulo inexistente en el programa": "línea mal imputada",
    "misma asignación en otro ítem": "línea mal imputada",
    "programa inexistente en DIPRES": "línea mal imputada",
    "programa no informado": "línea mal imputada",
}
ORDEN_GRUPOS = ["cuadra", "cuadra a nivel subtítulo", "menor que DIPRES",
                "excede a DIPRES", "línea mal imputada"]


# =====================================================
# A) Cruce por línea (2018)
# =====================================================
def bloques(cols: list[str]) -> list[tuple[str, list[str]]]:
    """[(sufijo, columnas)], un bloque por fuente: de PARTIDA{k} a SUBTOTAL{k}."""
    out = []
    for k in ["", "_1", "_2", "_3", "_4"]:
        if f"PARTIDA{k}" in cols and f"SUBTOTAL{k}" in cols:
            i, j = cols.index(f"PARTIDA{k}"), cols.index(f"SUBTOTAL{k}")
            out.append((k, cols[i:j + 1]))
    return out


def normalizar_codigo(valor, sub: int, item_col) -> tuple:
    """(ítem, asignación, estado) a partir del código informado. Formatos:
    700 (asignación) · 1009 (ítem 01 + asig. 009) · 2301001 (subt + ítem +
    asig.) · 198004520 (un monto en el campo del código: la línea queda sin
    asignación y se compara a nivel ítem/subtítulo)."""
    if pd.isna(valor):
        return item_col, np.nan, "ok"
    s = (str(int(valor)) if isinstance(valor, (int, float, np.integer, np.floating))
         else re.sub(r"\D", "", str(valor)))
    if not s:
        return item_col, np.nan, "ok"
    sb = f"{sub:02d}"
    if s in (str(sub), sb):                      # código del subtítulo: sin asignación
        return item_col, np.nan, "ok"
    if s.startswith(sb) and len(s) == 4:         # 2403: solo ítem
        it, asg = int(s[2:]), np.nan
    elif s.startswith(sb) and len(s) in (6, 7):  # 2403700 / 243700
        it, asg = int(s[2:-3]), int(s[-3:])
    elif len(s) <= 3:                            # 700
        it, asg = item_col, int(s)
    elif len(s) in (4, 5):                       # 1009 / 03700
        it, asg = int(s[:-3]), int(s[-3:])
    else:
        return item_col, np.nan, "monto en el campo código"
    if not pd.isna(item_col) and it != item_col:
        return item_col, asg, "ítem del código difiere"
    return it, asg, "ok"


def monitoreo_largo(p: pd.DataFrame) -> pd.DataFrame:
    """Una fila por programa × fuente × línea con gasto."""
    cols = list(p.columns)
    filas = []
    for k, bloque in bloques(cols):
        prog_col = next((c for c in bloque if c.startswith("PROGRAMA")), None)
        for c in bloque:
            m = RX_GASTO_SUB.match(c[: -len(k)] if k and c.endswith(k) else c)
            if not m:
                continue
            sub, item, _ = m.groups()
            asig_col = c.replace("GASTO_SUB_", "ASIGNACION_SUB_", 1)
            gasto = pd.to_numeric(p[c], errors="coerce")
            g = p[gasto.fillna(0) != 0]
            if g.empty:
                continue
            item_col = int(item) if item else np.nan
            crudo = g[asig_col] if asig_col in cols else pd.Series(np.nan, index=g.index)
            norm = [normalizar_codigo(v, int(sub), item_col) for v in crudo]
            filas.append(pd.DataFrame({
                "id_bips": g["ID_BIPS"], "nombre": g["NOMBRE"], "fuente": k or "_0",
                "Partida": pd.to_numeric(g[f"PARTIDA{k}"], errors="coerce"),
                "Capítulo": pd.to_numeric(g[f"CAPITULO{k}"], errors="coerce"),
                "Programa": (pd.to_numeric(g[prog_col], errors="coerce")
                             if prog_col else np.nan),
                "Subtítulo": int(sub),
                "Item": [n[0] for n in norm],
                "Asignación": [n[1] for n in norm],
                "estado_codigo": [n[2] for n in norm],
                "gasto_monitoreo": gasto[g.index],
            }))
    return pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()


def leer_ejecucion(anio: int, monedas=("PESOS",)) -> pd.DataFrame:
    """Ejecución acumulada a diciembre de `anio` desde cruce_programa (miles)."""
    cols = ["Año", "Mes", "Moneda"] + CLAVES + ["ejecucion_acumulada"]
    c = pd.read_csv(DIRS["consolidado"] / "cruce_programa.csv", encoding="utf-8-sig",
                    usecols=lambda k: k in cols, low_memory=False)
    return c[(c["Año"] == anio) & (c["Mes"] == "Diciembre")
             & c["Moneda"].str.upper().isin(monedas)]


def cruce_lineas(ml: pd.DataFrame, e: pd.DataFrame) -> pd.DataFrame:
    k3c, k4c = CLAVES[:3], CLAVES[:4]
    ee = (e.groupby(CLAVES, dropna=False).ejecucion_acumulada.sum().reset_index())
    por_sub = dict(tuple(ee.groupby(k4c)))
    progs = set(ee[k3c].itertuples(index=False, name=None))
    tot_sub = ee.groupby(k4c).ejecucion_acumulada.sum()

    lin = (ml.groupby(CLAVES, dropna=False)
             .agg(gasto_monitoreo=("gasto_monitoreo", "sum"),
                  programas=("id_bips", "nunique"),
                  nombres=("nombre", lambda s: " | ".join(sorted(set(map(str, s))))[:150]))
             .reset_index())

    def dipres(r) -> float:
        if np.isnan(r.Programa):     # sin programa: todo el capítulo
            g = ee[(ee.Partida == r.Partida) & (ee["Capítulo"] == r.Capítulo)
                   & (ee["Subtítulo"] == r.Subtítulo)]
        else:
            g = por_sub.get((r.Partida, r.Capítulo, r.Programa, r.Subtítulo))
            if g is None:
                return 0.0
        if not np.isnan(r.Item):
            g = g[g["Item"] == r.Item]
        if not np.isnan(r.Asignación):
            g = g[g["Asignación"] == r.Asignación]
        return float(g.ejecucion_acumulada.sum())

    lin["ejecucion_dipres"] = [dipres(r) for r in lin.itertuples()]
    lin["nivel"] = np.where(lin["Asignación"].notna(), "asignación", "subtítulo")
    lin["dif"] = lin.gasto_monitoreo - lin.ejecucion_dipres
    lin["razon"] = np.where(lin.ejecucion_dipres != 0,
                            lin.gasto_monitoreo / lin.ejecucion_dipres, np.nan)
    lin["resultado"] = np.select(
        [lin.ejecucion_dipres == 0, (lin.razon - 1).abs() * 100 <= TOL_PCT, lin.dif < 0],
        ["sin línea en DIPRES", "igual", "menor que DIPRES"], "mayor que DIPRES")

    def clase(r) -> str:
        if r.resultado in ("igual", "menor que DIPRES"):
            return r.resultado
        if np.isnan(r.Programa):
            return "programa no informado"
        k3 = (r.Partida, r.Capítulo, r.Programa)
        k4 = k3 + (r.Subtítulo,)
        if k3 not in progs:
            return "programa inexistente en DIPRES"
        if k4 not in por_sub:
            return "subtítulo inexistente en el programa"
        if (r.resultado == "mayor que DIPRES" and np.isnan(r.Asignación)
                and not np.isnan(r.Item)):
            t = tot_sub[k4]       # ¿el subtítulo completo puesto en un ítem?
            if t and abs(r.gasto_monitoreo / t - 1) * 100 <= TOL_PCT:
                return "declara el subtítulo completo"
            if r.gasto_monitoreo <= t:
                return "excede el ítem, cabe en el subtítulo"
        if not np.isnan(r.Asignación):
            g = por_sub[k4]
            otro = g[(g["Asignación"] == r.Asignación) & (g["Item"] != r.Item)]
            cerca = ((otro.ejecucion_acumulada - r.gasto_monitoreo).abs()
                     <= 0.1 * r.gasto_monitoreo).any()
            if len(otro) and (r.resultado == "sin línea en DIPRES" or cerca):
                return "misma asignación en otro ítem"
        if r.resultado == "sin línea en DIPRES":
            return "asignación inexistente en el programa"
        return "suma de programas excede" if r.programas > 1 else "monto excede DIPRES"

    lin["clase"] = [clase(r) for r in lin.itertuples()]
    lin["grupo"] = lin.clase.map(GRUPOS)
    return lin


def parte_a(reg: Registro) -> None:
    ruta = BIPS / f"base_{ANIO_LINEA}.xlsx"
    if not ruta.exists():
        reg.error("cruce_linea", f"falta {ruta.name}: correr 03b_descargar_monitoreo.py")
        return
    p = pd.read_excel(ruta, sheet_name="Presupuesto")
    ml = monitoreo_largo(p)
    if ml.empty:
        reg.error("cruce_linea", f"{ruta.name}: no se reconocieron columnas GASTO_SUB_ "
                                 f"en la hoja Presupuesto")
        return
    e = leer_ejecucion(ANIO_LINEA)
    if e.empty:
        reg.error("cruce_linea", f"cruce_programa no trae diciembre {ANIO_LINEA}")
        return
    lin = cruce_lineas(ml, e)
    lin.to_csv(REP / f"monitoreo_cruce_{ANIO_LINEA}.csv", index=False, encoding="utf-8-sig")

    total = lin.gasto_monitoreo.sum()
    cl = (lin.groupby(["grupo", "clase"])
             .agg(lineas=("dif", "size"), gasto=("gasto_monitoreo", "sum"))
             .reset_index())
    cl["pct_gasto"] = cl.gasto / total * 100
    cl["pct_lineas"] = cl.lineas / len(lin) * 100
    cl["orden"] = cl.grupo.map(ORDEN_GRUPOS.index)
    cl = cl.sort_values(["orden", "gasto"], ascending=[True, False]).drop(columns="orden")
    cl.to_csv(REP / f"monitoreo_clases_{ANIO_LINEA}.csv", index=False, encoding="utf-8-sig")

    gr = lin.groupby("grupo").agg(lineas=("dif", "size"), gasto=("gasto_monitoreo", "sum"))
    pg = lambda g: gr.gasto.get(g, 0) / total * 100
    pl = lambda g: gr.lineas.get(g, 0) / len(lin) * 100
    n_monto = int((ml.estado_codigo == "monto en el campo código").sum())
    resumen = {
        "anio": ANIO_LINEA, "programas": p["ID_BIPS"].nunique(),
        "declaraciones": len(ml), "lineas": len(lin), "gasto_total": total,
        "pct_gasto_cuadra": pg("cuadra"),
        "pct_gasto_cuadra_subtitulo": pg("cuadra a nivel subtítulo"),
        "pct_gasto_menor": pg("menor que DIPRES"),
        "pct_gasto_excede": pg("excede a DIPRES"),
        "pct_gasto_mal_imputada": pg("línea mal imputada"),
        "pct_lineas_excede": pl("excede a DIPRES"),
        "pct_lineas_mal_imputada": pl("línea mal imputada"),
        "lineas_excede": int(gr.lineas.get("excede a DIPRES", 0)),
        "lineas_mal_imputada": int(gr.lineas.get("línea mal imputada", 0)),
        "celdas_monto_en_codigo": n_monto,
        "programas_monto_en_codigo": ml.loc[ml.estado_codigo == "monto en el campo código",
                                            "id_bips"].nunique(),
    }
    pd.Series(resumen).to_csv(REP / f"monitoreo_resumen_{ANIO_LINEA}.csv",
                              header=["valor"], index_label="indicador", encoding="utf-8-sig")

    print(f"\nA) Cruce por línea {ANIO_LINEA}: {resumen['programas']} programas · "
          f"{len(lin)} líneas · {total / 1e9:,.2f} billones")
    print(cl.assign(gasto=(cl.gasto / 1e9).round(3), pct_gasto=cl.pct_gasto.round(1),
                    pct_lineas=cl.pct_lineas.round(1)).to_string(index=False))

    reg.ok("cruce_linea", f"{ANIO_LINEA}: {resumen['pct_gasto_cuadra'] + resumen['pct_gasto_cuadra_subtitulo']:.1f}% "
                          f"del gasto declarado cuadra con DIPRES (exacto o a nivel subtítulo)",
           anio=ANIO_LINEA)
    if resumen["lineas_mal_imputada"]:
        reg.warn("cruce_linea", f"{ANIO_LINEA}: {resumen['lineas_mal_imputada']} líneas "
                                f"declaran una línea presupuestaria inexistente",
                 patron="línea mal imputada", anio=ANIO_LINEA)
    if resumen["lineas_excede"]:
        reg.warn("cruce_linea", f"{ANIO_LINEA}: {resumen['lineas_excede']} líneas declaran "
                                f"más que lo ejecutado por DIPRES",
                 patron="gasto declarado sobre la ejecución", anio=ANIO_LINEA)
    if n_monto:
        reg.warn("cruce_linea", f"{ANIO_LINEA}: {n_monto} celdas traen un monto en el "
                                f"campo del código presupuestario",
                 patron="monto en el campo código", anio=ANIO_LINEA)


# =====================================================
# B) Cota por capítulo (años sin línea)
# =====================================================
def uf_anual() -> dict[int, float]:
    if not UF_ANUAL.exists():
        raise FileNotFoundError(f"{UF_ANUAL} no existe: correr 04_tipos_cambio.py")
    u = pd.read_csv(UF_ANUAL, encoding="utf-8-sig")
    return dict(zip(u["anio"].astype(int), u["uf"]))


def hoja_con_gasto_total(ruta) -> tuple | None:
    """(df, col_gasto, col_partida, col_capítulo, col_nombre, año, año_moneda) o None."""
    for _, d in pd.read_excel(ruta, sheet_name=None).items():
        cg = next((c for c in d.columns if RX_GASTO_TOTAL.search(str(c))), None)
        cp = next((c for c in d.columns if re.search(r"partida", str(c), re.I)), None)
        cc = next((c for c in d.columns if re.search(r"cap[ií]tulo", str(c), re.I)), None)
        cn = next((c for c in d.columns if re.match(r"\s*nombre\s*$", str(c), re.I)), None)
        if cg and cp and cc:
            m = RX_GASTO_TOTAL.search(str(cg))
            return d, cg, cp, cc, cn, int(m.group(1)), int(m.group(2))
    return None


def parte_b(reg: Registro, bases: list) -> None:
    """Cota por capítulo. Si el capítulo no alcanza: (1) sin los programas que
    son gasto tributario (franquicias, créditos), que no pasan por la
    ejecución; (2) contra la partida, porque un programa que ejecutan varios
    servicios (SERVIU, servicios de salud) se declara entero en un capítulo.
    Que la partida lo cubra no prueba que el gasto esté ahí (partidas grandes
    lo cubren casi todo): solo que la cota ya no lo puede refutar."""
    filas = []
    uf = None
    tope = 1 + TOL_COTA_PCT / 100
    for ruta in bases:
        h = hoja_con_gasto_total(ruta)
        if h is None:
            continue
        d, cg, cp, cc, cn, anio, anio_m = h
        try:
            uf = uf or uf_anual()
        except FileNotFoundError as err:
            reg.error("cota_capitulo", str(err))
            return
        if anio not in uf or anio_m not in uf:
            reg.error("cota_capitulo", f"{ruta.name}: falta la UF promedio de {anio} o {anio_m}")
            continue
        factor = uf[anio] / uf[anio_m]
        m = pd.DataFrame({"Partida": pd.to_numeric(d[cp], errors="coerce"),
                          "Capítulo": pd.to_numeric(d[cc], errors="coerce"),
                          "nombre": d[cn].astype(str) if cn else "",
                          "gasto": pd.to_numeric(d[cg], errors="coerce") * factor})
        m["tributario"] = m.gasto.where(m.nombre.str.contains(RX_TRIBUTARIO), 0)
        sin_id = m[["Partida", "Capítulo"]].isna().any(axis=1)
        if sin_id.any():
            reg.info("cota_capitulo", f"{anio}: {int(sin_id.sum())} programas sin partida "
                                      f"o capítulo (no entran a la cota)", anio=anio)
        m = m[~sin_id]
        mayor = m.loc[m.groupby(["Partida", "Capítulo"]).gasto.idxmax()] \
                 .set_index(["Partida", "Capítulo"])
        mon = (m.groupby(["Partida", "Capítulo"])
                .agg(monitoreo=("gasto", "sum"), programas=("gasto", "size"),
                     gasto_tributario=("tributario", "sum")))
        mon["programa_mayor"] = mayor.nombre
        mon["gasto_programa_mayor"] = mayor.gasto
        mon["programa_tributario"] = (m[m.tributario > 0]
                                      .groupby(["Partida", "Capítulo"]).nombre.first())

        e = leer_ejecucion(anio, monedas=("PESOS", "DOLARES"))
        if e.empty:
            reg.error("cota_capitulo", f"cruce_programa no trae diciembre {anio}")
            continue
        e = a_pesos(e[e["Subtítulo"] >= 21], ["ejecucion_acumulada"], "observado")
        dip = e.groupby(["Partida", "Capítulo"]).ejecucion_acumulada.sum().rename("dipres")

        t = mon.join(dip, how="left").reset_index()
        t.insert(0, "anio", anio)
        t["factor_uf"] = factor
        t["razon"] = t.monitoreo / t.dipres
        t["monitoreo_partida"] = t.Partida.map(m.groupby("Partida").gasto.sum())
        t["dipres_partida"] = t.Partida.map(e.groupby("Partida").ejecucion_acumulada.sum())
        t["razon_partida"] = t.monitoreo_partida / t.dipres_partida
        t["resultado"] = np.select(
            [t.dipres.isna() | (t.dipres <= 0), t.razon <= tope,
             (t.monitoreo - t.gasto_tributario) / t.dipres <= tope,
             t.razon_partida <= tope],
            ["capítulo sin ejecución en DIPRES", "dentro",
             "excede solo por gasto tributario declarado",
             "excede el capítulo, la partida lo cubre"], "excede")
        filas.append(t)

        ok = int((t.resultado == "dentro").sum())
        reg.ok("cota_capitulo", f"{anio}: {ok} de {len(t)} capítulos quedan bajo la "
                                f"ejecución", anio=anio)
        fmt = lambda x, col: "; ".join(f"{int(r.Partida):02d}-{int(r.Capítulo):02d} "
                                        f"×{r.razon:.2f} ({getattr(r, col)})"
                                        for r in x.itertuples())
        for res, patron, col in [
                ("excede solo por gasto tributario declarado",
                 "gasto tributario declarado como gasto ejecutado", "programa_tributario"),
                ("excede el capítulo, la partida lo cubre",
                 "programas sobre la ejecución de su capítulo", "programa_mayor"),
                ("excede", "programas sobre la ejecución de su partida", "programa_mayor")]:
            x = t[t.resultado == res].nlargest(3, "monitoreo")
            if len(x):
                reg.warn("cota_capitulo", f"{anio}: {len(t[t.resultado == res])} capítulos "
                                          f"— {res} (p. ej. {fmt(x, col)})",
                         patron=patron, anio=anio)
        sinej = int((t.resultado == "capítulo sin ejecución en DIPRES").sum())
        if sinej:
            reg.warn("cota_capitulo", f"{anio}: {sinej} capítulos declarados no tienen "
                                      f"ejecución en DIPRES",
                     patron="capítulo inexistente en DIPRES", anio=anio)

    if filas:
        out = pd.concat(filas, ignore_index=True)
        out.to_csv(REP / "monitoreo_cota_capitulo.csv", index=False, encoding="utf-8-sig")
        print("\nB) Cota por capítulo:")
        print(out.groupby(["anio", "resultado"]).size().unstack(fill_value=0).to_string())


# =====================================================
# C) Detalle publicado
# =====================================================
def nivel_publicado(ruta) -> str:
    cols = set()
    for _, d in pd.read_excel(ruta, sheet_name=None, nrows=0).items():
        cols |= {str(c) for c in d.columns}
    up = {c.upper().strip() for c in cols}
    prog = any(re.fullmatch(r"(CLASIFICADOR_PRESUPUESTARIO_)?PROGRAMA(_?\d+)?", c) for c in up)
    if prog and any(c.startswith("ASIGNACION_SUB_") for c in up):
        return "línea (programa, subtítulo, ítem y asignación)"
    if prog and any("PARTIDA" in c for c in up):
        return "programa presupuestario"
    if any("PARTIDA" in c for c in up) and any(re.search(r"CAP[IÍ]TULO", c) for c in up):
        return "capítulo"
    if any("NOMBRE DE LA ASIGNACI" in c for c in up):
        return "nombre de la asignación, sin código"
    return "sin identificación presupuestaria"


def parte_c(reg: Registro, bases: list) -> None:
    filas = []
    for ruta in bases:
        anio = int(re.search(r"(\d{4})", ruta.stem).group(1))
        filas.append({"base": anio, "archivo": ruta.name, "nivel": nivel_publicado(ruta)})
    t = pd.DataFrame(filas)
    t.to_csv(REP / "monitoreo_detalle_publicado.csv", index=False, encoding="utf-8-sig")
    print("\nC) Identificación presupuestaria publicada:")
    print(t.to_string(index=False))
    for r in t.itertuples():
        reg.info("detalle_publicado", f"base {r.base}: {r.nivel}", anio=r.base)


def main() -> None:
    reg = Registro("monitoreo_programas", salida_dir=REP)
    bases = sorted(BIPS.glob("base_*.xlsx"))
    if not bases:
        reg.error("bases", f"no hay bases en {BIPS}: correr 03b_descargar_monitoreo.py")
        reg.emitir()
        return
    parte_a(reg)
    parte_b(reg, [b for b in bases if b.stem != f"base_{ANIO_LINEA}"])
    parte_c(reg, bases)
    reg.emitir()


if __name__ == "__main__":
    main()