import pandas as pd
from config import DIRS
c = pd.read_csv(DIRS["consolidado"] / "ley_capitulo.csv", low_memory=False)
x = c[(c.Año == 2025) & (c.Moneda == "PESOS") & (
      ((c.Partida == 5) & c.Capítulo.isin([31, 33])) | ((c.Partida == 32) & c.Capítulo.isin([3, 5])))]
print(x.groupby(["Mes", "Partida", "Capítulo"], sort=False)["ley_vigente"].sum().unstack([1, 2]).to_string())