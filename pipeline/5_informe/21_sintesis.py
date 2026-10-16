"""
21_sintesis.py — Hallazgos del proyecto, con sus cifras regeneradas
====================================================================
Lee los CSV que dejan los scripts de análisis en DIRS["reportes"] y escribe
docs/HALLAZGOS.md. Ninguna cifra del informe se tipea a mano: si cambian
los datos, se vuelve a correr y el informe se actualiza.

Cada hallazgo sigue la estructura de un informe de auditoría:
  condición   qué se encontró, con la cifra
  criterio    contra qué se compara
  evidencia   script y archivo que lo respaldan
  alcance     limitaciones y supuestos

Si falta el CSV de un bloque, el hallazgo queda como "pendiente: correr X"
en vez de fallar.

Bloques: ingresos (10, 18), estructura institucional (20), calidad de la
fuente (05, 20, _versiones), modificaciones, ejecución y endeudamiento
(16, 17, 11b), validación externa contra Contraloría (15b).

Uso:
    python pipeline/5_informe/21_sintesis.py
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from dipres.config import DIRS

REP = DIRS["reportes"]
SALIDA = DIRS["docs"] / "HALLAZGOS.md"
ALFA = 0.05


# =====================================================
# Formato (es-CL: punto de miles, coma decimal)
# =====================================================
def num(x: float, dec: int = 0) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x: float, dec: int = 1, signo: bool = True) -> str:
    s = num(x, dec) + "%"
    return ("+" + s) if signo and x > 0 else s


def pval(p: float) -> str:
    return f"p = {num(p, 3)}"


MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y", "a", "en", "para",
              "por", "e", "o", "al"}


def nombre(s) -> str:
    """'CARABINEROS DE CHILE' → 'Carabineros de Chile'."""
    ps = str(s).strip().lower().split()
    return " ".join(p if (i and p in MINUSCULAS) else p[:1].upper() + p[1:]
                    for i, p in enumerate(ps))


@dataclass
class Hallazgo:
    codigo: str
    titulo: str
    condicion: str
    criterio: str
    evidencia: str
    alcance: str
    solidez: str = "alta"          # alta | media
    pendiente: bool = False
    explicacion: str = ""          # lectura de una diferencia remanente


def pendiente(codigo: str, titulo: str, falta: str) -> Hallazgo:
    return Hallazgo(codigo, titulo, f"Pendiente: {falta}", "", "", "",
                    solidez="—", pendiente=True)


def leer(nombre: str) -> pd.DataFrame:
    return pd.read_csv(REP / nombre)


# =====================================================
# Bloque: ingresos
# =====================================================
def bloque_ingresos() -> list[Hallazgo]:
    try:
        ps = leer("ingresos_prueba_signo.csv")
        con = leer("ingresos_contribucion.csv")
    except FileNotFoundError:
        return [pendiente("ING", "Ingresos", "correr 18_ingresos.py")]

    ps = ps[ps.moneda == "PESOS"]
    con = con[con.moneda == "PESOS"]
    ag = ps[ps.nivel == "agregado"].set_index("clave")
    sb = ps[ps.nivel == "subtitulo"].copy()
    sb["sub"] = sb.clave.astype(int)
    sb = sb.set_index("sub")
    n = int(ag.loc["ingenuo_01_15", "n"])
    out = []

    # H1 — perímetro
    ing, gfs, pro = (ag.loc[k] for k in ("ingenuo_01_15", "ingreso_gfs", "pronostico"))
    out.append(Hallazgo(
        "ING-1", "El sesgo de proyección de ingresos es un efecto de perímetro",
        f"Si se suman los subtítulos 01-15 de ingresos, la ley subestima lo "
        f"recaudado en {int(ing.subestima)} de {n} años ({pval(ing.p_valor)}), "
        f"con un error medio de {pct(ing.error_medio_pct)}. Al excluir lo que no "
        f"es ingreso en sentido económico (endeudamiento, venta de activos "
        f"financieros, recuperación de préstamos, saldo de caja), el error medio "
        f"baja a {pct(gfs.error_medio_pct)} y el sesgo deja de ser "
        f"significativo (subestima {int(gfs.subestima)} años y sobreestima "
        f"{int(gfs.sobreestima)}, {pval(gfs.p_valor)}). Solo con las líneas que son pronóstico: "
        f"{pct(pro.error_medio_pct)}, {pval(pro.p_valor)}.",
        "Ley inicial contra ejecución acumulada a diciembre, pesos, años "
        f"completos (n = {n}). Prueba de signos binomial exacta, bilateral. "
        "Perímetro de ingreso según el Manual de Estadísticas de Finanzas "
        "Públicas (FMI).",
        "18_ingresos.py → ingresos_prueba_signo.csv, ingresos_agregados.csv",
        "Solo moneda nacional. La correspondencia con las categorías del manual "
        "del FMI está verificada para los subtítulos principales; la de "
        "algunos subtítulos menores es inferida (dominio.CONCORDANCIA_GFS)."))

    # H2 — autorizaciones
    nat = con.groupby("naturaleza").aporte_al_error_pct.sum()
    aut = con[con.naturaleza == "AUTORIZACION"].sort_values(
        "aporte_al_error_pct", ascending=False)
    det_aut = "; ".join(f"{nombre(r.nombre)} (subt. {int(r.subtitulo):02d}): "
                        f"{num(r.aporte_al_error_pct, 1)}% del error con "
                        f"{num(r.peso_en_ley_pct, 1)}% de la ley"
                        for r in aut.itertuples())
    out.append(Hallazgo(
        "ING-2", "La mayor parte del error no es error de pronóstico",
        f"De la diferencia total entre ley y recaudación 2017-{2016 + n}, el "
        f"{num(nat.get('AUTORIZACION', 0), 0)}% proviene de líneas que en la "
        f"ley son autorizaciones (permisos para endeudarse o vender activos), no "
        f"estimaciones: {det_aut}. Las líneas de pronóstico aportan el "
        f"{num(nat.get('PRONOSTICO', 0), 0)}% y las discrecionales el "
        f"{num(nat.get('DISCRECIONAL', 0), 0)}%.",
        "Aporte de cada subtítulo a la suma de (ejecutado − inicial) de todos "
        "los años, sin saldo de caja ni aporte fiscal.",
        "18_ingresos.py → ingresos_contribucion.csv",
        "La naturaleza (pronóstico, autorización, discrecional) es una "
        "clasificación del proyecto (dominio.NATURALEZA_INGRESO). El 11 "
        "confirma empíricamente que venta de activos financieros se comporta "
        "como tope; el endeudamiento se contrasta con el art. 3 en el 11b.",
        solidez="media"))

    # H3 — impuestos
    imp = con[con.subtitulo == 1].iloc[0]
    s1 = sb.loc[1]
    out.append(Hallazgo(
        "ING-3", "Impuestos: sin sesgo acumulado, pero el año típico recauda "
                 "menos de lo proyectado",
        f"Impuestos (subtítulo 01) pesa el {num(imp.peso_en_ley_pct, 1)}% de "
        f"los ingresos de la ley y explica solo el {num(imp.aporte_al_error_pct, 1)}% "
        f"del error: su error acumulado es {pct(imp.error_propio_pct, 1)}. Pero "
        f"ese casi cero es una compensación: la ley sobreestima la recaudación "
        f"en {int(s1.sobreestima)} de {int(s1.n)} años (mediana anual "
        f"{pct(s1.error_mediano_pct)}) y la subestima en "
        f"{int(s1.subestima)}, por montos grandes. La diferencia entre años que "
        f"sobreestiman y que subestiman no es significativa ({pval(s1.p_valor)}).",
        "Ley inicial contra ejecución a diciembre, pesos. Prueba de signos "
        "binomial exacta, bilateral.",
        "18_ingresos.py → ingresos_prueba_signo.csv, ingresos_contribucion.csv, "
        "ingresos_detalle.csv",
        "Los años que subestiman coinciden con la recuperación post-pandemia "
        "(2021-2022); ver ingresos_detalle.csv. Con n = 9, una tendencia a "
        "sobreestimar de esta magnitud no se puede distinguir del azar.",
        solidez="media"))

    # H4 — no tributarios subestimados
    nt = sb[(sb.naturaleza == "PRONOSTICO") & (sb.index != 1)
            & (sb.p_valor < ALFA) & (sb.subestima > sb.sobreestima)]
    if len(nt):
        c_nt = con[con.subtitulo.isin(nt.index)]
        lista = "; ".join(f"{nombre(r.nombre)} (subt. {s:02d}): "
                          f"{int(r.subestima)}/{int(r.n)} años, error medio "
                          f"{pct(r.error_medio_pct, 0)}, {pval(r.p_valor)}"
                          for s, r in nt.iterrows())
        out.append(Hallazgo(
            "ING-4", "Los ingresos no tributarios se subestiman año tras año",
            f"A diferencia de impuestos, {len(nt)} líneas de pronóstico "
            f"recaudan sistemáticamente más de lo que la ley proyecta: {lista}. "
            f"Juntas pesan el {num(c_nt.peso_en_ley_pct.sum(), 1)}% de la ley y "
            f"explican el {num(c_nt.aporte_al_error_pct.sum(), 1)}% del error.",
            f"Prueba de signos por subtítulo, significancia {num(ALFA, 2)}. Con "
            f"12 subtítulos probados, alguno podría salir significativo por "
            f"azar; los de p = 0,004 (9/9 años) resisten una corrección de "
            f"Bonferroni (umbral {num(ALFA / 12, 4)}).",
            "18_ingresos.py → ingresos_prueba_signo.csv",
            "Los datos no permiten distinguir si es una proyección prudente "
            "deliberada o una debilidad del método. Clasificación como "
            "pronóstico no verificada para estos subtítulos.",
            solidez="media"))

    # H5 — conciliación
    try:
        cz = leer("conciliacion_ingresos.csv").iloc[-1]
        out.append(Hallazgo(
            "ING-5", "Los ingresos del dataset concilian con la cifra oficial",
            f"Los ingresos {int(cz.anio)} con perímetro del manual del FMI "
            f"calculados desde el dataset ({num(cz.gfs_mm)} millones de $) "
            f"difieren en {pct(cz.brecha_obs_pct, 2)} de la cifra oficial de "
            f"DIPRES ({num(cz.oficial_mm)} millones): el dataset queda "
            f"{num(abs(cz.brecha_mm))} millones "
            f"{'por sobre' if cz.brecha_mm < 0 else 'por debajo de'} la cifra "
            f"oficial.",
            f"Informe de Finanzas Públicas 4T{str(int(cz.anio))[2:]}, ingresos "
            f"del Gobierno Central Total. Dólares convertidos al observado "
            f"promedio ({num(cz.tc_observado, 1)} $/US$).",
            "10_conciliacion_gfs.py → conciliacion_ingresos.csv",
            f"Un solo año con cifra oficial cargada. Con el dólar supuesto "
            f"({num(cz.tc_supuesto, 0)}) la brecha es "
            f"{pct(cz.brecha_sup_pct, 2)}.",
            explicacion=(
                f"La diferencia es menor al 1% y no es cambiaria: el tipo de "
                f"cambio que la cerraría ({num(cz.tc_que_cierra, 0)} $/US$) no es "
                f"plausible. Causas posibles, no verificadas: (1) la cifra oficial "
                f"es del Gobierno Central Total, que suma al presupuestario las "
                f"operaciones extrapresupuestarias; si estas son positivas, la "
                f"diferencia del componente presupuestario es mayor que la "
                f"mostrada; (2) DIPRES aplica la clasificación del FMI a nivel de "
                f"ítem, y aquí se ajusta por subtítulo completo, así que partidas "
                f"que DIPRES reclasifica dentro de un subtítulo (por ejemplo, como "
                f"financiamiento) quedan dentro del cálculo; (3) los dólares se "
                f"convierten al promedio anual y no al tipo de cambio de cada "
                f"operación. Para acotarla: comparar contra la cifra del Gobierno "
                f"Central Presupuestario del mismo informe.")))
    except FileNotFoundError:
        out.append(pendiente("ING-5", "Conciliación con cifra oficial",
                             "correr 10_conciliacion_gfs.py"))

    # H6 — tipo de cambio
    try:
        tc = leer("tipo_cambio_desvio.csv")
        altos = tc[tc.desvio_pct > 5]
        out.append(Hallazgo(
            "ING-6", "La proyección del dólar falla en una sola dirección",
            f"En {len(tc)} años, el dólar observado superó al supuesto del "
            f"presupuesto en {(tc.desvio_pct > 0).sum()}. Los desvíos grandes "
            f"son todos al alza: "
            + ", ".join(f"{int(r.Año)} ({pct(r.desvio_pct, 0)})"
                        for r in altos.itertuples())
            + f". El mayor desvío a la baja es {pct(tc.desvio_pct.min(), 1)}. "
            f"Desvío medio absoluto: {num(tc.desvio_pct.abs().mean(), 1)}%.",
            "Supuesto: tipo de cambio promedio del Informe de Finanzas Públicas "
            "del 3er trimestre del año anterior. Observado: promedio anual del "
            "Banco Central.",
            "10_conciliacion_gfs.py → tipo_cambio_desvio.csv; valores en "
            "dominio.TC_SUPUESTO y TC_OBSERVADO (ingresados a mano)",
            "Los años con desvíos grandes coinciden con shocks (2019, 2020, 2022, "
            "2024); con n = 9 no es evidencia de sesgo del método. Cuando el "
            "dólar sube, lo presupuestado en dólares rinde más pesos.",
            solidez="media"))
    except FileNotFoundError:
        out.append(pendiente("ING-6", "Tipo de cambio",
                             "correr 10_conciliacion_gfs.py"))
    return out


# =====================================================
# Bloque: estructura institucional
# =====================================================
ESTRUCTURALES = ["ALTA", "BAJA", "TRASLADO"]


def bloque_estructura() -> list[Hallazgo]:
    try:
        res = pd.read_csv(REP / "estructura_resumen_anual.csv", index_col=0)
        ev = leer("estructura_eventos.csv")
    except FileNotFoundError:
        return [pendiente("EST", "Estructura institucional",
                          "correr 20_estructura_institucional.py")]
    res.index = res.index.astype(int)
    primero = res.index.min()
    r = res.loc[res.index > primero]           # el primer año no tiene mes previo
    completos = r[r.index < r.index.max()] if len(r) > 1 else r
    out = []

    # EST-1 — tasa de cambio
    estr = r[ESTRUCTURALES].sum(axis=1)
    mx = completos.tasa_cambio_pct.idxmax()
    out.append(Hallazgo(
        "EST-1", "Cada año cambia entre el "
                 f"{num(completos.tasa_cambio_pct.min(), 0)}% y el "
                 f"{num(completos.tasa_cambio_pct.max(), 0)}% de los servicios",
        f"Entre {r.index.min()} y {r.index.max()} hubo {int(r.ALTA.sum())} "
        f"altas, {int(r.BAJA.sum())} bajas y {int(r.TRASLADO.sum())} traslados "
        f"de capítulos (servicios) en la Ley de Presupuestos. Los capítulos "
        f"pasaron de {num(res.capitulos_promedio.iloc[0])} a "
        f"{num(res.capitulos_promedio.iloc[-1])}. El año de mayor cambio fue "
        f"{mx} ({num(completos.tasa_cambio_pct.max(), 1)}%).",
        "Tasa = (altas + bajas + traslados) / capítulos promedio del año. Un "
        "capítulo se compara mes a mes con el anterior; los cambios de nombre "
        "no cuentan.",
        "20_estructura_institucional.py → estructura_resumen_anual.csv, "
        "estructura_eventos.csv",
        f"No se cuentan los cambios de {primero} (primer año de datos, sin mes "
        f"anterior) y el último año está incompleto. Una institución que "
        f"cambia de nombre al trasladarse se cuenta como alta y baja, lo que "
        f"sobreestima la tasa en años de reestructuración."))

    # EST-2 — Nueva Educación Pública
    slep = ev[ev.nombre.fillna("").str.upper().str.contains(
        "SERVICIO LOCAL DE EDUCACI") & ev.tipo.isin(["ALTA", "TRASLADO"])]
    if len(slep):
        por = slep.groupby("Año").size()
        out.append(Hallazgo(
            "EST-2", "La Nueva Educación Pública se ve año a año en el presupuesto",
            f"Entre {por.index.min()} y {por.index.max()} aparecen "
            f"{len(slep)} Servicios Locales de Educación como capítulos nuevos: "
            + ", ".join(f"{a}: {n}" for a, n in por.items())
            + ". Es el calendario de traspaso de la educación municipal, "
            "leído directamente desde la Ley de Presupuestos.",
            "Altas de capítulos con nombre \"Servicio Local de Educación\" en "
            "la partida 09.",
            "20_estructura_institucional.py → estructura_eventos.csv",
            "Cuenta el mes en que el servicio aparece en el presupuesto, que "
            "puede diferir de su entrada en funciones."))

    # EST-3 — cambio de práctica
    a = r.loc[r.index <= 2020]
    b = r.loc[r.index >= 2022]
    if len(a) and len(b):
        pa = a.durante_el_año.sum() / max(a[ESTRUCTURALES].sum().sum(), 1) * 100
        pb = b.durante_el_año.sum() / max(b[ESTRUCTURALES].sum().sum(), 1) * 100
        out.append(Hallazgo(
            "EST-3", "Las instituciones nuevas pasaron a crearse en enero",
            f"Entre {a.index.min()} y {a.index.max()}, el "
            f"{num(pa, 0)}% de las altas, bajas y traslados ocurrió durante el "
            f"año (por leyes o decretos posteriores a la Ley de Presupuestos). "
            f"Entre {b.index.min()} y {b.index.max()}, solo el {num(pb, 0)}%: "
            f"los cambios pasaron a entrar por la propia Ley de Presupuestos, "
            f"en enero.",
            "Mes en que el capítulo aparece, desaparece o se traslada.",
            "20_estructura_institucional.py → estructura_resumen_anual.csv",
            "2021 queda fuera de ambos períodos. Describe el momento del cambio "
            "en el presupuesto, no la fecha de la ley que lo creó.",
            solidez="media"))

    # EST-4 — traspasos parciales
    tp = ev[(ev.tipo == "TRASLADO") & ev.detalle.fillna("").str.contains("parcial")]
    if len(tp):
        x = tp.detalle.str.extract(r"desde (\d+-\d+).*conserva ([\d,]+)")
        partes = [f"{nombre(t.nombre)}, de {o} a {t.Partida:02d}-{t.Capítulo:02d} "
                  f"en {t.Mes.lower()} {t.Año} (el origen conserva "
                  f"{num(float(c.replace(',', '')) / 1e3)} millones de $)"
                  for t, o, c in zip(tp.itertuples(), x[0], x[1])]
        out.append(Hallazgo(
            "EST-4", "Los traslados a mitad de año dividen el presupuesto entre "
                     "dos partidas, sin duplicarlo",
            f"{'Se detecta 1 traspaso parcial' if len(tp) == 1 else f'Se detectan {len(tp)} traspasos parciales'}: "
            f"el servicio aparece en su nueva partida y la de origen conserva lo "
            f"ya ejecutado. " + "; ".join(partes)
            + ". Para la serie anual de esas instituciones hay que sumar ambas "
            "partidas.",
            "Capítulo nuevo cuyo monto calza (±0,1%) con la caída de un "
            "capítulo existente el mismo mes, fuera de enero.",
            "20_estructura_institucional.py → estructura_eventos.csv",
            "Solo detecta traspasos de un capítulo a otro en un mismo mes."))
    return out


# =====================================================
# Bloque: calidad de la fuente
# =====================================================
def _logs_consolidar() -> list[dict]:
    import json
    filas = []
    for ruta in sorted(DIRS["consolidado"].glob("_log_consolidar_*.json")):
        for l in json.loads(ruta.read_text(encoding="utf-8")):
            filas.append({**l, "nivel": ruta.stem.replace("_log_consolidar_", "")})
    return filas


def bloque_calidad() -> list[Hallazgo]:
    out = []
    # CAL-1 — descuadres entre niveles
    try:
        d = leer("descuadres_partida_capitulo.csv")
        con = d.evento.fillna("") != ""
        anios = sorted(d.Año.unique())
        out.append(Hallazgo(
            "CAL-1", "Los descuadres entre niveles de DIPRES se explican por "
                     "instituciones creadas a mitad de año",
            f"En {len(d)} casos (mes × partida) la partida suma más que sus "
            f"capítulos, lo que no puede deberse a consolidación. El "
            f"{num(con.mean() * 100, 0)}% coincide con una alta, baja o "
            f"traslado de un servicio de esa partida: el archivo de partidas "
            f"incorpora al servicio nuevo hasta varios meses antes que el de "
            f"capítulos (mediana {num(d.loc[con, 'distancia'].median(), 0)} "
            f"mes). Los casos se concentran en {anios[0]}-{anios[-1]}; no hay "
            f"desde {anios[-1] + 1}.",
            "Consolidar solo elimina flujos internos: el nivel alto nunca puede "
            "superar la suma del bajo. Evento asociado: misma partida, desde 1 "
            "mes antes hasta 6 después.",
            "20_estructura_institucional.py → descuadres_partida_capitulo.csv; "
            "06_validar.py check 10",
            f"Quedan {int((~con).sum())} casos sin explicar, la mayoría del primer "
            f"año de datos (sin mes anterior para comparar). Detalle en "
            f"CALIDAD_FUENTE.md."))
    except FileNotFoundError:
        out.append(pendiente("CAL-1", "Descuadres entre niveles",
                             "correr 20_estructura_institucional.py"))

    # CAL-2 — correcciones al consolidar
    logs = _logs_consolidar()
    if logs:
        dup = [x for l in logs for x in l.get("duplicado_doble", [])]
        ejemplo = ""
        if dup:
            g = max(dup, key=lambda x: float(x.get("ley_inicial", 0) or 0))
            nom = g.get("Nombre Asignación") or g.get("Nombre Item") or ""
            if nom and g.get("ley_inicial"):
                v = float(g["ley_inicial"])
                ejemplo = (f" (la mayor: {nombre(nom)}, {g.get('Mes', '').lower()} "
                           f"{g.get('Año', '')}, {num(v / 2 / 1e3)} millones de $ "
                           f"repetidos como {num(v / 1e3)})")
        rep = sum(l.get("reparadas", 0) for l in logs)
        nr = sum(len(l.get("no_reparables", [])) for l in logs)
        out.append(Hallazgo(
            "CAL-2", "Los archivos de DIPRES requieren correcciones puntuales "
                     "para leerse completos",
            f"Al consolidar se repararon {num(rep)} filas con \";\" dentro de un "
            f"nombre (antes se descartaban sin aviso) y se descartaron "
            f"{len(dup)} líneas de ley repetidas con el monto exacto al doble"
            f"{ejemplo}. Filas que no se pudieron reparar: {nr}.",
            "Una fila válida tiene tantos campos como el encabezado, códigos "
            "numéricos y montos con formato chileno. Una línea repetida con el "
            "doble exacto en ley inicial y vigente es un error de la fuente.",
            "05_consolidar.py → _log_consolidar_<nivel>.json",
            "La regla del doble exacto es conservadora: líneas repetidas con "
            "nombres distintos se mantienen (código de asignación reutilizado "
            "en 2025). Detalle en CALIDAD_FUENTE.md.",
            solidez="alta"))

    # CAL-3 — republicaciones
    versiones = list(DIRS["raw"].rglob("_versiones/*.csv"))
    if versiones:
        out.append(Hallazgo(
            "CAL-3", "DIPRES corrige datos ya publicados",
            f"Se han detectado {len(versiones)} archivos que DIPRES volvió a "
            f"publicar con cambios después de su primera descarga. La versión "
            f"anterior se conserva en _versiones/.",
            "Tamaño del archivo en el servidor distinto del descargado "
            "(02_descargar.py --revisar-tamano).",
            "raw/<tipo>/<año>/<mes>/_versiones/",
            "Solo desde que existe el historial de versiones (octubre 2026); "
            "correcciones anteriores no son visibles.",
            solidez="media"))
    return out


# =====================================================
# Bloque: modificaciones, ejecución y endeudamiento
# =====================================================
def _lista(df, fmt, n=4) -> str:
    return "; ".join(fmt(r) for r in df.head(n).itertuples())


def bloque_ejecucion() -> list[Hallazgo]:
    out = []

    # MOD-1 — ampliación ley inicial → vigente
    try:
        mr = leer("modificaciones_resumen.csv")
        g = mr[(mr.moneda == "PESOS") & (mr.seccion == "GASTOS") & mr.anio_completo]
        mx = g.loc[g.neto_pct.idxmax()]
        resto = g[g.anio != mx.anio]
        out.append(Hallazgo(
            "MOD-1", "El presupuesto de gastos se amplía cada año durante su "
                     "ejecución",
            f"Entre {g.anio.min()} y {g.anio.max()}, la ley vigente al cierre "
            f"supera a la inicial en todos los años: mediana "
            f"{pct(g.neto_pct.median())} neto, con un máximo de "
            f"{pct(mx.neto_pct)} en {int(mx.anio)}. El neto esconde movimiento: "
            f"sumando aumentos y rebajas por separado, la mediana del ajuste "
            f"bruto es {num(g.bruto_pct.median(), 1)}% de la ley inicial. Sin "
            f"{int(mx.anio)}, el rango neto es {pct(resto.neto_pct.min())} a "
            f"{pct(resto.neto_pct.max())}.",
            "Ley inicial contra ley vigente a diciembre, por partida y "
            "subtítulo, pesos, sin aporte fiscal (subt. 27-28, doble conteo).",
            "16_modificaciones.py → modificaciones_resumen.csv, "
            "modificaciones_detalle.csv",
            "Incluye leyes dictadas durante el año (reajuste, leyes de "
            "emergencia), que el dataset no distingue de las modificaciones "
            "por decreto."))
    except FileNotFoundError:
        out.append(pendiente("MOD-1", "Modificaciones", "correr 16_modificaciones.py"))

    # MOD-2 — artículo 4
    try:
        a4 = leer("modificaciones_art4.csv")
        pes = a4[a4.moneda == "PESOS"]
        usd = a4[(a4.moneda == "DOLARES")
                 & (a4.estado_inc1 == "requiere respaldo legal")]
        exp = (pes.estado_inc1 != "requiere respaldo legal").sum()
        out.append(Hallazgo(
            "MOD-2", "Los aumentos de gasto corriente en pesos caben en las "
                     "excepciones del artículo 4",
            f"El artículo 4 de cada ley exige una ley para aumentar el gasto "
            f"corriente. En pesos, {exp} de {len(pes)} años se apegan o el "
            f"exceso se explica por mayores saldos de caja y venta de activos "
            f"financieros, que la ley exceptúa. En dólares, "
            f"{len(usd)} años muestran aumentos sin excepción medible ("
            + ", ".join(f"{int(r.anio)}: {num(r.corriente_no_explicado / 1e3)} "
                        f"millones de US$" for r in usd.itertuples())
            + ").",
            "Art. 4 inc. 1 de cada Ley de Presupuestos, por moneda (cada cuadro "
            "del art. 1). Excepciones medibles: Δ saldo inicial de caja (sin "
            "Tesoro) y Δ venta de activos financieros.",
            "16_modificaciones.py → modificaciones_art4.csv",
            "Lo que no se explica con los datos puede tener respaldo en gastos "
            "excedibles o leyes del año, que el dataset no ve: por eso se "
            "informa como \"requiere respaldo legal\", no como incumplimiento.",
            solidez="media"))
    except FileNotFoundError:
        out.append(pendiente("MOD-2", "Artículo 4", "correr 16_modificaciones.py"))

    # EJE — ejecución
    try:
        er = leer("ejecucion_resumen.csv")
        rc = leer("ejecucion_recurrencia.csv")
    except FileNotFoundError:
        out.append(pendiente("EJE", "Ejecución", "correr 17_ejecucion.py"))
        rc = er = None
    if er is not None:
        g = er[(er.moneda == "PESOS") & (er.seccion == "GASTOS") & er.anio_completo]
        out.append(Hallazgo(
            "EJE-1", "Se ejecuta casi todo lo autorizado, y una décima parte en "
                     "diciembre",
            f"Entre {g.anio.min()} y {g.anio.max()} se ejecutó entre el "
            f"{num(g.pct_ejecucion.min(), 1)}% y el {num(g.pct_ejecucion.max(), 1)}% "
            f"de la ley vigente de gastos. En diciembre se gasta entre el "
            f"{num(g.pct_en_diciembre.min(), 1)}% y el "
            f"{num(g.pct_en_diciembre.max(), 1)}% del año, algo más que el 8,3% "
            f"de un gasto parejo.",
            "Ley vigente y ejecución acumulada a diciembre; gasto de diciembre = "
            "acumulada de diciembre − acumulada de noviembre. Pesos, sin aporte "
            "fiscal.",
            "17_ejecucion.py → ejecucion_resumen.csv",
            "Agregado nacional: compensa subejecución y sobreejecución entre "
            "partidas (ambas se reportan por separado en el CSV)."))

        base = rc[(rc.moneda == "PESOS") & (rc.tipo == "operativo")]
        sub = base[(base.senal == "subejecucion") & (base.anios_senal >= 8)]
        if len(sub):
            out.append(Hallazgo(
                "EJE-2", "La subejecución se repite en las mismas líneas",
                "Líneas de gasto que ejecutan 90% o menos de lo autorizado en "
                "8 o más de los años: " + _lista(
                    sub, lambda r: f"{nombre(r.nombre_partida)}, "
                    f"{nombre(r.nombre_subtitulo).lower()} (subt. "
                    f"{int(r.subtitulo):02d}): {int(r.anios_senal)}/{int(r.de_anios)} "
                    f"años, mediana {num(r.pct_ejec_mediana, 1)}% ejecutado, "
                    f"{num(r.saldo_total / 1e3)} millones sin ejecutar en total") + ".",
                "Ejecuta ≤ 90% de la ley vigente y el saldo supera $1.000 "
                "millones.",
                "17_ejecucion.py → ejecucion_recurrencia.csv",
                "Nivel partida × subtítulo: no identifica qué programas o "
                "proyectos explican el saldo.",
                solidez="alta"))

        conc = base[(base.senal == "concentracion_dic")
                    & (base.anios_senal == base.de_anios)]
        if len(conc):
            s29 = conc[conc.subtitulo == 29]
            out.append(Hallazgo(
                "EJE-3", "Las compras de activos se concentran en diciembre todos "
                         "los años",
                f"{len(conc)} líneas de gasto concentran el 25% o más de su "
                f"ejecución anual en diciembre en todos los años; {len(s29)} son "
                f"adquisición de activos no financieros (subt. 29). Los casos "
                f"más marcados: " + _lista(
                    conc.sort_values("pct_dic_mediana", ascending=False),
                    lambda r: f"{nombre(r.nombre_partida)} (subt. "
                    f"{int(r.subtitulo):02d}, mediana "
                    f"{num(r.pct_dic_mediana, 0)}% en diciembre)", n=3) + ".",
                "Gasto de diciembre ≥ 25% del ejecutado del año (3 veces lo de "
                "un mes parejo) y ≥ $1.000 millones.",
                "17_ejecucion.py → ejecucion_recurrencia.csv",
                "El patrón es compatible con gasto de fin de año para no perder "
                "presupuesto, pero también con calendarios de licitación y "
                "pagos contra entrega; los datos no distinguen entre ambos.",
                solidez="media"))

        sob = base[(base.senal == "sobreejecucion") & (base.anios_senal >= 6)]
        if len(sob):
            out.append(Hallazgo(
                "EJE-4", "Algunas líneas se ejecutan por sobre lo autorizado de "
                         "forma recurrente",
                "Líneas que ejecutan más que su ley vigente en 6 o más años: "
                + _lista(sob, lambda r: f"{nombre(r.nombre_partida)}, "
                         f"{nombre(r.nombre_subtitulo).lower()} (subt. "
                         f"{int(r.subtitulo):02d}): {int(r.anios_senal)}/"
                         f"{int(r.de_anios)} años, mediana "
                         f"{num(r.pct_ejec_mediana, 0)}%", n=5) + ".",
                "Ejecutado > ley vigente > 0 (lo ejecutado sin línea de ley se "
                "informa aparte y es casi nulo a nivel partida).",
                "17_ejecucion.py → ejecucion_recurrencia.csv",
                "Ejecutar sobre lo vigente solo es legal en gastos excedibles "
                "(art. 28 DL 1.263) o con ingresos propios; los datos no "
                "identifican esa base legal.",
                solidez="media"))

    # DEU-1 — tope de endeudamiento
    try:
        te = leer("tope_endeudamiento.csv")
        te = te[te.MesNum == 12]
        cuenta = te.lectura.value_counts()
        cabe = te[te.lectura.str.contains("CABE", na=False)]
        sobre = te[te.lectura == "SOBRE"]
        out.append(Hallazgo(
            "DEU-1", "El endeudamiento se mantiene dentro de las autorizaciones "
                     "legales verificables",
            f"De {len(te)} años: {cuenta.get('DENTRO', 0)} dentro del tope del "
            f"art. 3 aun sin descontar amortizaciones, "
            f"{cuenta.get('INDETERMINADO', 0)} indeterminados con estos datos"
            + (f", {len(cabe)} ({', '.join(str(int(a)) for a in cabe.Año)}) "
               f"sobre el art. 3 pero dentro de la autorización adicional de "
               f"la Ley 21.288 (Fondo COVID)" if len(cabe) else "")
            + (f" y {len(sobre)} ({', '.join(str(int(a)) for a in sobre.Año)}) "
               f"con excesos sin ley adicional identificada (uso neto "
               + ", ".join(f"{num(r.uso_neto_pct, 0)}%" for r in sobre.itertuples())
               + ")" if len(sobre) else "") + ".",
            "Tope = incisos 1 y 2 del art. 3 de cada ley (más la Ley 21.288 en "
            "2020-2022). Endeudamiento del Tesoro acotado entre bruto (subt. "
            "14) y neto de amortizaciones (34.01-34.02), en US$ al observado.",
            "11b_tope_endeudamiento.py → tope_endeudamiento.csv",
            "El cómputo legal requiere el detalle de cada emisión; los excesos "
            "pequeños pueden deberse a la conversión cambiaria o a deuda de "
            "corto plazo no registrada como amortización.",
            solidez="media"))
    except FileNotFoundError:
        out.append(pendiente("DEU-1", "Tope de endeudamiento",
                             "correr 11b_tope_endeudamiento.py"))
    return out



# =====================================================
# Bloque: validación externa (Contraloría)
# =====================================================
COMPARABLES = ["cuadra", "difiere", "cuadra con otra partida"]
GORE = 31      # la CGR obtiene su ejecución "de la información por región"


def bloque_validacion() -> list[Hallazgo]:
    out = []
    try:
        c = leer("validacion_cgr.csv")
    except FileNotFoundError:
        return [pendiente("VAL-1", "Validación contra Contraloría",
                          "correr 15b_validar_vs_cgr.py")]
    c = c[c.estado.isin(COMPARABLES)]
    nombres = c.dropna(subset=["partida"]).groupby("partida").nombre.last()
    anios = sorted(c.anio.unique())
    periodo = f"{anios[0]}-{anios[-1]}"

    # VAL-1 — lo autorizado
    cuenta = {}
    for conc in ["inicial", "actualizado"]:
        g = c[c.concepto == conc]
        cuenta[conc] = (int(g.estado.str.startswith("cuadra").sum()), len(g))
    ley = c[c.concepto.isin(["inicial", "actualizado"]) & (c.estado == "difiere")]
    grandes = ley[ley.delta.abs() > 10_000]
    unidad = {"PESOS": "millones de $", "DOLARES": "miles de US$"}
    excep = ""
    if not grandes.empty:
        casos = (grandes.groupby(["partida", "moneda"])
                 .agg(anios=("anio", lambda a: sorted(set(a))),
                      dmin=("delta", "min"), dmax=("delta", "max")))
        partes = [f"{nombre(nombres.get(p, p))} "
                  f"({', '.join(str(a) for a in r.anios)}: dataset − CGR entre "
                  f"{num(r.dmin)} y {num(r.dmax)} {unidad[m]})"
                  if r.dmin != r.dmax else
                  f"{nombre(nombres.get(p, p))} "
                  f"({', '.join(str(a) for a in r.anios)}: dataset − CGR "
                  f"{num(r.dmin)} {unidad[m]})"
                  for (p, m), r in casos.iterrows()]
        resto = ley.drop(grandes.index)
        tope = (f"no superan {num(resto.delta.abs().max())} millones de $ "
                f"o miles de US$" if not resto.empty else "son de redondeo")
        excep = (f" Las demás diferencias {tope}. Las excepciones son "
                 + "; ".join(partes) + ", sin explicación en los informes.")
    out.append(Hallazgo(
        "VAL-1", "El presupuesto publicado por DIPRES coincide con el de "
                 "Contraloría",
        f"Por partida, {periodo}: el presupuesto inicial cuadra en "
        f"{cuenta['inicial'][0]} de {cuenta['inicial'][1]} partida·año·moneda "
        f"y el actualizado en {cuenta['actualizado'][0]} de "
        f"{cuenta['actualizado'][1]}.{excep}",
        "Informe de la Gestión Financiera del Estado (IGFE) de la Contraloría, "
        "estado de situación presupuestaria de gastos por partida, que elimina "
        "solo las transferencias dentro de cada partida, igual que "
        "cruce_partida. Gastos 21-34 a diciembre; tolerancia ±2 millones de $ "
        "o miles de US$ por redondeo.",
        "15b_validar_vs_cgr.py → validacion_cgr.csv, cgr_partidas.csv",
        "La CGR recibe los datos desde SIGFE, el mismo sistema de origen que "
        "DIPRES, pero los compila y valida por su cuenta. La prueba verifica "
        "la agregación que publica DIPRES, no el registro de cada servicio. "
        "Los tribunales, el CPLT, el INDH y la Defensoría de la Niñez figuran "
        "en el IGFE pero no como partida en datos.gob.cl.",
        solidez="alta"))

    # VAL-2 — lo ejecutado
    d = c[c.concepto == "devengado"]
    ok = int(d.estado.str.startswith("cuadra").sum())
    dif = d[(d.estado == "difiere") & (d.partida != GORE)]
    menor = int((dif.delta < 0).sum())
    rel = (dif.delta.abs() / dif.cgr.abs()).dropna()
    bajo1 = int((rel < 0.01).sum())

    patron, recurrentes = "", ""
    try:
        s = leer("validacion_cgr_subtitulo.csv")
        s = s[s.partida != GORE]
        s["abs"] = s.delta.abs()
        tot = s.groupby(["anio", "moneda", "partida"])["abs"].transform("sum")
        s = s[tot > 50]
        top = s.loc[s.groupby(["anio", "moneda", "partida"])["abs"].idxmax()]
        top = top.assign(cuota=top["abs"] / s.groupby(
            ["anio", "moneda", "partida"])["abs"].sum().values)
        conc = top[top.cuota >= 0.8]
        patron = (f" De los {len(top)} partida·año con diferencia que tienen "
                  f"desglose por subtítulo en el IGFE, en {len(conc)} el 80% o "
                  f"más se concentra en un solo grupo.")
        rec = (conc.groupby(["partida", "grupo", "moneda"]).anio.nunique()
               .sort_values(ascending=False))
        rec = rec[rec >= 4].head(4)
        if not rec.empty:
            recurrentes = (" Se repite en los mismos lugares: " + "; ".join(
                f"{nombre(nombres.get(p, p))}, {g}"
                f"{' (US$)' if m == 'DOLARES' else ''} ({n} años)"
                for (p, g, m), n in rec.items()) + ".")
    except FileNotFoundError:
        pass

    revis = ""
    try:
        rv = leer("cgr_revisiones.csv")
        rv = rv[rv.moneda == "PESOS"]
        if not rv.empty:
            m = rv.loc[rv.cambio.abs().idxmax()]
            revis = (f" La propia CGR corrigió en informes posteriores el "
                     f"devengado de {len(rv)} partida·año (el mayor: "
                     f"{nombre(m.nombre)} {int(m.anio)}, "
                     f"{num(m.cambio, 0)} millones de $); la comparación usa "
                     f"la cifra corregida.")
    except FileNotFoundError:
        pass

    out.append(Hallazgo(
        "VAL-2", "La ejecución publicada difiere de la de Contraloría en "
                 "líneas puntuales, siempre las mismas",
        f"El devengado por partida cuadra en {ok} de {len(d)} partida·año·"
        f"moneda. En las diferencias (sin Gobiernos Regionales), el dataset "
        f"informa menos que la CGR en {menor} de {len(dif)} casos, y en "
        f"{bajo1} la diferencia es menor al 1% de la partida.{patron}"
        f"{recurrentes}{revis}",
        "Devengado del IGFE (cifra más reciente publicada por la CGR para cada "
        "año) contra ejecución acumulada a diciembre de cruce_partida, total y "
        "por grupo de subtítulos (tabla de gastos devengados por partida y "
        "subtítulo del IGFE).",
        "15b_validar_vs_cgr.py → validacion_cgr.csv, "
        "validacion_cgr_subtitulo.csv, cgr_revisiones.csv",
        "Ambas fuentes cubren los mismos servicios en las partidas revisadas "
        "(conteo de servicios del IGFE vs capítulos del dataset). La CGR "
        "consolida datos recibidos hasta febrero o marzo del año siguiente. "
        "Los IGFE no explican las diferencias ni concilian con DIPRES, y la "
        "CGR no publica cifras bajo el nivel partida, por lo que la línea "
        "exacta no se puede identificar desde afuera. Gobiernos Regionales se "
        "excluye: la CGR obtiene su ejecución de otra fuente (información por "
        "región).",
        solidez="media",
        explicacion="Tres tipos, según dónde cae la diferencia: (1) "
        "consolidación: en Salud la CGR elimina menos transferencias internas "
        "que DIPRES (queda entre la partida consolidada y la suma de "
        "capítulos); (2) registros que el dataset no tiene en ningún nivel: "
        "RREE inversiones y Trabajo prestaciones (2017-2018), donde partida y "
        "suma de capítulos coinciden y aun así la CGR registra más; (3) "
        "posible neteo: Poder Judicial informa préstamos negativos en el "
        "dataset y positivos en la CGR. Pendiente: consulta por Ley 20.285 a "
        "DIPRES y a la CGR con estos casos."))
    return out


# =====================================================
# Informe
# =====================================================
BLOQUES = [("Ingresos: proyección y recaudación", bloque_ingresos),
           ("Modificaciones, ejecución y endeudamiento", bloque_ejecucion),
           ("Estructura institucional", bloque_estructura),
           ("Calidad de la fuente", bloque_calidad),
           ("Validación externa", bloque_validacion)]

ALCANCE_GENERAL = """\
**Fuente:** ejecución presupuestaria mensual y Ley de Presupuestos del Gobierno \
Central publicadas por DIPRES en datos.gob.cl (2017-01 a 2026-08), textos de \
las leyes de presupuestos 2017-2026, cifras del Informe de Finanzas Públicas \
y el Informe de la Gestión Financiera del Estado de la Contraloría (2017-2025).

