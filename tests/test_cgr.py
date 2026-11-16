"""15c_conciliar_cgr (VAL-2): la descomposición de la diferencia con la CGR.
El caso de RREE fija el error que ya ocurrió una vez: un subtítulo que solo
tiene la CGR no puede desaparecer de las sumas como NaN."""

import pandas as pd
import pytest

from conftest import cargar

m = cargar("pipeline/3_validacion/15c_conciliar_cgr.py")


def cgr(filas, perimetro=False):
    """filas: (subt, bruto, eliminado) de un caso 2017/PESOS/partida 6."""
    return pd.DataFrame([{"anio": 2017, "moneda": "PESOS", "partida": 6, "subt": s,
                          "cgr_bruto": b, "cgr_tr": t, "cgr_neto": b - t,
                          "perimetro": perimetro} for s, b, t in filas])


def dataset(filas):
    """filas: (subt, bruto, neto)."""
    return pd.DataFrame([{"anio": 2017, "moneda": "PESOS", "partida": 6, "subt": s,
                          "ds_bruto": b, "ds_neto": n} for s, b, n in filas])


def fila(c, d):
    t = m.descomponer(c, d)
    assert len(t) == 1
    return t.iloc[0]


def test_subtitulo_30_que_el_dataset_no_tiene():
    r = fila(cgr([(21, 100, 0), (30, 50, 0)]), dataset([(21, 100, 100)]))
    assert r.diferencia == -50 and r.subt30_sin_registro == -50
    assert r.otros_subtitulos == 0


def test_subtitulo_32_con_signo_contrario():
    r = fila(cgr([(32, 70, 0)]), dataset([(32, -60, -60)]))
    assert r.subt32_prestamos == -130 and r.diferencia == -130


def test_dipres_elimina_mas_transferencias():
    r = fila(cgr([(24, 1000, 800)]), dataset([(24, 1000, 150)]))
    assert r.transferencias == -50 and r.diferencia == -50


def test_los_componentes_suman_la_diferencia():
    r = fila(cgr([(21, 100, 0), (24, 1000, 800), (30, 5, 0), (32, 7, 0)]),
             dataset([(21, 90, 90), (24, 1000, 150), (32, -3, -3)]))
    suma = sum(r[c] for c in m.COMPONENTES)
    assert suma == pytest.approx(r.diferencia)
    assert r.otros_subtitulos == -10
