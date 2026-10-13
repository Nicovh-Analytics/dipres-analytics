"""
15_validar_partidas.py — ley_inicial vs ley, partida por partida
=================================================================
Baja la validación del script 14 un nivel: del total del artículo 1
al cuadro resumen de cada partida que trae el texto completo de la ley.

Fuente: texto/ley_presupuestos_<año>_dipres_completo.txt (script 12).
Cada partida abre con un cuadro "Partida : <nombre> / Miles de $ (o US$)
/ Clasificación Económica / Total" por subtítulo. Algunos años traen
tres columnas (Total Bruto, Transferencias, Total); se usa el Total,
que es el nivel que publica cruce_partida (sin transferencias internas).

Tres controles por año y moneda:
  1. Autoconsistencia del cuadro: Σ subtítulos = INGRESOS = GASTOS.
     Un cuadro que no cuadra se marca dudoso y NO se compara.
  2. Ley por partida vs cruce_partida[ley_inicial].
  3. Σ partidas de la ley vs artículo 1 (columna Resumen de las
     Partidas, extraída por el script 14). Detecta inconsistencias
     internas de la ley, como 2020 (préstamos).

Salida: docs/partidas_ley_dipres.csv (lo extraído, auditable).

Uso:
    python pipeline/3_validacion/15_validar_partidas.py
    python pipeline/3_validacion/15_validar_partidas.py --anio 2020
"""

import argparse
import re
import unicodedata
from itertools import combinations

import pandas as pd

from dipres.config import DIRS, TOLERANCIAS
from dipres.dominio import MES_A_NUM
from dipres.hallazgos import Registro
from dipres.utils import leer_csv_robusto

DIR_TEXTO = DIRS.get("normativa", DIRS["base"] / "normativa") / "texto"
ART1 = DIRS["docs"] / "art1_ley_presupuestos_dipres.csv"
SALIDA = DIRS["docs"] / "partidas_ley_dipres.csv"
ANIOS = range(2017, 2027)
COLS = ["bruto", "transferencias", "total"]

# Monto: 1.234.567 · negativo –1.234 / -1.234 · "–" o "-" solo = 0
RE_TOK = r"[–-]?\d{1,3}(?:\.\d{3})*|[–-](?=\s|$)"
RE_FILA = re.compile(
    rf"^(?:(?P<sub>\d{{2}})\s+)?(?P<nombre>[A-Za-zÁÉÍÓÚÑáéíóúñ][^\d–]*?)\s+"
    rf"(?P<montos>(?:(?:{RE_TOK})\s*)+)$")
RE_PARTIDA_HDR = re.compile(r"^Partida\s*:", re.I)
RE_PORTADA = re.compile(r"^PARTIDA\s+(\d{2})$")              # "PARTIDA 18"
RE_PARTIDA_NUM = re.compile(r"^PARTIDA\s*:?\s+(\d{2})\b", re.I)  # "PARTIDA : 18"


# Para filas que el PDF trae sin código ("Saldo Inicial de Caja 5.000.000")
SUBTITULOS = {
    "INGRESOS": {
        "impuestos": 1, "imposiciones previsionales": 4,
        "transferencias corrientes": 5, "rentas de la propiedad": 6,
        "ingresos de operacion": 7, "otros ingresos corrientes": 8,
        "aporte fiscal": 9, "venta de activos no financieros": 10,
        "venta de activos financieros": 11, "recuperacion de prestamos": 12,
        "transferencias para gastos de capital": 13, "endeudamiento": 14,
        "saldo inicial de caja": 15,
    },
    "GASTOS": {
        "gastos en personal": 21, "bienes y servicios de consumo": 22,
        "prestaciones de seguridad social": 23, "transferencias corrientes": 24,
        "integros al fisco": 25, "otros gastos corrientes": 26,
        "aporte fiscal libre": 27, "aporte fiscal para servicio de la deuda": 28,
        "adquisicion de activos no financieros": 29,
        "adquisicion de activos financieros": 30, "iniciativas de inversion": 31,
        "prestamos": 32, "transferencias de capital": 33,
        "servicio de la deuda": 34, "saldo final de caja": 35,
    },
}


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


