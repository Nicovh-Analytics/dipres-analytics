# Calidad de la fuente — datos de ejecución presupuestaria DIPRES

> Hallazgos sobre los CSV que DIPRES publica en datos.gob.cl (ley y ejecución, 2017-01 → 2026-08).
> Cada caso indica la evidencia, cómo lo trata el pipeline y cómo reproducirlo.
> Última revisión: 12-10-2026.

## Resumen

| # | Hallazgo | Alcance | Tratamiento |
|---|---|---|---|
| 1 | Niveles de agregación descuadrados al crear o reestructurar instituciones | 59 meses-partida 2017-2020, ninguno desde 2021 | Documentado; `06` check 10 y `20` lo detectan |
| 1b | Nombres de capítulo que alternan entre versiones | SLEP 2019-2021, entre otros | `20` los marca `NOMBRE_INESTABLE` y no los cuenta como cambio |
| 2 | Línea de ley repetida con el monto exacto al doble | 7 líneas: 2017 (ago-dic) y 2020-01 | `05b` descarta la copia doble y la registra |
| 3 | Código de asignación repetido para dos instituciones | 2025, partida 50 | Se conservan ambas líneas |
| 4 | Datos ya publicados que DIPRES vuelve a publicar con cambios | 2026-07 (3 archivos) | `02` guarda la versión anterior en `_versiones/` |
| 5 | `;` dentro de nombres de asignación | 31 filas de ley programa (2017-2019, 2021-11) | `05b` repara la fila |
| 6 | `;` sobrante al final de cada fila | ley 2017 | `05b` descarta el campo vacío |
| 7 | Mes en minúscula en la columna (`junio`) | 14 archivos de ley 2017-2023 | `05b` toma el mes de la carpeta |
| 8 | Encoding mixto (utf-8 / cp1252) | archivos 2024 | `05b` decodifica el archivo completo |
| 9 | Ejecución sin línea de ley | 189 filas nacional · 2,2 M programa | El cruce las conserva con `origen=solo_ejecucion` |
| 10 | La ley no cuadra consigo misma | 2018 y 2020 | `15` los separa; el dataset sigue los cuadros por partida |

---

## 1. Descuadres entre niveles al crear instituciones

DIPRES publica cada nivel (nacional, partida, capítulo, programa) como archivo independiente. Al consolidar solo se eliminan flujos internos, así que **el nivel alto nunca puede sumar más que el bajo**. Cuando lo hace, uno de los dos archivos está desactualizado.

**Casos confirmados (ley vigente, pesos, subtítulo 21):**

| Mes | Partida | Partida − Σ capítulos | Causa |
|---|---|---|---|
| 2018-02 | 09 Educación | 37.929.071 | El SLEP Barrancas ya está en partida.csv pero aún no en capitulo.csv. Aparece en marzo con exactamente ese monto en personal |
| 2018-05 | 29 Culturas | 330.836 | Mes de creación del Ministerio de las Culturas: aparecen sus capítulos (Subsecretaría de las Culturas y las Artes, Servicio Nacional del Patrimonio Cultural) y capitulo.csv queda incompleto |

**Patrón general (`20_estructura_institucional.py`):** al ampliar la búsqueda hasta 6 meses después del descuadre, los casos de Educación de 2018-06..08, 2019-03 y 2020-03..05, y el de Relaciones Exteriores de 2019-08, quedan antes de las altas de nuevos SLEP, de la Subrei y de ProChile. **El archivo de partidas incorpora el servicio nuevo hasta 4 meses antes que el de capítulos.** En total, 51 de los 59 descuadres (86%) coinciden con una alta, baja o traslado en la misma partida, entre 1 mes antes y 6 meses después; todos los de 2019 y 2020 lo hacen. Quedan sin explicar los 5 casos de 2017 (no se pueden evaluar porque es el primer año de datos, sin mes anterior para comparar) y 3 casos de la partida 05 entre enero y marzo de 2018 (1,5 millones en 4 subtítulos). Los descuadres desaparecen desde 2021, cuando casi todas las creaciones pasan a ocurrir en enero, a través de la propia Ley de Presupuestos.

