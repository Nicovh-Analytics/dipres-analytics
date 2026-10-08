"""
00_migrar_estructura.py — Reorganiza el proyecto
=================================================
Separa código (repo Git) de datos (fuera de Git).

ANTES                          DESPUÉS
D:\\dipres-datos\\              D:\\proyectos\\dipres-analytics\\   ← Git
  .py\\                           scripts\\
  ejecucion\\                   D:\\dipres-datos\\                 ← datos
  ley\\                           raw\\ejecucion\\  ley\\  inversion\\  normativa\\
  inversion\\                     processed\\consolidado\\  clean\\
  Normativa\\                     reports\\
  consolidado\\                   logs\\
  clean\\                         exploracion\\
  dipres-datos-clean\\  → descartada (versión antigua)
  reportes\\
  exploracion\\
  _log_*.json

Ejecutar primero en seco para revisar el plan:
    python 00_migrar_estructura.py
Y luego aplicar:
    python 00_migrar_estructura.py --aplicar
"""

import argparse
import shutil
from pathlib import Path

ORIGEN = Path(r"D:\dipres-datos")
REPO = Path(r"D:\proyectos\dipres-analytics")
DATOS = Path(r"D:\dipres-datos")

# (origen, destino, tipo)
#   mover  → cambia de lugar
#   copiar → se duplica (código: queda respaldo del original)
PLAN = [
    # ── Código al repo ──
    (ORIGEN / ".py",          REPO / "scripts",                "copiar"),

    # ── Datos crudos: inmutables, nunca se regeneran ──
    (ORIGEN / "ejecucion",    DATOS / "raw" / "ejecucion",     "mover"),
    (ORIGEN / "ley",          DATOS / "raw" / "ley",           "mover"),
    (ORIGEN / "inversion",    DATOS / "raw" / "inversion",     "mover"),
    (ORIGEN / "Normativa",    DATOS / "raw" / "normativa",     "mover"),

    # ── Derivados: se pueden regenerar corriendo el pipeline ──
    (ORIGEN / "consolidado",  DATOS / "processed" / "consolidado", "mover"),
    (ORIGEN / "clean",        DATOS / "processed" / "clean",       "mover"),

    # ── Salidas y metadata ──
    (ORIGEN / "reportes",     DATOS / "reports",               "mover"),
    (ORIGEN / "exploracion",  DATOS / "exploracion",           "mover"),
]

# Archivos sueltos de la raíz → logs/
LOGS = ["_log_descarga.json", "_log_inversion.json",
        "_datasets_encontrados.json", "_catalogo_no_procesado.json"]

# Carpeta obsoleta: versión anterior de `clean`
DESCARTAR = [ORIGEN / "dipres-datos-clean"]


def tamano(p: Path) -> str:
    if not p.exists():
        return "—"
    if p.is_file():
        return f"{p.stat().st_size / 1e6:.1f} MB"
    total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    n = sum(1 for f in p.rglob("*") if f.is_file())
    return f"{total / 1e6:.1f} MB · {n:,} archivos"


def main(aplicar: bool):
    modo = "APLICANDO" if aplicar else "SIMULACIÓN (usar --aplicar para ejecutar)"
    print("=" * 72)
    print(f"  MIGRACIÓN DE ESTRUCTURA — {modo}")
    print("=" * 72)

    print(f"\n  Repo:  {REPO}")
    print(f"  Datos: {DATOS}\n")

    for origen, destino, tipo in PLAN:
        if not origen.exists():
            print(f"  ⊘ {origen.name:<18} no existe, se omite")
            continue
        if destino.exists():
            print(f"  ⊘ {origen.name:<18} destino ya existe, se omite")
            continue

        print(f"  {tipo:<6} {origen.name:<18} → {destino.relative_to(destino.anchor)}")
        print(f"         {tamano(origen)}")

        if aplicar:
            destino.parent.mkdir(parents=True, exist_ok=True)
            if tipo == "mover":
                shutil.move(str(origen), str(destino))
            else:
                shutil.copytree(origen, destino)

    # ── Logs ──
    print(f"\n  logs → {DATOS / 'logs'}")
    for nombre in LOGS:
        f = ORIGEN / nombre
        if not f.exists():
            continue
        print(f"    {nombre:<32} {tamano(f)}")
        if aplicar:
            (DATOS / "logs").mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(DATOS / "logs" / nombre))

    # ── Obsoletos ──
    print(f"\n  Obsoleto (NO se borra — revisar y eliminar a mano):")
    for p in DESCARTAR:
        if p.exists():
            print(f"    {p}  →  {tamano(p)}")

    # ── Esqueleto del repo ──
    if aplicar:
        for sub in ("docs", "notebooks"):
            (REPO / sub).mkdir(parents=True, exist_ok=True)
        print(f"\n  Creadas: {REPO / 'docs'}, {REPO / 'notebooks'}")

    print(f"\n{'─' * 72}")
    print("  Pasos siguientes:")
    print("    1. Actualizar DIRS en scripts/config.py (ver abajo)")
    print("    2. Verificar que el pipeline corre con la nueva estructura")
    print("    3. Borrar D:\\dipres-datos\\.py y dipres-datos-clean")
    print("    4. git init en el repo")

    if not aplicar:
        print(f"\n  Nada se modificó. Correr con --aplicar para ejecutar.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(ap.parse_args().aplicar)