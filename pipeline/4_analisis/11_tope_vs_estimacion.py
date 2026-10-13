"""
11_tope_vs_estimacion.py — ¿ley_inicial es pronóstico o autorización?
======================================================================
Hipótesis: la columna ley_inicial no significa lo mismo en todos los
subtítulos. En Impuestos sería un pronóstico; en Endeudamiento, un tope
de autorización legislativa.

Prueba: comparar los tres momentos por subtítulo.

  inicial  → lo aprobado en noviembre del año anterior
  vigente  → lo autorizado tras modificaciones del año
  ejecutado→ lo efectivamente ocurrido

Patrón esperado si es PRONÓSTICO:
    el vigente se mueve poco; el ejecutado oscila alrededor del inicial

Patrón esperado si es TOPE:
    el vigente se amplía cuando hace falta; el ejecutado queda
    sistemáticamente POR DEBAJO del vigente (no se agota el permiso)

Cada moneda se analiza por separado y en su propia unidad (los ratios
no necesitan tipo de cambio). Además se agrega un bloque TOTAL con los
dólares convertidos al observado del año: el tope de endeudamiento del
Art. 3 se fija en dólares para el total, no por moneda del subtítulo 14,
así que el corte por moneda solo no basta. Antes se sumaban pesos y
dólares sin convertir, lo que distorsionaba los ratios.

Uso:
    python 11_tope_vs_estimacion.py
"""

import pandas as pd

from dipres.config import DIRS
from dipres.dominio import MES_A_NUM, a_pesos, naturaleza_ley, nombre_subtitulo
from dipres.utils import leer_csv_robusto

ANIO_EN_CURSO = 2026

# Uno de pronóstico (01), propiedad (06), los de financiamiento
# (11, 12, 14) y gastos de referencia (21, 29)
FOCO = [1, 6, 11, 12, 14, 21, 29]

# Años mínimos con dato para dar lectura automática
MIN_ANIOS = 3


def cargar_cierres() -> pd.DataFrame:
    df, _ = leer_csv_robusto(str(DIRS["consolidado"] / "cruce_nacional.csv"))
    df = df[df["Año"] < ANIO_EN_CURSO].copy()
    df["MesNum"] = df["Mes"].map(MES_A_NUM)
    df["Sub"] = df["Subtítulo"].astype(int)
    df["Moneda"] = df["Moneda"].str.upper()
    idx = df.groupby("Año")["MesNum"].transform("max") == df["MesNum"]
    return df[idx].copy()


def lectura(d: pd.DataFrame) -> str:
    """Clasificación empírica con medianas (robustas a años extremos).

    TOPE        uso mediano < 95% y se excede el vigente a lo más 1 año
    AJUSTADO    uso mediano 98-102% con ampliación mediana > 2%: el vigente
                se modifica hasta calzar con lo ejecutado
    PRONÓSTICO  la ejecución excede el vigente la mitad de los años o más,
                o el error vs inicial cambia de signo (≥2 años de cada uno)
                con un vigente que casi no se mueve
    """
    if len(d) < MIN_ANIOS:
        return "pocos años"
    uso = d["uso_del_permiso"].median()
    amp = d["ampliacion"].median()
    excede = int((d["ejec"] > d["vigente"]).sum())
    sobre = int((d["vs_inicial"] > 0).sum())
    bajo = int((d["vs_inicial"] < 0).sum())
    if uso < 95 and excede <= 1:
        return "TOPE"
    if 98 <= uso <= 102 and amp > 2:
        return "AJUSTADO"
    if excede >= len(d) / 2 or (min(sobre, bajo) >= 2 and abs(amp) < 5):
        return "PRONÓSTICO"
    return "ambiguo"


