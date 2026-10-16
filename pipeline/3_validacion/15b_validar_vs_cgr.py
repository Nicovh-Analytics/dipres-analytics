"""
15b_validar_vs_cgr.py — Ejecución por partida vs Contraloría (IGFE)
==================================================================
Contrasta cruce_partida con el Informe de la Gestión Financiera del
Estado (IGFE) anual de la Contraloría General de la República.

La CGR recibe la información de los servicios desde SIGFE Agregación
(el mismo registro de origen), pero la compila y valida por su cuenta
(SICOGEN II). Lo que esta prueba verifica es que la agregación por
partida que DIPRES publica en datos.gob.cl coincida con la de la CGR;
no verifica el registro de origen.

Tablas que se leen de cada IGFE (se ubican por título, no por página):
  - "ESTADO DE SITUACIÓN PRESUPUESTARIA / GASTOS POR PARTIDA": inicial,
    actualizado, devengado y pagado del año del informe.
  - "ESTADO COMPARATIVO DE EJECUCIÓN PRESUPUESTARIA / GASTOS DEVENGADOS
    POR PARTIDA": devengado de los 5 años que cubre el informe.
  Ambas en moneda nacional (millones de $) y extranjera (miles de US$).
  Ambas eliminan solo las transferencias dentro de cada partida, igual
  que cruce_partida, y excluyen el saldo final de caja (subt. 35).

Comparaciones (diciembre, gastos 21-34):
  devengado CGR   vs  ejecucion_acumulada
  inicial CGR     vs  ley_inicial
  actualizado CGR vs  ley_vigente
Pesos: el dataset (miles) se lleva a millones; tolerancia ±1 por
redondeo. Dólares: ambos en miles; tolerancia ±1.

Si una partida no cuadra, se prueba si cuadra sumándole una partida
del dataset sin par en la CGR (p. ej. Gobiernos Regionales dentro de
Interior hasta 2020).

Entrada: <raw>/externo/cgr/IGFE*<año>*.pdf, descargados a mano desde
https://www.contraloria.cl/web/cgr/igfe (ver fuentes.md en esa carpeta).
Requiere: pip install pdfplumber

Salidas:
  reports/cgr_partidas.csv     lo extraído de los PDF (auditable)
  reports/validacion_cgr.csv   la comparación, fila por partida·año

Uso:
    python pipeline/3_validacion/15b_validar_vs_cgr.py
"""

import re
import sys

import pandas as pd

from dipres.config import DIRS
from dipres.dominio import MES_A_NUM
from dipres.estructura import normalizar_nombre
from dipres.hallazgos import Registro
from dipres.utils import leer_csv_robusto

DIR_CGR = DIRS.get("externo", DIRS["raw"] / "externo") / "cgr"
URL_IGFE = "https://www.contraloria.cl/web/cgr/igfe"
SALIDA_EXT = DIRS["reportes"] / "cgr_partidas.csv"
SALIDA_CMP = DIRS["reportes"] / "validacion_cgr.csv"

TOL = 2                     # millones de $ o miles de US$ (redondeo CGR)
GASTOS = range(21, 35)      # 21-34: sin saldo final de caja
MONEDAS = {"MONEDA NACIONAL": "PESOS", "MONEDA EXTRANJERA": "DOLARES"}
ESCALA = {"PESOS": 1_000, "DOLARES": 1}   # dataset → unidad CGR

# Columnas de la tabla "GASTOS DEVENGADOS POR PARTIDA Y SUBTÍTULO" y los
# subtítulos que agrupa cada una (notas al pie del IGFE). La deuda flotante
# (34.07) va en funcionamiento y no en deuda; como cruce_partida no baja a
# ítem, funcionamiento y deuda se comparan juntos.
GRUPOS_CGR = ["funcionamiento", "prestaciones", "transferencias",
              "inversiones", "deuda", "otros"]
GRUPO_SUBT = {21: "func+deuda", 22: "func+deuda", 34: "func+deuda",
              23: "prestaciones", 24: "transferencias", 27: "transferencias",
              28: "transferencias", 33: "transferencias", 29: "inversiones",
              30: "inversiones", 31: "inversiones", 25: "otros", 26: "otros",
              32: "otros"}

