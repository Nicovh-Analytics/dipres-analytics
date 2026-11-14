"""
Configuración común de los tests.

Los tests no usan datos reales: DIPRES_HOME apunta a una carpeta temporal
(dipres.config crea sus subcarpetas al importarse) y cada test arma sus
tablas de juguete. Así corren igual en local y en GitHub Actions.

Los scripts del pipeline tienen nombres que empiezan con número
(16_modificaciones.py) y no se pueden importar con `import`: `cargar`
los importa por ruta, sin ejecutar su main.
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
os.environ.setdefault("DIPRES_HOME", tempfile.mkdtemp(prefix="dipres_test_"))
sys.path.insert(0, str(RAIZ))


def cargar(ruta_relativa: str):
    """Importa un script del repo por su ruta (p. ej. 'pipeline/4_analisis/16_modificaciones.py')."""
    ruta = RAIZ / ruta_relativa
    nombre = "m_" + ruta.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
