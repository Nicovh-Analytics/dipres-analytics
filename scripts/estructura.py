"""
estructura.py — Cambios en la estructura institucional y descuadres entre niveles
=================================================================================
Funciones compartidas por 06_validar.py (aviso mes a mes) y
20_estructura_institucional.py (análisis completo).

  catalogo_capitulos   un registro por Año × Mes × Partida × Capítulo
  eventos_estructura   altas, bajas, traslados y renombres de capítulos
  descuadres_partida   meses en que la partida suma MÁS que sus capítulos
                       (imposible por consolidación: consolidar solo resta)
  asociar              qué descuadres coinciden con un cambio de estructura

Origen de la idea: en 2018 los archivos de partida y capítulo de DIPRES
quedaron descuadrados justo cuando se crearon el SLEP Barrancas (feb-mar)
y el Ministerio de las Culturas (may). Un nivel se actualizó antes que otro.
"""

import difflib
import re
import unicodedata

import pandas as pd

from dominio import MES_A_NUM, NUM_A_MES

SIMILITUD_MISMA_INSTITUCION = 0.85   # traslado: alta y baja con el mismo nombre
SIMILITUD_RENOMBRE = 0.60            # bajo esto, el código pasó a otra institución
TOL_TRASPASO = 0.001                 # traspaso parcial: |caída origen − alta| ≤ 0,1%
# Descuadre ↔ evento: el archivo de partidas incorpora un servicio nuevo
# 2-4 meses ANTES que el de capítulos, así que se busca el evento hasta
# VENTANA_DESPUES meses después del descuadre y VENTANA_ANTES meses antes
VENTANA_ANTES = 1
VENTANA_DESPUES = 6


def normalizar_nombre(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Za-z0-9 ]", " ", s.upper()).split())


