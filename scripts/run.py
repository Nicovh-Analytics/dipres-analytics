"""
run.py — Corre el pipeline por etapas
======================================
Cada etapa es una carpeta en pipeline/; sus scripts corren en orden de
nombre. Si un script falla, se detiene.

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
"""

import argparse
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
    args = ap.parse_args()

    if args.solo:
        etapas = [args.solo]
    else:
        inicio = "extraccion" if args.todo else (args.desde or "consolidacion")
        etapas = ETAPAS[ETAPAS.index(inicio):]

    # Hace importable 'dipres' aunque no se haya hecho pip install -e .
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        [str(RAIZ), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
    sys.path.insert(0, str(RAIZ))

    if args.lista:
        for e in ETAPAS:
            print(f"\n{e}")
            for s in scripts(e):
                extra = " ".join(argumentos(s))
                print(f"  {s.name} {extra}".rstrip())
        return

    for e in etapas:
        print(f"\n{'#' * 78}\n#  {e.upper()}\n{'#' * 78}")
        for s in scripts(e):
            cmd = [sys.executable, str(s), *argumentos(s)]
            print(f"\n▶ {s.relative_to(RAIZ)} {' '.join(argumentos(s))}".rstrip())
            t0 = time.time()
            r = subprocess.run(cmd, cwd=RAIZ, env=env)
            if r.returncode != 0:
                sys.exit(f"\n✗ {s.name} terminó con error ({r.returncode}). "
                         f"Pipeline detenido.")
            print(f"  ✓ {s.name} ({time.time() - t0:,.0f} s)")
    print("\nPipeline completo.")


if __name__ == "__main__":
    main()