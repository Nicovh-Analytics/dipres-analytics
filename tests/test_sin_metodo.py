"""25_sin_metodo: los cálculos "ingenuos" reproducen el error que dicen medir."""

import pandas as pd
import pytest

from conftest import cargar

m = cargar("pipeline/4_analisis/25_sin_metodo.py")


def test_sumar_el_acumulado_de_12_meses_da_6_5_veces():
    # Gasto parejo: el acumulado crece 100 por mes; la suma es 78/12 del anual
    df = pd.DataFrame({"Año": 2024, "mes": range(1, 13), "Moneda": "PESOS",
                       "Subtítulo": 21, "ejecucion_acumulada": [100.0 * k for k in range(1, 13)]})
    r = m.caso_acumulado(df)[0]
    assert r["ingenuo"] / r["metodo"] == pytest.approx(6.5)
    assert r["cambia_conclusion"]


def test_fila_marca_si_cambia_la_conclusion():
    assert m.fila("x", 2020, 109, 109, "%", "excede", "cabe en ley")["cambia_conclusion"]
    assert not m.fila("x", 2022, 75, 75, "%", "dentro", "dentro")["cambia_conclusion"]
