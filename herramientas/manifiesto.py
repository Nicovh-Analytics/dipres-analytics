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

La URL de origen se toma del log de descarga (LOGS["descarga"]) cuando
existe; los archivos externos bajados a mano quedan sin URL.

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
from pathlib import Path

from dipres.config import DIRS, LOGS

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "manifiesto_datos.csv"
CAMPOS = ["ruta", "bytes", "modificado", "sha256", "url"]
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


def urls_descarga() -> dict[str, str]:
    """{ruta relativa a raw/: url} desde el log de descarga."""
    ruta = LOGS.get("descarga")
    if not ruta or not Path(ruta).exists():
        return {}
    base = Path(DIRS["raw"])
    out = {}
    for destino, d in json.loads(Path(ruta).read_text(encoding="utf-8")).items():
        try:
            rel = Path(destino).relative_to(base).as_posix()
        except ValueError:
            continue
        out[rel] = d.get("url") or ""
    return out


def construir(anterior: dict, completo: bool) -> tuple[list[dict], int]:
    base = Path(DIRS["raw"])
    urls = urls_descarga()
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
        filas.append({"ruta": rel, "bytes": st.st_size, "modificado": mod,
                      "sha256": h, "url": urls.get(rel, "")})
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
