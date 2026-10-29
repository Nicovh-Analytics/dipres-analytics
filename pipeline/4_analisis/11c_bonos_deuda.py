"""
11c_bonos_deuda.py — Bonos del Gobierno Central, serie por serie
================================================================
Extrae de los Reportes Trimestrales de Deuda Bruta del Gobierno Central
(DIPRES), edición de diciembre de cada año, las tablas de bonos vigentes:
locales (BTP en pesos, BTU en UF) e internacionales (globales en dólares,
euros y pesos). Con ellas calcula lo emitido en cada año, serie por serie:

    emitido(t) = monto colocado a dic. t − monto colocado a dic. t−1

El monto colocado de una serie es acumulado: crece con cada reapertura y no
baja con las recompras (lo que baja es el circulante). Una serie que aparece
por primera vez en t se cuenta completa si su fecha de emisión es de t.

Límite: una serie emitida y vencida entre dos reportes no aparece en
ninguno, y su emisión se pierde. Desde 2022 hay BTP cero cupón de corto plazo
(menos de un año) para los que esto puede pasar: entre diciembre 2023 y
diciembre 2025, tres de ellos (3,9 billones de pesos) solo se ven gracias
al reporte de marzo 2025. El cruce con el subtítulo 14 dimensiona lo que falte.

Validación: la suma de las series de cada tabla debe cuadrar con la fila de
total del mismo reporte (colocado y circulante). Una tabla que no cuadra se
informa: es señal de una fila mal leída.

Reportes intermedios: las ediciones de septiembre y diciembre 2024 publican
un "monto colocado" de los bonos locales que no es el acumulado (ver
tablas_no_acumuladas). Para no perder esos años se usa un reporte trimestral
con colocado acumulado (marzo 2025) como base intermedia, solo en las tablas
donde la cadena de diciembres está rota. El periodo resultante abarca más o
menos de un año (p. ej. "2024-01 a 2025-03").

Fuente: dipres.gob.cl, Reporte Trimestral de Deuda Bruta del Gobierno
Central. Los PDF se descargan a mano y se guardan como
    raw/externo/deuda/dic_AAAA.pdf     (2016 sirve de base para 2017)
    raw/externo/deuda/mar_AAAA.pdf     (u otro trimestre: mar, jun, sep)

Montos en la unidad de cada tabla:
    BTP y globales en CLP   millones de pesos
    BTU                     millones de UF
    globales en USD         millones de US$
    globales en EUR         millones de euros

Salidas en DIRS["reportes"]:
  deuda_bonos.csv       RESPALDO: cada serie en cada reporte leído
  deuda_emisiones.csv   emitido por periodo y serie, en la moneda de la serie
  deuda_prepagos.csv    prepagos de deuda por año (anexo "Prepagos de Deuda
                        Interna y Externa"), en millones de US$, según el
                        reporte más reciente que informa cada año

Prepagos: cada reporte trae el anexo con todos los años desde 1995, y las
ediciones posteriores corrigen cifras (2020: 6.813,9 en dic. 2024, 6.797,5
en dic. 2025). Se usa la cifra del reporte más reciente y se informan las
revisiones.

Uso:
    python pipeline/4_analisis/11c_bonos_deuda.py
"""

import re
from pathlib import Path

import pandas as pd
import pdfplumber

from dipres.config import DIRS

DIR_DEUDA = DIRS.get("externo", DIRS["raw"] / "externo") / "deuda"
REP = DIRS["reportes"]
TOL = 0.11              # diferencia admitida por serie (redondeo a 0,1)
TOL_FILA = 0.051        # contra el total: cada serie redondeada aporta ±0,05
MESES = {"mar": 3, "jun": 6, "sep": 9, "dic": 12}

