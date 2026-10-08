import pandas as pd

def leer_csv_robusto(ruta, nrows=None):
    import pandas as pd

    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    separadores = [";", ",", "\t"]

    with open(ruta, "rb") as f:
        muestra = f.read(8192)

    for enc in encodings:
        # errors="ignore" evita que un carácter cortado al final
        # de la muestra descarte un encoding válido
        texto = muestra.decode(enc, errors="ignore")

        if any(m in texto for m in ("Ã±", "Ã³", "Ã­", "Ã¡", "Ã©", "ï»¿", "Â")):
            continue

        primera_linea = texto.split("\n")[0].strip()
        mejor_sep = max(separadores, key=lambda s: primera_linea.count(s))
        if primera_linea.count(mejor_sep) < 1:
            continue

        try:
            df = pd.read_csv(
                ruta,
                encoding=enc,
                sep=mejor_sep,
                index_col=False,
                on_bad_lines="skip",
                nrows=nrows,
                low_memory=False,
            )
            if len(df.columns) > 2:
                return df, {"encoding": enc, "separador": mejor_sep}
        except Exception:
            continue

    raise ValueError(f"No se pudo leer: {ruta}")