"""
run.py — Corre el pipeline por etapas
======================================
Cada etapa es una carpeta en pipeline/; sus scripts corren en orden de
nombre. Si un script falla (termina con error), se detiene.

Controles: los scripts registran sus validaciones con dipres.hallazgos.
Registro, que deja un resumen en reports/_controles/. Al final de la
corrida se muestra una tabla con ✓ / ⚠ / ❌ por script, y si algún control
dio ❌ la corrida termina con código 1 (aunque todos los scripts hayan
corrido). Con --estricto se detiene en el primer script con ❌.

Cada script corre con PYTHONUTF8=1: sin eso, en Windows la salida
redirigida (| tail, > log.txt) usa cp1252 y falla con ✓, ❌ o ─.

Etapas:
  extraccion     descarga desde datos.gob.cl, Dipres y LeyChile (red)
  consolidacion  crudos → consolidados y cruces
  validacion     perfil, validación interna y contra la ley
  analisis       ingresos, modificaciones, ejecución, estructura
  informe        docs/HALLAZGOS.md

Por defecto corre desde consolidación (la extracción usa la red y se
corre aparte).

Uso:
    python run.py                         # consolidación → informe
    python run.py --todo                  # extracción → informe
    python run.py --desde analisis        # analisis → informe
    python run.py --solo validacion
    python run.py --lista                 # muestra etapas y scripts
    python run.py --estricto              # se detiene en el primer ❌
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PIPELINE = RAIZ / "pipeline"
ETAPAS = ["extraccion", "consolidacion", "validacion", "analisis", "informe"]


def argumentos(script: Path) -> list[str]:
    """Argumentos por defecto de los scripts que los necesitan."""
    from dipres.config import DIRS
    return {
        "02_descargar.py": ["--si"],
        "03_descargar_inv.py": ["--si"],
        "05_consolidar.py": ["--salida", str(DIRS["consolidado"])],
    }.get(script.name, [])


def controles_dir() -> Path:
    from dipres.config import DIRS
    return DIRS["reportes"] / "_controles"


def leer_controles(script: Path) -> dict | None:
    """Suma los resúmenes que dejó el script (puede tener varios Registro)."""
    archivos = list(controles_dir().glob(f"{script.stem}__*.json"))
    if not archivos:
        return None
    total = {"ok": 0, "info": 0, "warn": 0, "error": 0, "errores": []}
    for a in archivos:
        d = json.loads(a.read_text(encoding="utf-8"))
        for k in ("ok", "info", "warn", "error"):
            total[k] += d["resumen"].get(k, 0)
        total["errores"] += d.get("errores", [])
    return total


def tabla_controles(resultados: list[tuple[Path, dict | None]]) -> int:
    """Imprime la tabla final; devuelve cuántos scripts tuvieron ❌."""
    print(f"\n{'=' * 78}\n  CONTROLES DE LA CORRIDA\n{'=' * 78}")
    print(f"  {'script':40} {'✓':>6} {'⚠':>5} {'❌':>5}")
    con_error = 0
    for s, c in resultados:
        if c is None:
            print(f"  {s.stem:40} {'(sin registro de controles)':>18}")
            continue
        marca = "  ←" if c["error"] else ""
        print(f"  {s.stem:40} {c['ok']:>6} {c['warn']:>5} {c['error']:>5}{marca}")
        con_error += bool(c["error"])
    for s, c in resultados:
        if c and c["errores"]:
            print(f"\n  ❌ {s.stem}:")
            for m in c["errores"][:10]:
                print(f"     {m}")
            if len(c["errores"]) > 10:
                print(f"     … y {len(c['errores']) - 10} más (ver reports/)")
    return con_error


def scripts(etapa: str) -> list[Path]:
    carpeta = next(PIPELINE.glob(f"*_{etapa}"), None)
    return sorted(carpeta.glob("[0-9]*.py")) if carpeta else []


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--todo", action="store_true", help="incluye extracción")
    g.add_argument("--desde", choices=ETAPAS)
    g.add_argument("--solo", choices=ETAPAS)
    ap.add_argument("--lista", action="store_true")
    ap.add_argument("--estricto", action="store_true",
                    help="detenerse en el primer script con un control en ❌")
    args = ap.parse_args()

    if args.solo:
        etapas = [args.solo]
    else:
        inicio = "extraccion" if args.todo else (args.desde or "consolidacion")
        etapas = ETAPAS[ETAPAS.index(inicio):]

    # Hace importable 'dipres' aunque no se haya hecho pip install -e .
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": os.pathsep.join(
        [str(RAIZ), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
    sys.path.insert(0, str(RAIZ))

    if args.lista:
        for e in ETAPAS:
            print(f"\n{e}")
            for s in scripts(e):
                extra = " ".join(argumentos(s))
                print(f"  {s.name} {extra}".rstrip())
        return

    resultados = []
    for e in etapas:
        print(f"\n{'#' * 78}\n#  {e.upper()}\n{'#' * 78}")
        for s in scripts(e):
            # Resúmenes de corridas anteriores de este script: fuera
            for viejo in controles_dir().glob(f"{s.stem}__*.json"):
                viejo.unlink()
            cmd = [sys.executable, str(s), *argumentos(s)]
            print(f"\n▶ {s.relative_to(RAIZ)} {' '.join(argumentos(s))}".rstrip())
            t0 = time.time()
            r = subprocess.run(cmd, cwd=RAIZ,
                               env={**env, "DIPRES_SCRIPT": s.stem})
            if r.returncode != 0:
                tabla_controles(resultados)
                sys.exit(f"\n✗ {s.name} terminó con error ({r.returncode}). "
                         f"Pipeline detenido.")
            c = leer_controles(s)
            resultados.append((s, c))
            print(f"  ✓ {s.name} ({time.time() - t0:,.0f} s)")
            if args.estricto and c and c["error"]:
                tabla_controles(resultados)
                sys.exit(f"\n✗ {s.name} registró controles en ❌ "
                         f"(--estricto). Pipeline detenido.")
    con_error = tabla_controles(resultados)
    if con_error:
        sys.exit(f"\nPipeline completo, pero {con_error} script(s) con "
                 f"controles en ❌.")
    print("\nPipeline completo, sin controles en ❌.")


if __name__ == "__main__":
    main()