if __name__ == "__main__":
    c = cargar_cierres()
    c = c[c["Sub"].isin(FOCO)]
    monedas = ["PESOS", "DOLARES"]
    try:
        t = a_pesos(c, ["ley_inicial", "ley_vigente", "ejecucion_acumulada"],
                    "observado")
        c = pd.concat([c, t.drop(columns="tc").assign(Moneda="TOTAL")])
        monedas.append("TOTAL")
    except KeyError as e:
        print(f"  {e.args[0]} — se omite el bloque TOTAL\n")

    g = (c
         .groupby(["Moneda", "Sub", "Año"])
         .agg(inicial=("ley_inicial", "sum"),
              vigente=("ley_vigente", "sum"),
              ejec=("ejecucion_acumulada", "sum"))
         .reset_index())
    # Combinación moneda-subtítulo sin ley ni ejecución en el año: fuera
    g = g[(g[["inicial", "vigente", "ejec"]] != 0).any(axis=1)]

    ini = g["inicial"].abs().replace(0, pd.NA)
    g["ampliacion"] = (g["vigente"] - g["inicial"]) / ini * 100
    g["uso_del_permiso"] = g["ejec"] / g["vigente"].replace(0, pd.NA) * 100
    g["vs_inicial"] = (g["ejec"] - g["inicial"]) / ini * 100

    print("=" * 76)
    print("  ¿ley_inicial es pronóstico o tope de autorización?")
    print("=" * 76)

    # Moneda sobre la que se da la lectura: TOTAL si hay tipo de cambio
    base = "TOTAL" if "TOTAL" in monedas else None
    resumen = []
    for moneda in monedas:
        for sub in FOCO:
            d = g[(g["Moneda"] == moneda) & (g["Sub"] == sub)]
            if d.empty:
                continue

            print(f"\n{'─' * 76}")
            print(f"  {sub:02d} · {nombre_subtitulo(sub)} · {moneda}")
            print(f"{'─' * 76}")
            print(f"{'Año':>6}{'Ampliación':>14}{'Uso del':>12}{'Ejec vs':>12}")
            print(f"{'':>6}{'vig/ini':>14}{'permiso':>12}{'inicial':>12}")

            for _, r in d.iterrows():
                f = lambda v: f"{v:>11.1f}%" if pd.notna(v) else f"{'—':>12}"
                print(f"{int(r['Año']):>6}{f(r['ampliacion']):>14}"
                      f"{f(r['uso_del_permiso'])}{f(r['vs_inicial'])}")

            amp = d["ampliacion"].median()
            uso = d["uso_del_permiso"].median()
            excede = int((d["ejec"] > d["vigente"]).sum())
            # La lectura se hace sobre el total; las monedas sueltas son
            # detalle (líneas chicas dan porcentajes extremos)
            con_lectura = moneda == base
            lec = lectura(d) if con_lectura else ""

            print(f"\n  mediana: ampliación {amp:+.1f}% · uso del permiso {uso:.1f}%")
            print(f"  años en que la ejecución EXCEDE el vigente: {excede}/{len(d)}")
            if con_lectura:
                print(f"  → lectura: {lec}")

            resumen.append({"Moneda": moneda, "Subtítulo": sub,
                            "nombre": nombre_subtitulo(sub),
                            "naturaleza_dominio": naturaleza_ley(sub) or "GASTO",
                            "anios": len(d), "ampliacion_mediana": amp,
                            "uso_mediano": uso, "anios_excede": excede,
                            "lectura": lec})

    r = pd.DataFrame(resumen)
    if base is None:
        print("\n  Sin tipo de cambio: no hay bloque TOTAL ni lectura automática")

    # ── Resumen comparativo (solo la moneda con lectura) ──
    print(f"\n{'=' * 76}")
    print(f"  RESUMEN · {base or 'sin lectura'} (medianas)")
    print("=" * 76)
    print(f"\n{'Subtítulo':<38}{'Amplia':>9}{'Uso':>8}"
          f"{'Excede':>8}  {'Lectura':<11}{'Dominio':<12}")
    for _, x in r[r["Moneda"] == base].iterrows():
        print(f"{x['Subtítulo']:02d} {x['nombre'][:34]:<35}"
              f"{x['ampliacion_mediana']:>8.1f}%"
              f"{x['uso_mediano']:>7.1f}%"
              f"{x['anios_excede']:>4}/{x['anios']:<3}  "
              f"{x['lectura']:<11}{x['naturaleza_dominio']:<12}")

    print(f"\n  14 Endeudamiento: el tope legal es el del Art. 3 (en US$), que")
    print(f"     excluye la deuda amortizada en el mismo ejercicio; la ejecución")
    print(f"     bruta del subtítulo puede superarlo sin infringirlo.")
    print(f"\n  Amplia  = cuánto crece el vigente sobre el inicial")
    print(f"  Uso     = qué fracción del vigente se ejecuta")
    print(f"  Excede  = años en que la ejecución supera el vigente")
    print(f"  TOTAL   = pesos + dólares al dólar observado del año")
    print(f"  Dominio = naturaleza asignada en dominio.NATURALEZA_INGRESO,")
    print(f"            para contrastar con la lectura empírica")

    r.round(2).to_csv(DIRS["reportes"] / "tope_vs_estimacion.csv", index=False)