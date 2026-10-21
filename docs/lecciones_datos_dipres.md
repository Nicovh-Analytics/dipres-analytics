# Lecciones aprendidas — Datos presupuestarios DIPRES (datos.gob.cl)

## Contexto

Este documento registra los problemas encontrados y las soluciones aplicadas
al trabajar con los datos de ejecución presupuestaria y ley de presupuestos
publicados por DIPRES en datos.gob.cl vía la API CKAN.

Período analizado: 2017–2026.
Última actualización: octubre 2026.

Este documento reúne lecciones de **método** (cómo leer y tratar estos
datos). Los hallazgos concretos sobre la fuente, con su evidencia, están en
[CALIDAD_FUENTE.md](CALIDAD_FUENTE.md); los hallazgos de análisis, en
[HALLAZGOS.md](HALLAZGOS.md).

---

## 1. Formato inconsistente de los CSVs fuente

### Problema
Los CSVs publicados por DIPRES no mantienen un formato estable entre años
ni entre familias de datos (ley vs ejecución).

### Hallazgos concretos

- **Trailing semicolons**: algunos archivos de ley tienen un `;` extra al
  final de cada fila de datos, pero no en el header. Esto causa que pandas
  interprete la primera columna de datos como índice del DataFrame, corriendo
  todas las columnas una posición a la izquierda.
  - Archivos afectados: ley/2017/01–06 en partida y capítulo (al menos).
  - Síntoma: la columna "Año" contiene nombres de meses.

- **Tildes inconsistentes**: entre 2017–2023 los archivos de ejecución/programa
  usan "Item" (sin tilde), y desde 2024 usan "Ítem" (con tilde). Al
  concatenar, pandas crea dos columnas separadas.

- **Case inconsistente en nombres de columnas de monto**:
  - 2017–2023: `Ejecución de ENERO` (mes en mayúsculas)
  - 2024–2026: `Ejecución de Enero` (mes en Title Case)
  - Solución: normalizar con regex antes de concatenar.

- **Columna fantasma**: ley/programa/2021/12 tiene una columna "Unnamed: 17"
  extra, probablemente por un campo vacío al final del CSV.

### Soluciones aplicadas

```python
# 1. Siempre usar index_col=False al leer CSVs de DIPRES, y nunca descartar
#    filas mal formadas en silencio: contarlas y repararlas
#    (dipres/utils.py → leer_csv_robusto; 05_consolidar.py repara el ";"
#    dentro de nombres)
df = pd.read_csv(ruta, sep=sep, encoding=encoding, index_col=False)

# 2. Normalizar tildes en nombres de columna
rename_map = {}
for col in df.columns:
    col_lower = col.strip().lower()
    if col_lower in ("ítem", "item"):
        rename_map[col] = "Item"
    elif col_lower in ("nombre ítem", "nombre item"):
        rename_map[col] = "Nombre Item"
df = df.rename(columns=rename_map)

# 3. Derivar Año y Mes del path, no del CSV
df["Año"] = año_dir.name     # "2025"
df["Mes"] = MESES_MAP[mes_dir.name]  # "01" → "Enero"

# 4. Descartar columnas "Unnamed"
df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
```

### Recomendación general
**Nunca confiar en la estructura del CSV fuente.** Siempre:
- Detectar separador y encoding por archivo.
- Normalizar nombres de columna a un diccionario canónico.
- Derivar metadatos (año, mes) del path, no del contenido.
- Ejecutar un profiler antes de transformar.

---

## 2. Producto cartesiano en el merge (cruce)

### Problema
Al cruzar ejecución con ley a nivel de programa, las keys del merge no
eran suficientemente específicas. Faltaban `Item` y `Asignación`, lo que
causaba que una fila de ley matcheara con múltiples filas de ejecución.

### Síntoma
- ley_programa: ~1.4M filas
- cruce_programa: ~17.7M filas (debería ser ~1.4M)
- Totales inflados en Power BI