# Número del IGFE: 1.234.567 · (3,0) · 2,0 · - (cero)
RE_NUM = re.compile(r"^(?:\(?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?\)?|-)$")
RE_ANIOS = re.compile(r"^PARTIDAS((?:\s+(?:19|20)\d{2})+)\s*$")
RE_RUIDO = re.compile(r"SECTOR PÚBLICO|^\d{1,3}$|^PRESUPUESTO|^PARTIDAS|"
                      r"^INICIAL|^DO\d|^\(%\)")


# =====================================================
# Extracción
# =====================================================
def _valor(tok: str) -> float:
    """'1.234' → 1234 · '(3,0)' → -3.0 · '-' → 0."""
    if tok == "-":
        return 0.0
    neg = tok.startswith("(") or tok.startswith("-")
    t = tok.strip("()-").replace(".", "").replace(",", ".")
    return -float(t) if neg else float(t)


def _limpiar_nombre(s: str) -> str:
    """Quita las notas al pie pegadas al nombre: 'Interior4', 'Elecciones7 8'."""
    return re.sub(r"(?:\s*\d+)+$", "", s).strip()


def filas_tabla(lineas: list[str], ncols: int) -> list[tuple[str, list[float]]]:
    """
    Filas (nombre, valores) de una tabla de partidas, hasta TOTAL inclusive.
    Los nombres largos vienen partidos en tres líneas:
        'Ministerio Secretaría General de la'   ← prefijo
        '13.309 13.183 (0,9) 12.729 ...'        ← fila sin nombre propio
        'Presidencia de la República'           ← continuación
    """
    filas, prefijo, abierta = [], "", False
    for ln in lineas:
        ln = ln.strip()
        if not ln or RE_RUIDO.search(ln):
            continue
        toks = ln.split()
        nums = 0
        while nums < len(toks) and RE_NUM.match(toks[-1 - nums]):
            nums += 1
        if nums >= ncols:                       # fila con montos
            propio = " ".join(toks[:len(toks) - ncols])
            nombre = _limpiar_nombre(f"{prefijo} {propio}")
            valores = [_valor(t) for t in toks[len(toks) - ncols:]]
            filas.append([nombre, valores])
            abierta, prefijo = not propio, ""
            if nombre.upper().startswith("TOTAL"):
                break
        elif not re.search(r"[a-záéíóúñ]", ln):
            continue                            # títulos y encabezados
        elif abierta:                           # continuación del nombre
            filas[-1][0] = _limpiar_nombre(f"{filas[-1][0]} {ln}")
            abierta = False
        else:                                   # nombre que sigue abajo
            prefijo = f"{prefijo} {ln}".strip()
    return [(n, v) for n, v in filas]


def _tabla_de(titulo: str) -> str | None:
    """Qué tabla abre con estas líneas de título (o None)."""
    t = " ".join(titulo.split()).upper()
    if "SUBTÍTULO" in t:
        return ("subtitulo" if "GASTOS DEVENGADOS POR PARTIDA Y SUBTÍTULO" in t
                and "COMPARATIVO" not in t else None)
    if "SITUACIÓN PRESUPUESTARIA" in t and "GASTOS POR PARTIDA" in t:
        return "situacion"
    if "COMPARATIVO" in t and "GASTOS DEVENGADOS POR PARTIDA" in t:
        return "comparativo"
    return None