def _similitud(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


# =====================================================
# Catálogo
# =====================================================
def catalogo_capitulos(ley_cap: pd.DataFrame) -> pd.DataFrame:
    """Año, Mes, periodo (Año*12+mes), Partida, Capítulo, nombre."""
    cols = ["Año", "Mes", "Partida", "Capítulo", "Nombre Capítulo"]
    c = (ley_cap[[x for x in cols if x in ley_cap.columns]]
         .drop_duplicates(["Año", "Mes", "Partida", "Capítulo"]).copy())
    c["MesNum"] = c["Mes"].map(MES_A_NUM)
    c["periodo"] = c["Año"].astype(int) * 12 + c["MesNum"] - 1
    c["nombre_norm"] = c.get("Nombre Capítulo", "").map(normalizar_nombre)
    return c.sort_values(["periodo", "Partida", "Capítulo"]).reset_index(drop=True)


def _etiqueta(periodo: int) -> tuple[int, str]:
    return periodo // 12, NUM_A_MES[periodo % 12 + 1]


# =====================================================
# Eventos
# =====================================================
def montos_capitulo(ley_cap: pd.DataFrame, campo="ley_vigente") -> pd.Series:
    """Ley vigente total en pesos por (periodo, Partida, Capítulo)."""
    c = ley_cap[ley_cap["Moneda"].str.upper() == "PESOS"]
    per = c["Año"].astype(int) * 12 + c["Mes"].map(MES_A_NUM) - 1
    return c.assign(periodo=per).groupby(["periodo", "Partida", "Capítulo"])[campo].sum()


def eventos_estructura(cat: pd.DataFrame, montos: pd.Series | None = None) -> pd.DataFrame:
    """Compara cada mes con el anterior disponible.

    ALTA       capítulo que aparece
    BAJA       capítulo que desaparece
    TRASLADO   alta que corresponde a otro capítulo: por nombre (una baja del
               mismo mes con el mismo nombre) o, con `montos`, por traspaso
               parcial (un capítulo existente cae en lo mismo que trae el
               nuevo; p. ej. Carabineros 05-31 → 32-03 en abril 2025)
    RENOMBRE   mismo código, nombre parecido pero distinto
    CODIGO_REUTILIZADO  mismo código, nombre de otra institución
    NOMBRE_INESTABLE    el nombre vuelve a uno que ese código ya usó: es
               alternancia en los archivos, no un cambio real
    """
    periodos = sorted(cat["periodo"].unique())
    por_p = {p: g.set_index(["Partida", "Capítulo"]) for p, g in cat.groupby("periodo")}
    historial: dict[tuple, set] = {}
    filas = []

    def fila(p, tipo, k, nombre, detalle=""):
        a, m = _etiqueta(p)
        filas.append({"Año": a, "Mes": m, "periodo": p, "tipo": tipo,
                      "Partida": k[0], "Capítulo": k[1], "nombre": nombre,
                      "detalle": detalle, "inicio_de_año": m == NUM_A_MES[1]})

    for k, n in por_p[periodos[0]]["nombre_norm"].items():
        historial.setdefault(k, set()).add(n)

    def traspaso(k, ant, act, A, B, usados):
        """Capítulo existente cuya caída calza con el monto del nuevo.
        Solo dentro del año: en enero cambia toda la ley y cualquier
        capítulo puede caer, por azar, en lo que trae uno nuevo."""
        if montos is None or (act, *k) not in montos.index or act % 12 == 0:
            return None
        v = montos[(act, *k)]
        if v <= 0:
            return None
        mejor = None
        for j in A.index.intersection(B.index):
            if j in usados or (ant, *j) not in montos.index \
                    or (act, *j) not in montos.index:
                continue
            caida = montos[(ant, *j)] - montos[(act, *j)]
            err = abs(caida - v)
            if err <= max(TOL_TRASPASO * v, 1) and (mejor is None or err < mejor[0]):
                mejor = (err, j, montos[(act, *j)])
        return mejor

    for ant, act in zip(periodos, periodos[1:]):
        A, B = por_p[ant], por_p[act]
        altas = B.index.difference(A.index)
        bajas = A.index.difference(B.index)

        # Traslados: emparejar altas y bajas por nombre
        usadas, origenes = set(), set()
        for k in altas:
            nb = B.at[k, "nombre_norm"]
            cand = [(_similitud(nb, A.at[j, "nombre_norm"]), j) for j in bajas
                    if j not in usadas]
            s, j = max(cand, default=(0, None))
            if j is not None and s >= SIMILITUD_MISMA_INSTITUCION:
                usadas.add(j)
                fila(act, "TRASLADO", k, B.at[k, "Nombre Capítulo"],
                     f"desde {j[0]:02d}-{j[1]:02d}")
            elif (t := traspaso(k, ant, act, A, B, origenes)) is not None:
                _, j2, queda = t
                origenes.add(j2)
                fila(act, "TRASLADO", k, B.at[k, "Nombre Capítulo"],
                     f"desde {j2[0]:02d}-{j2[1]:02d} (parcial: el origen conserva "
                     f"{queda:,.0f})")
            else:
                fila(act, "ALTA", k, B.at[k, "Nombre Capítulo"])
        for j in bajas:
            if j not in usadas:
                fila(act, "BAJA", j, A.at[j, "Nombre Capítulo"])

        # Mismo código, otro nombre
        for k in B.index.intersection(A.index):
            na, nb = A.at[k, "nombre_norm"], B.at[k, "nombre_norm"]
            if na != nb:
                if nb in historial.get(k, set()):
                    tipo = "NOMBRE_INESTABLE"
                else:
                    s = _similitud(na, nb)
                    tipo = "RENOMBRE" if s >= SIMILITUD_RENOMBRE else "CODIGO_REUTILIZADO"
                fila(act, tipo, k, B.at[k, "Nombre Capítulo"],
                     f"antes: {A.at[k, 'Nombre Capítulo']}")
        for k, n in B["nombre_norm"].items():
            historial.setdefault(k, set()).add(n)

    ev = pd.DataFrame(filas, columns=["Año", "Mes", "periodo", "tipo", "Partida",
                                      "Capítulo", "nombre", "detalle",
                                      "inicio_de_año"])
    # El primer cambio de una alternancia parece un renombre: si después el
    # nombre vuelve, todos sus renombres pasan a NOMBRE_INESTABLE
    inest = set(map(tuple, ev.loc[ev["tipo"] == "NOMBRE_INESTABLE",
                                  ["Partida", "Capítulo"]].values))
    if inest:
        es = [(p, c) in inest for p, c in zip(ev["Partida"], ev["Capítulo"])]
        ev.loc[pd.Series(es, index=ev.index) & (ev["tipo"] == "RENOMBRE"),
               "tipo"] = "NOMBRE_INESTABLE"
    return ev


# =====================================================
# Descuadres partida vs capítulos
# =====================================================
def descuadres_partida(ley_par: pd.DataFrame, ley_cap: pd.DataFrame,
                       campo="ley_vigente", tol=1.0) -> pd.DataFrame:
    """(Año, Mes, Partida) donde para algún subtítulo la partida supera
    la suma de sus capítulos. Por moneda; monto en la unidad de la moneda."""
    k = ["Año", "Mes", "Moneda", "Partida", "Subtítulo"]
    p = ley_par.groupby(k)[campo].sum()
    c = ley_cap.groupby(k)[campo].sum().reindex(p.index, fill_value=0)
    exceso = (p - c)
    exceso = exceso[exceso > tol].rename("exceso").reset_index()
    if exceso.empty:
        return exceso.assign(periodo=pd.Series(dtype=int))
    d = (exceso.groupby(["Año", "Mes", "Moneda", "Partida"])
               .agg(subtitulos=("Subtítulo", "nunique"), exceso=("exceso", "sum"))
               .reset_index())
    d["periodo"] = d["Año"].astype(int) * 12 + d["Mes"].map(MES_A_NUM) - 1
    return d


def asociar(desc: pd.DataFrame, ev: pd.DataFrame, antes=VENTANA_ANTES,
            despues=VENTANA_DESPUES) -> pd.DataFrame:
    """Agrega a cada descuadre el evento de estructura más cercano de la
    misma partida (o del origen de un traslado) entre `antes` meses antes y
    `despues` meses después. distancia = meses del evento − meses del
    descuadre (positiva: el evento llega después)."""
    if desc.empty:
        return desc.assign(evento="", distancia=pd.NA)
    ev = ev[ev["tipo"].isin(["ALTA", "BAJA", "TRASLADO", "CODIGO_REUTILIZADO"])].copy()
    origen = ev["detalle"].str.extract(r"desde (\d+)-")[0]
    ev2 = pd.concat([ev, ev[origen.notna()].assign(
        Partida=origen.dropna().astype(int).values)], ignore_index=True)
    out = []
    for _, r in desc.iterrows():
        dist = ev2["periodo"] - r["periodo"]
        e = ev2[(ev2["Partida"] == r["Partida"]) & (dist >= -antes) & (dist <= despues)]
        if e.empty:
            out.append(("", pd.NA))
        else:
            e = e.assign(d=e["periodo"] - r["periodo"])
            e = e.loc[e["d"].abs().sort_values(kind="stable").index[0]]
            out.append((f"{e['tipo']} {e['Partida']:02d}-{e['Capítulo']:02d} "
                        f"{e['nombre']} ({e['Mes']} {e['Año']})", int(e["d"])))
    desc = desc.copy()
    desc["evento"] = [o[0] for o in out]
    desc["distancia"] = [o[1] for o in out]
    return desc