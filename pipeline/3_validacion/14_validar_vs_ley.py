"""
14_validar_vs_ley.py — ley_inicial vs artículo 1 de la ley
===========================================================
Validación contra un TERCERO real: la Ley de Presupuestos aprobada
por el Congreso, no un informe de DIPRES.

El artículo 1 publica tres columnas por subtítulo, para ingresos y
gastos, en moneda nacional (A) y extranjera (B):

    Resumen de las Partidas  →  suma bruta, sin consolidar
    Deducciones               →  eliminaciones de transferencias
    Total                     →  consolidado

Hipótesis:
    Σ cruce_partida[ley_inicial]   = Resumen de las Partidas
    Σ cruce_nacional[ley_inicial]  = Total
    diferencia                     = Deducciones

Ojo: el Resumen de las Partidas NO incluye el Aporte Fiscal
(sub 09 en ingresos, 27/28 del Tesoro en gastos). Por eso la
comparación se restringe a los subtítulos que la ley publica.

Referencia: se extrae del texto completo de la ley que descarga
12_descarga_normativa.py (texto/ley_presupuestos_<año>_dipres.txt).
Antes de comparar, cada tabla extraída se valida contra sí misma
(Σ filas = total, Resumen − Deducciones = Total). Si no cuadra, la
extracción se marca dudosa y ese año/moneda NO se compara: así un
✗ en la comparación siempre es del dato, nunca de la lectura.

Lo extraído queda en docs/art1_ley_presupuestos_dipres.csv como
respaldo auditable. Si existe la transcripción manual
(docs/art1_ley_presupuestos.csv) se usa como control cruzado.

Uso:
    python pipeline/3_validacion/14_validar_vs_ley.py
    python pipeline/3_validacion/14_validar_vs_ley.py --anio 2024
"""

import argparse
import re
import unicodedata

import pandas as pd

from dipres.config import DIRS, TOLERANCIAS
from dipres.dominio import MES_A_NUM
from dipres.hallazgos import Registro
from dipres.utils import leer_csv_robusto

DIR_TEXTO = DIRS.get("normativa", DIRS["base"] / "normativa") / "texto"
SALIDA_REF = DIRS["docs"] / "art1_ley_presupuestos_dipres.csv"
MANUAL = DIRS["docs"] / "art1_ley_presupuestos.csv"
ANIOS = range(2017, 2027)

# Columna del artículo 1 que debería reproducir cada nivel
COL_POR_NIVEL = {"partida": "resumen_partidas", "nacional": "total"}
COLS = ["resumen_partidas", "deducciones", "total"]

# La ley no trae el número de subtítulo, solo el nombre. Mapeo por
# (sección, nombre normalizado) según el clasificador del DS 854.
# Un nombre desconocido se avisa, nunca se adivina.
SUBTITULOS = {
    "INGRESOS": {
        "impuestos": 1,
        "tributacion sobre el uso de bienes y la realizacion de actos": 3,
        "imposiciones previsionales": 4,
        "transferencias corrientes": 5,
        "rentas de la propiedad": 6,
        "ingresos de operacion": 7,
        "otros ingresos corrientes": 8,
        "aporte fiscal": 9,
        "venta de activos no financieros": 10,
        "venta de activos financieros": 11,
        "recuperacion de prestamos": 12,
        "transferencias para gastos de capital": 13,
        "endeudamiento": 14,
        "saldo inicial de caja": 15,
    },
    "GASTOS": {
        "gastos en personal": 21,
        "bienes y servicios de consumo": 22,
        "prestaciones de seguridad social": 23,
        "transferencias corrientes": 24,
        "integros al fisco": 25,
        "otros gastos corrientes": 26,
        "adquisicion de activos no financieros": 29,
        "adquisicion de activos financieros": 30,
        "iniciativas de inversion": 31,
        "prestamos": 32,
        "transferencias de capital": 33,
        "servicio de la deuda": 34,
        "saldo final de caja": 35,
    },
}


