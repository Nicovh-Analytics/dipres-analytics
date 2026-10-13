"""
20_estructura_institucional.py — Creación y reestructuración de instituciones
==============================================================================
Pregunta: ¿cuánto cambia la estructura institucional del Gobierno Central
cada año, y los descuadres entre niveles de DIPRES coinciden con esos
cambios?

1. Eventos por mes (desde ley_capitulo): altas, bajas, traslados entre
   partidas (por nombre o por traspaso parcial de presupuesto), renombres
   y códigos reutilizados. Distingue los que ocurren en enero (los fija la
   Ley de Presupuestos) de los que ocurren durante el año. Los nombres que
   alternan entre versiones (NOMBRE_INESTABLE) se cuentan aparte: son
   ruido de la fuente, no cambios reales.
2. Tasa anual de cambio = eventos / capítulos vigentes.
3. Descuadres: meses en que una partida suma MÁS que sus capítulos
   (consolidar solo resta, así que esto no puede ser consolidación) y
   qué parte coincide con un evento de estructura de esa partida, desde
   1 mes antes hasta 6 meses después (el archivo de partidas incorpora un
   servicio nuevo antes que el de capítulos).

Salidas (DIRS["reportes"]):
  estructura_eventos.csv, estructura_resumen_anual.csv,
  descuadres_partida_capitulo.csv, estructura_institucional.png

Uso:
    python 20_estructura_institucional.py
"""

import pandas as pd

from dipres.config import DIRS, TOLERANCIAS
from dipres.estructura import (VENTANA_ANTES, VENTANA_DESPUES, asociar,
                        catalogo_capitulos, descuadres_partida,
                        eventos_estructura, montos_capitulo)

COLS = ["Año", "Mes", "Moneda", "Partida", "Capítulo", "Subtítulo",
        "Nombre Partida", "Nombre Capítulo", "ley_vigente"]


def cargar(nombre: str) -> pd.DataFrame:
    return pd.read_csv(DIRS["consolidado"] / nombre, encoding="utf-8-sig",
                       usecols=lambda c: c in COLS, low_memory=False)


AZUL, NARANJA = "#2a78d6", "#eb6834"      # paleta validada (dataviz)
TINTA, TINTA2, GRILLA = "#0b0b0b", "#52514e", "#e4e3df"


