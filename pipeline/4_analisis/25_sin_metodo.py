"""
25_sin_metodo.py — ¿Qué se concluye si se usa el dato abierto sin el método?
===========================================================================
Repite cálculos clave del proyecto por el camino que tomaría alguien que
baja el dataset de datos.gob.cl y lo usa tal cual, y los compara con el
resultado del pipeline. No es un hallazgo de la fuente: mide cuánto cambian
las conclusiones por decisiones de método que el dato no trae explícitas.

Casos:
  1. Límite de endeudamiento (DEU-1). Ingenuo: subtítulo 14 ejecutado contra
     los incisos 1 y 2 del art. 3. Pipeline: bonos a valor nominal, prepagos,
     autorización de bonos de reconocimiento y leyes especiales (11b, 18d).
  2. Sesgo de proyección de ingresos (ING-1). Ingenuo: todos los subtítulos
     de ingreso (01-15). Pipeline: perímetro del FMI (18).
  3. Ejecución anual. Ingenuo: sumar la columna ejecucion_acumulada de los
     12 meses. Pipeline: el acumulado a diciembre.
  4. Pesos y dólares. Ingenuo: sumar las filas PESOS y DOLARES tal cual.
     Pipeline: dólares convertidos con el tipo de cambio observado.
  5. Ejecución vs Contraloría (VAL-2). Ingenuo: toda diferencia es un
     error. Pipeline: diferencias explicadas por criterio (15c).

Entradas: cruce_nacional.csv y los reportes de 11b, 18d, 18 y 15c.
Salida (reports/): sin_metodo.csv, una fila por caso y año.

Uso:
    python pipeline/4_analisis/25_sin_metodo.py
"""

import pandas as pd

from dipres.config import DIRS, ULTIMO_ANIO_CERRADO
from dipres.dominio import MES_A_NUM, a_pesos
from dipres.hallazgos import Registro
from dipres.utils import leer_csv_robusto

REP = DIRS["reportes"]
GASTOS = range(21, 35)
SERVICIO_DEUDA = 34


def nacional() -> pd.DataFrame:
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_nacional.csv"))
    df["mes"] = df["Mes"].map(MES_A_NUM)
    df["Subtítulo"] = df["Subtítulo"].astype(int)
    df["Moneda"] = df["Moneda"].str.upper()
    return df[df["Año"] <= ULTIMO_ANIO_CERRADO]


def fila(caso, anio, ingenuo, metodo, unidad, concl_ingenua, concl_metodo):
    return {"caso": caso, "anio": anio, "ingenuo": ingenuo, "metodo": metodo,
            "unidad": unidad,
            "diferencia_pct": (ingenuo / metodo - 1) * 100 if metodo else float("nan"),
            "conclusion_ingenua": concl_ingenua, "conclusion_metodo": concl_metodo,
            "cambia_conclusion": concl_ingenua != concl_metodo}


# 1) Límite de endeudamiento -------------------------------------------------
def caso_endeudamiento() -> list[dict]:
    t = pd.read_csv(REP / "tope_endeudamiento.csv")
    m = pd.read_csv(REP / "margen_endeudamiento.csv", encoding="utf-8-sig",
                    dtype={"ventana": str})
    lectura = {}
    for r in m.itertuples():
        a0, a1 = (int(x) for x in (r.ventana.split("-") if "-" in r.ventana
                                   else (r.ventana, r.ventana)))
        for a in range(a0, a1 + 1):
            lectura[a] = (r.lectura, r.uso_base_pct)
    out = []
    for r in t.itertuples():
        tope_ley = r.tope_inciso1 + r.tope_inciso2
        if pd.isna(tope_ley) or r.Año not in lectura:
            continue
        uso = r.bruto / tope_ley * 100
        lec, uso_m = lectura[r.Año]
        out.append(fila("1. Límite de endeudamiento (art. 3)", r.Año, uso, uso_m,
                        "% del tope", "excede" if uso > 100 else "dentro",
                        {"DENTRO": "dentro", "SOBRE": "excede"}.get(lec, lec.lower())))
    return out