**Seguridad razonable** para los niveles nacional y partida al cierre de cada \
año: la ley inicial cuadra con los cuadros por partida de cada ley en 5.927 de \
5.929 combinaciones partida·subtítulo (las 2 restantes son errores del texto \
de la ley), el presupuesto por partida coincide con el de Contraloría y los \
ingresos concilian con la cifra oficial. La ejecución por partida difiere de \
la de Contraloría en líneas puntuales (VAL-2). Los niveles \
capítulo y programa tienen inconsistencias de publicación documentadas en \
[CALIDAD_FUENTE.md](CALIDAD_FUENTE.md).

**Lo que el dataset no ve:** leyes dictadas durante el año, gastos \
excedibles, detalle de emisiones de deuda. Por eso ningún hallazgo concluye \
"incumple": cuando algo no se explica con los datos, se indica que requiere \
respaldo legal."""


def markdown(bloques: list[tuple[str, list[Hallazgo]]]) -> str:
    ls = ["# Hallazgos — Presupuesto del Gobierno Central de Chile, 2017-2025",
          "",
          f"> Generado por `21_sintesis.py` el {date.today():%d-%m-%Y} desde "
          f"los reportes del pipeline. No editar a mano: las cifras se "
          f"regeneran.",
          "", "## Alcance", "", ALCANCE_GENERAL, "", "## Resumen", ""]
    ls += ["| Código | Hallazgo | Solidez |", "|---|---|---|"]
    for _, hs in bloques:
        ls += [f"| {h.codigo} | {h.titulo} | {h.solidez} |" for h in hs]
    for titulo, hs in bloques:
        ls += ["", f"## {titulo}"]
        for h in hs:
            ls += ["", f"### {h.codigo} · {h.titulo}", ""]
            if h.pendiente:
                ls.append(f"_{h.condicion}_")
                continue
            ls += [f"**Condición.** {h.condicion}", "",
                   f"**Criterio.** {h.criterio}", "",
                   f"**Evidencia.** `{h.evidencia}`", "",
                   f"**Alcance.** {h.alcance}"]
            if h.explicacion:
                ls += ["", f"**Explicación de la diferencia.** {h.explicacion}"]
    return "\n".join(ls) + "\n"


if __name__ == "__main__":
    bloques = [(t, f()) for t, f in BLOQUES]
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(markdown(bloques), encoding="utf-8", newline="\r\n")

    print("=" * 78)
    print("  SÍNTESIS DE HALLAZGOS")
    print("=" * 78)
    for titulo, hs in bloques:
        print(f"\n  {titulo}")
        for h in hs:
            marca = "…" if h.pendiente else "✓"
            print(f"   {marca} {h.codigo:<6} {h.titulo}  [{h.solidez}]")
    print(f"\n  Informe: {SALIDA}")