def leer_igfe(ruta) -> tuple[pd.DataFrame, list[str]]:
    """Extrae las dos tablas de partidas, en ambas monedas, de un IGFE."""
    import pdfplumber

    anio_inf = int(re.search(r"(20\d{2})", ruta.stem).group(1))
    registros, avisos = [], []
    pendientes = {(t, m) for t in ("situacion", "comparativo", "subtitulo")
                  for m in MONEDAS.values()}

    with pdfplumber.open(ruta) as pdf:
        textos = {}

        def texto(i):
            if i not in textos:
                textos[i] = ((pdf.pages[i].extract_text() or "")
                             if i < len(pdf.pages) else "")
            return textos[i]

        for i in range(len(pdf.pages)):
            if not pendientes:
                break
            propias = texto(i).splitlines()
            if not any("POR PARTIDA" in x for x in propias):
                continue
            # La tabla puede seguir en la página siguiente
            lineas = propias + texto(i + 1).splitlines()
            for j in range(len(propias)):
                mon = next((v for k, v in MONEDAS.items()
                            if propias[j].strip().startswith(k)), None)
                if mon is None:
                    continue
                tabla = _tabla_de(" ".join(lineas[max(0, j - 4):j]))
                if tabla is None or (tabla, mon) not in pendientes:
                    continue
                cuerpo = lineas[j + 1:]
                if tabla in ("situacion", "subtitulo"):
                    anios, ncols = [anio_inf], 7
                else:
                    m = next((RE_ANIOS.match(x.strip()) for x in cuerpo[:4]
                              if RE_ANIOS.match(x.strip())), None)
                    if m is None:
                        continue
                    anios = [int(a) for a in m.group(1).split()]
                    ncols = len(anios)
                filas = filas_tabla(cuerpo, ncols)
                if not filas or not filas[-1][0].upper().startswith("TOTAL"):
                    continue        # sigue más allá de i+1: se reintenta
                pendientes.discard((tabla, mon))
                *partidas, (_, total) = filas

                # Autoconsistencia de lo extraído: Σ partidas = TOTAL
                # Si no cuadra, la extracción corrió columnas: se descarta
                cols = [0, 1, 3, 4] if tabla == "situacion" else range(ncols)
                malas = [c for c in cols if abs(sum(v[c] for _, v in partidas)
                                                - total[c]) > len(partidas)]
                if malas:
                    avisos.append(f"{ruta.name} pág. {i + 1}: tabla {tabla} "
                                  f"{mon} descartada (Σ partidas ≠ TOTAL en "
                                  f"{len(malas)} columnas)")
                    continue
                for nombre, v in partidas:
                    if tabla == "subtitulo":
                        for grupo, x in zip(GRUPOS_CGR, v):
                            registros.append(dict(
                                informe=anio_inf, anio=anio_inf, moneda=mon,
                                tabla=tabla, nombre=nombre, grupo=grupo,
                                devengado=x, pagina=i + 1))
                    elif tabla == "situacion":
                        registros.append(dict(
                            informe=anio_inf, anio=anio_inf, moneda=mon,
                            tabla=tabla, nombre=nombre, inicial=v[0],
                            actualizado=v[1], devengado=v[3], pagado=v[4],
                            pagina=i + 1))
                    else:
                        for a, x in zip(anios, v):
                            registros.append(dict(
                                informe=anio_inf, anio=a, moneda=mon,
                                tabla=tabla, nombre=nombre, devengado=x,
                                pagina=i + 1))
    for t, m in sorted(pendientes):
        avisos.append(f"{ruta.name}: no se encontró la tabla {t} en {m}")
    return pd.DataFrame(registros), avisos


def extraer() -> tuple[pd.DataFrame, list[str]]:
    pdfs = sorted(DIR_CGR.glob("IGFE*.pdf"))
    if not pdfs:
        sys.exit(f"\n  No hay IGFE en {DIR_CGR}.\n  Descargar los informes "
                 f"anuales desde {URL_IGFE}\n  y guardarlos como IGFE <año>.pdf")
    partes, avisos = [], []
    for p in pdfs:
        print(f"  leyendo {p.name} ...")
        df, a = leer_igfe(p)
        partes.append(df)
        avisos += a
    # Un año aparece en hasta 5 informes (su situación + 4 comparativos
    # posteriores); se conservan todos para medir las revisiones de la CGR
    return pd.concat(partes, ignore_index=True), avisos