# =====================================================
# Lectura de los cuadros resumen
# =====================================================
def a_numero(tok: str) -> int:
    if tok in ("–", "-"):
        return 0
    n = int(re.sub(r"\D", "", tok))
    return -n if tok[0] in "–-" else n


def numero_partida(paginas: list[list[str]], i: int) -> int | None:
    """
    La portada ("PARTIDA 18") precede al cuadro, en la misma página o en
    las 2 anteriores: es lo más confiable. Si no está, el primer encabezado
    de programa que sigue ("PARTIDA : 18").
    """
    for pag in reversed(paginas[max(0, i - 2):i + 1]):
        for t in pag:
            m = RE_PORTADA.match(t)
            if m:
                return int(m.group(1))
    for pag in paginas[i:i + 80]:
        for t in pag:
            m = RE_PARTIDA_NUM.match(t)
            if m:
                return int(m.group(1))
    return None


def leer_cuadros(anio: int) -> tuple[pd.DataFrame, list[str]]:
    """
    Filas de todos los cuadros resumen de partida del año.

    Se trabaja por página: pypdf no siempre entrega el encabezado
    ("Partida : ... / Miles de $") antes de la tabla; en el Tesoro sale al
    final de la página. Por eso nombre y moneda se buscan en toda la página.
    """
    ruta = DIR_TEXTO / f"ley_presupuestos_{anio}_dipres_completo.txt"
    if not ruta.exists():
        return pd.DataFrame(), [f"no existe {ruta.name} (correr script 12)"]
    # U+FFFD = punto que la fuente del PDF no mapea (2017, 2019, 2020)
    texto = ruta.read_text(encoding="utf-8").replace("\ufffd", ".")
    paginas = [[l.strip() for l in p.splitlines()]
               for p in re.split(r"<<<PAGINA \d+>>>", texto)]

    filas, problemas, sin_filas = [], [], []
    for n, lineas in enumerate(paginas, start=1):
        cabeceras = [i for i, t in enumerate(lineas)
                     if "clasificación económica" in t.lower()]
        for c_i, i in enumerate(cabeceras):
            cabecera = lineas[i]
            # Sin "Total" es el cuadro por capítulos/programas (matriz)
            if "total" not in cabecera.lower():
                continue
            # Con dos cuadros en la página (Tesoro: $ y US$), el k-ésimo
            # cuadro toma el k-ésimo encabezado "Miles de ..." de la página
            nombres = [t.split(":", 1)[1].strip() for t in lineas
                       if RE_PARTIDA_HDR.match(t)]
            monedas = ["DOLARES" if "US$" in t else "PESOS" for t in lineas
                       if re.match(r"Miles de (US)?\$", t)]
            k = sum(1 for x in cabeceras[:c_i] if "total" in lineas[x].lower())
            nombre = nombres[min(k, len(nombres) - 1)] if nombres else None
            moneda = monedas[min(k, len(monedas) - 1)] if monedas else None
            if nombre is None or moneda is None:
                continue
            partida = numero_partida(paginas, n - 1)
            fin = cabeceras[c_i + 1] if c_i + 1 < len(cabeceras) else len(lineas)
            cuadro = _leer_tabla(lineas[i + 1:fin], anio, partida, nombre,
                                 moneda, 3 if "bruto" in cabecera.lower() else 1, n)
            if partida is None:
                problemas.append(f"pág. {n} '{nombre}': sin número de partida")
            elif not cuadro:
                sin_filas.append((partida, moneda, n))
            else:
                filas.extend(cuadro)

    df = pd.DataFrame(filas)
    # Un cuadro ilegible solo importa si la partida no tiene otro que sí lo sea
    leidas = set(zip(df.partida, df.moneda)) if not df.empty else set()
    problemas += [f"pág. {n} partida {p} {m}: cuadro sin filas legibles"
                  for p, m, n in sin_filas if (p, m) not in leidas]
    if df.empty:
        problemas.append("no se encontraron cuadros resumen de partida")
        return df, problemas
    # Una partida/moneda puede repetir el cuadro; vale el primero
    primero = df.groupby(["partida", "moneda"]).pagina.transform("min")
    df = df[df.pagina == primero].reset_index(drop=True)
    for (p, mon, sec), g in df.groupby(["partida", "moneda", "seccion"]):
        nota = resolver_ambiguas(df, g.index)
        if nota:
            problemas.append(f"partida {p} {mon}/{sec}: {nota}")
    return df.drop(columns="ambigua"), problemas