# =====================================================
# Extracción del artículo 1 desde el texto de la ley
# =====================================================
def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


# Una fila de la tabla: nombre seguido de 1 a 3 montos.
# Montos con punto de miles; negativo como -1.234 o (1.234).
RE_MONTO = r"(?:-\s?|\()?\d{1,3}(?:\.\d{3})*\)?"
RE_FILA = re.compile(rf"^(?P<nombre>[^\d()\-]*[A-Za-zÁÉÍÓÚÑáéíóúñ][^\d]*?)\s+"
                     rf"(?P<montos>{RE_MONTO}(?:\s+{RE_MONTO}){{0,2}})$")


def a_numero(tok: str) -> int:
    neg = tok.startswith(("-", "("))
    n = int(re.sub(r"[^\d]", "", tok))
    return -n if neg else n


def bloque_art1(texto: str) -> str | None:
    """
    Desde "Artículo 1" hasta "Artículo 3". Se exige que "Moneda Nacional"
    aparezca cerca del inicio: el texto puede citar "artículo 1" antes
    (decreto promulgatorio, referencias), y esas menciones no sirven.
    Se corta en el 3 y no en el 2 porque en algunos PDF (2023) la tabla
    en dólares queda DESPUÉS del texto del artículo 2; el corte fino lo
    hace extraer_art1() al terminar la tabla en dólares.
    """
    for m in re.finditer(r"Art[íi]culo\s+1\s*[.º°]", texto, re.I):
        if re.search(r"Moneda\s+Nacional", texto[m.end():m.end() + 600], re.I):
            fin = re.search(r"Art[íi]culo\s+3\s*[.º°]", texto[m.end():], re.I)
            return texto[m.start():m.end() + (fin.start() if fin else 20000)]
    return None


def limpiar_bloque(bloque: str) -> list[str]:
    """
    Repara lo que el texto de algunos PDF trae roto, antes de leer filas:
      - U+FFFD en vez de "." (2017, 2019, 2020: la fuente del PDF no
        mapea el glifo del punto) → se repone el punto
      - inicial separada del resto ("T" / "ransferencias", "GAST" / "OS")
      - monto cortado entre líneas ("17.344.158.1" / "13 1 .474.023.136")
      - montos en líneas propias, debajo de su nombre
      - números de página sueltos ("4")
    Lo que esto no arregle lo detecta autoconsistencia().
    """
    lineas, pendiente = [], ""
    for linea in bloque.replace("\ufffd", ".").splitlines():
        linea = pendiente + linea.strip().strip("“”\"")
        pendiente = ""
        if re.fullmatch(r"[A-ZÁÉÍÓÚÑ]{1,5}", linea):       # inicial suelta
            pendiente = linea
            continue
        if re.search(r"\d\.\d{1,2}$", linea):                # monto cortado
            pendiente = linea
            continue
        linea = re.sub(r"(\d) \.(\d{3})", r"\1.\2", linea)
        if re.fullmatch(r"\d{1,3}", linea):                  # n° de página
            continue
        if (lineas and re.fullmatch(rf"{RE_MONTO}(?:\s+{RE_MONTO})*", linea)
                and RE_FILA.match(lineas[-1])):               # montos sueltos
            lineas[-1] += " " + linea
            continue
        lineas.append(linea)
    return lineas


