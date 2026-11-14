"""Origen de los datos: el manifiesto encuentra la URL de cada archivo aunque
los logs se hayan escrito antes de mover los datos, y la descarga del
monitoreo no confunde las bases con los libros de códigos de CASEN."""

import pytest

from conftest import cargar

man = cargar("herramientas/manifiesto.py")
mon = cargar("pipeline/1_extraccion/03b_descargar_monitoreo.py")


def test_ruta_con_carpeta_raw(tmp_path):
    clave = r"D:\data\dipres-datos\raw\ley\2024\01\Ley.csv"
    assert man.relativa_a_raw(clave, tmp_path) == "ley/2024/01/ley.csv"


def test_ruta_anterior_a_la_migracion(tmp_path):
    # Logs escritos cuando los datos vivían en D:\dipres-datos\ejecucion\...
    (tmp_path / "ejecucion" / "2017").mkdir(parents=True)
    (tmp_path / "ejecucion" / "2017" / "ene.csv").write_text("x")
    clave = r"D:\dipres-datos\ejecucion\2017\ene.csv"
    assert man.relativa_a_raw(clave, tmp_path) == "ejecucion/2017/ene.csv"


def test_ruta_que_no_existe_bajo_raw(tmp_path):
    assert man.relativa_a_raw(r"C:\otra\cosa.csv", tmp_path) is None


def test_origen_prefiere_el_log_y_luego_el_registro():
    urls = {"ejecucion/2017/ene.csv": "https://datos.gob.cl/x"}
    fuentes = [("externo/cgr/IGFE *.pdf", "https://www.contraloria.cl/web/cgr/igfe")]
    assert man.origen("ejecucion/2017/ene.csv", urls, fuentes) == ("https://datos.gob.cl/x", "log")
    assert man.origen("externo/cgr/IGFE 2017.pdf", urls, fuentes)[1] == "registro"
    assert man.origen("raro/x.txt", urls, fuentes) == ("", "")


@pytest.mark.parametrize("titulo, recurso, url, esperado", [
    ("Base de datos CASEN 2022", "Libro de códigos base de datos Casen 2022",
     "x/libro.xlsx", None),
    ("Proceso de monitoreo de programas públicos 2022",
     "Base monitoreo 2022 - Oferta pública (SES-DIPRES)", "x/b.xlsx", ("base", 2022, "xlsx")),
    ("Proceso de monitoreo de programas públicos 2023", "Base",
     "x/20240730_bips-base.xlsx", ("base", 2023, "xlsx")),
    ("Proceso de monitoreo de programas públicos 2024", "Diccionario 2024",
     "x/dic.csv", ("diccionario", 2024, "csv")),
])
def test_seleccion_de_recursos_del_monitoreo(titulo, recurso, url, esperado):
    ds = {"title": titulo}
    rec = {"name": recurso, "format": url.rsplit(".", 1)[1].upper(), "url": url}
    assert mon.clasificar(ds, rec) == esperado
