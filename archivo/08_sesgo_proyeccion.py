"""
08_sesgo_proyeccion.py — ¿Hay sesgo en la proyección de ingresos?
==================================================================
Hipótesis: el error de proyección de ingresos (ley_inicial vs
ejecución efectiva) no es ruido aleatorio sino que apunta
sistemáticamente hacia un lado.

Método: prueba del signo (binomial). Solo cuenta la dirección
del error, no su magnitud — por eso 2020 no distorsiona.

H0: P(sobreestimar) = P(subestimar) = 0.5
H1: una dirección predomina

Uso:
    python 08_sesgo_proyeccion.py
"""

from scipy.stats import binomtest
import pandas as pd

from config import DIRS
from dominio import MES_A_NUM, SUBTITULOS_INGRESO, nombre_subtitulo, SUBTITULOS_SALDO
from utils import leer_csv_robusto

ANIO_EN_CURSO = 2026   # excluido: no tiene ejecución completa



# =====================================================
# Preparación
# =====================================================
def cargar_cierres() -> pd.DataFrame:
    """
    Devuelve una fila por Año × Subtítulo con el cierre del año:
    ley_inicial (lo proyectado) y ejecución acumulada (lo real).
    """
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_nacional.csv"))

    df = df[(df["Moneda"] == "PESOS") & (df["Año"] < ANIO_EN_CURSO)].copy()
    df["MesNum"] = df["Mes"].map(MES_A_NUM)

    # Último mes disponible de cada año = cierre
    idx = df.groupby("Año")["MesNum"].transform("max") == df["MesNum"]
    cierres = df[idx].copy()

    # ley_inicial y ejecucion_acumulada son stocks: no se suman entre
    # meses, pero sí entre subtítulos dentro del mismo cierre
    cierres["error"] = cierres["ejecucion_acumulada"] - cierres["ley_inicial"]
    cierres["error_pct"] = (
        cierres["error"] / cierres["ley_inicial"].replace(0, pd.NA) * 100
    )
    return cierres



# =====================================================
# Prueba del signo
# =====================================================
def prueba_signo(errores: pd.Series, etiqueta: str) -> dict | None:
    """
    errores: una observación por año (el signo es lo único que importa).
    Los ceros exactos se descartan — no aportan dirección.
    """
    e = errores.dropna()
    e = e[e != 0]
    n = len(e)
    if n < 5:
        return None

    sobre = int((e < 0).sum())   # ejecución < proyección → sobreestimó
    sub = int((e > 0).sum())     # ejecución > proyección → subestimó

    # Dos colas: no asumimos de antemano hacia qué lado falla
    p = binomtest(max(sobre, sub), n, 0.5, alternative="two-sided").pvalue

    return {
        "serie": etiqueta,
        "n": n,
        "sobreestimó": sobre,
        "subestimó": sub,
        "direccion": "sobreestima" if sobre > sub else "subestima",
        "p_valor": round(p, 4),
        "error_medio_pct": round(e.mean(), 1) if e.name == "error_pct" else None,
    }




# =====================================================
# Main
# =====================================================
if __name__ == "__main__":
    cierres = cargar_cierres()
    ingresos = cierres[
        cierres["Subtítulo"].astype(int).isin(SUBTITULOS_INGRESO)
        & ~cierres["Subtítulo"].astype(int).isin(SUBTITULOS_SALDO)]

    print("=" * 66)
    print("  SESGO EN LA PROYECCIÓN DE INGRESOS")
    print("=" * 66)

    # ── Serie agregada: total de ingresos por año ──
    total = (
        ingresos.groupby("Año")
        .agg(ley_inicial=("ley_inicial", "sum"),
             ejecutado=("ejecucion_acumulada", "sum"))
        .assign(error=lambda d: d["ejecutado"] - d["ley_inicial"])
        .assign(error_pct=lambda d: d["error"] / d["ley_inicial"] * 100)
    )

    print("\nIngresos totales — proyectado vs ejecutado (M$)")
    print(f"{'Año':>6} {'Proyectado':>18} {'Ejecutado':>18} {'Error %':>9}")
    for anio, r in total.iterrows():
        signo = "▼" if r["error"] < 0 else "▲"
        print(f"{anio:>6} {r['ley_inicial']:>18,.0f} {r['ejecutado']:>18,.0f} "
              f"{r['error_pct']:>8.1f}% {signo}")

    res = prueba_signo(total["error"], "Ingresos totales")
    if res:
        print(f"\n  Sobreestimó {res['sobreestimó']} de {res['n']} años · "
              f"subestimó {res['subestimó']}")
        print(f"  p-valor = {res['p_valor']}")
        print(f"  Error medio: {total['error_pct'].mean():.1f}% · "
              f"mediana: {total['error_pct'].median():.1f}%")
        print(f"  Sin 2020: {total.drop(2020, errors='ignore')['error_pct'].mean():.1f}%")

    # ── Por subtítulo: ¿falla todo igual o se concentra? ──
    filas = []
    for sub, g in ingresos.groupby(ingresos["Subtítulo"].astype(int)):
        serie = g.set_index("Año")["error"]
        r = prueba_signo(serie, nombre_subtitulo(sub))
        if r:
            r["error_medio_pct"] = round(g["error_pct"].mean(), 1)
            filas.append(r)

    if filas:
        tabla = pd.DataFrame(filas).sort_values("p_valor")
        print(f"\n{'─'*66}")
        print("Por subtítulo (ordenado por p-valor)\n")
        print(tabla.to_string(index=False))

    print(f"\n{'─'*66}")
    print("Lectura: p < 0.05 ⇒ el patrón es difícil de atribuir al azar.")
    print("Ojo: los años NO son independientes entre sí (mismo método de")
    print("proyección), así que el p-valor subestima la incertidumbre real.")

# 2. Separar operacionales de financiamiento
OPERACIONALES = range(1, 13)    # 01–12
FINANCIAMIENTO = {14}           # endeudamiento

for nombre, rango in [("Operacionales (01-12)", OPERACIONALES),
                      ("Financiamiento (14)", FINANCIAMIENTO)]:
    g = ingresos[ingresos["Subtítulo"].astype(int).isin(rango)]
    total = (g.groupby("Año")
               .agg(ley=("ley_inicial","sum"), ejec=("ejecucion_acumulada","sum"))
               .assign(error=lambda d: d["ejec"] - d["ley"]))
    r = prueba_signo(total["error"], nombre)
    print(f"\n{nombre}: {r}")