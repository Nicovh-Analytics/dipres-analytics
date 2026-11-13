"""
manifiesto.py — Huella de los datos de entrada (A3, reproducibilidad)
=====================================================================
Registra cada archivo de raw/ (datos.gob.cl, normativa, reportes de deuda,
tipos de cambio y los PDF bajados a mano) con su tamaño, fecha y SHA-256,
y lo compara con el manifiesto anterior. Responde dos preguntas:

  1. ¿Con qué versión exacta de los datos se obtuvieron los resultados?
     El manifiesto se versiona en el repo (docs/manifiesto_datos.csv):
     quien clone el repo puede verificar que tiene los mismos archivos.
  2. ¿Cambió algo desde la última vez? Lista archivos nuevos, cambiados
     y faltantes. Un cambio sin una descarga que lo explique es un
     archivo tocado a mano o corrupto.

Origen de cada archivo (columnas url y origen):
  - "log": la URL exacta, desde los logs de descarga (logs/_log*.json:
    datos.gob.cl, inversión, monitoreo). Las claves del log son rutas
    absolutas; se comparan desde la carpeta raw/ hacia abajo (o, en logs
    anteriores a la migración, por el tramo final que exista bajo raw/),
    así que sirven aunque los datos se hayan movido de disco o carpeta.
  - "registro": la página de origen, desde docs/fuentes_externas.csv
    (archivos bajados a mano o por scripts que no dejan log).
  - vacío: sin origen conocido. Se listan al final: es lo que falta
    documentar.

Por eficiencia, si un archivo tiene el mismo tamaño y fecha de
modificación que en el manifiesto anterior, se reutiliza su hash. Con
--completo se recalculan todos.

Uso (desde la raíz del repo):
    python herramientas/manifiesto.py              # actualiza el manifiesto
    python herramientas/manifiesto.py --verificar  # solo compara; sale con
                                                   # código 1 si hay cambios
    python herramientas/manifiesto.py --completo   # recalcula todos los hash
"""

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath, PureWindowsPath

from dipres.config import DIRS, LOGS

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "manifiesto_datos.csv"
FUENTES = RAIZ / "docs" / "fuentes_externas.csv"
CAMPOS = ["ruta", "bytes", "modificado", "sha256", "url", "origen"]
IGNORAR = {".part", ".tmp"}


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def leer_anterior() -> dict[str, dict]:
    if not SALIDA.exists():
        return {}
    with open(SALIDA, encoding="utf-8", newline="") as f:
        return {r["ruta"]: r for r in csv.DictReader(f)}


def relativa_a_raw(destino: str, base: Path) -> str | None:
    """Ruta desde raw/ (posix, minúsculas) de una clave de log, sea Windows o
    posix. Primero se ancla en una carpeta raw/; si la clave no la tiene (logs
    anteriores a la migración: D:\\dipres-datos\\ejecucion\\...), se busca el
    tramo final de la ruta que exista hoy bajo raw/."""
    partes = (PureWindowsPath(destino) if "\\" in destino else PurePosixPath(destino)).parts
    idx = [i for i, p in enumerate(partes) if p.lower() == "raw"]
    if idx:
        return "/".join(partes[idx[-1] + 1:]).lower()
    for i in range(1, len(partes)):
        rel = "/".join(partes[i:])
        if (base / rel).is_file():
            return rel.lower()
    return None


def urls_descarga() -> dict[str, str]:
    """{ruta relativa a raw/ en minúsculas: url} desde todos los logs."""
    base = Path(DIRS["raw"])
    logs = {Path(p) for p in LOGS.values()} | set(Path(DIRS["logs"]).glob("_log*.json"))
    out = {}
    for ruta in sorted(logs):
        if not ruta.exists():
            continue
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(datos, dict):
            continue
        for destino, d in datos.items():
            if not (isinstance(d, dict) and d.get("url")):
                continue
            rel = relativa_a_raw(destino, base)
            if rel:
                out[rel] = d["url"]
    return out


def fuentes_registradas() -> list[tuple[str, str]]:
    """[(patrón, url)] de docs/fuentes_externas.csv, en orden."""
    if not FUENTES.exists():
        return []
    with open(FUENTES, encoding="utf-8-sig", newline="") as f:
        return [(r["patron"], r.get("url") or "") for r in csv.DictReader(f)
                if r.get("patron")]


def origen(rel: str, urls: dict, fuentes: list) -> tuple[str, str]:
    if rel.lower() in urls:
        return urls[rel.lower()], "log"
    for patron, url in fuentes:
        if fnmatch(rel, patron):
            return url, "registro"
    return "", ""


def construir(anterior: dict, completo: bool) -> tuple[list[dict], int]:
    base = Path(DIRS["raw"])
    urls, fuentes = urls_descarga(), fuentes_registradas()
    filas, recalculados = [], 0
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.suffix in IGNORAR:
            continue
        rel = p.relative_to(base).as_posix()
        st = p.stat()
        mod = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        prev = anterior.get(rel)
        if (not completo and prev and int(prev["bytes"]) == st.st_size
                and prev["modificado"] == mod):
            h = prev["sha256"]
        else:
            h = sha256(p)
            recalculados += 1
        url, org = origen(rel, urls, fuentes)
        filas.append({"ruta": rel, "bytes": st.st_size, "modificado": mod,
                      "sha256": h, "url": url, "origen": org})
    return filas, recalculados


def comparar(anterior: dict, filas: list[dict]) -> dict[str, list[str]]:
    actual = {f["ruta"]: f for f in filas}
    return {
        "nuevos": sorted(set(actual) - set(anterior)),
        "faltantes": sorted(set(anterior) - set(actual)),
        "cambiados": sorted(r for r in set(actual) & set(anterior)
                            if actual[r]["sha256"] != anterior[r]["sha256"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verificar", action="store_true")
    ap.add_argument("--completo", action="store_true")
    args = ap.parse_args()

    anterior = leer_anterior()
    filas, recalculados = construir(anterior, args.completo or args.verificar)
    dif = comparar(anterior, filas)

    print("=" * 70)
    print("  MANIFIESTO DE DATOS DE ENTRADA")
    print("=" * 70)
    print(f"  {len(filas):,} archivos · {sum(f['bytes'] for f in filas) / 1e9:.2f} GB"
          f" · {recalculados:,} hash calculados")
    if not anterior:
        print("  Primer manifiesto: no hay con qué comparar")
    for k, lista in dif.items():
        print(f"  {k}: {len(lista)}")
        for r in lista[:15]:
            print(f"    · {r}")
        if len(lista) > 15:
            print(f"    … y {len(lista) - 15} más")

    # Origen: cuántos archivos lo tienen y qué carpetas quedan sin documentar
    por_origen = {o: sum(f["origen"] == o for f in filas) for o in ("log", "registro", "")}
    print(f"\n  origen: {por_origen['log']:,} con URL del log · "
          f"{por_origen['registro']:,} con fuente registrada · {por_origen['']:,} sin origen")
    sin = sorted({f["ruta"].rsplit("/", 1)[0] if "/" in f["ruta"] else "(raíz)"
                  for f in filas if not f["origen"]})
    for c in sin[:15]:
        print(f"    · sin origen: {c}/  (agregar a docs/fuentes_externas.csv)")

    if args.verificar:
        hay = anterior and (dif["cambiados"] or dif["faltantes"])
        print("\n  " + ("❌ Los datos no coinciden con el manifiesto"
                        if hay else "✓ Los datos coinciden con el manifiesto"))
        sys.exit(1 if hay else 0)

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(filas)
    print(f"\n  Manifiesto: {SALIDA}")


if __name__ == "__main__":
    main()
