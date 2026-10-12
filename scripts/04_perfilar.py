"""
Profiler y Documentador de Hallazgos — CSVs DIPRES
===================================================
- Audita de forma aislada por Familia x Nivel sin saturar RAM.
- Distingue entre campos vacíos legítimos y delimitadores incrustados reales.
- Tolera delimitadores terminales espurios (ej: ley 2017).
- Genera reporte JSON (DIRS["reportes"]) y un documento Markdown versionable
  (DIRS["docs"]/HALLAZGOS_PROFILING.md).

Uso:
    python 04_perfilar.py
"""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from config import DIRS, IO
from dominio import NIVELES

FAMILIAS = ["ley", "ejecucion"]

# =====================================================
# 1. NORMALIZACIÓN UNIVERSAL DE ENCABEZADOS
# =====================================================
def limpiar_texto_general(texto: str) -> str:
    """Pasa a minúsculas, remueve espacios duplicados y quita tildes de forma universal."""
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"\s+", " ", texto)
    return texto

def canonizar_columna(col: str, familia: str) -> str:
    """Mapea nombres variables a una etiqueta semántica canónica."""
    c = limpiar_texto_general(col)

    if familia == "ley":
        if re.search(r"^monto\s+ley\s+vigente\s+a\s+", c):
            return "<monto_ley_vigente>"
    elif familia == "ejecucion":
        if re.search(r"^ejecucion\s+de\s+", c):
            return "<ejecucion_mes>"
        if re.search(r"^ejecucion\s+a\s+", c):
            return "<ejecucion_acumulada>"

    return c

# =====================================================
# 2. DETECCIÓN DE FORMATO Y LECTURA
# =====================================================
def leer_texto(ruta: Path) -> tuple[str, str] | None:
    """(texto, encoding) decodificando el archivo COMPLETO: un carácter
    cp1252 en la fila 10.000 no se ve leyendo solo la primera línea."""
    crudo = ruta.read_bytes()
    for enc in IO["encodings"][:-1]:     # sin latin-1: nunca falla
        try:
            return crudo.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return None


def perfilar_archivo(ruta: Path, familia: str) -> dict:
    res = {
        "ruta": str(ruta),
        "archivo": f"{ruta.parent.parent.name}/{ruta.parent.name}/{ruta.name}",
        "error": None,
        "lineas_rotas": 0,
        "total_lineas": 0,
        "columnas_vacias_header": 0,
        "trailing_delimiter_detectado": False,
        "firma": ()
    }

    leido = leer_texto(ruta)
    if leido is None:
        res["error"] = f"no decodifica con {IO['encodings'][:-1]}"
        return res
    texto, enc = leido
    res["encoding"] = enc

    try:
        lineas = texto.splitlines()
        header_raw = lineas[0] if lineas else ""
        sep = max(IO["separadores"], key=header_raw.count)
        res["separador"] = sep
        columnas_raw = [c.strip() for c in header_raw.rstrip(sep).split(sep)]
        res["columnas_vacias_header"] = sum(1 for c in columnas_raw if c == "")
        n_esperado = len(columnas_raw)
        res["firma"] = tuple(canonizar_columna(c, familia) if c else "<columna_vacia>"
                             for c in columnas_raw)
        res["total_columnas"] = n_esperado

        total = rotas = trailing = 0
        for linea in lineas[1:]:
            if not linea.strip():
                continue
            total += 1
            # Sin rstrip(sep): no amputar campos vacíos válidos al final
            campos = linea.split(sep)
            if len(campos) == n_esperado:
                continue
            if len(campos) == n_esperado + 1 and campos[-1] == "":
                trailing += 1   # delimitador sobrante al final (ley 2017)
            else:
                rotas += 1

        res["total_lineas"] = total
        res["lineas_rotas"] = rotas
        res["trailing_delimiter_detectado"] = trailing > 0

    except Exception as e:
        res["error"] = f"Excepción durante lectura: {e}"

    return res