FECHA = r"\d{2}[-/]\d{2}[-/]\d{4}"     # 2024 usa barras
NUM = r"\d[\d\.]*(?:,\d+)?"
TASA = r"-?\d+(?:,\d+)?"                # bonos sin cupón con tasa negativa
FILA = re.compile(
    rf"(?P<nemo>BT[PU]\w+|Global \d{{4}}.*?)\s+(?P<emision>{FECHA})\s+"
    rf"(?P<vencimiento>{FECHA})\s+(?P<colocado>{NUM})\s+(?P<circulante>{NUM})"
    rf"\s+(?P<cupon>{TASA})\s+(?P<tasa>{TASA})\s*(?P<pago>.*)$")
TOTAL = re.compile(
    rf"^Total (?P<grupo>BTP|BTU|Global)[^(]*\((?P<unidad>MM ?[^)]+)\)\s+"
    rf"(?P<colocado>{NUM})\s+(?P<circulante>{NUM})")


def texto(pagina) -> str:
    """
    Texto de la página. Algunas ediciones marcan los caracteres de la tabla
    internacional como girados (upright=False) aunque se ven horizontales;
    pdfplumber los leería como columnas verticales. Se fuerzan a horizontal.
    """
    p = pagina.filter(lambda o: True)
    for c in p.chars:
        c["upright"] = True
    t = p.extract_text(x_tolerance=1.5, y_tolerance=2) or ""
    # Algunas ediciones usan guiones tipográficos en las fechas (01‐03‐2015)
    t = re.sub("[\u2010\u2011\u2012\u2013]", "-", t)
    # Espacios falsos dentro de los números: "1 .234.600", "4 ,2",
    # "2 5,0", "1 3.472.510". Regla: un dígito suelto (no precedido de otro
    # dígito, punto o coma) seguido de espacio y otro dígito es el mismo
    # número. En estas tablas ningún valor es un entero de un dígito, y las
    # fechas y los días de pago ("1 mar") no calzan con el patrón.
    t = re.sub(r"(?<=\d) (?=[\.,]\d)", "", t)
    t = re.sub(r"(?<![\d\.,])(\d) (?=\d)", r"\1", t)
    return t


def fecha(s: str) -> pd.Timestamp:
    return pd.to_datetime(s.replace("/", "-"), format="%d-%m-%Y")