**Traspaso parcial, que no es doble conteo:** en abril de 2025 Carabineros (05-31) y la PDI (05-33) aparecen en la partida 32 (Seguridad Pública) sin salir de la 05 hasta enero de 2026. El origen conserva lo que ya había ejecutado y el destino recibe el resto: 747.359 + 2.498.988 = 3.246.347 millones, exactamente la ley vigente de marzo. Para la serie anual de una institución trasladada hay que sumar ambas partidas. El `20` lo detecta como `TRASLADO (parcial)`.

**Casos probables o abiertos:**

- **Nacional − Σ partidas, 2018-03 y 2018-04:** la diferencia es idéntica en ambos meses, de 37,5 millones en personal y repartida en varios subtítulos. Es del orden de Barrancas, pero no calza exacto: no está confirmado.
- **Partida 05 (Interior):** partida − Σ capítulos es de 450.382 en todo el período revisado. Sin explicar.
- **Ley vigente capítulo vs programa:** 1.930 casos, de los cuales 745 son de 2019-11. Sin estudiar.

**Implicancia para el análisis:** para series por ministerio se usa el archivo de partida, no la suma de capítulos. Los análisis de cierre usan diciembre, mes en que los casos confirmados ya están alineados.

**Reproducir:** `python pipeline/4_analisis/20_estructura_institucional.py`, que lista cada alta, baja, traslado y renombre de capítulo, y asocia cada descuadre con el cambio de estructura más cercano.

## 2. Línea de ley duplicada al doble

En la ley de 2020-01 (programa), la misma línea aparece dos veces y la segunda trae exactamente el doble del monto:

```
2020;Enero;PESOS;50;...;01;Impuestos a la Renta;001;Primera Categoría;8.255.573.027;8.255.573.027
2020;Enero;PESOS;50;...;01;Impuestos a la Renta;001;Primera Categoría;16.511.146.054;16.511.146.054
```

Lo mismo ocurre en 2020-01 con la Subsecretaría de Energía (aporte fiscal: 96.006.997 / 192.013.994) y entre 2017-08 y 2017-12 con una asignación de la partida 05 (141.153 / 282.306).

**Regla de `05b`:** si una clave y sus nombres están repetidos y una copia trae el doble exacto en ley inicial y en ley vigente (con tolerancia de 1), se descarta la doble. 
Cada línea descartada queda en `_log_consolidar_programa.json`. Con nombres distintos, las líneas se conservan (ver caso 3).

**Efecto:** sin la regla, la ejecución de 2020-01 del Tesoro a nivel programa superaba al capítulo en 41.924.866, porque el cruce duplicaba la fila.

## 3. Código de asignación reutilizado

En 2025, la partida 50, subtítulo 28, ítem 04, asignación 20 identifica a dos instituciones distintas: la Dirección de Obras Hidráulicas y la Subdirección de Servicios Sanitarios Rurales. 
Son líneas reales: no se juntan. El check 2 del `06` las reporta como duplicado de clave.

## 4. Datos republicados

`02_descargar.py --revisar-tamano` encontró tres archivos de 2026-07 (ejecución: partida, capítulo y programa) más grandes en el servidor que en la copia local. DIPRES los volvió a publicar con cambios: la ejecución de programa pasó de 40.325 a 40.345 filas. Las versiones previas se perdieron. Desde esa fecha, `02` guarda la versión reemplazada en `<mes>/_versiones/<archivo>.<AAAAMMDD>.csv`.

## 5-8. Formato de los archivos