### Solución
Incluir TODAS las columnas jerárquicas en las keys del merge:

```python
def obtener_keys(nivel):
    base = ["Año", "Mes", "Moneda"]
    if nivel == "partida":
        return base + ["Partida", "Subtítulo"]
    elif nivel == "capitulo":
        return base + ["Partida", "Capítulo", "Subtítulo"]
    elif nivel == "programa":
        return base + ["Partida", "Capítulo", "Programa",
                       "Subtítulo", "Item", "Asignación"]
    return base
```

### Recomendación general
Antes de hacer cualquier merge, verificar cardinalidad de ambos lados:
```python
# Si este ratio es >> 1, hay producto cartesiano
print(len(resultado_merge) / max(len(tabla_izq), len(tabla_der)))
```

---

## 3. Estructura del presupuesto — subtítulos

### Problema
Los datos incluyen tanto ingresos como gastos en la misma tabla,
clasificados por subtítulo. Sumar todo sin filtrar mezcla ambos
lados del presupuesto y genera montos duplicados.

### Clasificación de subtítulos DIPRES

| Rango | Tipo | Ejemplos |
|-------|------|----------|
| 01–15 | Ingresos | 01: Impuestos, 08: Otros Ingresos, 09: Aporte Fiscal, 12: Recuperación Préstamos |
| 21–35 | Gastos | 21: Gastos en Personal, 22: Bienes y Servicios, 24: Transferencias Corrientes, 29: Adquisición Activos |

### Solución
Crear una columna clasificadora para separar:
```python
# En Python
df["tipo_flujo"] = df["Subtítulo"].apply(
    lambda x: "Ingreso" if int(x) <= 15 else "Gasto"
)
```
```dax
// En Power BI (columna calculada)
Tipo Flujo = IF(VALUE(cruce_partida[Subtítulo]) <= 15, "Ingreso", "Gasto")
```

### Recomendación general
Los datos presupuestarios del gobierno tienen una estructura contable
implícita. Antes de sumar, entender qué representan los clasificadores
(subtítulo, item, asignación) para evitar doble conteo.

---

## 4. Valores acumulados vs mensuales

### Problema
La columna `ejecucion_acumulada` (originalmente "Ejecución a [Mes]") es un
valor YTD (year-to-date). En enero vale lo mismo que `ejecucion_mes`, pero
en diciembre contiene el total del año. Si sumas `ejecucion_acumulada` de
todos los meses, estás contando el gasto de enero 12 veces, el de febrero
11 veces, etc.

Lo mismo aplica para `ley_vigente`: es el presupuesto total del año
replicado en cada fila mensual. La ley vigente puede cambiar mes a mes
(por modificaciones presupuestarias), pero sigue siendo el total del año,
no un monto mensual.

### Solución en Power BI
Siempre filtrar al último mes disponible antes de sumar:
```dax
Ley Vigente =
    IF(
        HASONEVALUE(dim_calendario[Año]),
        CALCULATE(
            SUM(cruce_partida[ley_vigente]),
            FILTER(
                VALUES(dim_calendario[MesNum]),
                dim_calendario[MesNum] = MAX(dim_calendario[MesNum])
            )
        ),
        BLANK()
    )
```

`ejecucion_mes` es el único campo que se puede sumar directamente entre meses.

### Recomendación general
Siempre identificar si un campo es un **stock** (valor a un punto en el
tiempo) o un **flujo** (variación en un período). Los stocks no se suman
entre períodos.

---

## 5. Pipeline de calidad de datos recomendado

### Orden de ejecución

Extracción → consolidación → validación → análisis → informe, una carpeta
por etapa en `pipeline/`. `python run.py --lista` muestra los scripts de cada
etapa; el detalle está en el [README](../README.md).

La validación tiene tres capas, de adentro hacia afuera:
1. **Interna** (`06`): consistencia del propio dataset entre niveles y meses.
2. **Contra la norma** (`14`, `15`): el dataset contra el texto de la Ley de
   Presupuestos (artículo 1 y cuadros por partida).
