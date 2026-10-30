"""
22_graficos_hallazgos.py — Gráficos de los hallazgos
====================================================
Un gráfico por hallazgo de la auditoría, cada uno con un solo mensaje. Los
gráficos descriptivos (sin hallazgo) van en 23_graficos_analisis.py. Lee los
CSV de DIRS["reportes"] (no recalcula nada) y escribe PNG + HTML en
docs/graficos/ con el estilo de dipres/viz.py.

Gráficos:
  ing1_perimetro        ING-1: el sesgo de proyección es un efecto de
                        perímetro; el error sigue siendo grande
  mod1_eje1_presupuesto MOD-1 / EJE-1: inicial → vigente → ejecutado
  eje3_diciembre        EJE-3: líneas que concentran su gasto en diciembre
  est3_creaciones       EST-1 / 3: cambios institucionales en enero vs en el año
  deu1_endeudamiento    DEU-1: uso del tope de endeudamiento del art. 3
  val2_dataset_vs_cgr   VAL-2: dónde difiere la ejecución publicada de la
                        de Contraloría (partida × año)

Uso:
    python pipeline/5_informe/22_graficos_hallazgos.py
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from dipres.config import DIRS
from dipres.viz import (AQUA, AZUL, DIVERGENTE, EJE, NARANJA, SUPERFICIE,
                        TINTA, TINTA_2, TINTA_MUTED, ULTIMO_ANIO, PERIODO, ejecutar,
                        ejes_anio, leer, monto_mm, nota, num, pct_txt,
                        titulo, titulo_caso)

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
            f"{PERIODO}."),
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
# ING-1: error de proyección de ingresos
# =====================================================
GRIS_CONTEXTO = "#a3a29b"


def grafico_ing1() -> tuple[go.Figure, int] | None:
    a = leer("ingresos_agregados", "18_ingresos.py")
    if a is None:
        return None
    a = a[(a.moneda == "PESOS") & (a.anio <= ULTIMO_ANIO)]
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=EJE, width=1))
    pos = ejes_anio(fig, sorted(a.anio.unique()))
    finales, errores_fmi = [], None
    # La suma de subtítulos va en gris: es el contexto, no el hallazgo
    for clave, etiqueta, color in [("ingenuo_01_15", "Suma de subtítulos 01-15",
                                    GRIS_CONTEXTO),
                                   ("ingreso_gfs", "Perímetro FMI", AZUL)]:
        d = a[a.agregado == clave].sort_values("anio")
        if d.empty:
            continue
        y = d.error_vs_inicial * 100
        if clave == "ingreso_gfs":
            errores_fmi = y
        fig.add_trace(go.Scatter(
            x=d.anio.astype(str), y=y, name=etiqueta, mode="lines+markers",
            line=dict(color=color, width=2.5 if clave == "ingreso_gfs" else 2),
            marker=dict(size=8, color=color, line=dict(width=2, color=SUPERFICIE)),
            customdata=[[monto_mm(i / 1000), monto_mm(e / 1000)]
                        for i, e in zip(d.inicial, d.ejecutado)],
            hovertemplate=(f"<b>{etiqueta}</b> · %{{x}}<br>"
                           "Error: %{y:+.1f}%<br>Ley inicial: %{customdata[0]}"
                           "<br>Recaudado: %{customdata[1]}<extra></extra>")))
        # Sesgo (promedio con signo) y tamaño del error (promedio absoluto)
        texto = (f"<b>{etiqueta}</b><br>sesgo {pct_txt(y.mean(), 1)}<br>"
                 f"error típico {num(y.abs().mean(), 1)}%")
        finales.append((y.iloc[-1], pos[int(d.anio.iloc[-1])], texto, color))
    finales.sort(key=lambda z: z[0])
    cerca = len(finales) == 2 and abs(finales[1][0] - finales[0][0]) < 10
    for k, (yf, xf, texto, color) in enumerate(finales):
        fig.add_annotation(x=xf, y=yf, text=texto, xanchor="left", xshift=10,
                           align="left", showarrow=False,
                           font=dict(size=11, color=color),
                           yshift=(-16 if k == 0 else 16) if cerca else 0)
    fig.update_yaxes(ticksuffix="%", title=None)
    maximo = errores_fmi.abs().max() if errores_fmi is not None else 0
    fig.update_layout(
        title=titulo(
            "Con el perímetro del FMI desaparece el sesgo, pero no el error: "
            f"hasta {num(maximo, 0)}% en un año",
            "Error de la Ley de Presupuestos: (recaudado − ley inicial) / ley "
            "inicial. Positivo: se recaudó más de lo proyectado.<br>Moneda "
            f"nacional, {PERIODO}."),
        showlegend=False, hovermode="closest",
        margin=dict(l=55, r=175, t=110, b=150))
    nota(fig, [
        "Sesgo: promedio del error con signo. Error típico: promedio del error "
        "sin signo.",
        "La suma de subtítulos incluye endeudamiento, venta de activos "
        "financieros y recuperación de préstamos, que son financiamiento y no "
        "ingreso,",
        "y las operaciones de cambio: dólares convertidos a pesos, que en moneda "
        "nacional se registran como ingreso.",
        "Perímetro según el Manual de Estadísticas de Finanzas Públicas del FMI. "
        "Fuente: datos.gob.cl (DIPRES). Hallazgo ING-1.",
    ], bajo_eje=True)
    return fig, 560


# =====================================================
# MOD-1 / EJE-1
# =====================================================
def grafico_mod1() -> tuple[go.Figure, int] | None:
    m = leer("modificaciones_resumen", "16_modificaciones.py")
    e = leer("ejecucion_resumen", "17_ejecucion.py")
    if m is None or e is None:
        return None
    filtro = lambda d: d[(d.moneda == "PESOS") & (d.seccion == "GASTOS")
                         & d.anio_completo & (d.anio <= ULTIMO_ANIO)]
    d = (filtro(m)[["anio", "inicial", "vigente"]]
         .merge(filtro(e)[["anio", "ejecutado", "pct_ejecucion"]], on="anio")
         .sort_values("anio"))
    x = d.anio.astype(str)
    a_billones = lambda v: v / 1e9          # miles de pesos → billones
    barras = [("inicial", "Ley inicial", "#c3c2b7"),
              ("vigente", "Ley vigente al cierre", AZUL),
              ("ejecutado", "Ejecutado", AQUA)]
    fig = go.Figure()
    for col, etiqueta, color in barras:
        fig.add_trace(go.Bar(
            x=x, y=a_billones(d[col]), name=etiqueta, marker_color=color,
            marker_line=dict(width=0),
            customdata=[monto_mm(v / 1000) for v in d[col]],
            hovertemplate=f"<b>{etiqueta}</b> · %{{x}}<br>%{{customdata}}"
                          "<extra></extra>"))
    pos = ejes_anio(fig, d.anio)
    # Etiqueta selectiva: cuánto creció la ley en el año
    for r in d.itertuples():
        fig.add_annotation(
            x=pos[int(r.anio)], y=a_billones(max(r.vigente, r.ejecutado)),
            text=pct_txt((r.vigente / r.inicial - 1) * 100, 0),
            yshift=10, showarrow=False, font=dict(size=11, color=TINTA))
    fig.update_yaxes(title=dict(text="Billones de pesos", font=dict(size=11)),
                     rangemode="tozero")
    fig.update_layout(
        title=titulo(
            "El presupuesto de gastos se amplía todos los años, y se ejecuta "
            "casi todo lo ampliado",
            "Gastos del Gobierno Central sin aporte fiscal, moneda nacional, "
            f"{PERIODO}. Sobre cada año: crecimiento de la ley durante el año."),
        barmode="group", bargap=0.25, bargroupgap=0.08,
        legend=dict(orientation="h", x=0.5, xanchor="center", y=1.02,
                    yanchor="bottom", font=dict(size=11)),
        margin=dict(l=70, r=30, t=120, b=100))
    nota(fig, [
        "La ley vigente incluye leyes dictadas durante el año (reajuste, "
        "emergencias), que el dato no distingue de los decretos.",
        "Fuente: datos.gob.cl (DIPRES). Hallazgos MOD-1 y EJE-1.",
    ], bajo_eje=True)
    return fig, 540


# =====================================================
# EJE-3
# =====================================================
def grafico_eje3(max_lineas: int = 15) -> tuple[go.Figure, int] | None:
    r = leer("ejecucion_recurrencia", "17_ejecucion.py")
    if r is None:
        return None
    d = r[(r.senal == "concentracion_dic") & (r.moneda == "PESOS")].copy()
    if d.empty:
        print("  · eje3: sin líneas con concentración en diciembre")
        return None
    # Mediana sobre 100%: el resto del año suma negativo, y el % de diciembre
    # deja de medir concentración
    fuera = d[d.pct_dic_mediana > 100]
    for f in fuera.itertuples():
        print(f"  · eje3 excluye {f.nombre_partida} subt. {f.subtitulo}: "
              f"mediana {f.pct_dic_mediana:.0f}%")
    d = d[d.pct_dic_mediana <= 100].copy()
    # Solo las líneas que superan el umbral todos los años: las esporádicas
    # (1 o 2 años con todo el gasto en diciembre) son pagos únicos, no patrón
    d["todos"] = d.anios_senal == d.de_anios
    n_algunos = int((~d.todos).sum())
    d = (d[d.todos].sort_values("pct_dic_mediana", ascending=False)
         .head(max_lineas).iloc[::-1])          # la mayor arriba
    d["etiqueta"] = [f"{corto(titulo_caso(p))} · subt. {int(s)}"
                     for p, s in zip(d.nombre_partida, d.subtitulo)]
    fig = go.Figure(go.Bar(
        x=d.pct_dic_mediana, y=d.etiqueta, orientation="h",
        marker_color=[AZUL if t else "#c3c2b7" for t in d.todos],
        text=[f"{a}/{n} años" for a, n in zip(d.anios_senal, d.de_anios)],
        textposition="outside", textfont=dict(size=10, color=TINTA_2),
        cliponaxis=False,
        customdata=[[titulo_caso(n), a] for n, a in zip(d.nombre_subtitulo, d.anios)],
        hovertemplate=("<b>%{y}</b><br>%{customdata[0]}<br>Mediana en "
                       "diciembre: %{x:.0f}% del gasto del año<br>Años: "
                       "%{customdata[1]}<extra></extra>")))
    for v, txt in [(100 / 12, "mes parejo (8%)"), (25, "umbral (25%)")]:
        fig.add_vline(x=v, line=dict(color=TINTA_MUTED, width=1, dash="dot"))
        fig.add_annotation(x=v, y=1, yref="paper", text=txt, showarrow=False,
                           yanchor="bottom", font=dict(size=10, color=TINTA_MUTED))
    fig.update_xaxes(ticksuffix="%", range=[0, 100], showgrid=True,
                     tickvals=[0, 20, 40, 60, 80, 100],
                     ticktext=[f"{v}%" for v in (0, 20, 40, 60, 80, 100)])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11, color=TINTA),
                     automargin=True)
    fig.update_layout(
        title=titulo(
            "Las mismas líneas concentran su gasto en diciembre, año tras año",
            "Mediana del % del gasto anual ejecutado en diciembre, líneas que "
            f"superan el 25% todos los años. Moneda nacional, {PERIODO}."),
        bargap=0.35, showlegend=False, margin=dict(l=10, r=75, t=120, b=115))
    lineas = ["Umbral: 25% del gasto del año en diciembre, tres veces un mes "
              f"parejo. Otras {n_algunos} líneas lo superan solo algunos años."]
    if len(fuera):
        lineas.append(f"Se excluyen {len(fuera)} líneas con mediana sobre 100%: "
                      "el resto del año suma montos netos negativos.")
    lineas.append("El dato no distingue gasto de fin de año de calendarios de "
                  "licitación o pagos contra entrega. Fuente: datos.gob.cl "
                  "(DIPRES). Hallazgo EJE-3.")
    nota(fig, lineas, bajo_eje=True)
    return fig, max(420, 30 * len(d) + 260)


# =====================================================
# EST-1 / EST-3
# =====================================================
def grafico_est3() -> tuple[go.Figure, int] | None:
    e = leer("estructura_resumen_anual", "20_estructura_institucional.py")
    if e is None:
        return None
    col = "Año" if "Año" in e.columns else e.columns[0]
    e = e[e[col] > e[col].min()].sort_values(col)   # el 1er año no tiene base
    x = e[col].astype(str)
    fig = go.Figure()
    for c, etiqueta, color in [("en_enero", "En enero (Ley de Presupuestos)", AZUL),
                               ("durante_el_año", "Durante el año (leyes y decretos)",
                                NARANJA)]:
        fig.add_trace(go.Bar(
            x=x, y=e[c], name=etiqueta, marker_color=color,
            marker_line=dict(width=2, color=SUPERFICIE),
            hovertemplate=f"<b>{etiqueta}</b> · %{{x}}<br>%{{y}} cambios"
                          "<extra></extra>"))
    pos = ejes_anio(fig, e[col])
    for anio, total, tasa in zip(e[col], e.en_enero + e["durante_el_año"],
                                 e.tasa_cambio_pct):
        fig.add_annotation(x=pos[int(anio)], y=total, text=f"{num(tasa, 1)}%",
                           yshift=10, showarrow=False,
                           font=dict(size=10, color=TINTA_2))
    fig.update_yaxes(title=dict(text="Altas, bajas y traslados de servicios",
                                font=dict(size=11)), rangemode="tozero")
    fig.update_layout(
        title=titulo(
            "Desde 2022, los cambios de servicios ocurren en enero, con la Ley de "
            "Presupuestos",
            "Altas, bajas y traslados de capítulos (servicios) por año y momento "
            "en que ocurren. Sobre cada barra: % de los servicios que cambió."),
        barmode="stack", bargap=0.35,
        legend=dict(orientation="h", x=0.5, xanchor="center", y=1.02,
                    traceorder="normal",
                    yanchor="bottom", font=dict(size=11)),
        margin=dict(l=70, r=30, t=120, b=100))
    ultimo = int(e[col].max())
    nota(fig, [
        "No incluye cambios de nombre. Una institución que cambia de nombre al "
        "trasladarse cuenta como alta y baja.",
        f"{ultimo}: año en curso, con datos parciales. Fuente: datos.gob.cl "
        f"(DIPRES). Hallazgos EST-1 y EST-3.",
    ], bajo_eje=True)
    return fig, 520


# =====================================================
# DEU-1
# =====================================================
LECTURA = {
    "DENTRO": ("Dentro del tope", AZUL),
    "INDETERMINADO": ("Indeterminado", "#898781"),
    "SOBRE ART.3, CABE EN LEY": ("Sobre el art. 3, cabe en la Ley 21.288", AQUA),
    "SOBRE": ("Sobre el tope", "#e34948"),
}


def grafico_deu1() -> tuple[go.Figure, int] | None:
    t = leer("tope_endeudamiento", "11b_tope_endeudamiento.py")
    if t is None:
        return None
    t = t[t["Año"] <= ULTIMO_ANIO].sort_values("Año")
    x = t["Año"].astype(str)
    fig = go.Figure()
    fig.add_hline(y=100, line=dict(color=TINTA_MUTED, width=1, dash="dot"))
    fig.add_annotation(x=1, xref="paper", y=100, text="tope del<br>art. 3",
                       xanchor="left", xshift=6, align="left", showarrow=False,
                       font=dict(size=10, color=TINTA_MUTED))
    # Rango: el endeudamiento real queda entre el neto y el bruto
    for r in t.itertuples():
        fig.add_trace(go.Scatter(
            x=[str(r.Año)] * 2, y=[r.uso_neto_pct, r.uso_bruto_pct],
            mode="lines", line=dict(color="#c3c2b7", width=6),
            hoverinfo="skip", showlegend=False))
    vistos = set()
    for r in t.itertuples():
        etiqueta, color = LECTURA.get(r.lectura, (r.lectura, TINTA_2))
        fig.add_trace(go.Scatter(
            x=[str(r.Año)], y=[r.uso_neto_pct], mode="markers",
            marker=dict(size=11, color=color, line=dict(width=2, color=SUPERFICIE)),
            name=etiqueta, legendgroup=etiqueta, showlegend=etiqueta not in vistos,
            customdata=[[num(r.uso_bruto_pct, 0), num(r.tope_total / 1e6, 1)]],
            hovertemplate=(f"<b>%{{x}}</b> · {etiqueta}<br>Uso neto: %{{y:.0f}}%"
                           "<br>Uso bruto: %{customdata[0]}%<br>Tope: "
                           "US$ %{customdata[1]} mil millones<extra></extra>")))
        vistos.add(etiqueta)
    ejes_anio(fig, t["Año"])
    fig.update_yaxes(ticksuffix="%", rangemode="tozero",
                     title=dict(text="Uso del tope", font=dict(size=11)))
    sobre = [str(a) for a in t.loc[t.lectura == "SOBRE", "Año"]]
    n_ind = int((t.lectura == "INDETERMINADO").sum())
    principal = (f"El endeudamiento neto superó el tope en "
                 f"{' y '.join([', '.join(sobre[:-1]), sobre[-1]] if len(sobre) > 1 else sobre)}"
                 if sobre else "El endeudamiento neto no superó el tope")
    if n_ind:
        principal += f"; en {n_ind} años el dato no permite determinarlo"
    fig.update_layout(
        title=titulo(
            principal,
            "Endeudamiento del Tesoro como % del tope del art. 3 de cada Ley de "
            "Presupuestos. Punto: neto de amortizaciones. Barra gris: hasta el "
            "bruto."),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=1.02,
                    yanchor="bottom", font=dict(size=11)),
        margin=dict(l=70, r=80, t=120, b=110))
    nota(fig, [
        "El cómputo legal requiere el detalle de cada emisión: el uso real está "
        "entre el neto y el bruto. Indeterminado: el tope cae dentro de ese "
        "rango.",
        "2020-2021: la Ley 21.288 (Fondo COVID) autorizó US$ 8.000 millones "
        "adicionales. Fuente: datos.gob.cl y leyes de presupuestos. Hallazgo "
        "DEU-1.",
    ], bajo_eje=True)
    return fig, 540


# =====================================================
GRAFICOS = {
    "ing1_perimetro": grafico_ing1,
    "mod1_eje1_presupuesto": grafico_mod1,
    "eje3_diciembre": grafico_eje3,
    "est3_creaciones": grafico_est3,
    "deu1_endeudamiento": grafico_deu1,
    "val2_dataset_vs_cgr": grafico_val2,
}

if __name__ == "__main__":
    ejecutar(GRAFICOS, "GRÁFICOS DE HALLAZGOS")