# =====================================================
# 3. GENERADOR DE DOCUMENTACIÓN MARKDOWN PARA GIT
# =====================================================
def exportar_markdown_hallazgos(resumen_segmentos: list[dict], ruta_md: Path):
    lineas = [
        "# Hallazgos y Ficha Técnica de Estructura — Datos DIPRES\n",
        "> Documento generado automáticamente por `04_perfilar.py` para versionar contratos de datos.\n",
        "## 1. Resumen de Anomalías Estructurales Identificadas\n",
        "- **Delimitadores incrustados en texto**: Se presentan en archivos `programa.csv` dentro de la columna `Nombre Asignación`. Requiere reparación determinista en memoria fusionando campos centrales.",
        "- **Variación léxica de flujos**: En la familia `ejecucion`, la preposición `de` denota flujo mensual (`ejecucion_mes`), mientras que `a` denota saldo acumulado (`ejecucion_acumulada`).",
        "- **Discrepancia ortográfica**: Variación entre `ítem` e `item` unificada mediante desacentuación Unicode (`NFD`).",
        "- **Delimitador terminal huérfano**: Archivos de `ley/2017` presentan un punto y coma `;` final en filas de datos que no existe en el encabezado, generando un campo vacío adicional.\n",
        "## 2. Contratos Canónicos por Familia y Nivel\n"
    ]

    for seg in resumen_segmentos:
        lineas.append(f"### Familia: `{seg['familia'].upper()}` | Nivel: `{seg['nivel'].upper()}`")
        lineas.append(f"- **Archivos analizados**: {seg['total_archivos']}")
        lineas.append(f"- **Archivos con roturas reales de texto**: {len(seg['archivos_rotos'])}")
        lineas.append(f"- **Estructuras canónicas detectadas**: {len(seg['firmas'])}\n")
        
        for i, (firma, cant) in enumerate(seg['firmas'].items(), 1):
            lineas.append(f"#### Estructura #{i} ({cant} archivos - {len(firma)} columnas)")
            lineas.append("```python")
            lineas.append(str(list(firma)))
            lineas.append("```\n")

    ruta_md.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))

# =====================================================
# 4. EJECUCIÓN PRINCIPAL
# =====================================================
def ejecutar_profiling():
    catalogo_completo = []
    resumen_segmentos = []

    print("=" * 80)
    print("PROFILING DE ESTRUCTURAS DIPRES (AUDITORÍA DE INTEGRIDAD)")
    print("=" * 80)

    for fam in FAMILIAS:
        dir_familia = DIRS[fam]
        if not dir_familia.exists():
            continue

        for niv in NIVELES:
            archivos = sorted([a for a in dir_familia.rglob(f"{niv}.csv") if "clean" not in str(a).lower()])
            if not archivos:
                continue

            print(f"\n🔍 Auditando: [{fam.upper()}] / [{niv.upper()}] ({len(archivos)} archivos)...")

            firmas = Counter()
            archivos_rotos = []

            for ruta_csv in archivos:
                perfil = perfilar_archivo(ruta_csv, fam)
                perfil["familia"] = fam
                perfil["nivel"] = niv
                catalogo_completo.append(perfil)

                if not perfil["error"]:
                    firmas[perfil["firma"]] += 1
                    if perfil["lineas_rotas"] > 0:
                        archivos_rotos.append(perfil)

            resumen_segmentos.append({
                "familia": fam,
                "nivel": niv,
                "total_archivos": len(archivos),
                "firmas": dict(firmas),
                "archivos_rotos": archivos_rotos
            })

    # Guardar catálogo JSON
    salida_json = DIRS["reportes"] / "catalogo_profiling.json"
    salida_json.parent.mkdir(parents=True, exist_ok=True)
    with open(salida_json, "w", encoding="utf-8") as f:
        exportable = [{k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()} for p in catalogo_completo]
        json.dump(exportable, f, ensure_ascii=False, indent=2)

    # Guardar Markdown para Git
    salida_md = DIRS["docs"] / "HALLAZGOS_PROFILING.md"
    exportar_markdown_hallazgos(resumen_segmentos, salida_md)

    print(f"\n{'='*80}")
    print(f"✓ Diagnóstico JSON guardado en: {salida_json}")
    print(f"✓ Documentación Markdown guardada en: {salida_md}")
    print(f"{'='*80}")

if __name__ == "__main__":
    ejecutar_profiling()