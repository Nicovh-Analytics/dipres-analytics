"""
Profiler y Documentador de Hallazgos — CSVs DIPRES
===================================================
- Audita de forma aislada por Familia x Nivel sin saturar RAM.
- Distingue entre campos vacíos legítimos y delimitadores incrustados reales.
- Tolera delimitadores terminales espurios (ej: ley 2017).
- Genera reporte JSON y un documento en Markdown (HALLAZGOS_PROFILING.md).
"""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

# =====================================================
# CONFIGURACIÓN
# =====================================================
DATOS_DIR = Path("D:/dipres-datos")
FAMILIAS = ["ley", "ejecucion"]
NIVELES = ["partida", "capitulo", "programa"]
ENCODINGS = ["utf-8-sig", "latin-1"]

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
def detectar_formato(ruta: Path) -> dict | None:
    for encoding in ENCODINGS:
        try:
            with open(ruta, "r", encoding=encoding) as f:
                linea = f.readline()
                if not linea.strip():
                    continue
                sep = ";" if linea.count(";") >= linea.count(",") else ","
                return {"encoding": encoding, "separador": sep, "header": linea}
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

    formato = detectar_formato(ruta)
    if not formato:
        res["error"] = "Fallo de decodificación (probado utf-8-sig y latin-1)"
        return res

    sep = formato["separador"]
    enc = formato["encoding"]

    try:
        with open(ruta, "r", encoding=enc) as f:
            header_raw = f.readline()
            header_limpio = header_raw.rstrip("\r\n").rstrip(sep)
            
            columnas_raw = [c.strip() for c in header_limpio.split(sep)]
            res["columnas_vacias_header"] = sum(1 for c in columnas_raw if c == "")
            n_esperado = len(columnas_raw)

            firma = tuple(canonizar_columna(c, familia) if c else "<columna_vacia>" for c in columnas_raw)
            res["firma"] = firma
            res["total_columnas"] = n_esperado

            total_lineas = 0
            lineas_rotas = 0
            trailing_delimiters = 0

            for linea in f:
                if not linea.strip():
                    continue
                total_lineas += 1
                
                # Sin rstrip(sep) para no amputar campos vacíos válidos al final
                campos = linea.rstrip("\r\n").split(sep)
                n_campos = len(campos)

                if n_campos == n_esperado:
                    continue
                # Caso: Fila con delimitador sobrante al final (ej. ley 2017)
                elif n_campos == n_esperado + 1 and campos[-1] == "":
                    trailing_delimiters += 1
                else:
                    lineas_rotas += 1

            res["total_lineas"] = total_lineas
            res["lineas_rotas"] = lineas_rotas
            res["trailing_delimiter_detectado"] = trailing_delimiters > 0

    except Exception as e:
        res["error"] = f"Excepción durante lectura: {e}"

    return res

# =====================================================
# 3. GENERADOR DE DOCUMENTACIÓN MARKDOWN PARA GIT
# =====================================================
def exportar_markdown_hallazgos(resumen_segmentos: list[dict], ruta_md: Path):
    lineas = [
        "# Hallazgos y Ficha Técnica de Estructura — Datos DIPRES\n",
        "> Documento generado automáticamente por `04_profiler.py` para versionar contratos de datos.\n",
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
        dir_familia = DATOS_DIR / fam
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
    salida_json = DATOS_DIR / "consolidado" / "catalogo_profiling.json"
    salida_json.parent.mkdir(parents=True, exist_ok=True)
    with open(salida_json, "w", encoding="utf-8") as f:
        exportable = [{k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()} for p in catalogo_completo]
        json.dump(exportable, f, ensure_ascii=False, indent=2)

    # Guardar Markdown para Git
    salida_md = DATOS_DIR / "consolidado" / "HALLAZGOS_PROFILING.md"
    exportar_markdown_hallazgos(resumen_segmentos, salida_md)

    print(f"\n{'='*80}")
    print(f"✓ Diagnóstico JSON guardado en: {salida_json}")
    print(f"✓ Documentación Markdown guardada en: {salida_md}")
    print(f"{'='*80}")

if __name__ == "__main__":
    ejecutar_profiling()