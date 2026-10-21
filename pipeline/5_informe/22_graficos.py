"""
22_graficos.py — Gráficos de los hallazgos
==========================================
Un gráfico por hallazgo, cada uno con un solo mensaje. Lee los CSV de
DIRS["reportes"] (no recalcula nada) y escribe PNG + HTML en docs/graficos/
con el estilo de dipres/viz.py.

Gráficos:
  val2_dataset_vs_cgr   VAL-2: dónde difiere la ejecución publicada de la
                        de Contraloría (partida × año)

Uso:
    python pipeline/5_informe/22_graficos.py
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from dipres.config import DIRS
from dipres.viz import (DIVERGENTE, SUPERFICIE, TINTA, TINTA_2, TINTA_MUTED,
                        guardar, monto_mm, nota, num, titulo)

REP = DIRS["reportes"]
COMPARABLES = ["cuadra", "difiere", "cuadra con otra partida"]
GORE = 31                       # la CGR usa otra fuente: no comparable
TOPE_PCT = 5                    # la escala de color satura en ±5%
MATERIAL_PCT, MATERIAL_MM = 1.0, 1_000     # criterio de las consultas


ABREVIA = {
    "Ministerio Secretaría General de la Presidencia de la República":
        "Secretaría General de la Presidencia",
    "Ministerio Secretaría General de Gobierno": "Secretaría General de Gobierno",
    "Ministerio de Ciencia, Tecnología, Conocimiento e Innovación":
        "Ciencia, Tecnología e Innovación",
}


def corto(nombre: str) -> str:
    """'Ministerio de Relaciones Exteriores' → 'Relaciones Exteriores'."""
    if nombre in ABREVIA:
        return ABREVIA[nombre]
    for pref in ("Ministerio de las ", "Ministerio de la ", "Ministerio del ",
                 "Ministerio de "):
        if nombre.startswith(pref):
            return nombre[len(pref):]
    return nombre


# =====================================================
# VAL-2
# =====================================================
def grafico_val2() -> tuple[go.Figure, int] | None:
    try:
        c = pd.read_csv(REP / "validacion_cgr.csv")
    except FileNotFoundError:
        print("  · val2: falta validacion_cgr.csv (correr 15b_validar_vs_cgr.py)")
        return None

    d = c[(c.concepto == "devengado") & (c.moneda == "PESOS")
          & c.estado.isin(COMPARABLES) & c.partida.notna()
          & (c.partida != GORE)].copy()
    d["partida"] = d.partida.astype(int)
    d["cuadra"] = d.estado.str.startswith("cuadra")
    d["pct"] = np.where(d.cuadra, 0.0, (d.dataset - d.cgr) / d.cgr * 100)
    d["material"] = (~d.cuadra & (d.pct.abs() >= MATERIAL_PCT)
                     & (d.delta.abs() >= MATERIAL_MM))

    # Nombre más reciente de cada partida (Interior y Seg. Pública → Interior)
    nombres = d.sort_values("anio").groupby("partida").nombre.last().map(corto)

    # Orden: las que más años difieren arriba; las que siempre cuadran, abajo
    rango = (d.assign(dif=~d.cuadra, mag=d.pct.abs())
             .groupby("partida").agg(n=("dif", "sum"), mag=("mag", "mean"))
             .sort_values(["n", "mag"], ascending=False))
    filas = list(rango.index)
    anios = sorted(d.anio.unique())

    z = d.pivot(index="partida", columns="anio", values="pct").reindex(
        index=filas, columns=anios)
    mat = d.pivot(index="partida", columns="anio", values="material").reindex(
        index=filas, columns=anios).fillna(False)

    def hover(r):
        if r.cuadra:
            return (f"<b>{nombres[r.partida]}</b> · {r.anio}<br>"
                    f"Cuadra (±2 millones de pesos)")
        signo = "+" if r.delta > 0 else ""
        return (f"<b>{nombres[r.partida]}</b> · {r.anio}<br>"
                f"Contraloría: {monto_mm(r.cgr)}<br>"
                f"Dataset: {monto_mm(r.dataset)}<br>"
                f"Diferencia: {signo}{monto_mm(r.delta)} "
                f"({signo}{num(r.pct, 2)}%)")
    d["hover"] = d.apply(hover, axis=1)
    hov = d.pivot(index="partida", columns="anio", values="hover").reindex(
        index=filas, columns=anios).fillna("")

    # Celdas sin registro: la partida aún no existía ese año
    falta = z.isna()
    creada = {p: anios[int(np.argmax(~falta.loc[p].values))] for p in filas
              if falta.loc[p].any() and not falta.loc[p].all()}
    etiquetas = [f"{nombres[p]} (desde {creada[p]})" if p in creada
                 else nombres[p] for p in filas]
    hov_falta = np.where(
        falta.values,
        [[f"<b>{nombres[p]}</b> · {a}<br>Sin registro: partida creada en "
          f"{creada.get(p, '—')}" for a in anios] for p in filas], "")

    x = [str(a) for a in anios]
    fig = go.Figure()
    fig.add_trace(go.Heatmap(                   # capa de fondo: sin registro
        z=np.where(falta.values, 0, np.nan), x=x, y=etiquetas,
        colorscale=[[0, SUPERFICIE], [1, SUPERFICIE]], showscale=False,
        hoverongaps=False,
        xgap=2, ygap=2, text=np.where(falta.values, "–", ""),
        texttemplate="%{text}", textfont=dict(size=11, color=TINTA_MUTED),
        customdata=hov_falta, hovertemplate="%{customdata}<extra></extra>"))
    fig.add_trace(go.Heatmap(
        z=z.values, x=x, y=etiquetas,
        zmin=-TOPE_PCT, zmax=TOPE_PCT, zmid=0, colorscale=DIVERGENTE,
        xgap=2, ygap=2, hoverongaps=False,   # el hover de "sin registro" es de la capa de fondo
        text=np.where(mat.values, "●", ""),
        texttemplate="%{text}", textfont=dict(size=9, color="white"),
        customdata=hov.values, hovertemplate="%{customdata}<extra></extra>",
        colorbar=dict(
            title=dict(text="Dataset vs<br>Contraloría", side="top",
                       font=dict(size=11, color=TINTA_2)),
            tickvals=[-5, -2.5, 0, 2.5, 5],
            ticktext=["−5% o menos", "−2,5%", "0", "+2,5%", "+5% o más"],
            thickness=10, len=0.4, y=0.5, yanchor="middle", ypad=0,
            outlinewidth=0),
    ))
    fig.add_annotation(                          # qué significa cada color
        text=(f"<span style='color:#184f95'>■</span> dataset informa más<br>"
              f"<span style='color:#a8262a'>■</span> dataset informa menos"),
        xref="paper", yref="paper", x=1.02, y=0.28, xanchor="left",
        yanchor="top", showarrow=False, align="left",
        font=dict(size=11, color=TINTA_2))
    fig.update_layout(
        title=titulo(
            "Diferencias en la ejecución presupuestaria informada: "
            "DIPRES vs Contraloría",
            "Devengado de gastos por partida: dataset de DIPRES menos IGFE de "
            "Contraloría, en % de la cifra de Contraloría.<br>Moneda nacional, "
            "2017-2025."),
        margin=dict(l=10, r=150, t=115, b=110),
        xaxis=dict(side="top", showgrid=False, type="category",
                   tickmode="array", tickvals=x, tickfont=dict(color=TINTA)),
        yaxis=dict(autorange="reversed", showgrid=False, automargin=True,
                   tickfont=dict(size=11, color=TINTA)),
    )
    nota(fig, [
        f"● Diferencia material: al menos {num(MATERIAL_PCT)}% de la partida "
        f"y al menos {num(MATERIAL_MM)} millones de pesos (ambas condiciones). "
        f"Incluida en las consultas por Ley 20.285.",
        "Gris: cuadra (±2 millones de pesos). –: sin registro, la partida aún "
        "no existía. Sin Gobiernos Regionales: la CGR usa otra fuente.",
        "Fuente: datos.gob.cl (DIPRES) e Informe de la Gestión Financiera del "
        "Estado 2017-2025 (CGR).",
    ])
    return fig, max(500, 24 * len(filas) + 230)


# =====================================================
GRAFICOS = {"val2_dataset_vs_cgr": grafico_val2}

if __name__ == "__main__":
    print("=" * 78)
    print("  GRÁFICOS")
    print("=" * 78)
    for nombre, f in GRAFICOS.items():
        r = f()
        if r is None:
            continue
        fig, alto = r
        for p in guardar(fig, nombre, ancho=900, alto=alto):
            print(f"  ✓ {p}")