# =====================================================
# Dataset
# =====================================================
def dataset_partida() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Diciembre de cada año cerrado, gastos 21-34, por partida; y la
    ejecución por partida × grupo de subtítulos del IGFE.
    """
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_partida.csv"))
    df["MesNum"] = df["Mes"].map(MES_A_NUM)
    df["Sub"] = df["Subtítulo"].astype(int)
    df = df[(df["MesNum"] == 12) & df["Sub"].isin(GASTOS)].copy()
    df["Moneda"] = df["Moneda"].str.upper()
    esc = df["Moneda"].map(ESCALA)
    for c in ["ejecucion_acumulada", "ley_inicial", "ley_vigente"]:
        df[c] = df[c] / esc
    claves = ["Año", "Moneda", "Partida"]
    g = (df.groupby(claves, as_index=False)
         .agg(nombre_ds=("Nombre Partida", "last"),
              ejecucion=("ejecucion_acumulada", "sum"),
              ley_inicial=("ley_inicial", "sum"),
              ley_vigente=("ley_vigente", "sum")))
    df["grupo"] = df["Sub"].map(GRUPO_SUBT)
    sub = (df.groupby(claves + ["grupo"], as_index=False)
           ["ejecucion_acumulada"].sum()
           .rename(columns={"ejecucion_acumulada": "dataset"}))
    ren = {"Año": "anio", "Moneda": "moneda", "Partida": "partida"}
    return g.rename(columns=ren), sub.rename(columns=ren)


# =====================================================
# Correspondencia nombre CGR → código de partida
# =====================================================
def _tokens(s: str) -> set[str]:
    vacias = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "E", "MINISTERIO"}
    return set(normalizar_nombre(s).split()) - vacias


def asignar_partidas(ext: pd.DataFrame, ds: pd.DataFrame) -> pd.DataFrame:
    """
    Por año: nombre exacto normalizado; si no, inclusión de palabras
    (Interior ⊂ Interior y Seguridad Pública) con candidato único.
    """
    ext = ext.copy()
    ext["partida"] = pd.NA
    nombres = ds.drop_duplicates(["anio", "partida"])[
        ["anio", "partida", "nombre_ds"]]
    for anio, g in ext.groupby("anio"):
        cand = nombres[nombres.anio == anio]
        if cand.empty:          # 2016: fuera de la ventana del dataset
            continue
        exacto = {normalizar_nombre(n): p for n, p in
                  zip(cand.nombre_ds, cand.partida)}
        toks = [(p, _tokens(n)) for n, p in zip(cand.nombre_ds, cand.partida)]
        for idx, nombre in g["nombre"].items():
            p = exacto.get(normalizar_nombre(nombre))
            if p is None:
                t = _tokens(nombre)
                hits = [q for q, tq in toks if t and (t <= tq or tq <= t)]
                p = hits[0] if len(hits) == 1 else None
            ext.at[idx, "partida"] = p
    return ext


# =====================================================
# Comparación
# =====================================================
PARES = [("devengado", "ejecucion"), ("inicial", "ley_inicial"),
         ("actualizado", "ley_vigente")]


def cifras_cgr(ext: pd.DataFrame) -> pd.DataFrame:
    """
    Una fila por año·moneda·partida (o nombre, si no tiene partida):
      devengado          la cifra más reciente (último informe que cubre el año)
      devengado_original la del informe del propio año (situación)
      inicial, actualizado  de la situación del propio año
    La clave es la partida y no el nombre: los informes posteriores
    renombran (Interior y Seguridad Pública → Interior) y agregan filas en
    cero para partidas que aún no existían (Seguridad Pública en 2021).
    """
    e = ext[ext.devengado.fillna(0) != 0].copy()        # partida aún no creada
    e["clave"] = [f"p{int(p)}" if pd.notna(p) else f"n{n}"
                  for p, n in zip(e.partida, e.nombre)]
    e["_t"] = e.tabla.map({"situacion": 0, "comparativo": 1})
    e = e.sort_values(["informe", "_t"])
    claves = ["anio", "moneda", "clave"]
    ult = e.groupby(claves, as_index=False).agg(
        devengado=("devengado", "last"), informe=("informe", "last"),
        partida=("partida", "last"), nombre=("nombre", "last"))
    sit = (e[(e.tabla == "situacion") & (e.informe == e.anio)]
           [claves + ["inicial", "actualizado", "devengado"]]
           .rename(columns={"devengado": "devengado_original"}))
    return ult.merge(sit, on=claves, how="left")


def revisiones(cgr: pd.DataFrame) -> pd.DataFrame:
    """Partidas cuyo devengado la CGR cambió en informes posteriores."""
    r = cgr.dropna(subset=["devengado_original"])
    r = r[(r.devengado - r.devengado_original).abs() > TOL]
    return r.assign(cambio=r.devengado - r.devengado_original)


def comparar(cgr: pd.DataFrame, ds: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for (anio, mon), g in cgr[cgr.anio.isin(set(ds.anio))].groupby(
            ["anio", "moneda"]):
        d = ds[(ds.anio == anio) & (ds.moneda == mon)].set_index("partida")
        usados = set(g.partida.dropna())
        sin_par = [p for p in d.index if p not in usados]
        absorbidas = set()      # sin par, pero explican la diferencia de otra

        for r in g.itertuples():
            p = r.partida
            for col_cgr, col_ds in PARES:
                cgr_v = getattr(r, col_cgr)
                if pd.isna(cgr_v):
                    continue
                base = dict(anio=anio, moneda=mon, nombre=r.nombre,
                            concepto=col_cgr, cgr=float(cgr_v),
                            informe=r.informe if col_cgr == "devengado" else anio)
                if pd.isna(p):
                    filas.append(base | dict(partida=None, estado="solo CGR"))
                    continue
                v = float(d.at[p, col_ds]) if p in d.index else 0.0
                delta = v - float(cgr_v)
                estado, nota = ("cuadra" if abs(delta) <= TOL else "difiere"), ""
                if estado == "difiere":
                    for q in sin_par:
                        if abs(v + float(d.at[q, col_ds]) - cgr_v) <= TOL:
                            estado = "cuadra con otra partida"
                            nota = f"+ partida {int(q):02d} {d.at[q, 'nombre_ds']}"
                            absorbidas.add(q)
                            break
                filas.append(base | dict(partida=int(p), dataset=round(v, 1),
                                         delta=round(delta, 1), estado=estado,
                                         nota=nota))
        for q in sin_par:
            if q in absorbidas:
                continue
            filas.append(dict(anio=anio, moneda=mon, nombre=d.at[q, "nombre_ds"],
                              partida=int(q), concepto="devengado", cgr=None,
                              dataset=round(float(d.at[q, "ejecucion"]), 1),
                              estado="solo dataset"))
    return pd.DataFrame(filas)


def comparar_grupos(sub_cgr: pd.DataFrame, sub_ds: pd.DataFrame,
                    c: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada partida·año cuyo devengado total no cuadra: en qué grupo de
    subtítulos está la diferencia. Usa la tabla del informe del propio año
    (no hay versión revisada de esta tabla).
    """
    malas = c[(c.concepto == "devengado") & (c.estado == "difiere")][
        ["anio", "moneda", "partida"]].drop_duplicates()
    if malas.empty or sub_cgr.empty:
        return pd.DataFrame()
    cg = sub_cgr.dropna(subset=["partida"]).copy()
    cg["grupo"] = cg.grupo.replace({"funcionamiento": "func+deuda",
                                   "deuda": "func+deuda"})
    cg = (cg.groupby(["anio", "moneda", "partida", "grupo"], as_index=False)
          .devengado.sum().rename(columns={"devengado": "cgr"}))
    cg["partida"] = cg.partida.astype(int)
    m = (malas.merge(cg, on=["anio", "moneda", "partida"])
         .merge(sub_ds, on=["anio", "moneda", "partida", "grupo"], how="left")
         .fillna({"dataset": 0}))
    m["delta"] = (m.dataset - m.cgr).round(1)
    return m


