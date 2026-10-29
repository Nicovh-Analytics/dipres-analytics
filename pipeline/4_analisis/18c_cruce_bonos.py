"""
18c_cruce_bonos.py — ¿Cuadra la emisión de bonos con el subtítulo 14?
=====================================================================
Compara dos fuentes independientes sobre lo mismo:

  Bonos      lo emitido según los Reportes de Deuda Bruta de DIPRES, serie
             por serie (11c_bonos_deuda.py), a valor nominal (face value)
  Subt. 14   el endeudamiento ejecutado en el presupuesto
             (18_ingresos.py, ingresos_detalle.csv)

Cada sección del presupuesto se compara en su moneda:
  PESOS     BTP (pesos) + BTU (UF a pesos con la UF promedio del periodo)
  DOLARES   globales en USD + globales en EUR (a dólares con el euro y el
            dólar promedio del periodo)

Las emisiones de un periodo que cruza años (los bonos locales de 2024-2025,
ver 11c) se juntan con los años que toca, así que la comparación se hace por
"ventana": un año, o varios cuando un periodo no calza con el año calendario.

Diferencias esperables, sin que haya error:
  - El subt. 14 incluye créditos (BID, Banco Mundial, otros) que no son bonos
  - El subt. 14 registra lo recibido en caja, que difiere del valor nominal
    cuando el bono se coloca con premio o descuento
  - Bonos emitidos y vencidos entre dos reportes no aparecen en el 11c
Una diferencia grande o de signo cambiante pide revisión.

Salidas en DIRS["reportes"]:
  deuda_cruce_subt14.csv   ventana × sección: bonos, subt. 14, diferencia
  deuda_emisiones_usd.csv  cada emisión del 11c convertida a millones de US$
                           (para 18d_margen_endeudamiento.py), con su
                           ventana considerando todas las monedas juntas

Uso:
    python pipeline/4_analisis/18c_cruce_bonos.py
"""

import pandas as pd

from dipres.config import DIRS
from dipres.hallazgos import Registro

REP = DIRS["reportes"]
TC = DIRS.get("externo", DIRS["raw"] / "externo") / "tipo_cambio" / "diario.csv"
SECCION = {"CLP": "PESOS", "UF": "PESOS", "USD": "DOLARES", "EUR": "DOLARES"}
TOL_CRUCE_PCT = 20      # |subt. 14 − bonos| / subt. 14 sobre esto: aviso. Lo
                        # esperado está entre 0% y 15% (créditos, premio)


def promedio(tc: pd.DataFrame, indicador: str, desde: str, hasta: str) -> float:
    """Promedio diario entre el fin del mes `desde` (excluido) y el fin de `hasta`."""
    ini = pd.Period(desde, "M").end_time
    fin = pd.Period(hasta, "M").end_time
    s = tc[(tc.indicador == indicador) & (tc.fecha > ini) & (tc.fecha <= fin)]
    if s.empty:
        raise ValueError(f"sin {indicador} entre {desde} y {hasta}")
    return float(s.valor.mean())


def a_moneda_seccion(e: pd.DataFrame, tc: pd.DataFrame) -> pd.Series:
    """Emitido en miles de la moneda de la sección (pesos o dólares)."""
    factores = {}
    for (desde, hasta), _ in e.groupby(["desde", "hasta"]):
        dolar = promedio(tc, "dolar", desde, hasta)
        factores[(desde, hasta, "UF")] = promedio(tc, "uf", desde, hasta)
        factores[(desde, hasta, "EUR")] = promedio(tc, "euro", desde, hasta) / dolar
    f = [factores.get((d, h, m), 1.0)
         for d, h, m in zip(e.desde, e.hasta, e.moneda)]
    return e.emitido * pd.Series(f, index=e.index) * 1e3   # millones → miles


def a_usd(e: pd.DataFrame, tc: pd.DataFrame) -> pd.Series:
    """Emitido en millones de US$, con los promedios del periodo."""
    factores = {}
    for (desde, hasta), _ in e.groupby(["desde", "hasta"]):
        dolar = promedio(tc, "dolar", desde, hasta)
        factores[(desde, hasta, "CLP")] = 1 / dolar
        factores[(desde, hasta, "UF")] = promedio(tc, "uf", desde, hasta) / dolar
        factores[(desde, hasta, "EUR")] = promedio(tc, "euro", desde, hasta) / dolar
    f = [factores.get((d, h, m), 1.0)
         for d, h, m in zip(e.desde, e.hasta, e.moneda)]
    return e.emitido * pd.Series(f, index=e.index)


