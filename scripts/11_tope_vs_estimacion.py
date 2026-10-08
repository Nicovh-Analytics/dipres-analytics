"""
11_tope_vs_estimacion.py — ¿ley_inicial es pronóstico o autorización?
======================================================================
Hipótesis del punto 8: la columna ley_inicial no significa lo mismo
en todos los subtítulos. En Impuestos sería un pronóstico; en
Endeudamiento, un tope de autorización legislativa.

Prueba: comparar los tres momentos por subtítulo.

  inicial  → lo aprobado en noviembre del año anterior
  vigente  → lo autorizado tras modificaciones del año
  ejecutado→ lo efectivamente ocurrido

Patrón esperado si es PRONÓSTICO:
    el vigente se mueve poco; el ejecutado oscila alrededor del inicial

Patrón esperado si es TOPE:
    el vigente se amplía cuando hace falta; el ejecutado queda
    sistemáticamente POR DEBAJO del vigente (no se agota el permiso)

Uso:
    python 11_tope_vs_estimacion.py
"""

import pandas as pd

from config import DIRS
from dominio import MES_A_NUM, nombre_subtitulo
from utils import leer_csv_robusto

ANIO_EN_CURSO = 2026

# Subtítulos a contrastar: uno claramente de pronóstico (01),
# los de financiamiento (11, 12, 14) y un gasto de referencia (21)
FOCO = [1, 6, 11, 12, 14, 21, 29]


def cargar_cierres() -> pd.DataFrame:
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_nacional.csv"))
    df = df[df["Año"] < ANIO_EN_CURSO].copy()
    df["MesNum"] = df["Mes"].map(MES_A_NUM)
    df["Sub"] = df["Subtítulo"].astype(int)
    idx = df.groupby("Año")["MesNum"].transform("max") == df["MesNum"]
    return df[idx].copy()


if __name__ == "__main__":
    c = cargar_cierres()

    g = (c[c["Sub"].isin(FOCO)]
         .groupby(["Sub", "Año"])
         .agg(inicial=("ley_inicial", "sum"),
              vigente=("ley_vigente", "sum"),
              ejec=("ejecucion_acumulada", "sum"))
         .reset_index())

    # Dos ratios que distinguen los dos regímenes
    g["ampliacion"] = (g["vigente"] - g["inicial"]) / g["inicial"].abs() * 100
    g["uso_del_permiso"] = g["ejec"] / g["vigente"].replace(0, pd.NA) * 100
    g["vs_inicial"] = (g["ejec"] - g["inicial"]) / g["inicial"].abs() * 100

    print("=" * 76)
    print("  ¿ley_inicial es pronóstico o tope de autorización?")
    print("=" * 76)

    for sub in FOCO:
        d = g[g["Sub"] == sub]
        if d.empty:
            continue

        print(f"\n{'─' * 76}")
        print(f"  {sub:02d} · {nombre_subtitulo(sub)}")
        print(f"{'─' * 76}")
        print(f"{'Año':>6}{'Ampliación':>14}{'Uso del':>12}{'Ejec vs':>12}")
        print(f"{'':>6}{'vig/ini':>14}{'permiso':>12}{'inicial':>12}")

        for _, r in d.iterrows():
            print(f"{int(r['Año']):>6}{r['ampliacion']:>13.1f}%"
                  f"{r['uso_del_permiso']:>11.1f}%{r['vs_inicial']:>11.1f}%")

        amp = d["ampliacion"].mean()
        uso = d["uso_del_permiso"].mean()
        excede = int((d["ejec"] > d["vigente"]).sum())

        print(f"\n  media: ampliación {amp:+.1f}% · uso del permiso {uso:.1f}%")
        print(f"  años en que la ejecución EXCEDE el vigente: {excede}/{len(d)}")

        # Lectura automática
        if uso < 95 and excede <= 1:
            print(f"  → compatible con TOPE: no se agota, casi nunca se excede")
        elif excede >= len(d) // 2:
            print(f"  → compatible con PRONÓSTICO: la ejecución excede el "
                  f"vigente con frecuencia")
        else:
            print(f"  → ambiguo")

    # ── Resumen comparativo ──
    print(f"\n{'=' * 76}")
    print("  RESUMEN")
    print("=" * 76)
    print(f"\n{'Subtítulo':<44}{'Amplia':>9}{'Uso':>9}{'Excede':>9}")
    for sub in FOCO:
        d = g[g["Sub"] == sub]
        if d.empty:
            continue
        excede = int((d["ejec"] > d["vigente"]).sum())
        print(f"{sub:02d} {nombre_subtitulo(sub)[:40]:<41}"
              f"{d['ampliacion'].mean():>8.1f}%"
              f"{d['uso_del_permiso'].mean():>8.1f}%"
              f"{excede:>6}/{len(d)}")

    print(f"\n  Amplia = cuánto crece el vigente sobre el inicial")
    print(f"  Uso    = qué fracción del vigente se ejecuta")
    print(f"  Excede = años en que la ejecución supera el vigente")