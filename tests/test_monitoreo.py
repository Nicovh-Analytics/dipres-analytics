"""24_monitoreo_programas (MON-1): lectura del código presupuestario que
declaran los programas y clasificación de cada línea contra DIPRES. Los
casos salen de la base 2018 real (Subvencionada, JUNJI, FOSIS, Chile Crece
Contigo)."""

import numpy as np
import pandas as pd
import pytest

from conftest import cargar

m = cargar("pipeline/4_analisis/24_monitoreo_programas.py")
nan = np.nan


@pytest.mark.parametrize("valor, sub, item, esperado", [
    (700.0, 24, 3, (3, 700, "ok")),                 # asignación sola
    (2301001.0, 23, nan, (1, 1, "ok")),             # subt + ítem + asignación
    (1009.0, 23, nan, (1, 9, "ok")),                # ítem + asignación
    ("24.03.700", 24, 3, (3, 700, "ok")),           # texto con puntos
    (22.0, 22, nan, (nan, nan, "ok")),              # el código del subtítulo
    (198004520.0, 21, nan, (nan, nan, "monto en el campo código")),  # FOSIS
    (5311097599.0, 24, 1, (1, nan, "monto en el campo código")),     # Subvencionada
])
def test_normalizar_codigo(valor, sub, item, esperado):
    r = m.normalizar_codigo(valor, sub, item)
    for a, b in zip(r, esperado):
        assert (pd.isna(a) and pd.isna(b)) or a == b


def ejecucion(filas):
    return pd.DataFrame(filas, columns=m.CLAVES + ["ejecucion_acumulada"])


def monitoreo(filas):
    """filas: (id, Partida, Capítulo, Programa, Subtítulo, Item, Asignación, gasto)."""
    return pd.DataFrame(filas, columns=["id_bips", "Partida", "Capítulo", "Programa",
                                        "Subtítulo", "Item", "Asignación",
                                        "gasto_monitoreo"]).assign(nombre="p")


E = ejecucion([
    (9, 1, 20, 24, 1, 255, 4686), (9, 1, 20, 24, 3, 398, 680),   # Subvencionada
    (21, 1, 6, 24, 2, 2, 14706),                                  # ChCC, ítem 02
    (21, 9, 1, 21, nan, nan, 85),                                 # FOSIS
])


def clase(*fila):
    return m.cruce_lineas(monitoreo([fila]), E).clase.iloc[0]


def test_linea_igual():
    assert clase(1, 9, 1, 20, 24, 1, 255, 4686) == "igual"


def test_subtitulo_completo_bajo_un_item_cabe_en_el_subtitulo():
    # Subvencionada: declara casi todo el subt. 24 bajo el ítem 01
    assert clase(1, 9, 1, 20, 24, 1, nan, 5301) == "excede el ítem, cabe en el subtítulo"


def test_misma_asignacion_en_otro_item():
    # Chile Crece Contigo: declara 24-03-002, DIPRES tiene 24-02-002
    assert clase(1, 21, 1, 6, 24, 3, 2, 15519) == "misma asignación en otro ítem"


def test_monto_que_excede_sin_explicacion():
    assert clase(1, 21, 9, 1, 21, nan, nan, 1980) == "monto excede DIPRES"


def test_programa_inexistente():
    assert clase(1, 9, 1, 12, 24, 3, 52, 100) == "programa inexistente en DIPRES"


def test_dos_programas_que_declaran_la_misma_asignacion_se_suman():
    ml = monitoreo([(1, 9, 1, 20, 24, 1, 255, 4686), (2, 9, 1, 20, 24, 1, 255, 4686)])
    r = m.cruce_lineas(ml, E).iloc[0]
    assert r.programas == 2 and r.clase == "suma de programas excede"