def extraer_art1(anio: int) -> tuple[pd.DataFrame, list[str]]:
    """Devuelve (filas, problemas). Filas con subtitulo 0 = total de sección."""
    ruta = DIR_TEXTO / f"ley_presupuestos_{anio}_dipres.txt"
    if not ruta.exists():
        return pd.DataFrame(), [f"no existe {ruta.name}"]
    texto = ruta.read_text(encoding="utf-8")
    bloque = bloque_art1(texto)
    if bloque is None:
        return pd.DataFrame(), ["no se ubicó el artículo 1"]

    ley = re.search(r"LEY\s+N[º°o]?\.?\s*(\d{2}\.?\d{3})", texto[:5000], re.I)
    ley = ley.group(1).replace(".", "") if ley else ""

    filas, problemas = [], []
    moneda = seccion = None
    previa = ""          # línea sin montos: posible nombre partido en dos
    for linea in limpiar_bloque(bloque):
        if re.search(r"Art[íi]culo\s+2\s*[.º°]", linea, re.I) \
                and moneda == "DOLARES" and seccion == "GASTOS":
            break                       # terminó la tabla en dólares
        # Encabezado de tabla, no menciones en el texto ("...o en moneda
        # nacional." dentro del artículo 2 de 2023)
        if re.match(r"(?:[AB]\s*[.\-–]+\s*)?En\s+Moneda\s+Nacional", linea, re.I):
            moneda, seccion = "PESOS", None
            continue
        if re.match(r"(?:[AB]\s*[.\-–]+\s*)?En\s+Moneda\s+Extranjera", linea, re.I):
            moneda, seccion = "DOLARES", None
            continue
        m = RE_FILA.match(linea)
        if not m or moneda is None:
            previa = linea
            continue

        nombre = re.sub(r"[.\s]+$", "", m.group("nombre"))  # puntos de relleno
        v = [a_numero(t) for t in re.findall(RE_MONTO, m.group("montos"))]
        # 1 monto: sin deducción · 2: resumen y total · 3: las tres.
        # Ambigua: dos montos iguales pueden ser "resumen y total" o
        # "resumen y deducción, total 0 omitido" (2024-2026 en US$).
        res, ded, tot = (v[0], 0, v[0]) if len(v) == 1 else \
                        (v[0], 0, v[1]) if len(v) == 2 else v
        ambigua = len(v) == 2 and v[0] == v[1]

        clave = normalizar(nombre)
        if clave in ("ingresos", "gastos"):
            seccion = clave.upper()
            sub = 0
        elif seccion is None:
            previa = linea
            continue
        else:
            mapa = SUBTITULOS[seccion]
            sub = mapa.get(clave) or mapa.get(normalizar(f"{previa} {nombre}"))
            if sub is None:
                problemas.append(f"{moneda}/{seccion}: nombre desconocido "
                                 f"'{nombre}' (fila omitida)")
                previa = ""
                continue
        previa = ""
        filas.append({"anio": anio, "ley": ley, "moneda": moneda,
                      "seccion": seccion, "subtitulo": sub, "concepto": nombre,
                      "resumen_partidas": res, "deducciones": ded, "total": tot,
                      "ambigua": ambigua, "inferida": False})

    df = pd.DataFrame(filas)
    if df.empty:
        problemas.append("artículo 1 ubicado pero sin filas legibles")
        return df, problemas
    for (mon, sec), g in df.groupby(["moneda", "seccion"]):
        nota = resolver_ambiguas(df, g.index)
        if nota:
            problemas.append(f"{mon}/{sec}: {nota}")
    return df.drop(columns="ambigua"), problemas


def resolver_ambiguas(df: pd.DataFrame, idx) -> str | None:
    """
    Si Σ deducciones no cuadra con la fila total, busca qué filas ambiguas
    son en realidad (resumen, deducción, total 0). Solo se aplica si hay
    UNA combinación que cuadra; si hay varias o ninguna, no se toca y
    autoconsistencia() marcará la tabla como dudosa.
    """
    from itertools import combinations
    g = df.loc[idx]
    tot = g[g.subtitulo == 0]
    if len(tot) != 1:
        return None
    falta = int(tot.deducciones.iloc[0] - g[g.subtitulo != 0].deducciones.sum())
    cand = g[g.ambigua & (g.subtitulo != 0)]
    if falta == 0 or cand.empty:
        return None
    sols = [c for k in range(1, len(cand) + 1)
            for c in combinations(cand.index, k)
            if cand.loc[list(c), "resumen_partidas"].sum() == falta]
    if len(sols) != 1:
        return None
    sol = list(sols[0])
    df.loc[sol, "deducciones"] = df.loc[sol, "resumen_partidas"]
    df.loc[sol, "total"] = 0
    df.loc[sol, "inferida"] = True
    return ("interpretado como deducción con total 0 (la ley omite el 0): "
            + ", ".join(df.loc[sol, "concepto"]))