| Problema | Ejemplo | Corrección en `05b` |
|---|---|---|
| `;` dentro del nombre | "U. de Atacama-Soluciones ácidas de fundición; Una fuente alternativa…" | Los campos sobrantes se asignan a la columna de nombre donde la fila queda válida; si no hay exactamente una opción, la fila se registra y no se carga |
| `;` sobrante al final | Ley 2017, todas las filas | Se descarta el campo vacío |
| Mes en minúscula | `junio` en ley 2017-2023 | El mes se toma de la carpeta; la discrepancia queda en el log |
| cp1252 | Archivos 2024 | Se decodifica el archivo completo: utf-8-sig → cp1252 → latin-1 |
| Montos | `2.710` | Se leen como texto y se quitan los puntos antes de convertir (antes `2.710` se leía como 2,71) |

## 9. Ejecución sin ley

El cruce original (left join desde la ley) descartaba sin aviso la ejecución sin línea de ley. A nivel programa, en 2020, eso era el 41,6% de la ejecución en pesos. El cruce actual es un outer join con la columna `origen`.

A nivel programa la diferencia es estructural: la ley trae subtotales por subtítulo e ítem, mientras que la ejecución viene por asignación. El cruce a ese nivel sirve poco para análisis. Queda pendiente un cruce por subtítulo e ítem.

## 10. La ley no cuadra consigo misma

La Ley de Presupuestos presenta las mismas cifras dos veces: en el
**artículo 1**, el total del país por subtítulo, y en los **cuadros por
partida**, el detalle de cada ministerio. La suma de los cuadros debería
dar el artículo 1. El `15` lo verifica para cada año y cada moneda, y en
2017-2026 encontró dos casos donde no pasa (miles de $).

**2018: una línea con la etiqueta equivocada.** En el cuadro de Educación
(partida 09), una línea de 43.109 aparece rotulada como subtítulo 34
(Servicio de la Deuda), cuando corresponde al 35 (Saldo Final de Caja):

| Subtítulo | Artículo 1 | Σ cuadros por partida | Dataset |
|---|---:|---:|---:|
| 34 Servicio de la deuda | 2.511.346.039 | 2.511.389.148 | 2.511.346.039 |
| 35 Saldo final de caja | 28.662.280 | 28.619.171 | 28.662.280 |

El artículo 1 y el dataset coinciden: el error está solo en el rótulo del cuadro.

**2020: el mismo monto falta en ingresos y gastos.** El artículo 1 tiene
60.273.744 menos que la suma de los cuadros, tanto en préstamos que el
Estado otorga como en préstamos que recupera:

| Subtítulo | Artículo 1 | Σ cuadros por partida | Diferencia |
|---|---:|---:|---:|
| Gasto 32 Préstamos | 1.229.013.088 | 1.289.286.832 | 60.273.744 |
| Ingreso 12 Recuperación de préstamos | 703.718.071 | 763.991.815 | 60.273.744 |

El dataset coincide con los cuadros por partida (600 de 600 combinaciones).
Se descartó que el artículo 1 elimine préstamos entre servicios públicos:
en 2021-2024 hay préstamos de magnitud similar (Subsecretaría de Redes
Asistenciales) y en esos años el artículo 1 y los cuadros cuadran. Que la
diferencia sea idéntica en ingreso y gasto sugiere un cambio aplicado en
un lugar de la ley y no en el otro. Los datos no permiten saber cuál de
las dos cifras es la aprobada.

**Implicancia:** el texto de la ley es el criterio de validación, pero no
es infalible. Ante una diferencia con el dataset, primero hay que verificar
que la ley cuadre consigo misma.

| 11 | La ejecución por partida difiere de la de Contraloría | 2017-2025, líneas puntuales | `15b` las mide y las localiza por grupo de subtítulos; consulta Ley 20.285 pendiente |

## 11. Ejecución por partida vs Contraloría (IGFE)