def informar_grupos(m: pd.DataFrame) -> None:
    if m.empty:
        return
    orden = ["func+deuda", "prestaciones", "transferencias", "inversiones",
             "otros"]
    t = (m.pivot_table(index=["anio", "moneda", "partida"], columns="grupo",
                       values="delta", aggfunc="sum")
         .reindex(columns=orden).fillna(0))
    print(f"\n{'─' * 78}\n  Dónde está la diferencia del devengado "
          f"(dataset − CGR, por grupo de subtítulos)\n")
    print(f"  {'':<18}" + "".join(f"{g[:13]:>14}" for g in orden))
    for (anio, mon, p), r in t.iterrows():
        print(f"  {anio} {mon[:3]} {int(p):02d}{'':<8}"
              + "".join(f"{v:>14,.0f}" for v in r))
    m.to_csv(DIRS["reportes"] / "validacion_cgr_subtitulo.csv", index=False,
             encoding="utf-8")


def informar(c: pd.DataFrame, reg: Registro) -> None:
    unidad = {"PESOS": "MM$", "DOLARES": "MUS$"}
    orden = {cgr: i for i, (cgr, _) in enumerate(PARES)}
    c = c.assign(_o=c.concepto.map(orden)).sort_values(["anio", "moneda", "_o"])
    for (anio, mon, conc), g in c.groupby(["anio", "moneda", "concepto"],
                                          sort=False):
        comparables = g[g.estado.isin(["cuadra", "difiere",
                                       "cuadra con otra partida"])]
        ok = comparables.estado.str.startswith("cuadra").sum()
        marca = "✓" if ok == len(comparables) else "✗"
        print(f"  {marca} {anio} {mon:<8} {conc:<12} "
              f"{ok:>2}/{len(comparables):<2} partidas cuadran")
        for r in g[g.estado != "cuadra"].itertuples():
            par = f"{int(r.partida):02d}" if pd.notna(r.partida) else "--"
            if r.estado == "difiere":
                print(f"        {par} {str(r.nombre)[:38]:<38} CGR={r.cgr:>13,.0f} "
                      f"dataset={r.dataset:>13,.0f}  Δ={r.delta:,.0f} {unidad[mon]}")
                reg.warn("cgr", f"{anio}/{mon}/{par} {conc}: dataset "
                         f"{r.dataset:,.0f} vs CGR {r.cgr:,.0f}", anio=anio,
                         patron="dataset ≠ Contraloría")
            elif r.estado == "cuadra con otra partida":
                print(f"        {par} {str(r.nombre)[:38]:<38} cuadra {r.nota}")
            elif conc == "devengado":
                monto = r.cgr if r.estado == "solo CGR" else r.dataset
                print(f"        {par} {str(r.nombre)[:38]:<38} {r.estado} "
                      f"({monto:,.0f} {unidad[mon]})")
        if ok == len(comparables):
            reg.ok("cgr", f"{anio}/{mon} {conc}: {ok} partidas")