# 2) Sesgo de proyección de ingresos -----------------------------------------
def caso_ingresos() -> list[dict]:
    p = pd.read_csv(REP / "ingresos_prueba_signo.csv")
    p = p[(p.nivel == "agregado") & (p.moneda.str.upper() == "PESOS")].set_index("clave")
    concl = lambda r: (f"sesgo significativo (p = {r.p_valor:.3f})" if r.p_valor < 0.05
                       else f"sin sesgo significativo (p = {r.p_valor:.2f})")
    ing, gfs = p.loc["ingenuo_01_15"], p.loc["ingreso_gfs"]
    return [fila("2. Sesgo de proyección de ingresos", "todos",
                 ing.error_medio_pct, gfs.error_medio_pct, "% error medio",
                 concl(ing), concl(gfs))]


# 3) Sumar el acumulado mes a mes --------------------------------------------
def caso_acumulado(df: pd.DataFrame) -> list[dict]:
    g = df[(df.Moneda == "PESOS") & df["Subtítulo"].isin(GASTOS)]
    out = []
    for a, x in g.groupby("Año"):
        if x.mes.nunique() < 12:
            continue
        ingenuo = x.ejecucion_acumulada.sum()
        metodo = x[x.mes == 12].ejecucion_acumulada.sum()
        out.append(fila("3. Gasto anual: sumar el acumulado de 12 meses", a,
                        ingenuo / 1e9, metodo / 1e9, "billones de $",
                        f"{ingenuo / metodo:.1f} veces el gasto real", "gasto real"))
    return out


# 4) Pesos y dólares sin convertir -------------------------------------------
def caso_monedas(df: pd.DataFrame) -> list[dict]:
    g = df[(df.mes == 12) & df["Subtítulo"].isin(GASTOS)]
    out = []
    for a, x in g.groupby("Año"):
        conv = a_pesos(x, ["ejecucion_acumulada"], "observado")
        for nombre, sel in [("gasto total", x["Subtítulo"].isin(GASTOS)),
                            ("servicio de la deuda (subt. 34)",
                             x["Subtítulo"] == SERVICIO_DEUDA)]:
            ingenuo = x[sel].ejecucion_acumulada.sum()
            metodo = conv[sel].ejecucion_acumulada.sum()
            dif = (ingenuo / metodo - 1) * 100
            out.append(fila(f"4. Pesos y dólares sin convertir: {nombre}", a,
                            ingenuo / 1e9, metodo / 1e9, "billones de $",
                            f"subestima {abs(dif):.1f}%", "gasto real"))
    return out


# 5) Diferencias con Contraloría ---------------------------------------------
def caso_cgr() -> list[dict]:
    c = pd.read_csv(REP / "conciliacion_cgr_val2.csv", encoding="utf-8-sig")
    n, sin = len(c), int((c.explicacion == "sin explicar").sum())
    return [fila("5. Ejecución vs Contraloría", "todos", n, sin, "diferencias",
                 f"{n} diferencias sin explicación",
                 f"{n - sin} explicadas por criterio, {sin} sin explicar")]


def main() -> None:
    reg = Registro("sin_metodo", salida_dir=REP)
    df = nacional()
    filas = []
    for nombre, f in [("endeudamiento", caso_endeudamiento),
                      ("ingresos", caso_ingresos),
                      ("acumulado", lambda: caso_acumulado(df)),
                      ("monedas", lambda: caso_monedas(df)),
                      ("contraloria", caso_cgr)]:
        try:
            filas += f()
        except FileNotFoundError as e:
            reg.error(nombre, f"falta un reporte de entrada: {e.filename}")
    t = pd.DataFrame(filas)
    t.round(3).to_csv(REP / "sin_metodo.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 220)
    for caso, g in t.groupby("caso", sort=False):
        print(f"\n{caso}")
        print(g[["anio", "ingenuo", "metodo", "unidad", "diferencia_pct",
                 "conclusion_ingenua", "conclusion_metodo"]]
              .round(2).to_string(index=False))
        cambia = int(g.cambia_conclusion.sum())
        reg.info("caso", f"{caso}: la conclusión cambia en {cambia} de {len(g)}",
                 patron=caso)
    reg.ok("sin_metodo", f"{len(t)} comparaciones en {t.caso.nunique()} casos")
    reg.emitir()


if __name__ == "__main__":
    main()
