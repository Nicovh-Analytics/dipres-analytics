"""
18b_financiamiento.py — ¿De dónde salen los fondos de cada año?
===============================================================
Arma las fuentes de financiamiento ejecutadas del Gobierno Central por año,
en billones de pesos (dólares convertidos con el dólar observado promedio
del año), con dos neteos que la suma por subtítulo no hace:

  Deuda      El endeudamiento (subt. 14) es bruto: una parte solo paga deuda
             que vence en el año. Se separa en "paga vencimientos"
             (amortizaciones del subt. 34, calculadas en el 11b) y "deuda
             neta".
  Activos    La venta de títulos y depósitos (11.01) es bruta: el Tesoro
             compra y vende instrumentos de liquidez durante el año. Se netea
             contra la compra de títulos (30.01). Negativo = ahorro neto.

Y una exclusión:

  Operaciones de cambio (11.03): cuando el Tesoro convierte dólares a pesos,
  se registra como ingreso positivo en pesos y negativo en dólares. No es
  una fuente: es la misma plata cambiando de moneda. Llevadas a pesos, las
  dos mitades se anulan; se informan como control.

La compra de acciones (30.02: capitalizaciones de empresas y fondos) es un
uso de fondos real, no rotación de liquidez: se informa aparte y no entra
al neteo.

Base:
  ingresos_detalle.csv        (18_ingresos.py)  ingresos por subtítulo, nacional
  tope_endeudamiento.csv      (11b)             amortizaciones en miles de US$
  ejecucion_programa_consolidado.parquet        subt. 11 y 30 por ítem
Diciembre de cada año completo. Montos de origen en miles (de pesos o de US$).

Salidas en DIRS["reportes"]:
  financiamiento_fuentes.csv  año × componente, en billones de pesos
  financiamiento_activos.csv  RESPALDO: subt. 11 y 30 por año, moneda e ítem

Uso:
    python pipeline/4_analisis/18b_financiamiento.py
"""

import numpy as np
import pandas as pd

from dipres.config import DIRS
from dipres.dominio import tipo_cambio

REP = DIRS["reportes"]
PROGRAMA = DIRS["clean"] / "ejecucion_programa_consolidado.parquet"

# Ítems del clasificador (subt. 11 venta / 30 compra de activos financieros)
TITULOS = 1             # títulos, valores y depósitos: liquidez
ACCIONES = 2            # acciones y participaciones de capital
CAMBIO = 3              # 11.03 operaciones de cambio
OTROS_ACT = 99          # otros activos financieros

TOL_CAMBIO = 0.05       # operaciones de cambio netas: aviso si superan 5%
                        # del total de fuentes del año


def a_billones(df: pd.DataFrame, col: str) -> pd.Series:
    """Miles de pesos o miles de US$ → billones de pesos."""
    tc = df["anio"].map(lambda a: tipo_cambio(a, "observado"))
    return np.where(df["moneda"] == "DOLARES", df[col] * tc, df[col]) / 1e9


def cargar_activos() -> pd.DataFrame:
    """Subt. 11 y 30 a diciembre, por año, moneda e ítem (todas las partidas)."""
    cols = ["Año", "Mes", "Moneda", "Partida", "Subtítulo", "Item", "Ítem",
            "Nombre Item", "Nombre Ítem", "Ejecución Acumulada"]
    d = pd.read_parquet(PROGRAMA, columns=cols,
                        filters=[("Mes", "==", "Diciembre"),
                                 ("Subtítulo", "in", [11, 30])])
    # El nombre de la columna del ítem cambió entre años
    d["item"] = d["Item"].fillna(d["Ítem"])
    d["nombre_item"] = d["Nombre Item"].fillna(d["Nombre Ítem"])
    d = d.rename(columns={"Año": "anio", "Moneda": "moneda",
                          "Subtítulo": "subtitulo",
                          "Ejecución Acumulada": "ejecutado"})
    d = (d.groupby(["anio", "moneda", "subtitulo", "item", "nombre_item"],
                   dropna=False, as_index=False)["ejecutado"].sum())
    d["billones"] = a_billones(d, "ejecutado")
    return d