# =====================================================
if __name__ == "__main__":
    reg = Registro("validacion_cgr", salida_dir=DIRS["reportes"])
    print("=" * 78)
    print("  EJECUCIÓN POR PARTIDA — DATASET vs CONTRALORÍA (IGFE)")
    print("=" * 78 + "\n")

    ext, avisos = extraer()
    for a in avisos:
        print(f"  ⚠ {a}")
        reg.warn("extraccion_cgr", a)
    print(f"\n  Extraído: {len(ext)} filas · años "
          f"{ext.anio.min()}-{ext.anio.max()}")

    ds, sub_ds = dataset_partida()
    ext = asignar_partidas(ext, ds)
    SALIDA_EXT.parent.mkdir(parents=True, exist_ok=True)
    ext.to_csv(SALIDA_EXT, index=False, encoding="utf-8")

    sin = ext[ext.partida.isna() & ext.anio.isin(set(ds.anio))
              & (ext.tabla != "subtitulo")
              & (ext.devengado != 0)]
    if not sin.empty:
        print("\n  Nombres CGR sin partida en el dataset:")
        for n in sorted(sin.nombre.unique()):
            print(f"    · {n}")

    sub_cgr = ext[ext.tabla == "subtitulo"]
    cgr = cifras_cgr(ext[ext.tabla != "subtitulo"])
    rev = revisiones(cgr[cgr.anio.isin(set(ds.anio))])
    if not rev.empty:
        print(f"\n  La CGR revisó el devengado de {len(rev)} partida·año en "
              f"informes posteriores (se compara contra la cifra revisada):")
        for r in rev.sort_values(["anio", "moneda"]).itertuples():
            print(f"    {r.anio} {r.moneda:<8} {r.nombre[:40]:<40} "
                  f"{r.devengado_original:>13,.0f} → {r.devengado:>13,.0f} "
                  f"(IGFE {r.informe})")
        rev.to_csv(DIRS["reportes"] / "cgr_revisiones.csv", index=False,
                   encoding="utf-8")

    print()
    c = comparar(cgr, ds)
    informar(c, reg)
    c.to_csv(SALIDA_CMP, index=False, encoding="utf-8")
    informar_grupos(comparar_grupos(sub_cgr, sub_ds, c))

    comp = c[c.estado.isin(["cuadra", "difiere", "cuadra con otra partida"])]
    print(f"\n{'─' * 78}\n  Resumen por concepto\n")
    for conc, g in comp.groupby("concepto", sort=False):
        ok = g.estado.str.startswith("cuadra").sum()
        print(f"  {conc:<12} {ok:>4}/{len(g):<4} partida·año·moneda cuadran")
    print(f"\n  Extraído:   {SALIDA_EXT}\n  Comparación: {SALIDA_CMP}")
    reg.emitir()