def _leer_tabla(lineas, anio, partida, nombre, moneda, ncols, pagina) -> list:
    """
    Primero línea a línea. Si así la tabla no cuadra (2023: código, nombre
    y monto vienen en líneas separadas), se relee como un solo flujo.
    """
    cuerpo = []
    for t in lineas:
        if t.startswith("GLOSAS"):
            break
        cuerpo.append(t)
    args = (anio, partida, nombre, moneda, ncols, pagina)
    por_linea = _filas(cuerpo, *args)
    if _cuadra(por_linea):
        return por_linea
    por_flujo = _filas(_flujo(" ".join(cuerpo)), *args, flujo=True)
    return por_flujo if _cuadra(por_flujo) else por_linea


RE_MONTO_PAL = re.compile(r"^(?:[–-]?\d{1,3}(?:\.\d{3})*|[–-])$")


def _es_seccion(pal: list[str], j: int) -> bool:
    """"GASTOS 152.557.255" es fila de sección; "Ingresos de Operación" no."""
    return (pal[j].upper() in ("INGRESOS", "GASTOS") and j + 1 < len(pal)
            and bool(RE_MONTO_PAL.match(pal[j + 1])))


def _flujo(texto: str) -> list[tuple[str, str, str]]:
    """
    Parte un cuadro en filas sin depender de los saltos de línea.
    Recorre palabra a palabra: un número de 2 dígitos seguido de una
    palabra es el código de la fila siguiente ("111 08 Otros Ingresos"),
    salvo que sea una fila de sección ("Caja 40 GASTOS 152.557.255").
    """
    pal = texto.split()
    filas, i = [], 0
    while i < len(pal):
        sub = ""
        if (re.fullmatch(r"\d{2}", pal[i]) and i + 1 < len(pal)
                and not RE_MONTO_PAL.match(pal[i + 1])):
            sub, i = pal[i], i + 1
        nombre = []
        while i < len(pal) and not RE_MONTO_PAL.match(pal[i]):
            nombre.append(pal[i])
            i += 1
        montos = []
        while i < len(pal) and RE_MONTO_PAL.match(pal[i]):
            es_codigo = (re.fullmatch(r"\d{2}", pal[i]) and i + 1 < len(pal)
                         and not RE_MONTO_PAL.match(pal[i + 1])
                         and not _es_seccion(pal, i + 1))
            if es_codigo and montos:
                break
            montos.append(pal[i])
            i += 1
        if nombre and montos:
            filas.append((sub, " ".join(nombre), " ".join(montos)))
        elif not nombre and not montos and not sub:
            i += 1
    return filas


def _filas(items, anio, partida, nombre, moneda, ncols, pagina,
           flujo=False) -> list:
    cuadro, seccion = [], None
    for it in items:
        if flujo:
            sub_txt, nom, montos = it
        else:
            fm = RE_FILA.match(it)
            if not fm:
                continue
            sub_txt, nom, montos = fm.group("sub"), fm.group("nombre"), fm.group("montos")
        nom = nom.strip()
        v = [a_numero(x) for x in re.findall(RE_TOK, montos)]
        if not v:
            continue
        if nom.upper() in ("INGRESOS", "GASTOS"):
            seccion, sub = nom.upper(), 0
        elif sub_txt and seccion:
            sub = int(sub_txt)
        elif seccion and normalizar(nom) in SUBTITULOS[seccion]:
            sub = SUBTITULOS[seccion][normalizar(nom)]   # fila sin código
        else:
            continue
        cuadro.append(_fila(anio, partida, nombre, moneda, seccion, sub,
                            nom, v, ncols, pagina))
    return cuadro


def _cuadra(cuadro: list) -> bool:
    """Chequeo rápido: cada sección tiene total y Σ filas = total."""
    for sec in ("INGRESOS", "GASTOS"):
        f = [x for x in cuadro if x["seccion"] == sec]
        tot = [x["total"] for x in f if x["subtitulo"] == 0]
        if len(tot) != 1 or sum(x["total"] for x in f if x["subtitulo"]) != tot[0]:
            return False
    return True