def graficar(res: pd.DataFrame, desc: pd.DataFrame, ruta) -> None:
    """Dos paneles con el mismo eje de años (sin doble eje Y):
    arriba, cambios de estructura apilados enero / durante el año;
    abajo, descuadres partida > Σ capítulos."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    anios = [int(a) for a in res.index]
    x = range(len(anios))
    ene = res["en_enero"].to_numpy()
    dur = res["durante_el_año"].to_numpy()
    nd = (desc.groupby("Año").size().reindex(res.index, fill_value=0).to_numpy()
          if not desc.empty else [0] * len(anios))

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 2]})
    for ax in (a1, a2):
        ax.set_facecolor("#fcfcfb")
        ax.grid(axis="y", color=GRILLA, linewidth=0.8)
        ax.set_axisbelow(True)
        for lado in ("top", "right", "left"):
            ax.spines[lado].set_visible(False)
        ax.spines["bottom"].set_color(TINTA2)
        ax.tick_params(colors=TINTA2, length=0)
    fig.patch.set_facecolor("#fcfcfb")

    a1.bar(x, ene, width=0.6, color=AZUL, label="En enero (Ley de Presupuestos)",
           edgecolor="#fcfcfb", linewidth=2)
    a1.bar(x, dur, width=0.6, bottom=ene, color=NARANJA,
           label="Durante el año", edgecolor="#fcfcfb", linewidth=2)
    a1.set_title("Altas, bajas y traslados de servicios por año",
                 loc="left", color=TINTA, fontsize=12)
    a1.legend(frameon=False, loc="upper left", labelcolor=TINTA2, fontsize=9)

    a2.bar(x, nd, width=0.6, color=TINTA2, edgecolor="#fcfcfb", linewidth=2)
    for i, v in enumerate(nd):
        if v:
            a2.text(i, v, f"{int(v)}", ha="center", va="bottom", color=TINTA2,
                    fontsize=9)
    a2.set_title("Meses-partida en que la partida suma más que sus capítulos",
                 loc="left", color=TINTA, fontsize=11)
    a2.set_xticks(list(x), [str(a) for a in anios])

    fig.text(0.01, 0.005, "Fuente: DIPRES, Ley de Presupuestos por capítulo y "
             "partida. Descuadre = partida > Σ capítulos (no puede ser "
             "consolidación).", color=TINTA2, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    print(f"\n  Gráfico: {ruta}")


if __name__ == "__main__":
    cap = cargar("ley_capitulo.csv")
    par = cargar("ley_partida.csv")

    cat = catalogo_capitulos(cap)
    ev = eventos_estructura(cat, montos_capitulo(cap))
    inestables = ev[ev["tipo"] == "NOMBRE_INESTABLE"]

    # ── 1. Eventos ────────────────────────────────────
    print("=" * 78)
    print("  CAMBIOS DE ESTRUCTURA INSTITUCIONAL (capítulos de la Ley de Presupuestos)")
    print("=" * 78)
    for (a, m), g in ev[ev["tipo"] != "NOMBRE_INESTABLE"].groupby(
            ["Año", "periodo"], sort=True):
        mes = g["Mes"].iloc[0]
        print(f"\n  {mes} {a}")
        for _, e in g.iterrows():
            det = f"  [{e['detalle']}]" if e["detalle"] else ""
            print(f"    {e['tipo']:<18} {e['Partida']:02d}-{e['Capítulo']:02d} "
                  f"{str(e['nombre'])[:48]}{det}")

    if not inestables.empty:
        cods = inestables.groupby(["Partida", "Capítulo"]).size()
        print(f"\n  NOMBRE_INESTABLE (omitidos arriba): {len(inestables)} cambios en "
              f"{len(cods)} capítulos que alternan entre nombres ya usados")

    # ── 2. Resumen anual ──────────────────────────────
    vigentes = cat.groupby("Año").apply(
        lambda g: g.groupby("periodo").size().mean(), include_groups=False)
    tipos = ["ALTA", "BAJA", "TRASLADO", "RENOMBRE", "CODIGO_REUTILIZADO",
             "NOMBRE_INESTABLE"]
    res = (ev.pivot_table(index="Año", columns="tipo", values="periodo",
                          aggfunc="count", fill_value=0)
             .reindex(columns=tipos, fill_value=0)
             .reindex(sorted(cat["Año"].unique()), fill_value=0))
    # Enero / durante el año: solo cambios estructurales (alta, baja, traslado)
    estr = ev[ev["tipo"].isin(["ALTA", "BAJA", "TRASLADO"])]
    res["en_enero"] = estr[estr["inicio_de_año"]].groupby("Año").size() \
        .reindex(res.index, fill_value=0)
    res["durante_el_año"] = estr[~estr["inicio_de_año"]].groupby("Año").size() \
        .reindex(res.index, fill_value=0)
    res["capitulos_promedio"] = vigentes.round(0)
    estructurales = res[["ALTA", "BAJA", "TRASLADO"]].sum(axis=1)
    res["tasa_cambio_pct"] = (estructurales / res["capitulos_promedio"] * 100).round(1)

    print(f"\n{'=' * 78}\n  RESUMEN ANUAL\n{'=' * 78}\n")
    print(res.to_string())
    print("\n  tasa_cambio = (altas + bajas + traslados) / capítulos promedio del año")
    print("  en_enero / durante_el_año: solo altas, bajas y traslados")
    print("  El primer mes del primer año no tiene mes anterior: no genera eventos")

    # ── 3. Descuadres y su asociación ─────────────────
    desc = asociar(descuadres_partida(par, cap, tol=TOLERANCIAS["monto"]), ev)
    print(f"\n{'=' * 78}\n  DESCUADRES: partida > Σ capítulos\n{'=' * 78}")
    if desc.empty:
        print("\n  Sin descuadres")
    else:
        con = desc["evento"] != ""
        print(f"\n  {len(desc)} casos (Año-Mes-Moneda-Partida) · "
              f"{int(con.sum())} ({con.mean() * 100:.0f}%) coinciden con un cambio "
              f"de estructura de la misma partida (de {VENTANA_ANTES} mes antes a "
              f"{VENTANA_DESPUES} después)")
        if con.any():
            d = desc.loc[con, "distancia"].astype(int)
            print(f"  meses entre descuadre y evento: mediana {d.median():+.0f} "
                  f"(positivo: el capítulo aparece después)")
        anual = desc.groupby("Año").agg(casos=("Partida", "size"),
                                        con_evento=("evento", lambda s: (s != "").sum()))
        print("\n" + anual.to_string())
        print("\n  Casos sin evento asociado (los más grandes en pesos):")
        sin = desc[~con & (desc["Moneda"] == "PESOS")].nlargest(10, "exceso")
        for _, r in sin.iterrows():
            print(f"    {r['Mes']} {r['Año']} partida {r['Partida']:02d}: "
                  f"{r['exceso']:,.0f} en {r['subtitulos']} subtítulos")

    # ── 4. Gráfico ────────────────────────────────────
    graficar(res, desc, DIRS["reportes"] / "estructura_institucional.png")

    out = DIRS["reportes"]
    ev.to_csv(out / "estructura_eventos.csv", index=False, encoding="utf-8-sig")
    res.to_csv(out / "estructura_resumen_anual.csv", encoding="utf-8-sig")
    desc.to_csv(out / "descuadres_partida_capitulo.csv", index=False,
                encoding="utf-8-sig")
    print(f"\n  Salidas en {out}")