3. **Contra un tercero** (`15b`): el dataset contra el Informe de la Gestión
   Financiera del Estado de la Contraloría.

### Checks del profiler (pre-transformación)
- Detectar separador y encoding por archivo
- Agrupar por firma de columnas (con mes normalizado)
- Identificar archivos con estructura distinta a la mayoría
- Medir completitud por columna

### Checks del validador (post-transformación)
- Cobertura temporal (12 meses por año)
- Duplicados en keys del nivel
- Nulos en columnas clave
- Coherencia entre niveles (partida = sum(capitulo) = sum(programa))
- Anomalías de valores (ley=0 con ejecución>0, negativos)
- Valores pegados entre meses consecutivos
- Consistencia del cruce (pct_ejecucion, conteo de filas)

### Qué NO asumir
- Que los CSVs mantendrán el mismo formato entre años
- Que los separadores serán consistentes (`;` vs `,`)
- Que los encodings serán iguales
- Que las columnas vendrán en el mismo orden
- Que no habrá campos extra o faltantes
- Que los nombres de columna usarán las mismas tildes

---

## 6. Datos negativos

Los valores negativos en ley vigente y ejecución son legítimos en el
contexto presupuestario chileno:
- **Ley vigente negativa**: recortes o transferencias de presupuesto
  entre partidas. La Partida A cede recursos a la Partida B.
- **Ejecución negativa**: devoluciones, reversiones de gasto, o
  correcciones contables.

No filtrarlos — son parte del cuadro real.

---

## 7. Niveles de consolidación contable

### Descubrimiento
Los archivos de DIPRES NO son tres niveles de detalle del mismo dato.
Son tres niveles de **consolidación contable**:

| Archivo | Nivel | Qué hace |
|---------|-------|----------|
| programa / capítulo | Datos brutos | Todas las transacciones, incluidas transferencias internas |
| partida | Consolidado ministerial | Elimina transferencias entre capítulos del mismo ministerio |
| nacional | Consolidado gobierno | Elimina transferencias entre ministerios |

### Evidencia
Las discrepancias entre niveles se concentran en subtítulos de
transferencia — siempre en pares ingreso/gasto con el mismo monto:
- Sub 5 (Transf. Corrientes recibidas) ↔ Sub 24 (Transf. Corrientes dadas)
- Sub 13 (Transf. Capital recibidas) ↔ Sub 33 (Transf. Capital dadas)

Es el mismo principio de la NIC 27 / NIIF 10: se eliminan las
transacciones intragrupo al consolidar.

### Implicancia
**No comparar niveles asumiendo que son la misma base.**
Cada nivel es autoritativo para su propio alcance:
- ¿Cuánto gastó el ministerio? → cruce_partida
- ¿Cuánto gastó cada servicio? → cruce_capitulo
- ¿Cuánto gastó el gobierno en total? → cruce_nacional (con eliminaciones)

---

## 8. Subtotales mezclados con detalle en programa

### Problema
El archivo de programa contiene filas a distintos niveles jerárquicos
en el mismo CSV:
- Filas sin Item ni Asignación → subtotales de subtítulo
- Filas con Item sin Asignación → subtotales de ítem
- Filas con Item y Asignación → detalle

### Evidencia
Para Carabineros Sub 24, Dic 2024: subtotal = 1,993,924;
Σ items = 1,993,924; Σ asignaciones = 1,993,924. Las tres capas
cuadran, confirmando que las filas sin detalle son redundancias.

### Implicancia
- **Para sumar y cuadrar con capítulo**: usar solo subtotales
  (filas donde Item es NULL). Cuadra al 99.2%.
- **Para análisis granular**: usar filas con detalle, pero
  aceptando que no todos los subtítulos tienen desglose completo.
- **Nunca mezclar niveles en una suma** — produce doble conteo.

