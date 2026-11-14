"""dominio.py: cada hecho del clasificador vive en un solo lugar; estos tests
fijan los que sostienen hallazgos (perímetro de ingresos, conversión a pesos)."""

import pandas as pd
import pytest

from dipres import dominio


def test_ingresos_y_gastos_no_se_solapan():
    assert not set(dominio.SUBTITULOS_INGRESO) & set(dominio.SUBTITULOS_GASTO)
    assert dominio.tipo_flujo(1) == "Ingreso"
    assert dominio.tipo_flujo(22) == "Gasto"
    assert dominio.tipo_flujo(18) == "Desconocido"


@pytest.mark.parametrize("subt", [1, 5, 7, 8])
def test_ingresos_del_perimetro_fmi(subt):
    assert dominio.es_ingreso_gfs(subt)


@pytest.mark.parametrize("subt", [11, 12, 14])
def test_financiamiento_fuera_del_perimetro(subt):
    # ING-1: venta de activos financieros y endeudamiento no son ingreso
    assert not dominio.es_ingreso_gfs(subt)


def test_a_pesos_no_toca_las_filas_en_pesos():
    df = pd.DataFrame({"Año": [2024], "Moneda": ["PESOS"], "monto": [100.0]})
    out = dominio.a_pesos(df, ["monto"], "supuesto")
    assert out.monto.iloc[0] == 100.0 and out.tc.iloc[0] == 1.0


def test_a_pesos_convierte_dolares_con_el_tipo_de_cambio_del_anio():
    anio = next(iter(dominio.TC_SUPUESTO))
    df = pd.DataFrame({"Año": [anio], "Moneda": ["DOLARES"], "monto": [2.0]})
    out = dominio.a_pesos(df, ["monto"], "supuesto")
    assert out.monto.iloc[0] == pytest.approx(2.0 * dominio.TC_SUPUESTO[anio])


def test_tipo_de_cambio_faltante_falla_con_mensaje():
    with pytest.raises(KeyError, match="Falta el tipo de cambio"):
        dominio.tipo_cambio(1900, "supuesto")
