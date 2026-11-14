"""16_modificaciones.prueba_art4 (MOD-2): cuándo un aumento de gasto se apega
al art. 4, se explica por excepciones medibles o requiere respaldo legal."""

import pandas as pd
import pytest

from conftest import cargar

m = cargar("pipeline/4_analisis/16_modificaciones.py")


def nacional(filas):
    """filas: [(subtitulo, inicial, vigente)] de un año-moneda completo."""
    return pd.DataFrame([{"anio": 2023, "moneda": "PESOS", "subtitulo": s,
                          "ley_inicial": i, "ley_vigente": v, "anio_completo": True}
                         for s, i, v in filas])


def partidas(filas):
    """filas: [(partida, subtitulo, inicial, vigente)]."""
    return pd.DataFrame([{"anio": 2023, "moneda": "PESOS", "partida": p, "subtitulo": s,
                          "ley_inicial": i, "ley_vigente": v} for p, s, i, v in filas],
                        columns=["anio", "moneda", "partida", "subtitulo",
                                 "ley_inicial", "ley_vigente"])


SIN_OC = pd.DataFrame(columns=["anio", "moneda", "delta"])


def fila(n, p, oc=SIN_OC):
    r = m.prueba_art4(n, p, oc)
    assert len(r) == 1
    return r.iloc[0]


def test_sin_aumento_se_apega():
    r = fila(nacional([(22, 1000, 1000), (31, 500, 500)]), partidas([]))
    assert r.estado_inc1 == "se apega" and r.estado_inc3 == "se apega"


def test_aumento_corriente_sin_excepciones_requiere_respaldo():
    r = fila(nacional([(22, 1000, 1100)]), partidas([]))
    assert r.corriente_exceso == 100
    assert r.estado_inc1 == "requiere respaldo legal"


def test_aumento_cubierto_por_caja_de_una_partida():
    p = partidas([(9, 15, 0, 100)])
    r = fila(nacional([(22, 1000, 1100)]), p)
    assert r.estado_inc1 == "explicable por excepciones medibles"


def test_la_caja_del_tesoro_no_cuenta_como_excepcion():
    p = partidas([(m.TESORO, 15, 0, 100)])
    r = fila(nacional([(22, 1000, 1100)]), p)
    assert r.exc_caja_sin_tesoro == 0
    assert r.estado_inc1 == "requiere respaldo legal"


def test_venta_de_activos_suma_solo_aumentos_por_partida():
    # El neto nacional (+100 − 100 = 0) escondería la fuente: se suman aumentos
    p = partidas([(7, 11, 0, 100), (m.TESORO, 11, 100, 0)])
    r = fila(nacional([(22, 1000, 1100)]), p)
    assert r.exc_venta_act_financieros == 100
    assert r.estado_inc1 == "explicable por excepciones medibles"


def test_ingresos_propios_sin_tesoro():
    p = partidas([(12, 7, 0, 60), (12, 8, 0, 40), (m.TESORO, 8, 0, 500)])
    r = fila(nacional([(22, 1000, 1100)]), p)
    assert r.exc_ingresos_propios == 100


def test_capital_tolera_el_margen_de_la_ley():
    # Inversión: se apega mientras el aumento no pase el margen sobre la inicial
    dentro = 1000 * (1 + m.ART4_MARGEN_CAPITAL)
    r = fila(nacional([(31, 1000, dentro)]), partidas([]))
    assert r.estado_inc3 == "se apega"
    r = fila(nacional([(31, 1000, dentro + 50)]), partidas([]))
    assert r.capital_exceso == pytest.approx(50)
    assert r.estado_inc3 == "requiere respaldo legal"