def numero(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def moneda_de(nemo: str) -> str:
    if nemo.startswith("BTP"):
        return "CLP"
    if nemo.startswith("BTU"):
        return "UF"
    n = nemo.upper()
    if "EUR" in n:
        return "EUR"
    if "CLP" in n:
        return "CLP"
    return "USD"


def grupo_de(moneda: str, nemo: str) -> str:
    """Grupo de la fila de total que la suma: BTP, BTU o Global por moneda."""
    if nemo.startswith(("BTP", "BTU")):
        return nemo[:3]
    return f"Global {moneda}"


def grupo_total(grupo: str, unidad: str) -> str:
    if grupo != "Global":
        return grupo
    u = unidad.upper()
    return "Global " + ("EUR" if "EURO" in u else "CLP" if "CLP" in u else "USD")


def leer_reporte(ruta: Path, corte: pd.Period) -> tuple[pd.DataFrame,
                                                        pd.DataFrame]:
    """Series y filas de total de un reporte; corte = mes del reporte."""
    filas, totales = [], []
    with pdfplumber.open(ruta) as pdf:
        for i, pag in enumerate(pdf.pages, 1):
            for linea in texto(pag).splitlines():
                m = FILA.search(linea)
                if m:
                    d = m.groupdict()
                    nemo = re.sub(r"\s+", " ", d["nemo"]).strip()
                    mon = moneda_de(nemo)
                    filas.append({
                        "corte": str(corte), "anio": corte.year,
                        "pagina": i, "nemo": nemo, "moneda": mon,
                        "grupo": grupo_de(mon, nemo),
                        "mercado": "local" if nemo.startswith("BT")
                                   else "internacional",
                        "emision": fecha(d["emision"]),
                        "vencimiento": fecha(d["vencimiento"]),
                        "colocado": numero(d["colocado"]),
                        "circulante": numero(d["circulante"]),
                        "cupon": numero(d["cupon"]),
                        "tasa_colocacion": numero(d["tasa"]),
                        "pago_cupon": d["pago"].strip()})
                    continue
                t = TOTAL.search(linea.strip())
                if t:
                    totales.append({
                        "corte": str(corte), "pagina": i,
                        "grupo": grupo_total(t["grupo"], t["unidad"]),
                        "total_colocado": numero(t["colocado"]),
                        "total_circulante": numero(t["circulante"])})
    return pd.DataFrame(filas), pd.DataFrame(totales)


PREPAGO = re.compile(r"(?<!\d)((?:19|20)\d{2})\s+([\d\.]+,\d)\s+millones")


def leer_prepagos(ruta: Path, corte: pd.Period) -> pd.DataFrame:
    """Anexo de prepagos (millones de US$, face value consolidado)."""
    filas = []
    with pdfplumber.open(ruta) as pdf:
        for pag in pdf.pages:
            t = texto(pag)
            if "Prepagos de Deuda Interna y Externa" not in t:
                continue
            for anio, monto in PREPAGO.findall(t):
                filas.append({"anio": int(anio), "prepago_musd": numero(monto),
                              "corte": str(corte)})
            break
    return pd.DataFrame(filas)


def prepagos_vigentes(p: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cifra del reporte más reciente por año, y las revisiones entre ediciones."""
    p = p.drop_duplicates(["anio", "corte"]).sort_values(["anio", "corte"])
    ult = p.groupby("anio").tail(1).reset_index(drop=True)
    rev = (p.groupby("anio").prepago_musd.agg(["min", "max"])
             .query("max - min > 0.05").reset_index())
    return ult, rev


def validar(bonos: pd.DataFrame, totales: pd.DataFrame) -> pd.DataFrame:
    s = (bonos.groupby(["corte", "grupo"], as_index=False)
              [["colocado", "circulante"]].sum())
    # Puede haber más de una fila "Total BTP" en el reporte (otros cuadros);
    # se compara contra la de la misma página que las series
    pag = bonos.groupby(["corte", "grupo"]).pagina.max().rename("pagina")
    t = totales.merge(pag.reset_index(), on=["corte", "grupo", "pagina"])
    v = s.merge(t, on=["corte", "grupo"], how="left")
    v["dif_colocado"] = v.colocado - v.total_colocado
    v["dif_circulante"] = v.circulante - v.total_circulante
    n = bonos.groupby(["corte", "grupo"]).size().rename("n").reset_index()
    v = v.merge(n, on=["corte", "grupo"])
    tol = TOL_FILA * v.n + 0.01
    v["cuadra"] = (v.dif_colocado.abs() <= tol) & (v.dif_circulante.abs() <= tol)
    return v


def tablas_no_acumuladas(bonos: pd.DataFrame) -> set:
    """
    Tablas (corte, grupo) cuyo "monto colocado" no es el acumulado: alguna
    serie tiene más circulante que colocado, lo que es imposible si el
    colocado suma todas las reaperturas. Pasa en las ediciones de septiembre
    y diciembre 2024 (bonos locales). Esas tablas no sirven de base.
    """
    malo = bonos[bonos.circulante > bonos.colocado + TOL]
    return set(zip(malo.corte, malo.grupo))


def clave_serie(b: pd.DataFrame) -> pd.Series:
    """
    Locales: el nemotécnico. Globales: moneda + año de emisión + año de
    vencimiento. Ni el nombre ni el cupón sirven de clave porque cambian
    entre ediciones (el cupón de los dos Global 2042 en USD aparece cruzado en
    2025; en 2021 un bono a 2029 figura como "Global 2027"). Las reaperturas
    que van en fila aparte comparten clave y se suman.
    """
    glob = ("Global " + b.moneda + " " + b.emision.dt.year.astype(str) + "→"
            + b.vencimiento.dt.year.astype(str))
    return b.nemo.where(b.mercado == "local", glob)


def emparejar(ahora: pd.DataFrame, antes: pd.DataFrame) -> dict:
    """
    {serie actual: serie en el reporte base}. Exacto por clave; para los
    globales sin pareja, se acepta la del mismo año de emisión y moneda con
    vencimiento a ±1 año (el Global 2050 en USD vence "25-07-2049" en 2019-2020
    y "25-01-2050" desde 2021).
    """
    base = set(antes.serie)
    par = {s: s for s in ahora.serie if s in base}
    libres = antes[~antes.serie.isin(par.values())]
    for r in ahora[~ahora.serie.isin(par)].itertuples():
        if r.mercado == "local":
            continue
        c = libres[(libres.moneda == r.moneda)
                   & (libres.emision.dt.year == r.emision.year)
                   & ((libres.vencimiento.dt.year - r.vencimiento.year).abs() <= 1)]
        if len(c) == 1:
            par[r.serie] = c.serie.iloc[0]
            libres = libres[libres.serie != c.serie.iloc[0]]
    return par


def cadena(cortes: list[str], grupo: str, malas: set) -> list[str]:
    """
    Reportes que se restan, en orden, para un grupo. Los de diciembre, salvo
    los que no tienen colocado acumulado; los trimestrales solo si la cadena
    de diciembres de ese grupo está rota (si no, partirían años completos).
    """
    rota = any((c, grupo) in malas for c in cortes if c.endswith("-12"))
    return [c for c in cortes if (c, grupo) not in malas
            and (c.endswith("-12") or rota)]


def etiqueta(base: str, corte: str) -> str:
    """'2023-12' → '2024-12' da '2024'; otro tramo da 'AAAA-MM a AAAA-MM'."""
    b, c = pd.Period(base, "M"), pd.Period(corte, "M")
    if b.month == 12 and c.month == 12 and c.year == b.year + 1:
        return str(c.year)
    return f"{b + 1} a {c}"


def emisiones(bonos: pd.DataFrame) -> pd.DataFrame:
    """
    Emitido por serie entre dos reportes consecutivos de la cadena de cada
    grupo (ver cadena). Una serie nueva se cuenta completa si su fecha de
    emisión es posterior al reporte base.
    """
    b = bonos.copy()
    b["serie"] = clave_serie(b)
    malas = tablas_no_acumuladas(b)
    b = (b.groupby(["corte", "anio", "serie", "grupo", "mercado", "moneda"],
                   as_index=False)
          .agg(emision=("emision", "min"), vencimiento=("vencimiento", "max"),
               colocado=("colocado", "sum"), circulante=("circulante", "sum")))
    cortes = sorted(b.corte.unique())
    filas = []
    for g in sorted(b.grupo.unique()):
        c_g = [c for c in cadena(cortes, g, malas)
               if ((b.corte == c) & (b.grupo == g)).any()]
        for base, corte in zip(c_g, c_g[1:]):
            ahora = b[(b.corte == corte) & (b.grupo == g)]
            antes = b[(b.corte == base) & (b.grupo == g)]
            fin_base = pd.Period(base, "M").end_time
            par = emparejar(ahora, antes)
            col_antes = antes.set_index("serie").colocado
            for r in ahora.itertuples():
                if r.serie in par:
                    previo = float(col_antes[par[r.serie]])
                    estado = ("reapertura" if r.colocado > previo + TOL
                              else "sin cambio")
                elif r.emision > fin_base:
                    previo, estado = 0.0, "nueva"
                else:
                    # Existía antes pero no figura en el reporte base
                    previo, estado = 0.0, "ausente en la base"
                emitido = r.colocado - previo
                if emitido < -TOL:
                    estado = "colocado baja"
                filas.append({
                    "anio": r.anio, "periodo": etiqueta(base, corte),
                    "desde": base, "hasta": corte,
                    "serie": r.serie, "mercado": r.mercado, "moneda": r.moneda,
                    "emision": r.emision.date(),
                    "vencimiento": r.vencimiento.date(),
                    "colocado_anterior": previo, "colocado": r.colocado,
                    "emitido": emitido, "estado": estado})
    return pd.DataFrame(filas)


def main() -> None:
    print("=" * 78)
    print("  BONOS DEL GOBIERNO CENTRAL (reportes de deuda bruta)")
    print("=" * 78)
    rutas = []
    for r in DIR_DEUDA.glob("*.pdf"):
        m = re.fullmatch(r"(mar|jun|sep|dic)_(\d{4})", r.stem.lower())
        if m:
            rutas.append((pd.Period(year=int(m[2]), month=MESES[m[1]],
                                    freq="M"), r))
    if not rutas:
        print(f"  · no hay PDF en {DIR_DEUDA} (dic_AAAA.pdf)")
        return
    partes_b, partes_t, partes_p = [], [], []
    for corte, r in sorted(rutas):
        b, t = leer_reporte(r, corte)
        partes_b.append(b)
        partes_t.append(t)
        partes_p.append(leer_prepagos(r, corte))
        print(f"  {corte}: {len(b)} series leídas")
    bonos = pd.concat(partes_b, ignore_index=True)
    totales = pd.concat(partes_t, ignore_index=True)

    v = validar(bonos, totales)
    print("\n  Validación contra los totales de cada tabla")
    for r in v.itertuples():
        if pd.isna(r.total_colocado):
            print(f"    ⚠ {r.corte} {r.grupo:11}: sin fila de total")
        else:
            marca = "✓" if r.cuadra else "❌"
            print(f"    {marca} {r.corte} {r.grupo:11}: colocado {r.colocado:,.1f} "
                  f"vs {r.total_colocado:,.1f} · circulante {r.circulante:,.1f} "
                  f"vs {r.total_circulante:,.1f}")

    malas = tablas_no_acumuladas(bonos)
    for c, g in sorted(malas):
        print(f"    ⚠ {c} {g:11}: monto colocado no acumulado (hay series con "
              "más circulante que colocado); no se usa como base")

    e = emisiones(bonos)
    resumen = (e.groupby(["periodo", "moneda"]).emitido.sum()
                .unstack("moneda").round(1))
    print("\n  Emitido por periodo, en millones de la moneda de cada serie")
    print(resumen.to_string())
    raros = e[e.estado.isin(["ausente en la base", "colocado baja"])]
    if len(raros):
        print("\n  Series a revisar")
        print(raros[["periodo", "serie", "emision", "colocado_anterior",
                     "colocado", "estado"]].to_string(index=False))

    pre, rev = prepagos_vigentes(pd.concat(partes_p, ignore_index=True))
    print("\n  Prepagos por año (millones de US$, reporte más reciente)")
    print("    " + " · ".join(f"{r.anio}: {r.prepago_musd:,.1f}"
                              for r in pre[pre.anio >= 2016].itertuples()))
    for r in rev.itertuples():
        print(f"    ⚠ {r.anio}: revisado entre ediciones ({r.min:,.1f} a "
              f"{r.max:,.1f})")

    pre.to_csv(REP / "deuda_prepagos.csv", index=False, encoding="utf-8-sig")
    bonos.to_csv(REP / "deuda_bonos.csv", index=False, encoding="utf-8-sig")
    e.to_csv(REP / "deuda_emisiones.csv", index=False, encoding="utf-8-sig")
    print(f"\n  Salida: {REP / 'deuda_bonos.csv'}")
    print(f"          {REP / 'deuda_emisiones.csv'}")
    print(f"          {REP / 'deuda_prepagos.csv'}")


if __name__ == "__main__":
    main()