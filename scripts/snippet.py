import pandas as pd
from config import DIRS
cols = ["Año", "Mes", "Moneda", "Partida", "Capítulo", "Programa", "Subtítulo", "Item",
        "Asignación", "Nombre Capítulo", "Nombre Item", "Nombre Asignación", "ley_inicial"]
p = pd.read_csv(DIRS["consolidado"] / "ley_programa.csv", low_memory=False,
                usecols=lambda c: c in cols)
x = p[(p.Año == 2020) & (p.Mes == "Enero") & (p.Moneda == "PESOS")
      & p.Subtítulo.isin([12, 32]) & (p.ley_inicial > 0)]
s32 = x[x.Subtítulo == 32]; s12 = x[x.Subtítulo == 12]
comunes = set(s32.ley_inicial) & set(s12.ley_inicial)
m = x[x.ley_inicial.isin(comunes)].sort_values(["ley_inicial", "Subtítulo"])
print(m[["Subtítulo", "Partida", "Capítulo", "Item", "Asignación", "Nombre Capítulo",
         "Nombre Asignación", "ley_inicial"]].to_string())
print("\nsuma de montos comunes:", sum(comunes), "· objetivo: 60,273,744")