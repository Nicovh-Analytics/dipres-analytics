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
dipres/        módulos compartidos (paquete importable)
pipeline/      scripts del pipeline, una carpeta por etapa
exploratorio/  catálogo inicial de la API CKAN
archivo/       scripts reemplazados o de una sola vez
docs/          hallazgos, calidad de la fuente y lecciones aprendidas
run.py         corre el pipeline por etapas
```

Los datos viven fuera del repo. La ruta se define con la variable de
entorno `DIPRES_HOME` (por defecto `D:\dipres-datos`):

```
raw/          descargado; las versiones reemplazadas quedan en _versiones/
processed/    consolidados y cruces generados por el pipeline
reports/      salidas de validación y análisis
logs/         metadata de descarga
```

## Módulos compartidos (`dipres/`)

| Módulo | Responsabilidad |
|---|---|
| `config.py` | rutas, endpoints, tolerancias |
| `dominio.py` | clasificador presupuestario, concordancia GFS, tipos de cambio |
| `normativa.py` | corpus legal y régimen por subtítulo |
| `estructura.py` | altas, bajas, traslados y renombres de instituciones |
| `descarga.py` | descarga con verificación de tamaño y respaldo de versiones |
| `utils.py` | lectura robusta de CSV |
| `hallazgos.py` | registro estructurado de validaciones |

Cada hecho vive en un solo lugar. Si un subtítulo se reclasifica, se
corrige en `dominio.py` y todo el pipeline queda consistente.

## Pipeline

| Etapa | Scripts |
|---|---|
| 1. Extracción | `02` ejecución y ley · `03` iniciativas de inversión · `12` corpus legal (LeyChile, Dipres) · `13` tablas del artículo 1 |
| 2. Consolidación | `05` crudos → consolidados y cruce ley/ejecución · `07` diccionario de datos |
| 3. Validación | `04` perfil · `06` consistencia interna · `14` dataset vs artículo 1 · `15` dataset vs tablas por partida |
| 4. Análisis | `10` conciliación GFS · `11` topes vs estimaciones · `11b` límite de endeudamiento · `16` modificaciones · `17` ejecución · `18` ingresos · `19` aporte fiscal · `20` estructura institucional |
| 5. Informe | `21` genera [`docs/HALLAZGOS.md`](docs/HALLAZGOS.md) |

## Problemas de datos resueltos

| Problema | Causa | Solución |
|---|---|---|
| Columnas corridas | `;` sobrante al final de fila | se descarta el campo vacío |
| Delimitador dentro de texto | `;` en nombres de asignación | reparación por conteo de campos |
| Producto cartesiano (17,7M → 1,4M filas) | faltaban `Item` y `Asignación` en las claves | claves completas por nivel |
| Ejecución descartada sin aviso | cruce left join desde la ley | outer join con columna `origen` |
| Línea de ley al doble exacto | error de la fuente | se descarta la copia y se registra |
| Encoding mixto | archivos en cp1252 | se decodifica el archivo completo: utf-8 → cp1252 → latin-1 |

Detalle en [`docs/CALIDAD_FUENTE.md`](docs/CALIDAD_FUENTE.md) y
[`docs/lecciones_datos_dipres.md`](docs/lecciones_datos_dipres.md).

## Reproducir

```bash
git clone <url> && cd dipres-analytics
pip install -e .
export DIPRES_HOME=/d/dipres-datos     # Git Bash; ajustar
python run.py --lista                  # etapas y scripts
python run.py --todo                   # descarga → informe
python run.py                          # desde consolidación (sin red)
python run.py --solo analisis
```

## Marco normativo

- **DL 1.263/1975** — Administración Financiera del Estado
- **DS 854/2004** — Clasificador presupuestario
- **Ley 20.285** — Transparencia; exige que la información pública sea veraz
- **Ley de Presupuestos anual** — artículos 1 (cálculo de ingresos y gastos), 3 (endeudamiento), 4 (topes), 32 (gastos excedibles)
- **Ley 21.288** — Fondo COVID; endeudamiento adicional 2020–2022
- **MEFP 2001/2014 (FMI)** — marco del Estado de Operaciones de Gobierno

## Estado

- [x] Extracción, consolidación y validación interna
- [x] Validación contra el artículo 1 y las tablas por partida de la ley
- [x] Conciliación de ingresos con la cifra oficial (2024: −0,55%)
- [x] Topes del artículo 4 y límite de endeudamiento del artículo 3
- [x] Modificaciones, ejecución y estructura institucional
- [x] Síntesis de hallazgos en formato de auditoría
- [ ] Cruce a nivel programa por subtítulo e ítem
- [ ] Visualización