def _fila(anio, partida, nombre, moneda, seccion, sub, concepto, v, ncols,
          pagina) -> dict:
    """
    Normaliza a (bruto, transferencias, total). En cuadros de 3 columnas
    el PDF omite ceros: con 2 montos distintos falta la transferencia
    (= a − b); con 2 iguales es ambiguo (sin transferencia, o total 0).
    """
    ambigua = False
    if ncols == 1 or len(v) == 1:
        b, t, tot = v[0], 0, v[-1]
    elif len(v) == 2:
        a, c = v
        b, t, tot = (a, 0, c) if a == c else (a, a - c, c)
        ambigua = a == c and a != 0
    else:
        b, t, tot = v[:3]
    return {"anio": anio, "partida": partida, "nombre_partida": nombre,
            "moneda": moneda, "seccion": seccion, "subtitulo": sub,
            "concepto": concepto, "bruto": b, "transferencias": t,
            "total": tot, "pagina": pagina, "ambigua": ambigua,
            "inferida": False}


def resolver_ambiguas(df: pd.DataFrame, idx) -> str | None:
    """
    Igual que en el artículo 1: si Σ transferencias no cuadra con la fila
    total, busca qué filas ambiguas son (bruto, transferencia, total 0).
    Solo se aplica si hay UNA combinación que cuadra.
    """
    g = df.loc[idx]
    tot = g[g.subtitulo == 0]
    if len(tot) != 1:
        return None
    falta = int(tot.transferencias.iloc[0]
                - g[g.subtitulo != 0].transferencias.sum())
    cand = g[g.ambigua & (g.subtitulo != 0)]
    if falta == 0 or cand.empty or len(cand) > 15:
        return None
    sols = [c for k in range(1, len(cand) + 1)
            for c in combinations(cand.index, k)
            if cand.loc[list(c), "bruto"].sum() == falta]
    if len(sols) != 1:
        return None
    sol = list(sols[0])
    df.loc[sol, "transferencias"] = df.loc[sol, "bruto"]
    df.loc[sol, "total"] = 0
    df.loc[sol, "inferida"] = True
    return ("interpretado como transferencia con total 0: "
            + ", ".join(df.loc[sol, "concepto"]))


def repetidos(df: pd.DataFrame) -> list[str]:
    """
    Subtítulos que la propia ley lista dos veces en un cuadro (2018,
    Educación: dos filas "34 Servicio de la Deuda"). No invalida el cuadro
    si cuadra; se suman y la comparación muestra si el dataset lo separó.
    """
    d = df[(df.subtitulo != 0)
           & df.duplicated(["partida", "moneda", "seccion", "subtitulo"],
                           keep=False)]
    return [f"partida {int(p):02d} {mon}: la ley repite el subtítulo {int(s)} "
            f"({', '.join(f'{x:,}' for x in g.total)})"
            for (p, mon, s), g in d.groupby(["partida", "moneda", "subtitulo"])]