La Contraloría publica cada año el Informe de la Gestión Financiera del Estado (IGFE), con el presupuesto inicial, el actualizado y el devengado por partida. Recibe los datos de los servicios desde SIGFE, el mismo sistema de origen que DIPRES, pero los compila, consolida y valida por su cuenta. Es la única fuente externa con ese nivel de detalle. Los PDF se descargan a mano desde contraloria.cl y se guardan en `raw/externo/cgr/`.

**Lo autorizado coincide.** El presupuesto inicial y el actualizado por partida cuadran en casi todos los casos. La excepción es el Tesoro Público en 2020-2021, donde el dataset trae entre 0,36 y 0,56 billones de pesos más que la CGR, incluso en el presupuesto inicial. Como la Ley de Presupuestos 2020 se aprobó antes de la pandemia, el Fondo COVID no puede explicarlo. Una pista sin confirmar: en esos dos años existe en el Tesoro el programa "Financiamiento Gobiernos Regionales".

El Tesoro 2018 en moneda extranjera también difiere: la CGR registra un presupuesto actualizado de US$ 8.821 millones y el dataset US$ 7.763 millones, mientras el devengado coincide.

**Lo ejecutado difiere en líneas puntuales, siempre las mismas.** Casi siempre el dataset informa menos que la CGR, y en cada partida la diferencia cae en un solo grupo de subtítulos, el mismo todos los años:

| Partida | Dónde está la diferencia | Lectura |
|---|---|---|
| Salud | transferencias | La CGR queda entre la partida consolidada y la suma de capítulos: elimina menos transferencias internas que DIPRES |
| Relaciones Exteriores | inversiones, todos los años | Partida = suma de capítulos, y aun así la CGR registra casi el doble. El dataset no tiene esos registros en ningún nivel |
| Trabajo | prestaciones, 2017-2018 | Igual que RREE: unos 8 mil millones constantes que el dataset no tiene |
| Poder Judicial | otros, 2017-2019 | El dataset trae préstamos (subt. 32) negativos y la CGR positivos: posible neteo de recuperaciones |
| Defensa (US$) | inversiones, 2017-2021 | Mismo patrón que RREE: operaciones en el exterior, entre US$ 3 y 15 millones al año |
| Interior | transferencias, 2022 | Un solo año, 6% de la partida; posible relación con el financiamiento de los Gobiernos Regionales |
| Gobiernos Regionales | todos los grupos | No comparable: la CGR obtiene su ejecución "de la información por región" |

**Lo que se descartó:**
- **Corte de fecha:** si fuera por registros posteriores al cierre, la diferencia aparecería en funcionamiento (personal y bienes y servicios), y ahí es prácticamente cero.
- **Servicios distintos:** el número de servicios del IGFE coincide con los capítulos del dataset en RREE, Trabajo y Poder Judicial.

**La CGR también corrige sus cifras.** En 18 partida·año, el devengado de un año cambió en informes posteriores, por "antecedentes adicionales recibidos de forma posterior al cierre". Los casos más grandes son OOPP 2018 (+134 mil millones) y Vivienda 2019 (+93 mil millones). En varios, el dataset coincide con la cifra corregida y no con la original. El `15b` compara siempre contra la más reciente.

**Lo que no se puede saber desde afuera:** ninguno de los IGFE de 2017 a 2025 menciona diferencias con DIPRES ni las concilia, y la CGR no publica cifras bajo el nivel partida. El 16-10-2026 se enviaron consultas por Ley 20.285 a DIPRES y a la CGR con los casos materiales (diferencia ≥ 1% de la partida y ≥ 1.000 millones de $ o miles de US$, por moneda): Salud 2017, 2018 y 2025; RREE y Defensa (inversiones); Poder Judicial 2018-2019; Interior 2022, y Tesoro 2018 US$. Detalle en consultas_transparencia.md.

**Reproducir:** `python pipeline/3_validacion/15b_validar_vs_cgr.py` (requiere los IGFE en `raw/externo/cgr/` y `pip install pdfplumber`).