def autoconsistencia(df: pd.DataFrame) -> dict[tuple, tuple[list[str], str]]:
    """
    {(moneda, seccion): ([fallas], errata)}. Una tabla bien leída cumple:
      Σ filas = fila total, en cada columna
      Resumen − Deducciones = Total, en cada fila

    Si la única falla es el total de UNA fila y con resumen − deducciones
    toda la tabla cuadra, la lectura es correcta y el error es de la ley
    publicada (2022, sub 24). Se corrige en df con el valor aritmético, se
    deja constancia en la columna "errata" y la tabla sí se compara.
    """
    out = {}
    for (mon, sec), g in df.groupby(["moneda", "seccion"]):
        fallas = []
        tot = g[g.subtitulo == 0]
        det = g[g.subtitulo != 0]
        if len(tot) != 1:
            fallas.append(f"{len(tot)} filas de total")
        else:
            for c in COLS:
                if det[c].sum() != tot[c].iloc[0]:
                    fallas.append(f"Σ {c} = {det[c].sum():,} ≠ {tot[c].iloc[0]:,}")
        malas = g[g.resumen_partidas - g.deducciones != g.total]
        fallas += [f"fila '{r.concepto}': resumen − deducciones ≠ total"
                   for r in malas.itertuples()]
        errata = ""
        if (len(tot) == 1 and len(malas) == 1 and malas.subtitulo.iloc[0] != 0
                and det.resumen_partidas.sum() == tot.resumen_partidas.iloc[0]
                and det.deducciones.sum() == tot.deducciones.iloc[0]):
            f = malas.iloc[0]
            calc = f.resumen_partidas - f.deducciones
            if det.total.sum() - f.total + calc == tot.total.iloc[0]:
                errata = (f"errata de la ley en sub {f.subtitulo} "
                          f"'{f.concepto}': total publicado {f.total:,}, "
                          f"resumen − deducciones = {calc:,} "
                          f"(Δ {f.total - calc:,}); se usa {calc:,}")
                df.loc[f.name, "total"] = calc
                df.loc[f.name, "errata"] = errata
                fallas = []
        if det.subtitulo.duplicated().any():
            fallas.append("subtítulo repetido")
        out[(mon, sec)] = (fallas, errata)
    return out


def construir_referencia(anios, reg: Registro) -> pd.DataFrame:
    print(f"\n{'─' * 78}\n  Extracción del artículo 1 (texto Dipres)\n")
    validas = []
    for anio in anios:
        df, problemas = extraer_art1(anio)
        for p in problemas:
            reg.warn("extraccion_art1", f"{anio}: {p}", anio=anio,
                     patron="lectura del artículo 1")
        if df.empty:
            print(f"  ✗ {anio}  {problemas[0]}")
            continue
        df["errata"] = ""
        for (mon, sec), (fallas, errata) in autoconsistencia(df).items():
            n = int(((df.moneda == mon) & (df.seccion == sec)
                     & (df.subtitulo != 0)).sum())
            if fallas:
                print(f"  ✗ {anio} {mon:<8} {sec:<9} extracción dudosa, "
                      f"no se compara:")
                for f in fallas:
                    print(f"        {f}")
                reg.warn("extraccion_art1", f"{anio}/{mon}/{sec}: "
                         f"{'; '.join(fallas)}", anio=anio,
                         patron="tabla del artículo 1 inconsistente")
            else:
                print(f"  ✓ {anio} {mon:<8} {sec:<9} {n:>2} subtítulos, "
                      f"tabla consistente" + (" (con errata corregida)"
                                              if errata else ""))
                if errata:
                    print(f"        {errata}")
                    reg.warn("ley_art1", f"{anio}/{mon}/{sec}: {errata}",
                             anio=anio, patron="errata en la ley publicada")
                validas.append(df[(df.moneda == mon) & (df.seccion == sec)])

    ref = pd.concat(validas, ignore_index=True) if validas else pd.DataFrame()
    if not ref.empty:
        SALIDA_REF.parent.mkdir(parents=True, exist_ok=True)
        ref.to_csv(SALIDA_REF, index=False, encoding="utf-8")
    return ref