def ventanas(e: pd.DataFrame) -> pd.Series:
    """
    Asigna cada periodo a una ventana de años completos. Dentro de una
    sección, los periodos cuyos años se tocan se funden (2024-01 a 2025-03 y
    2025-04 a 2025-12 quedan en la ventana 2024-2025).
    """
    anios = {p: set(range((pd.Period(d, "M") + 1).year, pd.Period(h, "M").year + 1))
             for p, d, h in zip(e.periodo, e.desde, e.hasta)}
    salida = pd.Series(index=e.index, dtype=object)
    for sec, idx in e.groupby("seccion").groups.items():
        grupos: list[set] = []
        for p in e.loc[idx, "periodo"].unique():
            a = set(anios[p])
            for g in [g for g in grupos if g & a]:
                a |= g
                grupos.remove(g)
            grupos.append(a)
        nombre = {}
        for g in grupos:
            etiqueta = (str(min(g)) if len(g) == 1
                        else f"{min(g)}-{max(g)}")
            for p, ya in anios.items():
                if ya <= g:
                    nombre[p] = etiqueta
        salida[idx] = e.loc[idx, "periodo"].map(nombre)
    return salida


def main() -> None:
    print("=" * 78)
    print("  CRUCE: BONOS EMITIDOS (reportes de deuda) vs SUBTÍTULO 14")
    print("=" * 78)
    e = pd.read_csv(REP / "deuda_emisiones.csv", encoding="utf-8-sig",
                    dtype={"desde": str, "hasta": str})
    ing = pd.read_csv(REP / "ingresos_detalle.csv", encoding="utf-8-sig")
    tc = pd.read_csv(TC, encoding="utf-8-sig", parse_dates=["fecha"])
    if not {"desde", "hasta"} <= set(e.columns):
        print("  · deuda_emisiones.csv es de una versión anterior del 11c "
              "(sin desde/hasta): correr 11c_bonos_deuda.py")
        return

    e = e[e.emitido.abs() > 0].copy()
    e["seccion"] = e.moneda.map(SECCION)
    e["emitido_seccion"] = a_moneda_seccion(e, tc)
    e["ventana"] = ventanas(e)

    s14 = ing[ing.subtitulo == 14].groupby(["moneda", "anio"]).ejecutado.sum()
    filas = []
    for (sec, v), g in e.groupby(["seccion", "ventana"]):
        a0, a1 = (int(x) for x in (v.split("-") if "-" in v else (v, v)))
        sub = sum(s14.get((sec, a), 0) for a in range(a0, a1 + 1))
        anios_s14 = [a for a in range(a0, a1 + 1) if (sec, a) in s14.index]
        bonos = g.emitido_seccion.sum()
        filas.append({
            "ventana": v, "seccion": sec,
            "bonos_locales": g[g.mercado == "local"].emitido_seccion.sum(),
            "bonos_internacionales":
                g[g.mercado == "internacional"].emitido_seccion.sum(),
            "bonos": bonos, "subt14": sub if anios_s14 else float("nan"),
            "anios_subt14": len(anios_s14), "anios_ventana": a1 - a0 + 1})
    c = pd.DataFrame(filas).sort_values(["seccion", "ventana"])
    c["diferencia"] = c.subt14 - c.bonos
    c["dif_pct"] = c.diferencia / c.subt14 * 100

    for sec, unidad, div in [("PESOS", "billones de pesos", 1e9),
                             ("DOLARES", "millones de US$", 1e3)]:
        t = c[c.seccion == sec]
        print(f"\n  {sec} ({unidad}); diferencia = subt. 14 − bonos")
        for r in t.itertuples():
            incompleta = (" (subt. 14 incompleto)"
                          if r.anios_subt14 < r.anios_ventana else "")
            print(f"    {r.ventana:9}  bonos {r.bonos / div:10,.2f}  "
                  f"subt.14 {r.subt14 / div:10,.2f}  "
                  f"dif {r.diferencia / div:+9,.2f} ({r.dif_pct:+6.1f}%)"
                  f"{incompleta}")

    c.to_csv(REP / "deuda_cruce_subt14.csv", index=False, encoding="utf-8-sig")
    reg = Registro("cruce_bonos", salida_dir=REP, eco=False)
    for r in c.itertuples():
        msg = (f"{r.seccion} {r.ventana}: subt. 14 − bonos = "
               f"{r.dif_pct:+.1f}%")
        if pd.isna(r.dif_pct):
            reg.warn("cruce_subt14", msg + " (sin subt. 14)", anio=r.ventana,
                     patron="ventana sin subt. 14")
        elif abs(r.dif_pct) > TOL_CRUCE_PCT:
            reg.warn("cruce_subt14", msg, anio=r.ventana,
                     patron=f"diferencia mayor a {TOL_CRUCE_PCT}%")
        else:
            reg.ok("cruce_subt14", msg, anio=r.ventana)

    # Todas las monedas en US$, para el margen de endeudamiento (18d)
    u = e.drop(columns=["seccion", "emitido_seccion", "ventana"]).copy()
    u["emitido_musd"] = a_usd(u, tc)
    u["seccion"] = "TOTAL"
    u["ventana"] = ventanas(u)
    u.drop(columns="seccion").to_csv(REP / "deuda_emisiones_usd.csv",
                                     index=False, encoding="utf-8-sig")
    print(f"\n  Salida: {REP / 'deuda_cruce_subt14.csv'}")
    print(f"          {REP / 'deuda_emisiones_usd.csv'}")
    reg.emitir()


if __name__ == "__main__":
    main()