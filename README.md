# DIPRES — Auditoría de datos presupuestarios

Pipeline de extracción, validación y análisis del presupuesto público
chileno (2017–2026), a partir de los datos abiertos de
[datos.gob.cl](https://datos.gob.cl) y la normativa publicada en
[LeyChile](https://www.bcn.cl/leychile).

El proyecto no busca describir en qué gasta el Estado —eso ya lo hace el
Observatorio del Gasto Fiscal— sino examinar si los datos publicados
permiten fiscalizar, y si la ejecución se ajusta a lo que la norma
autoriza.

## Hallazgos

**El agregado de ingresos no mide lo que parece medir.**
Sumar los subtítulos 01–15 del clasificador presupuestario arroja una
subestimación sistemática de 14,8% (9 de 9 años, p=0,0039). Al aplicar
el criterio del Estado de Operaciones de Gobierno —que excluye venta de
activos financieros, recuperación de préstamos y endeudamiento por ser
financiamiento y no ingreso— el sesgo desaparece por completo (p=1,0).
El componente que efectivamente se proyecta, Impuestos, tiene un error
medio de 1,0%.

**La conciliación entre ambos marcos existe y no se publica.**
DIPRES construye el Estado de Operaciones reclasificando partidas del
clasificador presupuestario. Ese procedimiento está documentado en sus
anexos metodológicos, pero no acompaña al dataset. Quien use los datos
abiertos sin conocerlo obtiene un resultado técnicamente correcto y
analíticamente falso.

**El diccionario de datos no describe el dataset que acompaña.**
Los nombres de columna documentados (`Ejecución del Mes`) no existen en
ningún archivo publicado, que usan el mes embebido
(`Ejecución de ENERO`). Mismo caso con los valores de moneda, el tipo de
los códigos y las tildes.

**Las cifras aprobadas por el Congreso se publican como imagen.**
El artículo 1 de la Ley de Presupuestos —el detalle de ingresos y gastos
que el Congreso aprueba— se publica en LeyChile como JPEG embebido. No
es texto seleccionable ni dato procesable.

**La norma predice el comportamiento de los datos.**
El articulado define el régimen de cada subtítulo: los protegidos por el
artículo 4 requieren ley para incrementarse y nunca exceden su
autorización (uso 99–100%, 0 excesos en 9 años); los exceptuados por el
inciso segundo la exceden sistemáticamente (uso 157–216%). Sin leer la
norma, ambos comportamientos se ven iguales en los datos.

## Estructura

```
scripts/     pipeline y módulos compartidos
docs/        hallazgos curados y lecciones aprendidas
notebooks/   exploración
```

Los datos viven fuera del repo. La ruta se define con la variable de
entorno `DIPRES_HOME` (por defecto `D:\dipres-datos`):

```
raw/          descargado, inmutable
processed/    generado por el pipeline
reports/      salidas de validación
logs/         metadata de descarga
```

## Módulos compartidos

| Archivo | Responsabilidad |
|---|---|
| `config.py` | rutas, endpoints, tolerancias |
| `dominio.py` | clasificador presupuestario, concordancia GFS |
| `normativa.py` | corpus legal y régimen por subtítulo |
| `utils.py` | lectura robusta de CSV (encoding y separador) |
| `hallazgos.py` | registro estructurado de validaciones |

Cada hecho vive en un solo lugar. Si un subtítulo se reclasifica, se
corrige en `dominio.py` y todo el pipeline queda consistente.

## Pipeline

```
01_explorar.py             cataloga datasets en la API CKAN
02_descargar.py            ejecución y ley, por año/mes/nivel
03_descargar_inv.py        iniciativas de inversión (incluye geografía)
04_perfilar.py             detecta anomalías de estructura
05_transformar.py          normaliza, limpia y cruza ley con ejecución
06_validar.py              9 checks de consistencia
12_descargar_normativa.py  corpus legal desde LeyChile
```

## Problemas de datos resueltos

| Problema | Causa | Solución |
|---|---|---|
| Columnas corridas en 12 archivos | delimitador sobrante al final de fila | `index_col=False` |
| Delimitador dentro de campos de texto | `;` en Nombre Asignación | reparación por conteo de campos |
| Producto cartesiano (17,7M → 1,4M filas) | faltaban `Item` y `Asignación` en las claves | claves completas por nivel |
| Granularidad desigual ley vs ejecución | ejecución llega a Sub-Asignación, ley no | colapso previo al cruce |
| Encoding mixto (77 archivos en cp1252) | latin-1 nunca falla al decodificar | detección por marcadores de mojibake |

Detalle en [`docs/lecciones_datos_dipres.md`](docs/lecciones_datos_dipres.md).

## Reproducir

```bash
git clone <url> && cd dipres-analytics
pip install pandas requests scipy
set DIPRES_HOME=D:\dipres-datos        # ajustar
python scripts/02_descargar.py
python scripts/05_transformar.py
python scripts/06_validar.py
```

## Marco normativo

- **DL 1.263/1975** — Administración Financiera del Estado
- **DS 854/2004** — Clasificador presupuestario
- **Ley 20.285** — Transparencia; exige que la información pública sea veraz
- **Ley de Presupuestos anual** — artículos 3 (endeudamiento), 4 (topes), 32 (gastos excedibles)
- **MEFP 2001/2014 (FMI)** — marco del Estado de Operaciones de Gobierno

## Estado

- [x] Extracción, perfilado, transformación y validación
- [x] Reconciliación con cifra oficial (2,6% de diferencia, explicada)
- [x] Hallazgo de ingresos cerrado
- [x] Corpus normativo — articulado extraído
- [ ] Validación de `ley_inicial` contra el artículo 1 (tablas en imagen)
- [ ] Prueba de cumplimiento por subtítulo
- [ ] Visualización

## Licencia

Código bajo MIT. Los datos son públicos y pertenecen al Estado de Chile.