def autoconsistencia(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por cuadro (partida, moneda) con sus fallas."""
    res = []
    for (p, mon), g in df.groupby(["partida", "moneda"]):
        fallas = []
        totales = {}
        for sec in ("INGRESOS", "GASTOS"):
            s = g[g.seccion == sec]
            tot, det = s[s.subtitulo == 0], s[s.subtitulo != 0]
            if len(tot) != 1:
                fallas.append(f"{sec}: {len(tot)} filas de total")
                continue
            totales[sec] = tot.total.iloc[0]
            for c in COLS:
                if det[c].sum() != tot[c].iloc[0]:
                    fallas.append(f"{sec} Σ {c} = {det[c].sum():,} "
                                  f"≠ {tot[c].iloc[0]:,}")
        if len(totales) == 2 and totales["INGRESOS"] != totales["GASTOS"]:
            fallas.append(f"INGRESOS {totales['INGRESOS']:,} ≠ "
                          f"GASTOS {totales['GASTOS']:,}")
        res.append({"partida": p, "moneda": mon, "pagina": g.pagina.iloc[0],
                    "fallas": fallas})
    return pd.DataFrame(res)


# =====================================================
# Comparaciones
# =====================================================
def ley_inicial_partida() -> pd.DataFrame:
    """Último mes de cada año (ley_inicial no cambia en el año)."""
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_partida.csv"))
    df["MesNum"] = df["Mes"].map(MES_A_NUM)
    df = df[df.groupby("Año")["MesNum"].transform("max") == df["MesNum"]]
    df = df.rename(columns={"Año": "anio", "Moneda": "moneda",
                            "Partida": "partida", "Subtítulo": "subtitulo"})
    df["subtitulo"] = df["subtitulo"].astype(int)
    return (df.groupby(["anio", "moneda", "partida", "subtitulo"],
                       as_index=False)["ley_inicial"].sum())


def comparar_dataset(ley: pd.DataFrame, obs: pd.DataFrame, anio: int,
                     reg: Registro) -> pd.DataFrame:
    """Ley por partida vs cruce_partida, solo en partidas con cuadro válido."""
    l = (ley[ley.subtitulo != 0]
         .groupby(["moneda", "partida", "subtitulo"], as_index=False).total.sum())
    o = obs[obs.anio == anio].drop(columns="anio")
    validas = set(zip(l.moneda, l.partida))
    o = o[[(m, p) in validas for m, p in zip(o.moneda, o.partida)]]
    c = l.merge(o, on=["moneda", "partida", "subtitulo"], how="outer").fillna(0)
    c["delta"] = c.ley_inicial - c.total
    malas = c[c.delta.abs() > TOLERANCIAS["monto"]]

    for (mon, p), g in c.groupby(["moneda", "partida"]):
        m = malas[(malas.moneda == mon) & (malas.partida == p)]
        if m.empty:
            reg.ok("partida", f"{anio}/{mon}/{int(p):02d}: {len(g)} subtítulos")
            continue
        print(f"  ✗ {anio} {mon:<8} partida {int(p):02d}: "
              f"{len(g) - len(m)}/{len(g)} subtítulos")
        for f in m.itertuples():
            print(f"        sub {int(f.subtitulo):>2}  ley={f.total:>16,.0f}  "
                  f"dataset={f.ley_inicial:>16,.0f}  Δ={f.delta:,.0f}")
        reg.warn("partida", f"{anio}/{mon}/{int(p):02d}: {len(m)} subtítulos "
                 f"≠ ley", anio=anio, patron="ley_inicial ≠ ley por partida")
    return c


def comparar_art1(ley: pd.DataFrame, art1: pd.DataFrame, anio: int,
                  partidas_ok: set, partidas_ds: set, reg: Registro) -> None:
    """
    Σ partidas de la ley vs artículo 1 (Resumen de las Partidas). Solo es
    concluyente si están TODAS las partidas del año; si falta alguna, se
    informa la cobertura y no se emite juicio.
    """
    for mon in sorted(set(art1[art1.anio == anio].moneda)):
        faltan = sorted(p for m, p in partidas_ds - partidas_ok if m == mon)
        if faltan:
            print(f"  · {anio} {mon:<8} Σ partidas vs art. 1: no concluyente, "
                  f"faltan partidas {faltan}")
            continue
        a = art1[(art1.anio == anio) & (art1.moneda == mon)
                 & (art1.subtitulo != 0)]
        s = (ley[(ley.moneda == mon) & (ley.subtitulo != 0)]
             .groupby(["seccion", "subtitulo"]).total.sum())
        c = a.set_index(["seccion", "subtitulo"])["resumen_partidas"]
        d = pd.concat([c.rename("art1"), s.rename("partidas")], axis=1)
        d = d[d.index.isin(c.index)].fillna(0)  # art. 1 omite el aporte fiscal
        d["delta"] = d.partidas - d.art1
        malas = d[d.delta.abs() > TOLERANCIAS["monto"]]
        if malas.empty:
            print(f"  ✓ {anio} {mon:<8} Σ partidas = art. 1 "
                  f"({len(d)} subtítulos)")
            reg.ok("art1_partidas", f"{anio}/{mon}: Σ partidas = art. 1")
            continue
        print(f"  ✗ {anio} {mon:<8} Σ partidas ≠ art. 1 (inconsistencia "
              f"interna de la ley):")
        for (sec, sub), f in malas.iterrows():
            print(f"        {sec[:3]} sub {sub:>2}  art.1={f.art1:>16,.0f}  "
                  f"Σ partidas={f.partidas:>16,.0f}  Δ={f.delta:,.0f}")
        reg.warn("art1_partidas", f"{anio}/{mon}: {len(malas)} subtítulos, "
                 f"Σ partidas ≠ art. 1", anio=anio,
                 patron="ley inconsistente: partidas vs artículo 1")


# =====================================================
# Main
# =====================================================
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int)
    args = ap.parse_args()
    anios = [args.anio] if args.anio else list(ANIOS)

    reg = Registro("validacion_partidas", salida_dir=DIRS["reportes"])
    obs = ley_inicial_partida()
    art1 = pd.read_csv(ART1) if ART1.exists() else pd.DataFrame()
    if art1.empty:
        print(f"  (sin {ART1.name}: correr 14_validar_vs_ley.py para el "
              f"control Σ partidas vs art. 1)")

    print("=" * 78)
    print("  LEY_INICIAL vs LEY DE PRESUPUESTOS — por partida")
    print("=" * 78)

    todas, resumen = [], []
    for anio in anios:
        print(f"\n{'─' * 78}\n  {anio}\n")
        ley, problemas = leer_cuadros(anio)
        for p in problemas:
            print(f"  ⚠ {p}")
            reg.warn("extraccion_partidas", f"{anio}: {p}", anio=anio)
        if ley.empty:
            continue

        for r in repetidos(ley):
            print(f"  ⚠ {r}")
            reg.warn("ley_partidas", f"{anio}: {r}", anio=anio,
                     patron="ley repite un subtítulo en el cuadro")
        auto = autoconsistencia(ley)
        dudosos = auto[auto.fallas.str.len() > 0]
        for r in dudosos.itertuples():
            print(f"  ✗ partida {int(r.partida):02d} {r.moneda} (pág. "
                  f"{r.pagina}) cuadro dudoso, no se compara: "
                  f"{'; '.join(r.fallas)}")
            reg.warn("extraccion_partidas", f"{anio}/{r.moneda}/"
                     f"{int(r.partida):02d}: {'; '.join(r.fallas)}", anio=anio,
                     patron="cuadro de partida inconsistente")
        ok = set(zip(auto.moneda, auto.partida)) - set(
            zip(dudosos.moneda, dudosos.partida))
        ley = ley[[(m, p) in ok for m, p in zip(ley.moneda, ley.partida)]]
        # Partidas creadas durante el año (Culturas 2018, Ciencia 2019,
        # Seguridad Pública 2025) tienen ley_inicial 0: no están en la ley
        o = obs[obs.anio == anio]
        o = o[o.groupby(["moneda", "partida"]).ley_inicial
               .transform(lambda x: x.abs().sum()) > 0]
        en_ds = set(zip(o.moneda, o.partida))
        sin_cuadro = sorted(en_ds - ok)
        print(f"  {len(ok)} cuadros válidos · dataset tiene {len(en_ds)} "
              f"partida/moneda" + (f" · sin cuadro: {sin_cuadro}"
                                   if sin_cuadro else ""))
        todas.append(ley)

        c = comparar_dataset(ley, obs, anio, reg)
        n_ok = int((c.delta.abs() <= TOLERANCIAS["monto"]).sum())
        resumen.append((anio, len(ok), n_ok, len(c)))
        print(f"  ley vs dataset: {n_ok}/{len(c)} partida·subtítulo cuadran")
        if not art1.empty:
            comparar_art1(ley, art1, anio, ok, en_ds, reg)

    if resumen:
        print(f"\n{'─' * 78}\n  Resumen\n")
        for anio, nc, n_ok, n in resumen:
            print(f"  {anio}: {nc:>2} cuadros · {n_ok:>4}/{n:<4} partida·subtítulo")
        print(f"  Total: {sum(r[2] for r in resumen)}/{sum(r[3] for r in resumen)}")
    if todas:
        SALIDA.parent.mkdir(parents=True, exist_ok=True)
        pd.concat(todas).to_csv(SALIDA, index=False, encoding="utf-8")
        print(f"\n  Extraído: {SALIDA}")
    reg.emitir()