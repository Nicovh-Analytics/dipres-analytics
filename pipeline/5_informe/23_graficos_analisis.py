"""
23_graficos_analisis.py — Gráficos de análisis
==============================================
Gráficos descriptivos: muestran cómo funciona el presupuesto sin afirmar un
hallazgo de auditoría (esos van en 22_graficos_hallazgos.py). Leen los CSV de
DIRS["reportes"] (no recalculan nada) y escriben PNG + HTML en docs/graficos/.

Gráficos:
  fin1_fuentes   FIN-1: fuentes de financiamiento del año, con la deuda y los
                 títulos neteados (lee financiamiento_fuentes.csv del 18b)

Uso:
    python pipeline/5_informe/23_graficos_analisis.py
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from dipres.viz import (AQUA, AZUL, EJE, NARANJA, SUPERFICIE, ULTIMO_ANIO,
                        ejecutar, ejes_anio, leer, monto_mm, nota, num,
                        titulo)

NARANJA_CLARO = "#f5b393"
AMARILLO, AMARILLO_CLARO = "#eda100", "#f6d58a"


# =====================================================
# FIN-1: fuentes de financiamiento del año
# =====================================================
# (columna de financiamiento_fuentes.csv, etiqueta, color), de abajo hacia
# arriba. Los títulos van dos veces: uso neto (arriba de 0) y ahorro neto
# (bajo 0), según el signo de cada año.
TITULOS_USO = "Uso neto de títulos y depósitos"
TITULOS_AHORRO = "Ahorro neto en títulos y depósitos"
CAPAS_FIN = [
    ("ingresos_fmi", "Ingresos (perímetro FMI)", AZUL),
    ("otras", "Venta de activos y recuperación de préstamos", AQUA),
    ("titulos_uso", TITULOS_USO, AMARILLO),
    ("paga_vencimientos", "Deuda que paga vencimientos", NARANJA_CLARO),
    ("deuda_neta", "Deuda neta", NARANJA),
    ("titulos_ahorro", TITULOS_AHORRO, AMARILLO_CLARO),
]


def grafico_fin1() -> tuple[go.Figure, int] | None:
    f = leer("financiamiento_fuentes", "18b_financiamiento.py")
    if f is None:
        return None
    f = f[f.anio <= ULTIMO_ANIO].sort_values("anio").set_index("anio")
    f["titulos_uso"] = f.titulos_neto.clip(lower=0)
    f["titulos_ahorro"] = f.titulos_neto.clip(upper=0)
    pct = f.div(f.total_fuentes, axis=0) * 100
    x = [str(a) for a in f.index]
    fig = go.Figure()
    orden = {c: i for i, (c, _, _) in enumerate(CAPAS_FIN)}
    for col, etiqueta, color in CAPAS_FIN:
        if not f[col].any():
            continue
        # Leyenda en el orden visual: de la capa de arriba a la de abajo, y el
        # ahorro (bajo 0) al final
        rango = (100 if col == "titulos_ahorro"
                 else len(CAPAS_FIN) - orden[col])
        es_neta = col == "deuda_neta"
        fig.add_trace(go.Bar(
            x=x, y=pct[col], name=etiqueta, marker_color=color,
            legendrank=rango,
            marker_line=dict(width=1, color=SUPERFICIE),
            # Solo la deuda neta lleva etiqueta: es el mensaje
            text=[f"<b>{num(v, 0)}%</b>" for v in pct[col]] if es_neta else None,
            textposition="inside", insidetextanchor="middle",
            textfont=dict(size=11, color="white"),
            customdata=np.c_[[monto_mm(v * 1e6) for v in f[col]],
                             [monto_mm(v * 1e6) for v in f.total_fuentes]],
            hovertemplate=(f"<b>{etiqueta}</b> · %{{x}}<br>%{{y:.1f}}% de las "
                           "fuentes<br>%{customdata[0]}<br>Total de fuentes: "
                           "%{customdata[1]}<extra></extra>")))
    ejes_anio(fig, f.index)
    # float(): plotly rechaza los tipos de numpy (np.bool_, np.float64) en
    # propiedades de layout
    piso = float(min(0, np.floor(pct.titulos_ahorro.min() / 5) * 5))
    marcas = sorted({0, 25, 50, 75, 100} | ({int(piso)} if piso < 0 else set()))
    fig.update_yaxes(range=[piso, 100], tickvals=marcas,
                     ticktext=[f"{v}%" for v in marcas], title=None,
                     zeroline=bool(piso < 0), zerolinecolor=EJE, zerolinewidth=1)
    deuda, refi = pct.deuda_neta, pct.paga_vencimientos
    fig.update_layout(
        title=titulo(
            f"La deuda neta financió entre el {num(deuda.min(), 0)}% y el "
            f"{num(deuda.max(), 0)}% de las fuentes de cada año",
            "Fuentes de financiamiento ejecutadas del Gobierno Central, en % del "
            "total de cada año. Pesos y dólares, 2017-2025.<br>La deuda que paga "
            f"vencimientos pasó del {num(refi.iloc[0], 0)}% en {f.index[0]} al "
            f"{num(refi.iloc[-1], 0)}% en {f.index[-1]}."),
        barmode="relative", bargap=0.3,
        legend=dict(orientation="h", x=0.5, xanchor="center", y=1.02,
                    yanchor="bottom", font=dict(size=11), traceorder="normal"),
        margin=dict(l=55, r=30, t=175, b=185))
    nota(fig, [
        "Deuda neta: endeudamiento (subt. 14) menos amortizaciones del año "
        "(subt. 34). Títulos y depósitos: venta (11.01) menos compra (30.01); "
        "bajo 0, el año ahorró.",
        "El dato no identifica por separado los retiros de los fondos soberanos "
        "(FEES, FRP).",
        "Sin operaciones de cambio (11.03): dólares convertidos a pesos, que se "
        "registran positivos en pesos y negativos en dólares y se anulan.",
        "Ejecutado de diciembre; dólares a pesos con el dólar observado promedio "
        "del año (Banco Central). Sin aporte fiscal ni saldo inicial de caja.",
        "En % para que la inflación no afecte la comparación; los montos están "
        "en el detalle de cada barra. Fuente: datos.gob.cl (DIPRES). Análisis "
        "FIN-1.",
    ], bajo_eje=True)
    return fig, 660


# =====================================================
GRAFICOS = {
    "fin1_fuentes": grafico_fin1,
}

if __name__ == "__main__":
    ejecutar(GRAFICOS, "GRÁFICOS DE ANÁLISIS")