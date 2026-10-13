"""
reorganizar.py — Reordena el repo por etapas (se corre una vez y se borra)
==========================================================================
Antes:  scripts/ con todo junto
Después:
  dipres/                 módulos compartidos (paquete): config, dominio,
                          utils, descarga, estructura, hallazgos, normativa
  pipeline/1_extraccion/  02, 03, 12, 13
  pipeline/2_consolidacion/ 05 (ex 05b), 07
  pipeline/3_validacion/  04, 06, 14, 15
  pipeline/4_analisis/    10, 11, 11b, 16-20
  pipeline/5_informe/     21
  exploracion/            01
  archivo/                lo que estaba en scripts/_archivo + 05 viejo, 00, 08, 09

Además:
  - reescribe los imports de los módulos compartidos:
      from config import DIRS   →   from dipres.config import DIRS
  - crea dipres/__init__.py y pyproject.toml (para `pip install -e .`)
  - en dipres/config.py, DIRS["scripts"] pasa a apuntar a pipeline/

Usa `git mv` para que git conserve el historial de cada archivo.
Por defecto solo MUESTRA el plan; con --aplicar lo ejecuta.
Lo que no reconoce no lo toca: lo lista al final.

Uso (desde la raíz del repo, con el árbol de git limpio):
    python reorganizar.py            # ver el plan
    python reorganizar.py --aplicar  # ejecutar
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ORIGEN = RAIZ / "scripts"

COMPARTIDOS = ["config", "dominio", "utils", "descarga", "estructura",
               "hallazgos", "normativa"]

# prefijo del nombre → (carpeta destino, nombre nuevo o None = mismo)
ETAPAS = {
    "01_": ("exploracion", None),
    "02_": ("pipeline/1_extraccion", None),
    "03_": ("pipeline/1_extraccion", None),
    "12_": ("pipeline/1_extraccion", None),
    "13_": ("pipeline/1_extraccion", None),
    "05b_": ("pipeline/2_consolidacion", "05_consolidar.py"),
    "07_": ("pipeline/2_consolidacion", None),
    "04_": ("pipeline/3_validacion", None),
    "06_": ("pipeline/3_validacion", None),
    "14_": ("pipeline/3_validacion", None),
    "15_": ("pipeline/3_validacion", None),
    "10_": ("pipeline/4_analisis", None),
    "11_": ("pipeline/4_analisis", None),
    "11b_": ("pipeline/4_analisis", None),
    "16_": ("pipeline/4_analisis", None),
    "17_": ("pipeline/4_analisis", None),
    "18_": ("pipeline/4_analisis", None),
    "19_": ("pipeline/4_analisis", None),
    "20_": ("pipeline/4_analisis", None),
    "21_": ("pipeline/5_informe", None),
    # reemplazados o de una sola vez
    "00_": ("archivo", None),
    "05_": ("archivo", None),          # 05_transformar (reemplazado por 05b)
    "08_": ("archivo", None),
    "09_": ("archivo", None),
}

RX_IMPORT = re.compile(
    r"^(\s*)(from|import)\s+(" + "|".join(COMPARTIDOS) + r")\b", re.M)

PYPROJECT = """\
[project]
name = "dipres-analytics"
version = "0.1.0"
description = "Auditoría de datos de ejecución presupuestaria del Gobierno Central de Chile"
requires-python = ">=3.11"
dependencies = ["pandas", "numpy", "requests", "scipy", "matplotlib"]

[tool.setuptools]
packages = ["dipres"]
"""


def destino(nombre: str) -> tuple[str, str] | None:
    # el prefijo más largo gana (05b_ antes que 05_, 11b_ antes que 11_)
    for pref in sorted(ETAPAS, key=len, reverse=True):
        if nombre.startswith(pref):
            carpeta, nuevo = ETAPAS[pref]
            return carpeta, nuevo or nombre
    return None


def plan() -> tuple[list, list]:
    movs, desconocidos = [], []
    for f in sorted(ORIGEN.glob("*.py")):
        stem = f.stem
        if stem in COMPARTIDOS:
            movs.append((f, RAIZ / "dipres" / f.name))
        elif (d := destino(f.name)) is not None:
            movs.append((f, RAIZ / d[0] / d[1]))
        else:
            desconocidos.append(f)
    arch = ORIGEN / "_archivo"
    if arch.exists():
        for f in sorted(arch.iterdir()):
            movs.append((f, RAIZ / "archivo" / f.name))
    return movs, desconocidos


def git(*args):
    subprocess.run(["git", *args], cwd=RAIZ, check=True)


def reescribir_imports(ruta: Path) -> int:
    txt = ruta.read_bytes().decode("utf-8")
    nuevo, n = RX_IMPORT.subn(
        lambda m: f"{m.group(1)}{m.group(2)} dipres.{m.group(3)}"
        if m.group(2) == "from"
        else f"{m.group(1)}from dipres import {m.group(3)}", txt)
    if n:
        ruta.write_bytes(nuevo.encode("utf-8"))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    if not ORIGEN.exists():
        sys.exit(f"No existe {ORIGEN}: ¿ya se reorganizó?")
    movs, desconocidos = plan()

    print("PLAN\n")
    for a, b in movs:
        print(f"  {a.relative_to(RAIZ)!s:<45} → {b.relative_to(RAIZ)}")
    if desconocidos:
        print("\nNo reconocidos (quedan en scripts/, decidir a mano):")
        for f in desconocidos:
            print(f"  {f.relative_to(RAIZ)}")

    if not args.aplicar:
        print("\nNada cambió. Para ejecutar: python reorganizar.py --aplicar")
        return

    estado = subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ,
                            capture_output=True, text=True).stdout.strip()
    if estado:
        sys.exit("\nHay cambios sin commit. Haz commit antes de reorganizar.")

    for a, b in movs:
        b.parent.mkdir(parents=True, exist_ok=True)
        git("mv", str(a), str(b))

    # Paquete y config
    init = RAIZ / "dipres" / "__init__.py"
    init.write_text('"""Módulos compartidos del pipeline DIPRES."""\n',
                    encoding="utf-8", newline="\r\n")
    (RAIZ / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8",
                                         newline="\r\n")
    cfg = RAIZ / "dipres" / "config.py"
    txt = cfg.read_bytes().decode("utf-8")
    txt = txt.replace('REPO_DIR / "scripts"', 'REPO_DIR / "pipeline"')
    txt = txt.replace("repo/scripts/config.py", "repo/dipres/config.py")
    cfg.write_bytes(txt.encode("utf-8"))

    total = 0
    for carpeta in ("dipres", "pipeline", "exploracion"):
        for f in (RAIZ / carpeta).rglob("*.py"):
            total += reescribir_imports(f)
    git("add", "-A", "dipres", "pipeline", "exploracion", "archivo",
        "pyproject.toml")

    print(f"\nListo: {len(movs)} archivos movidos, {total} imports reescritos.")
    print("Siguiente:")
    print("  pip install -e .            # una vez: deja 'dipres' importable")
    print("  python run.py --lista       # ver las etapas")
    print("  python run.py --desde validacion")


if __name__ == "__main__":
    main()