def control_manual(ref: pd.DataFrame, reg: Registro) -> None:
    """Transcripción manual (solo ingresos) vs extracción automática."""
    if not MANUAL.exists() or ref.empty:
        return
    man = pd.read_csv(MANUAL)
    man["seccion"] = "INGRESOS"
    m = man.merge(ref, on=["anio", "moneda", "seccion", "subtitulo"],
                  how="left", suffixes=("_man", "_aut"))
    m = m[m.anio.isin(ref.anio.unique())]
    if m.empty:
        return
    sin_par = m["total_aut"].isna()
    distintas = ~sin_par & (m[[f"{c}_man" for c in COLS]].values
                            != m[[f"{c}_aut" for c in COLS]].values).any(axis=1)

    print(f"\n{'─' * 78}\n  Control cruzado: transcripción manual vs texto\n")
    print(f"  {len(m) - sin_par.sum() - distintas.sum()}/{len(m)} filas idénticas")
    for r in m[sin_par].itertuples():
        print(f"  ? {r.anio} {r.moneda} sub {r.subtitulo}: solo en la manual")
    for r in m[distintas].itertuples():
        print(f"  ≠ {r.anio} {r.moneda} sub {r.subtitulo} ({r.concepto_man}): "
              f"manual={r.total_man:,} texto={r.total_aut:,.0f}")
        reg.warn("control_manual", f"{r.anio}/{r.moneda}/sub {r.subtitulo}: "
                 f"manual ≠ texto", anio=r.anio)


# =====================================================
# Comparación contra el dataset
# =====================================================
def cierres(nivel: str) -> pd.DataFrame:
    """Último mes de cada año: el presupuesto aprobado."""
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / f"cruce_{nivel}.csv"))
    df["MesNum"] = df["Mes"].map(MES_A_NUM)
    idx = df.groupby(["Año", "Moneda"])["MesNum"].transform("max") == df["MesNum"]
    df = df[idx].copy()
    df["Sub"] = df["Subtítulo"].astype(int)
    return df.groupby(["Año", "Moneda", "Sub"], as_index=False)["ley_inicial"].sum()


def _ref(ref, anio, moneda, seccion):
    return ref[(ref.anio == anio) & (ref.moneda == moneda)
               & (ref.seccion == seccion)]


def comparar(obs: pd.DataFrame, ref: pd.DataFrame, nivel: str, anio: int,
             moneda: str, seccion: str, reg: Registro) -> dict:
    col = COL_POR_NIVEL[nivel]
    r = _ref(ref, anio, moneda, seccion)
    detalle = r[r.subtitulo != 0]
    subs = detalle.subtitulo.tolist()

    o = obs[(obs["Año"] == anio) & (obs["Moneda"] == moneda)]
    o = o.set_index("Sub")["ley_inicial"]

    comp = detalle.assign(
        dataset=lambda d: d.subtitulo.map(lambda s: float(o.get(s, 0))),
    )
    comp["delta"] = comp.dataset - comp[col]
    cuadran = int((comp.delta.abs() <= TOLERANCIAS["monto"]).sum())

    tot_ref = float(r.loc[r.subtitulo == 0, col].iloc[0])
    tot_obs = float(o.loc[o.index.isin(subs)].sum())
    delta_tot = tot_obs - tot_ref
    ok = abs(delta_tot) <= TOLERANCIAS["monto"] and cuadran == len(comp)

    estado = "✓" if ok else "✗"
    print(f"  {estado} {anio} {moneda:<8} {seccion:<9}{nivel:<9}"
          f"{cuadran:>3}/{len(comp)} subtítulos · total Δ={delta_tot:>16,.0f}")

    if not ok:
        for _, f in comp[comp.delta.abs() > TOLERANCIAS["monto"]].iterrows():
            print(f"        {f.subtitulo:>2} {f.concepto[:35]:<37}"
                  f"ley={f[col]:>18,.0f}  dataset={f.dataset:>18,.0f}")

    (reg.ok if ok else reg.warn)(
        "art1", f"{anio}/{moneda}/{seccion}/{nivel}: {cuadran}/{len(comp)}, "
                f"Δ={delta_tot:,.0f}", anio=anio)

    return {"anio": anio, "moneda": moneda, "seccion": seccion, "nivel": nivel,
            "cuadran": cuadran, "de": len(comp), "delta": delta_tot, "ok": ok}