def fuentes(ing: pd.DataFrame, act: pd.DataFrame,
            tope: pd.DataFrame) -> pd.DataFrame:
    anios = sorted(set(ing.anio) & set(act.anio))
    ing = ing[ing.anio.isin(anios)].copy()
    ing["billones"] = a_billones(ing, "ejecutado")
    por = lambda d, m: d[m].groupby("anio").billones.sum().reindex(anios,
                                                                 fill_value=0)
    a11, a30 = act.subtitulo == 11, act.subtitulo == 30

    f = pd.DataFrame(index=pd.Index(anios, name="anio"))
    f["ingresos_fmi"] = por(ing, ing.categoria_gfs == "INGRESO")
    # Fuentes menores: venta de activos no financieros (10), recuperación de
    # préstamos (12) y venta de acciones u otros activos financieros
    f["otras"] = (por(ing, ing.subtitulo.isin([10, 12]))
                  + por(act, a11 & act.item.isin([ACCIONES, OTROS_ACT])))
    f["venta_titulos"] = por(act, a11 & (act.item == TITULOS))
    f["compra_titulos"] = por(act, a30 & (act.item == TITULOS))
    f["titulos_neto"] = f.venta_titulos - f.compra_titulos
    f["endeudamiento"] = por(ing, ing.subtitulo == 14)
    tc = pd.Series({a: tipo_cambio(a, "observado") for a in anios})
    amort = tope.set_index("Año").amortizacion.reindex(anios) * tc / 1e9
    f["amortizaciones"] = amort.fillna(0)
    f["paga_vencimientos"] = np.minimum(f.amortizaciones, f.endeudamiento)
    f["deuda_neta"] = f.endeudamiento - f.paga_vencimientos

    # Controles e informativos (no son fuentes)
    f["operaciones_cambio"] = por(act, a11 & (act.item == CAMBIO))
    f["compra_acciones"] = por(act, a30 & (act.item == ACCIONES))
    f["subt11_detalle"] = por(ing, ing.subtitulo == 11)
    f["subt11_items"] = por(act, a11)

    positivas = ["ingresos_fmi", "otras", "paga_vencimientos", "deuda_neta"]
    f["total_fuentes"] = (f[positivas].sum(axis=1)
                          + f.titulos_neto.clip(lower=0))
    return f.reset_index()


def informar(f: pd.DataFrame) -> None:
    pct = lambda c: f[c] / f.total_fuentes * 100
    t = pd.DataFrame({
        "año": f.anio,
        "total": f.total_fuentes.round(1),
        "ingresos%": pct("ingresos_fmi").round(0),
        "otras%": pct("otras").round(0),
        "títulos_neto%": pct("titulos_neto").round(0),
        "paga_venc%": pct("paga_vencimientos").round(0),
        "deuda_neta%": pct("deuda_neta").round(0),
    })
    print("\n  Fuentes de financiamiento (billones de pesos y % del total)")
    print(t.to_string(index=False))

    print("\n  Controles")
    cambio = (f.operaciones_cambio / f.total_fuentes).abs()
    for a, c, v in zip(f.anio, cambio, f.operaciones_cambio):
        marca = "⚠" if c > TOL_CAMBIO else "✓"
        print(f"    {marca} {a}: operaciones de cambio netas {v:+.2f} billones "
              f"({c * 100:.1f}% de las fuentes)")
    dif = (f.subt11_items - f.subt11_detalle).abs()
    print(f"    subt. 11 por ítem (programa) vs ingresos_detalle (nacional): "
          f"diferencia máxima {dif.max():.2f} billones")
    print("    (programa no consolida; el subt. 11 no tiene transferencias "
          "internas, así que debería cuadrar)")


def main() -> None:
    print("=" * 78)
    print("  FUENTES DE FINANCIAMIENTO")
    print("=" * 78)
    ing = pd.read_csv(REP / "ingresos_detalle.csv", encoding="utf-8-sig")
    tope = pd.read_csv(REP / "tope_endeudamiento.csv", encoding="utf-8-sig")
    act = cargar_activos()
    f = fuentes(ing, act, tope)
    informar(f)

    act.to_csv(REP / "financiamiento_activos.csv", index=False,
               encoding="utf-8-sig")
    f.to_csv(REP / "financiamiento_fuentes.csv", index=False,
             encoding="utf-8-sig")
    print(f"\n  Salida: {REP / 'financiamiento_fuentes.csv'}")
    print(f"          {REP / 'financiamiento_activos.csv'}")


if __name__ == "__main__":
    main()
