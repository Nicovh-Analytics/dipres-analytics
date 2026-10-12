"""
utils.py — Lectura robusta de CSV
==================================
Detecta encoding y separador con los parámetros de config.IO.

Las filas mal formadas ya no se descartan en silencio: se cuentan y se
avisa. Con estricto=True se aborta (útil para los consolidados, que no
deberían traer ninguna).
"""

import re
import warnings

import pandas as pd

from config import IO

_RX_SALTO = re.compile(r"Skipping line \d+")


def leer_csv_robusto(ruta, nrows=None, estricto=False, **kwargs):
    """(DataFrame, {"encoding", "separador", "filas_descartadas"}).

    kwargs se pasan a pd.read_csv (p. ej. usecols, dtype)."""
    with open(ruta, "rb") as f:
        muestra = f.read(IO["bytes_muestra"])

    for enc in IO["encodings"]:
        # errors="ignore": un carácter cortado al final de la muestra no
        # debe descartar un encoding válido
        texto = muestra.decode(enc, errors="ignore")
        if any(m in texto for m in IO["marcadores_mojibake"]):
            continue

        primera = texto.split("\n")[0].strip()
        sep = max(IO["separadores"], key=primera.count)
        if primera.count(sep) < 1:
            continue

        try:
            with warnings.catch_warnings(record=True) as avisos:
                warnings.simplefilter("always", pd.errors.ParserWarning)
                df = pd.read_csv(ruta, encoding=enc, sep=sep, index_col=False,
                                 on_bad_lines="error" if estricto else "warn",
                                 nrows=nrows, low_memory=False, **kwargs)
        except UnicodeDecodeError:
            continue
        except pd.errors.ParserError as e:
            if estricto:
                raise ValueError(f"{ruta}: fila mal formada ({e})") from e
            continue

        if len(df.columns) <= 2:
            continue

        descartadas = sum(len(_RX_SALTO.findall(str(a.message)))
                          for a in avisos
                          if issubclass(a.category, pd.errors.ParserWarning))
        if descartadas:
            print(f"  ⚠ {ruta}: {descartadas:,} filas mal formadas descartadas")
        return df, {"encoding": enc, "separador": sep,
                    "filas_descartadas": descartadas}

    raise ValueError(f"No se pudo leer: {ruta}")