En Power BI, filtrar con ISBLANK(Item) para subtotales,
NOT(ISBLANK(Asignación)) para detalle.

---

## 9. Duplicados en la ley

### Problema
Líneas de ley repetidas con las mismas claves y nombres, donde una copia trae
exactamente el doble del monto de la otra (por ejemplo, Primera Categoría en
enero de 2020: 8,26 y 16,51 billones de pesos).

### Tratamiento
`05_consolidar.py` descarta la copia doble cuando el doble es exacto en ley
inicial y en ley vigente, y registra cada descarte en el log. Las líneas
repetidas con nombres distintos se conservan: son instituciones distintas
con el mismo código (caso de 2025, partida 50).

### Lección
Una regla de limpieza debe ser lo bastante estrecha para no tocar casos
legítimos, y dejar rastro de cada fila que modifica. Detalle en
CALIDAD_FUENTE.md, sección 2.

---

## 10. SIGFE y la brecha de publicación

### Contexto
SIGFE (Sistema de Información de Gestión Financiera del Estado) es
la plataforma donde cada servicio registra su ejecución presupuestaria.
Cada transacción se clasifica obligatoriamente hasta Sub-Asignación.
El sistema no permite registrar sin clasificar.

### La brecha
- **SIGFE** → detalle completo de cada peso gastado
- **datos.gob.cl** → agregación editorial de SIGFE, donde DIPRES
  decide a qué nivel publica cada subtítulo

### Marco legal
- DL 1.263 art 15: jefes de servicio responsables de la veracidad
- Ley 20.285: información pública debe ser veraz
- DS 854: define el clasificador completo como obligatorio para ejecución
- Instructivo Presidencial de datos abiertos: enfocado en accesibilidad
  y formatos, no en nivel de granularidad

### Hallazgo
No se encontró una obligación explícita de que la publicación como datos
abiertos mantenga el mismo nivel de detalle que existe en SIGFE. Lo
publicado cuadra en sus totales, pero omite desglose que sí existe
internamente. Desde afuera se pueden detectar señales y anomalías (dónde
mirar), pero no probar una falla de control: esa prueba vive en el dato
interno o en terreno.

---

## 11. Validación externa

### Qué sirve y qué no
- **datos.gob.cl y dipres.gob.cl**: misma fuente (SIGFE) con distinta
  presentación. No aportan validación cruzada.
- **Banco Central, FMI, Consejo Fiscal Autónomo**: usan cifras de DIPRES.
  Tampoco son independientes.
- **Contraloría (IGFE)**: recibe los datos desde el mismo sistema de origen,
  pero los compila, consolida y valida por su cuenta. Es la única fuente
  externa con detalle por partida. Se usa en `15b_validar_vs_cgr.py`.

### Lecciones del contraste con Contraloría
- **Comparar contra la cifra más reciente.** La CGR corrige en informes
  posteriores cifras que ya publicó; comparar contra la del informe del
  propio año produce diferencias falsas.
- **Ubicar la diferencia antes de explicarla.** Desagregar por grupo de
  subtítulos descartó la hipótesis del corte de fecha: las diferencias no
  estaban en funcionamiento, sino siempre en el mismo grupo de cada partida.
- **Saber cuándo parar.** Cuando la fuente externa no publica bajo cierto
  nivel, lo que queda es documentar el límite y preguntar formalmente (Ley
  20.285), no especular.

Resultados en HALLAZGOS.md (VAL-1, VAL-2) y CALIDAD_FUENTE.md, sección 11.

---

## 12. Unidades de los datos

Los valores en los CSVs de datos.gob.cl están en:
- **Miles de pesos (M$)** para moneda nacional
- **Miles de dólares (MUSD)** para moneda extranjera

Para convertir a pesos reales: multiplicar por 1,000.
Para mostrar en millones de pesos: dividir por 1,000.

Los informes consolidados de DIPRES (operación mensual/trimestral)
usan millones de pesos.

Etiquetar siempre las unidades en el dashboard para evitar
confusión.
