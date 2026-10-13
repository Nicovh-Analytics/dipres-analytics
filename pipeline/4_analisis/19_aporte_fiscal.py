"""
19_aporte_fiscal.py — Aporte fiscal por ministerio, 2017-2026
==============================================================
Hasta 2020 la Ley de Presupuestos publicaba en su artículo 2 una tabla
de aporte fiscal por ministerio. Desde 2021 ya no. Este script la
reconstruye desde el dato y valida el método donde la ley sí la trae.

Reconstrucción (ley_inicial, nivel programa, subtítulo 09, pesos):
  libre  = total sub 09 − ítem 02 (deuda interna) − ítem 03 (deuda externa)
La tabla de la ley muestra solo el aporte LIBRE; el aporte para servicio
de la deuda va agrupado en el Tesoro ("Servicio de la Deuda Pública").
Se resta en vez de sumar el ítem 01 porque hay programas que publican el
total del sub 09 sin desglose por ítem (2020: Red de Bibliotecas
Públicas, 6.957.464): restando, ese monto cae en libre; sumando ítems,
se perdería. Esas brechas se registran.

Validación: la tabla del artículo 2 se extrae del texto de la ley
(texto/ley_presupuestos_<año>_dipres.txt) y se acepta solo si sus filas
suman el TOTAL APORTES que publica la misma tabla.

Entrada: cruce_programa.csv (o un programa.csv crudo de la familia ley,
con --archivo). Salida en DIRS["reportes"]:
  aporte_fiscal_por_ministerio.csv   año × partida, con la referencia
                                     de la ley donde existe
  aporte_fiscal_brechas.csv          programas con sub 09 sin ítems

Uso:
    python pipeline/4_analisis/19_aporte_fiscal.py
    python pipeline/4_analisis/19_aporte_fiscal.py --archivo ruta/a/programa.csv
"""

import argparse
import difflib
from itertools import combinations
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from dipres.config import DIRS
from dipres.dominio import MES_A_NUM
from dipres.hallazgos import Registro
from dipres.utils import leer_csv_robusto

DIR_TEXTO = DIRS.get("normativa", DIRS["base"] / "normativa") / "texto"
SALIDA = DIRS["reportes"]
ANIOS_CON_TABLA = range(2017, 2021)

# Nombres posibles de columnas (crudo de datos.gob.cl o cruce del pipeline)
COLUMNAS = {
    "anio": ["Año", "anio"], "mes": ["Mes", "mes"], "moneda": ["Moneda", "moneda"],
    "partida": ["Partida", "partida"], "nombre_partida": ["Nombre Partida"],
    "capitulo": ["Capítulo", "Capitulo"], "programa": ["Programa"],
    "nombre_programa": ["Nombre Programa"],
    "subtitulo": ["Subtítulo", "Subtitulo"], "item": ["Item", "Ítem"],
    "asignacion": ["Asignación", "Asignacion"],
    "ley_inicial": ["ley_inicial", "Monto Ley Inicial"],
}


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z ]", " ", s.lower()).split())