def deducciones(p: pd.DataFrame, n: pd.DataFrame, ref: pd.DataFrame, anio: int,
                moneda: str, seccion: str, reg: Registro) -> dict:
    r = _ref(ref, anio, moneda, seccion)
    subs = r[r.subtitulo != 0].subtitulo.tolist()
    esperado = float(r.loc[r.subtitulo == 0, "deducciones"].iloc[0])

    sel = lambda d: d[(d["Año"] == anio) & (d["Moneda"] == moneda)
                      & d["Sub"].isin(subs)]["ley_inicial"].sum()
    obs = float(sel(p) - sel(n))
    delta = obs - esperado
    ok = abs(delta) <= TOLERANCIAS["monto"]

    print(f"  {'✓' if ok else '✗'} {anio} {moneda:<8} {seccion:<9}"
          f"ley={esperado:>16,.0f}  obs={obs:>16,.0f}  Δ={delta:,.0f}")
    (reg.ok if ok else reg.warn)(
        "deducciones", f"{anio}/{moneda}/{seccion}: Δ={delta:,.0f}", anio=anio)
    return {"anio": anio, "moneda": moneda, "seccion": seccion,
            "ok": ok, "delta": delta}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int)
    args = ap.parse_args()

    reg = Registro("validacion_vs_ley", salida_dir=DIRS["reportes"])
    anios = [args.anio] if args.anio else list(ANIOS)

    print("=" * 78)
    print("  LEY_INICIAL vs ARTÍCULO 1 — Ley de Presupuestos")
    print("=" * 78)

    ref = construir_referencia(anios, reg)
    if ref.empty:
        print("\n  Sin tablas válidas: nada que comparar.")
        reg.emitir()
        raise SystemExit(1)
    control_manual(ref, reg)

    grupos = (ref[["anio", "moneda", "seccion"]].drop_duplicates()
              .sort_values(["anio", "moneda", "seccion"]).itertuples(index=False))
    grupos = list(grupos)
    niveles = {n: cierres(n) for n in COL_POR_NIVEL}

    print(f"\n{'─' * 78}\n  Comparación por nivel\n")
    res = [comparar(obs, ref, nivel, g.anio, g.moneda, g.seccion, reg)
           for g in grupos for nivel, obs in niveles.items()]

    print(f"\n{'─' * 78}\n  Deducciones de transferencias\n")
    for g in grupos:
        deducciones(niveles["partida"], niveles["nacional"],
                    ref, g.anio, g.moneda, g.seccion, reg)

    d = pd.DataFrame(res)
    print(f"\n{'─' * 78}")
    print(f"  {d.ok.sum()}/{len(d)} comparaciones cuadran "
          f"({d.cuadran.sum()}/{d['de'].sum()} subtítulos)")

    faltan = [a for a in anios if a not in set(ref.anio)]
    if faltan:
        print(f"\n  Años sin tabla válida: {faltan} (ver extracción arriba)")
    print(f"\n  Referencia extraída: {SALIDA_REF}")

    reg.emitir()