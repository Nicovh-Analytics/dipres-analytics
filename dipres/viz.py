"""
viz.py — Estilo común de los gráficos del proyecto
===================================================
Paleta, tipografía y exportación, para que todos los gráficos se vean
como un solo sistema. Cada gráfico se guarda dos veces:
  docs/graficos/<nombre>.png   estático, para el README y HALLAZGOS.md
  docs/graficos/<nombre>.html  interactivo (hover, zoom), para GitHub Pages

Paleta: la de referencia del método de visualización (categórica en orden
fijo, divergente azul ↔ rojo con gris neutro al centro).

Requiere: pip install plotly kaleido
(kaleido usa Chrome para el PNG; si no lo encuentra: plotly_get_chrome)
Al final: funciones comunes a los scripts de gráficos (lectura de reportes,
eje de años, formatos) y el ejecutor.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from dipres.config import DIRS
from dipres.hallazgos import Registro

SALIDA = DIRS["docs"] / "graficos"

# ── Tinta y superficies (modo claro) ─────────────────
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_MUTED = "#898781"
GRILLA = "#e1e0d9"
EJE = "#c3c2b7"
NEUTRO = "#f0efec"          # punto medio divergente: "sin diferencia"

FUENTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# Categórica, en orden fijo (nunca se cicla ni se reordena por ranking)
CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
              "#e87ba4", "#008300", "#6250d6", "#e34948"]

# Divergente: rojo (negativo) ↔ gris ↔ azul (positivo), tres pasos por brazo
DIVERGENTE = [
    [0.00, "#a8262a"], [0.25, "#e34948"], [0.42, "#f4b4b0"],
    [0.50, NEUTRO],
    [0.58, "#9ec5f4"], [0.75, "#2a78d6"], [1.00, "#184f95"],
]


def num(x: float, dec: int = 0) -> str:
    """Formato es-CL: punto de miles, coma decimal."""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def monto_mm(x: float) -> str:
    """
    Millones de pesos en palabras legibles: 950 millones · 265,2 mil millones ·
    4,23 billones (billón chileno = millón de millones).
    """
    a, signo = abs(x), ("−" if x < 0 else "")
    if a >= 1_000_000:
        return f"{signo}{num(a / 1_000_000, 2)} billones de pesos"
    if a >= 1_000:
        return f"{signo}{num(a / 1_000, 1)} mil millones de pesos"
    return f"{signo}{num(a)} millones de pesos"


# Firma de autoría: va en todos los gráficos, discreta, abajo a la derecha
FIRMA = "nicovh-analytics | dipres-analytics"


def titulo(principal: str, sub: str) -> dict:
    """Título centrado + subtítulo con qué se mide."""
    return dict(
        text=(f"<b>{principal}</b><br>"
              f"<span style='font-size:13px;color:{TINTA_2}'>{sub}</span>"),
        # Distancia al borde en px y no en fracción: con y=0.985 el título
        # se cortaba en los gráficos bajos (1,5% de 520 px son 8 px)
        x=0.5, xanchor="center", y=1, yref="container", yanchor="top",
        pad=dict(t=26), font=dict(size=17, color=TINTA))


def nota(fig: go.Figure, lineas: list[str], bajo_eje: bool = False) -> None:
    """
    Notas y fuente al pie: centradas, en cursiva y tinta tenue.
    Ojo: no usar "$" en textos de plotly; dos "$" en un mismo texto lo
    convierten en fórmula LaTeX. Escribir "pesos".
    bajo_eje: True si el eje x tiene etiquetas abajo (la nota baja para no
    montarse sobre ellas).
    """
    fig.add_annotation(
        text="<br>".join(f"<i>{l}</i>" for l in lineas),
        xref="paper", yref="paper", x=0.5, y=0, yshift=-36 if bajo_eje else -12,
        xanchor="center", yanchor="top", showarrow=False, align="center",
        font=dict(size=11, color=TINTA_MUTED))


def firmar(fig: go.Figure, borde: int = 10) -> None:
    """
    Firma en la esquina inferior derecha del lienzo, a `borde` px del canto.
    Las coordenadas "paper" son las del área de datos, así que se desplaza
    por el margen derecho e inferior para llegar a la esquina del lienzo.
    """
    m = fig.layout.margin
    fig.add_annotation(
        text=FIRMA, xref="paper", yref="paper", x=1, y=0,
        xshift=(m.r if m.r is not None else 80) - borde,
        yshift=-((m.b if m.b is not None else 80) - borde),
        xanchor="right", yanchor="bottom", showarrow=False,
        font=dict(size=10, color=TINTA_MUTED))


_plantilla = go.layout.Template()
_plantilla.layout = go.Layout(
    font=dict(family=FUENTE, size=12, color=TINTA_2),
    paper_bgcolor=SUPERFICIE, plot_bgcolor=SUPERFICIE,
    colorway=CATEGORICA,
    xaxis=dict(gridcolor=GRILLA, linecolor=EJE, zeroline=False,
               tickfont=dict(color=TINTA_2), ticks=""),
    yaxis=dict(gridcolor=GRILLA, linecolor=EJE, zeroline=False,
               tickfont=dict(color=TINTA_2), ticks=""),
    hoverlabel=dict(bgcolor="white", bordercolor=EJE,
                    font=dict(family=FUENTE, size=12, color=TINTA)),
    separators=",.",          # decimales con coma, miles con punto
)
pio.templates["dipres"] = _plantilla
pio.templates.default = "dipres"


def guardar(fig: go.Figure, nombre: str, ancho: int = 1000,
            alto: int = 600) -> list[Path]:
    """
    Escribe <nombre>.html (siempre) y <nombre>.png (si hay kaleido).
    El tamaño queda fijo en el layout para que el HTML se vea igual que el
    PNG (si no, plotly lo adapta al ancho de la ventana y todo se corre).
    """
    fig.update_layout(width=ancho, height=alto, autosize=False)
    firmar(fig)
    SALIDA.mkdir(parents=True, exist_ok=True)
    html = SALIDA / f"{nombre}.html"
    fig.update_layout(modebar=dict(orientation="v", bgcolor="rgba(0,0,0,0)",
                                   color=TINTA_MUTED, activecolor=TINTA_2))
    fig.write_html(html, include_plotlyjs="cdn", full_html=True, config={
        "displaylogo": False, "locale": "es",
        # Solo descargar imagen y restablecer vista: el resto (lazo,
        # selección, paneo) no aporta en gráficos de lectura
        "modeBarButtons": [["toImage", "resetScale2d"]],
        "toImageButtonOptions": {"format": "png", "filename": nombre,
                                 "scale": 2},
    })
    escritos = [html]
    try:
        png = SALIDA / f"{nombre}.png"
        fig.write_image(png, scale=2)
        escritos.append(png)
    except Exception as e:                        # kaleido o Chrome ausentes
        print(f"  ⚠ PNG no generado ({type(e).__name__}): {e}")
        print("    Instalar: pip install kaleido · luego: plotly_get_chrome")
    return escritos


# =====================================================
# Comunes a los scripts de gráficos (22 y 23)
# =====================================================
ULTIMO_ANIO = 2025              # último año cerrado que muestran los gráficos
AZUL, NARANJA, AQUA = CATEGORICA[0], CATEGORICA[1], CATEGORICA[2]


def leer(nombre: str, script: str) -> pd.DataFrame | None:
    try:
        return pd.read_csv(DIRS["reportes"] / f"{nombre}.csv",
                           encoding="utf-8-sig")
    except FileNotFoundError:
        print(f"  · falta {nombre}.csv (correr {script})")
        return None


def pct_txt(x: float, dec: int = 1) -> str:
    return f"{'+' if x > 0 else ''}{num(x, dec)}%"


def ejes_anio(fig: go.Figure, anios) -> dict:
    """
    Eje x categórico de años. Devuelve {año: posición} para las anotaciones:
    en un eje categórico, una anotación con x="2017" se lee como la posición
    2017 y no como la categoría, y estira el eje hasta ahí.
    """
    anios = [int(a) for a in anios]
    fig.update_xaxes(type="category", tickmode="array",
                     tickvals=[str(a) for a in anios], showgrid=False,
                     tickfont=dict(color=TINTA),
                     # Rango fijo: si no, plotly ensancha el eje para que
                     # quepan las anotaciones (las etiquetas finales del ING-1)
                     range=[-0.5, len(anios) - 0.5])
    return {a: i for i, a in enumerate(anios)}


def titulo_caso(s) -> str:
    """'MINISTERIO DE EDUCACIÓN' → 'Ministerio de Educación'."""
    menores = {"de", "del", "la", "las", "los", "el", "y", "e", "a", "en"}
    ps = str(s).strip().lower().split()
    return " ".join(p if (i and p in menores) else p[:1].upper() + p[1:]
                    for i, p in enumerate(ps))


def ejecutar(graficos: dict, encabezado: str, ancho: int = 900) -> None:
    """
    Genera cada gráfico de {nombre: función}; la función devuelve (figura,
    alto) o None si faltan sus datos. Registra un aviso por gráfico sin
    datos o sin PNG (kaleido/Chrome ausente), para que se vea en run.py.
    """
    print("=" * 78)
    print(f"  {encabezado}")
    print("=" * 78)
    # El reporte toma el nombre del script que llama (22 o 23), sin "22_"
    nombre_script = Path(sys.argv[0]).stem.split("_", 1)[-1]
    reg = Registro(nombre_script, salida_dir=DIRS["reportes"], eco=False)
    for nombre, f in graficos.items():
        r = f()
        if r is None:
            reg.warn("datos", f"{nombre}: sin datos, no se generó",
                     patron="gráfico sin datos")
            continue
        fig, alto = r
        escritos = guardar(fig, nombre, ancho=ancho, alto=alto)
        for p in escritos:
            print(f"  ✓ {p}")
        if any(p.suffix == ".png" for p in escritos):
            reg.ok("png", nombre)
        else:
            reg.warn("png", f"{nombre}: solo HTML, sin PNG",
                     patron="PNG no generado (kaleido o Chrome)")
    reg.emitir()