# =====================================================
# Dato: sub 09 por programa
# =====================================================
def cargar_programa(ruta: Path) -> pd.DataFrame:
    df, _ = leer_csv_robusto(str(ruta))
    ren = {}
    for std, opciones in COLUMNAS.items():
        col = next((c for c in opciones if c in df.columns), None)
        if col is None and std not in ("nombre_partida", "nombre_programa", "mes"):
            raise SystemExit(f"Falta la columna {opciones} en {ruta.name}. "
                             f"Columnas: {list(df.columns)}")
        if col:
            ren[col] = std
    df = df.rename(columns=ren)[list(ren.values())]
    # Montos con punto de miles (archivo crudo) → número
    if not pd.api.types.is_numeric_dtype(df.ley_inicial):
        df["ley_inicial"] = pd.to_numeric(
            df.ley_inicial.astype(str).str.replace(".", "", regex=False),
            errors="coerce")
    for c in ("subtitulo", "item", "asignacion", "partida"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "mes" in df.columns:   # ley_inicial no cambia en el año: último mes
        df["mes_num"] = df.mes.map(MES_A_NUM)
        df = df[df.groupby("anio").mes_num.transform("max") == df.mes_num]
    return df[(df.subtitulo == 9) & (df.moneda == "PESOS")]


def reconstruir(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Por programa: total = fila sin ítem (subtotal del subtítulo);
    ítems = filas con ítem y sin asignación. Libre = total − 02 − 03.
    """
    prog = ["anio", "partida", "capitulo", "programa"]
    total = df[df.item.isna()].groupby(prog).ley_inicial.sum().rename("total_09")
    items = (df[df.item.notna() & df.asignacion.isna()]
             .pivot_table(index=prog, columns="item", values="ley_inicial",
                          aggfunc="sum"))
    p = pd.concat([total, items.reindex(columns=[1, 2, 3])], axis=1).fillna(0)
    p.columns = ["total_09", "item01_libre", "item02_deuda_int", "item03_deuda_ext"]
    p["sin_item"] = p.total_09 - p[["item01_libre", "item02_deuda_int",
                                     "item03_deuda_ext"]].sum(axis=1)
    p["libre"] = p.total_09 - p.item02_deuda_int - p.item03_deuda_ext

    brechas = p[p.sin_item != 0].reset_index()
    nombres = df.groupby(prog).nombre_programa.first() if "nombre_programa" in df else None
    if nombres is not None and not brechas.empty:
        brechas = brechas.merge(nombres.reset_index(), on=prog, how="left")

    m = p.groupby(["anio", "partida"]).sum().reset_index()
    if "nombre_partida" in df.columns:
        m = m.merge(df.groupby(["anio", "partida"]).nombre_partida.first()
                      .reset_index(), on=["anio", "partida"], how="left")
    return m, brechas


# =====================================================
# Referencia: tabla del artículo 2 (2017-2020)
# =====================================================
RE_NUM = r"\d{1,3}(?:\.\d{3})*"


def extraer_art2(anio: int) -> tuple[dict[str, int], int | None, str]:
    """
    {nombre: pesos}, total publicado y estado. Bloque entre "APORTE
    FISCAL:" y "TOTAL APORTES". Repara montos cortados entre líneas
    ("1" / "17.948.203" → 117.948.203) antes de leer.

    La tabla tiene dos columnas ($ y US$) y una fila con un solo monto
    no dice en cuál está (2018: Fondo de Reserva de Pensiones va en US$).
    Se resuelve con los dos totales publicados: se busca la ÚNICA
    combinación de filas de un monto que, pasadas a US$, hace cuadrar
    ambas columnas. Si no hay una sola, la tabla no se usa.
    """
    ruta = DIR_TEXTO / f"ley_presupuestos_{anio}_dipres.txt"
    if not ruta.exists():
        return {}, None, f"no existe {ruta.name}"
    t = ruta.read_text(encoding="utf-8").replace("\ufffd", ".")
    i = t.find("APORTE FISCAL:")
    mj = re.search(r"T\s*OTAL\s+APORTES", t[i:]) if i >= 0 else None
    if i < 0 or mj is None:
        return {}, None, "no se ubicó la tabla de aporte fiscal"
    j = i + mj.start()
    tot = [int(x.replace(".", "")) for x in
           re.findall(RE_NUM, t[i + mj.end():i + mj.end() + 120].split("\n")[0])]
    if not tot:
        return {}, None, "TOTAL APORTES sin monto"
    total_p, total_d = tot[0], (tot[1] if len(tot) > 1 else 0)

    lineas = [x.strip() for x in t[i + len("APORTE FISCAL:"):j].splitlines()
              if x.strip()]
    # Uniones entre líneas: "1.1" + "17.965.074" es un monto cortado
    # (segura); "1" + "15.618.574" puede ser un monto cortado (115.618.574)
    # o dos columnas ("30" $ y "1.023.674" US$): ambigua, se prueban ambas.
    ambiguas = [k for k in range(1, len(lineas))
                if re.search(r"(?:^|\s)\d{1,3}$", lineas[k - 1])
                and re.match(r"\d", lineas[k])]
    if len(ambiguas) > 10:
        return {}, total_p, f"{len(ambiguas)} uniones ambiguas: demasiadas"
    validas = []
    for n in range(2 ** len(ambiguas)):
        pegar = {k for b, k in enumerate(ambiguas) if n >> b & 1}
        flujo = lineas[0]
        for k in range(1, len(lineas)):
            segura = (re.search(r"\d\.\d{1,2}$", lineas[k - 1])
                      and re.match(r"\d", lineas[k]))
            flujo += ("" if segura or k in pegar else " ") + lineas[k]
        r = _cuadrar(flujo, total_p, total_d)
        if r is not None:
            validas.append(r)
    if len(validas) != 1:
        return {}, total_p, (f"{len(validas)} lecturas cuadran con ambos totales "
                             f"(se exige exactamente una)")
    return validas[0], total_p, "ok"


def _cuadrar(flujo: str, total_p: int, total_d: int) -> dict[str, int] | None:
    """Lee las filas y las cuadra con ambos totales; None si no se puede."""
    filas = []
    for m in re.finditer(rf"([A-Za-zÁÉÍÓÚÑáéíóúñ–][^\d]*?)\s*(?:\.{{3,}})?\s*({RE_NUM})"
                         rf"(?:\s+({RE_NUM}))?(?=\s|$)", flujo):
        nombre = re.sub(r"^[–\-\s]+|[.\s]+$", "", m.group(1))
        nombre = re.sub(r"^P\s*r\s*ogramas Especiales del Tesoro Público:\s*[–-]?\s*",
                        "", nombre)
        a_ = int(m.group(2).replace(".", ""))
        b_ = int(m.group(3).replace(".", "")) if m.group(3) else None
        filas.append([nombre, a_, b_])
    exceso = sum(f[1] for f in filas) - total_p
    if exceso:
        solas = [k for k, f in enumerate(filas) if f[2] is None]
        sols = [c for n in range(1, min(len(solas), 6) + 1)
                for c in combinations(solas, n)
                if sum(filas[k][1] for k in c) == exceso]
        if len(sols) != 1:
            return None
        for k in sols[0]:
            filas[k][1], filas[k][2] = 0, filas[k][1]
    if sum(f[2] or 0 for f in filas) != total_d:
        return None
    return {f[0]: f[1] for f in filas if f[1]}


def asignar_partidas(filas: dict[str, int], nombres: pd.Series) -> dict[int, int]:
    """
    Nombre del texto → partida, uno a uno. Se puntúa cada par (similitud,
    y 1.0 si un nombre es prefijo del otro: "Ministerio de Justicia" →
    "... y Derechos Humanos") y se asigna de mayor a menor puntaje sin
    repetir partida. Sin uno a uno, "Justicia" caía en "Minería" (2017).
    """
    candidatos = {normalizar(n): int(p) for p, n in nombres.items()}
    pares = []
    for nombre in filas:
        nn = normalizar(nombre)
        for c in candidatos:
            puntaje = 1.0 if (c.startswith(nn) or nn.startswith(c)) else \
                difflib.SequenceMatcher(None, nn, c).ratio()
            if puntaje >= 0.75:
                pares.append((puntaje, nombre, c))
    out, usados_t, usados_c = {}, set(), set()
    for _, nombre, c in sorted(pares, reverse=True):
        if nombre in usados_t or c in usados_c:
            continue
        usados_t.add(nombre)
        usados_c.add(c)
        out[candidatos[c]] = filas[nombre]
    return out


# =====================================================
# Main
# =====================================================
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--archivo", type=Path,
                    default=DIRS["consolidado"] / "cruce_programa.csv")
    args = ap.parse_args()

    reg = Registro("aporte_fiscal", salida_dir=DIRS["reportes"])
    df = cargar_programa(args.archivo)
    ministerios, brechas = reconstruir(df)
    ministerios["art2_ley"] = np.nan

    print("=" * 78)
    print("  APORTE FISCAL POR MINISTERIO (libre, ley inicial, pesos)")
    print("=" * 78)
    print(f"\n{'─' * 78}\n  Validación contra el artículo 2 (años con tabla)\n")
    for anio in ANIOS_CON_TABLA:
        filas, total, estado = extraer_art2(anio)
        if estado != "ok":
            print(f"  ✗ {anio}: tabla de la ley no utilizable ({estado})")
            reg.warn("art2", f"{anio}: {estado}", anio=anio)
            continue
        m = ministerios[ministerios.anio == anio]
        if m.empty:
            print(f"  · {anio}: tabla leída ({len(filas)} filas, Σ = TOTAL "
                  f"APORTES {total:,}); sin datos de programa para ese año")
            continue
        nombres = (m.set_index("partida").nombre_partida
                   if "nombre_partida" in m else pd.Series(dtype=str))
        ref = asignar_partidas(filas, nombres)
        idx = ministerios.anio == anio
        ministerios.loc[idx, "art2_ley"] = ministerios.loc[idx, "partida"].map(ref)
        # Partidas creadas durante el año (Culturas 2018, Ciencia 2019):
        # ley_inicial 0 y no figuran en la tabla; no se comparan
        c = ministerios[idx & ~((ministerios.total_09 == 0)
                               & ministerios.art2_ley.isna())]
        ok = (c.libre == c.art2_ley).sum()
        print(f"  {'✓' if ok == len(c) else '✗'} {anio}: {ok}/{len(c)} partidas = "
              f"art. 2 (tabla: {len(filas)} filas, Σ = TOTAL APORTES)")
        for r in c[c.libre != c.art2_ley].itertuples():
            print(f"        partida {int(r.partida):02d}: reconstruido "
                  f"{r.libre:>16,.0f}  ley {r.art2_ley:>16,.0f}")
        reg.ok("art2", f"{anio}: {ok}/{len(c)}") if ok == len(c) else \
            reg.warn("art2", f"{anio}: {len(c) - ok} partidas ≠ art. 2", anio=anio)

    ministerios["delta_vs_art2"] = ministerios.libre - ministerios.art2_ley

    print(f"\n{'─' * 78}\n  Brechas: programas con sub 09 sin desglose por ítem\n")
    for r in brechas.itertuples():
        print(f"  {r.anio} {int(r.partida):02d}-{int(r.capitulo):02d}-"
              f"{int(r.programa):02d} {str(getattr(r, 'nombre_programa', ''))[:40]:<41}"
              f"{r.sin_item:>14,.0f}")
    if not brechas.empty:
        reg.warn("calidad", f"{len(brechas)} programas con sub 09 sin ítems",
                 patron="subtítulo sin desglose por ítem")

    print(f"\n{'─' * 78}\n  Total por año (millones de $)\n")
    t = ministerios.groupby("anio")[["total_09", "libre", "item02_deuda_int",
                                     "item03_deuda_ext"]].sum() / 1e3
    print(t.round(0).to_string())

    SALIDA.mkdir(parents=True, exist_ok=True)
    ministerios.to_csv(SALIDA / "aporte_fiscal_por_ministerio.csv",
                       index=False, encoding="utf-8")
    brechas.to_csv(SALIDA / "aporte_fiscal_brechas.csv", index=False,
                   encoding="utf-8")
    print(f"\n  Salida: {SALIDA / 'aporte_fiscal_por_ministerio.csv'}")
    reg.emitir()