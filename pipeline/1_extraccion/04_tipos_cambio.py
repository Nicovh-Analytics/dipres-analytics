"""
04_tipos_cambio.py — Dólar, euro y UF diarios (Banco Central vía mindicador.cl)
================================================================================
Descarga las series diarias del dólar observado, el euro y la UF, todas en
pesos, desde mindicador.cl (que replica las del Banco Central de Chile), y
guarda la serie diaria y los promedios anuales.

Las usan los cruces que convierten monedas: 18c_cruce_bonos.py pasa los
bonos en UF a pesos y los bonos en euros a dólares con el promedio del
periodo de cada emisión.

Control: el dólar promedio anual se compara con dominio.TC_OBSERVADO, que
se cargó a mano desde la BDE del Banco Central. Si difieren más de 0,1%, se
avisa (son la misma serie, así que no debería pasar).

Salidas en raw/externo/tipo_cambio/:
  diario.csv   fecha, indicador, valor     (pesos por unidad)
  anual.csv    anio, dolar, euro, uf       (promedio del año)

Uso:
    python pipeline/1_extraccion/04_tipos_cambio.py              # 2016 a hoy
    python pipeline/1_extraccion/04_tipos_cambio.py --desde 2020
"""

import argparse
import time
from datetime import date

import pandas as pd
import requests

from dipres.config import DIRS
from dipres.dominio import TC_OBSERVADO

URL = "https://mindicador.cl/api/{indicador}/{anio}"
INDICADORES = ["dolar", "euro", "uf"]
SALIDA = DIRS.get("externo", DIRS["raw"] / "externo") / "tipo_cambio"
TOL_PCT = 0.1


def descargar(sesion: requests.Session, indicador: str, anio: int,
              intentos: int = 3) -> pd.DataFrame:
    for i in range(intentos):
        try:
            r = sesion.get(URL.format(indicador=indicador, anio=anio),
                           timeout=30)
            r.raise_for_status()
            serie = r.json().get("serie", [])
            if not serie:
                raise ValueError("serie vacía")
            d = pd.DataFrame(serie)
            # La API entrega UTC (2024-12-31T03:00:00Z = 31-12 en Chile)
            d["fecha"] = (pd.to_datetime(d.fecha, utc=True)
                            .dt.tz_convert("America/Santiago").dt.date)
            d["indicador"] = indicador
            return d[["fecha", "indicador", "valor"]]
        except (requests.RequestException, ValueError) as e:
            if i == intentos - 1:
                raise RuntimeError(f"{indicador} {anio}: {e}") from e
            time.sleep(2 * (i + 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=2016)
    ap.add_argument("--hasta", type=int, default=date.today().year)
    args = ap.parse_args()

    print("=" * 78)
    print("  TIPOS DE CAMBIO (mindicador.cl, series del Banco Central)")
    print("=" * 78)
    SALIDA.mkdir(parents=True, exist_ok=True)
    partes = []
    with requests.Session() as s:
        for anio in range(args.desde, args.hasta + 1):
            for ind in INDICADORES:
                partes.append(descargar(s, ind, anio))
                time.sleep(0.3)
            print(f"  {anio}: listo")
    diario = (pd.concat(partes, ignore_index=True)
                .drop_duplicates(["fecha", "indicador"])
                .sort_values(["indicador", "fecha"]))
    anual = (diario.assign(anio=pd.to_datetime(diario.fecha).dt.year)
                   .pivot_table(index="anio", columns="indicador",
                                values="valor", aggfunc="mean")
                   [INDICADORES].round(2).reset_index())

    print("\n  Control: dólar promedio anual vs dominio.TC_OBSERVADO")
    for r in anual.itertuples():
        ref = TC_OBSERVADO.get(r.anio)
        if ref is None:
            continue
        dif = (r.dolar / ref - 1) * 100
        marca = "✓" if abs(dif) <= TOL_PCT else "⚠"
        print(f"    {marca} {r.anio}: {r.dolar:,.2f} vs {ref:,.2f} ({dif:+.2f}%)")

    diario.to_csv(SALIDA / "diario.csv", index=False, encoding="utf-8-sig")
    anual.to_csv(SALIDA / "anual.csv", index=False, encoding="utf-8-sig")
    print(f"\n  Salida: {SALIDA / 'diario.csv'}")
    print(f"          {SALIDA / 'anual.csv'}")


if __name__ == "__main__":
    main()
