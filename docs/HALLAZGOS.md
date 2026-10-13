# Hallazgos — Presupuesto del Gobierno Central de Chile, 2017-2025

> Generado por `21_sintesis.py` el 13-10-2026 desde los reportes del pipeline. No editar a mano: las cifras se regeneran.

## Alcance

**Fuente:** ejecución presupuestaria mensual y Ley de Presupuestos del Gobierno Central publicadas por DIPRES en datos.gob.cl (2017-01 a 2026-08), textos de las leyes de presupuestos 2017-2026 y cifras del Informe de Finanzas Públicas.

**Seguridad razonable** para los niveles nacional y partida al cierre de cada año: la ley inicial cuadra con los cuadros por partida de cada ley en 5.927 de 5.929 combinaciones partida·subtítulo (las 2 restantes son errores del texto de la ley), y los ingresos concilian con la cifra oficial. Los niveles capítulo y programa tienen inconsistencias de publicación documentadas en [CALIDAD_FUENTE.md](CALIDAD_FUENTE.md).

**Lo que el dataset no ve:** leyes dictadas durante el año, gastos excedibles, detalle de emisiones de deuda. Por eso ningún hallazgo concluye "incumple": cuando algo no se explica con los datos, se indica que requiere respaldo legal.

## Resumen

| Código | Hallazgo | Solidez |
|---|---|---|
| ING-1 | El sesgo de proyección de ingresos es un efecto de perímetro | alta |
| ING-2 | La mayor parte del error no es error de pronóstico | media |
| ING-3 | Impuestos: sin sesgo acumulado, pero el año típico recauda menos de lo proyectado | media |
| ING-4 | Los ingresos no tributarios se subestiman año tras año | media |
| ING-5 | Los ingresos del dataset concilian con la cifra oficial | alta |
| ING-6 | La proyección del dólar falla en una sola dirección | media |
| MOD-1 | El presupuesto de gastos se amplía cada año durante su ejecución | alta |
| MOD-2 | Los aumentos de gasto corriente en pesos caben en las excepciones del artículo 4 | media |
| EJE-1 | Se ejecuta casi todo lo autorizado, y una décima parte en diciembre | alta |
| EJE-2 | La subejecución se repite en las mismas líneas | alta |
| EJE-3 | Las compras de activos se concentran en diciembre todos los años | media |
| EJE-4 | Algunas líneas se ejecutan por sobre lo autorizado de forma recurrente | media |
| DEU-1 | El endeudamiento se mantiene dentro de las autorizaciones legales verificables | media |
| EST-1 | Cada año cambia entre el 1% y el 10% de los servicios | alta |
| EST-2 | La Nueva Educación Pública se ve año a año en el presupuesto | alta |
| EST-3 | Las instituciones nuevas pasaron a crearse en enero | media |
| EST-4 | Los traslados a mitad de año dividen el presupuesto entre dos partidas, sin duplicarlo | alta |
| CAL-1 | Los descuadres entre niveles de DIPRES se explican por instituciones creadas a mitad de año | alta |
| CAL-2 | Los archivos de DIPRES requieren correcciones puntuales para leerse completos | alta |

## Ingresos: proyección y recaudación

### ING-1 · El sesgo de proyección de ingresos es un efecto de perímetro

**Condición.** Si se suman los subtítulos 01-15 de ingresos, la ley subestima lo recaudado en 9 de 9 años (p = 0,004), con un error medio de +14,9%. Al excluir lo que no es ingreso en sentido económico (endeudamiento, venta de activos financieros, recuperación de préstamos, saldo de caja), el error medio baja a +3,7% y el sesgo deja de ser significativo (subestima 5 años y sobreestima 4, p = 1,000). Solo con las líneas que son pronóstico: +4,1%, p = 1,000.

**Criterio.** Ley inicial contra ejecución acumulada a diciembre, pesos, años completos (n = 9). Prueba de signos binomial exacta, bilateral. Perímetro de ingreso según el Manual de Estadísticas de Finanzas Públicas (FMI).

**Evidencia.** `18_ingresos.py → ingresos_prueba_signo.csv, ingresos_agregados.csv`

**Alcance.** Solo moneda nacional. La correspondencia con las categorías del manual del FMI está verificada para los subtítulos principales; la de algunos subtítulos menores es inferida (dominio.CONCORDANCIA_GFS).

### ING-2 · La mayor parte del error no es error de pronóstico

**Condición.** De la diferencia total entre ley y recaudación 2017-2025, el 76% proviene de líneas que en la ley son autorizaciones (permisos para endeudarse o vender activos), no estimaciones: Venta de Activos Financieros (subt. 11): 57,6% del error con 2,8% de la ley; Endeudamiento (subt. 14): 18,6% del error con 16,4% de la ley. Las líneas de pronóstico aportan el 18% y las discrecionales el 6%.

**Criterio.** Aporte de cada subtítulo a la suma de (ejecutado − inicial) de todos los años, sin saldo de caja ni aporte fiscal.

**Evidencia.** `18_ingresos.py → ingresos_contribucion.csv`

**Alcance.** La naturaleza (pronóstico, autorización, discrecional) es una clasificación del proyecto (dominio.NATURALEZA_INGRESO). El 11 confirma empíricamente que venta de activos financieros se comporta como tope; el endeudamiento se contrasta con el art. 3 en el 11b.

### ING-3 · Impuestos: sin sesgo acumulado, pero el año típico recauda menos de lo proyectado

**Condición.** Impuestos (subtítulo 01) pesa el 68,6% de los ingresos de la ley y explica solo el 0,5% del error: su error acumulado es +0,1%. Pero ese casi cero es una compensación: la ley sobreestima la recaudación en 7 de 9 años (mediana anual -6,1%) y la subestima en 2, por montos grandes. La diferencia entre años que sobreestiman y que subestiman no es significativa (p = 0,180).

**Criterio.** Ley inicial contra ejecución a diciembre, pesos. Prueba de signos binomial exacta, bilateral.

**Evidencia.** `18_ingresos.py → ingresos_prueba_signo.csv, ingresos_contribucion.csv, ingresos_detalle.csv`

**Alcance.** Los años que subestiman coinciden con la recuperación post-pandemia (2021-2022); ver ingresos_detalle.csv. Con n = 9, una tendencia a sobreestimar de esta magnitud no se puede distinguir del azar.

### ING-4 · Los ingresos no tributarios se subestiman año tras año

**Condición.** A diferencia de impuestos, 3 líneas de pronóstico recaudan sistemáticamente más de lo que la ley proyecta: Imposiciones Previsionales (subt. 04): 9/9 años, error medio +16%, p = 0,004; Ingresos de Operación (subt. 07): 8/9 años, error medio +15%, p = 0,039; Recuperación de Préstamos (subt. 12): 9/9 años, error medio +90%, p = 0,004. Juntas pesan el 7,2% de la ley y explican el 14,6% del error.

**Criterio.** Prueba de signos por subtítulo, significancia 0,05. Con 12 subtítulos probados, alguno podría salir significativo por azar; los de p = 0,004 (9/9 años) resisten una corrección de Bonferroni (umbral 0,0042).

**Evidencia.** `18_ingresos.py → ingresos_prueba_signo.csv`

**Alcance.** Los datos no permiten distinguir si es una proyección prudente deliberada o una debilidad del método. Clasificación como pronóstico no verificada para estos subtítulos.

### ING-5 · Los ingresos del dataset concilian con la cifra oficial

**Condición.** Los ingresos 2024 con perímetro del manual del FMI calculados desde el dataset (67.650.572 millones de $) difieren en -0,55% de la cifra oficial de DIPRES (67.283.221 millones): el dataset queda 367.351 millones por sobre la cifra oficial.

**Criterio.** Informe de Finanzas Públicas 4T24, ingresos del Gobierno Central Total. Dólares convertidos al observado promedio (943,0 $/US$).

**Evidencia.** `10_conciliacion_gfs.py → conciliacion_ingresos.csv`

**Alcance.** Un solo año con cifra oficial cargada. Con el dólar supuesto (832) la brecha es -0,17%.

**Explicación de la diferencia.** La diferencia es menor al 1% y no es cambiaria: el tipo de cambio que la cerraría (780 $/US$) no es plausible. Causas posibles, no verificadas: (1) la cifra oficial es del Gobierno Central Total, que suma al presupuestario las operaciones extrapresupuestarias; si estas son positivas, la diferencia del componente presupuestario es mayor que la mostrada; (2) DIPRES aplica la clasificación del FMI a nivel de ítem, y aquí se ajusta por subtítulo completo, así que partidas que DIPRES reclasifica dentro de un subtítulo (por ejemplo, como financiamiento) quedan dentro del cálculo; (3) los dólares se convierten al promedio anual y no al tipo de cambio de cada operación. Para acotarla: comparar contra la cifra del Gobierno Central Presupuestario del mismo informe.

### ING-6 · La proyección del dólar falla en una sola dirección

**Condición.** En 9 años, el dólar observado superó al supuesto del presupuesto en 5. Los desvíos grandes son todos al alza: 2019 (+10%), 2020 (+17%), 2022 (+18%), 2024 (+13%), 2025 (+7%). El mayor desvío a la baja es -3,1%. Desvío medio absoluto: 8,1%.

**Criterio.** Supuesto: tipo de cambio promedio del Informe de Finanzas Públicas del 3er trimestre del año anterior. Observado: promedio anual del Banco Central.

**Evidencia.** `10_conciliacion_gfs.py → tipo_cambio_desvio.csv; valores en dominio.TC_SUPUESTO y TC_OBSERVADO (ingresados a mano)`

**Alcance.** Los años con desvíos grandes coinciden con shocks (2019, 2020, 2022, 2024); con n = 9 no es evidencia de sesgo del método. Cuando el dólar sube, lo presupuestado en dólares rinde más pesos.

## Modificaciones, ejecución y endeudamiento

### MOD-1 · El presupuesto de gastos se amplía cada año durante su ejecución

**Condición.** Entre 2017 y 2025, la ley vigente al cierre supera a la inicial en todos los años: mediana +17,5% neto, con un máximo de +61,4% en 2021. El neto esconde movimiento: sumando aumentos y rebajas por separado, la mediana del ajuste bruto es 30,1% de la ley inicial. Sin 2021, el rango neto es +9,9% a +28,2%.

**Criterio.** Ley inicial contra ley vigente a diciembre, por partida y subtítulo, pesos, sin aporte fiscal (subt. 27-28, doble conteo).

**Evidencia.** `16_modificaciones.py → modificaciones_resumen.csv, modificaciones_detalle.csv`

**Alcance.** Incluye leyes dictadas durante el año (reajuste, leyes de emergencia), que el dataset no distingue de las modificaciones por decreto.

### MOD-2 · Los aumentos de gasto corriente en pesos caben en las excepciones del artículo 4

**Condición.** El artículo 4 de cada ley exige una ley para aumentar el gasto corriente. En pesos, 9 de 9 años se apegan o el exceso se explica por mayores saldos de caja y venta de activos financieros, que la ley exceptúa. En dólares, 5 años muestran aumentos sin excepción medible (2021: 21 millones de US$, 2022: 4 millones de US$, 2023: 87 millones de US$, 2024: 60 millones de US$, 2025: 37 millones de US$).

**Criterio.** Art. 4 inc. 1 de cada Ley de Presupuestos, por moneda (cada cuadro del art. 1). Excepciones medibles: Δ saldo inicial de caja (sin Tesoro) y Δ venta de activos financieros.

**Evidencia.** `16_modificaciones.py → modificaciones_art4.csv`

**Alcance.** Lo que no se explica con los datos puede tener respaldo en gastos excedibles o leyes del año, que el dataset no ve: por eso se informa como "requiere respaldo legal", no como incumplimiento.

### EJE-1 · Se ejecuta casi todo lo autorizado, y una décima parte en diciembre

**Condición.** Entre 2017 y 2025 se ejecutó entre el 93,7% y el 99,0% de la ley vigente de gastos. En diciembre se gasta entre el 8,8% y el 13,1% del año, algo más que el 8,3% de un gasto parejo.

**Criterio.** Ley vigente y ejecución acumulada a diciembre; gasto de diciembre = acumulada de diciembre − acumulada de noviembre. Pesos, sin aporte fiscal.

**Evidencia.** `17_ejecucion.py → ejecucion_resumen.csv`

**Alcance.** Agregado nacional: compensa subejecución y sobreejecución entre partidas (ambas se reportan por separado en el CSV).

### EJE-2 · La subejecución se repite en las mismas líneas

**Condición.** Líneas de gasto que ejecutan 90% o menos de lo autorizado en 8 o más de los años: Ministerio de Educación, iniciativas de inversión (subt. 31): 9/9 años, mediana 62,4% ejecutado, 298.846 millones sin ejecutar en total; Ministerio de Educación, adquisición de activos no financieros (subt. 29): 8/9 años, mediana 77,3% ejecutado, 35.658 millones sin ejecutar en total; Ministerio de Salud, préstamos (subt. 32): 8/9 años, mediana 48,6% ejecutado, 441.086 millones sin ejecutar en total.

**Criterio.** Ejecuta ≤ 90% de la ley vigente y el saldo supera $1.000 millones.

**Evidencia.** `17_ejecucion.py → ejecucion_recurrencia.csv`

**Alcance.** Nivel partida × subtítulo: no identifica qué programas o proyectos explican el saldo.

### EJE-3 · Las compras de activos se concentran en diciembre todos los años

**Condición.** 6 líneas de gasto concentran el 25% o más de su ejecución anual en diciembre en todos los años; 5 son adquisición de activos no financieros (subt. 29). Los casos más marcados: Poder Judicial (subt. 29, mediana 78% en diciembre); Ministerio de Salud (subt. 29, mediana 61% en diciembre); Ministerio de Vivienda y Urbanismo (subt. 29, mediana 57% en diciembre).

**Criterio.** Gasto de diciembre ≥ 25% del ejecutado del año (3 veces lo de un mes parejo) y ≥ $1.000 millones.

**Evidencia.** `17_ejecucion.py → ejecucion_recurrencia.csv`

**Alcance.** El patrón es compatible con gasto de fin de año para no perder presupuesto, pero también con calendarios de licitación y pagos contra entrega; los datos no distinguen entre ambos.

### EJE-4 · Algunas líneas se ejecutan por sobre lo autorizado de forma recurrente

**Condición.** Líneas que ejecutan más que su ley vigente en 6 o más años: Ministerio de Vivienda y Urbanismo, otros gastos corrientes (subt. 26): 9/9 años, mediana 129%; Ministerio de Hacienda, otros gastos corrientes (subt. 26): 6/9 años, mediana 133%; Ministerio de Educación, otros gastos corrientes (subt. 26): 6/9 años, mediana 106%; Ministerio de Bienes Nacionales, transferencias de capital (subt. 33): 6/9 años, mediana 311%; Ministerio de Salud, otros gastos corrientes (subt. 26): 6/9 años, mediana 118%.

**Criterio.** Ejecutado > ley vigente > 0 (lo ejecutado sin línea de ley se informa aparte y es casi nulo a nivel partida).

**Evidencia.** `17_ejecucion.py → ejecucion_recurrencia.csv`

**Alcance.** Ejecutar sobre lo vigente solo es legal en gastos excedibles (art. 28 DL 1.263) o con ingresos propios; los datos no identifican esa base legal.

### DEU-1 · El endeudamiento se mantiene dentro de las autorizaciones legales verificables

**Condición.** De 9 años: 1 dentro del tope del art. 3 aun sin descontar amortizaciones, 4 indeterminados con estos datos, 2 (2020, 2021) sobre el art. 3 pero dentro de la autorización adicional de la Ley 21.288 (Fondo COVID) y 2 (2017, 2019) con excesos sin ley adicional identificada (uso neto 104%, 108%).

**Criterio.** Tope = incisos 1 y 2 del art. 3 de cada ley (más la Ley 21.288 en 2020-2022). Endeudamiento del Tesoro acotado entre bruto (subt. 14) y neto de amortizaciones (34.01-34.02), en US$ al observado.

**Evidencia.** `11b_tope_endeudamiento.py → tope_endeudamiento.csv`

**Alcance.** El cómputo legal requiere el detalle de cada emisión; los excesos pequeños pueden deberse a la conversión cambiaria o a deuda de corto plazo no registrada como amortización.

## Estructura institucional

### EST-1 · Cada año cambia entre el 1% y el 10% de los servicios

**Condición.** Entre 2018 y 2026 hubo 85 altas, 30 bajas y 6 traslados de capítulos (servicios) en la Ley de Presupuestos. Los capítulos pasaron de 208 a 268. El año de mayor cambio fue 2022 (10,4%).

**Criterio.** Tasa = (altas + bajas + traslados) / capítulos promedio del año. Un capítulo se compara mes a mes con el anterior; los cambios de nombre no cuentan.

**Evidencia.** `20_estructura_institucional.py → estructura_resumen_anual.csv, estructura_eventos.csv`

**Alcance.** No se cuentan los cambios de 2017 (primer año de datos, sin mes anterior) y el último año está incompleto. Una institución que cambia de nombre al trasladarse se cuenta como alta y baja, lo que sobreestima la tasa en años de reestructuración.

### EST-2 · La Nueva Educación Pública se ve año a año en el presupuesto

**Condición.** Entre 2018 y 2026 aparecen 59 Servicios Locales de Educación como capítulos nuevos: 2018: 4, 2019: 3, 2020: 4, 2022: 6, 2023: 10, 2024: 11, 2025: 10, 2026: 11. Es el calendario de traspaso de la educación municipal, leído directamente desde la Ley de Presupuestos.

**Criterio.** Altas de capítulos con nombre "Servicio Local de Educación" en la partida 09.

**Evidencia.** `20_estructura_institucional.py → estructura_eventos.csv`

**Alcance.** Cuenta el mes en que el servicio aparece en el presupuesto, que puede diferir de su entrada en funciones.

### EST-3 · Las instituciones nuevas pasaron a crearse en enero

**Condición.** Entre 2018 y 2020, el 79% de las altas, bajas y traslados ocurrió durante el año (por leyes o decretos posteriores a la Ley de Presupuestos). Entre 2022 y 2026, solo el 9%: los cambios pasaron a entrar por la propia Ley de Presupuestos, en enero.

**Criterio.** Mes en que el capítulo aparece, desaparece o se traslada.

**Evidencia.** `20_estructura_institucional.py → estructura_resumen_anual.csv`

**Alcance.** 2021 queda fuera de ambos períodos. Describe el momento del cambio en el presupuesto, no la fecha de la ley que lo creó.

### EST-4 · Los traslados a mitad de año dividen el presupuesto entre dos partidas, sin duplicarlo

**Condición.** Se detectan 5 traspasos parciales: el servicio aparece en su nueva partida y la de origen conserva lo ya ejecutado. Servicio de Biodiversidad y Áreas Protegidas, de 25-01 a 25-04 en julio 2024 (el origen conserva 86.542 millones de $); Carabineros de Chile, de 05-31 a 32-03 en abril 2025 (el origen conserva 747.359 millones de $); Hospital de Carabineros, de 05-32 a 32-04 en abril 2025 (el origen conserva 18.110 millones de $); Policía de Investigaciones, de 05-33 a 32-05 en abril 2025 (el origen conserva 257.246 millones de $); Agencia Nacional de Ciberseguridad, de 05-36 a 32-06 en abril 2025 (el origen conserva 804 millones de $). Para la serie anual de esas instituciones hay que sumar ambas partidas.

**Criterio.** Capítulo nuevo cuyo monto calza (±0,1%) con la caída de un capítulo existente el mismo mes, fuera de enero.

**Evidencia.** `20_estructura_institucional.py → estructura_eventos.csv`

**Alcance.** Solo detecta traspasos de un capítulo a otro en un mismo mes.

## Calidad de la fuente

### CAL-1 · Los descuadres entre niveles de DIPRES se explican por instituciones creadas a mitad de año

**Condición.** En 59 casos (mes × partida) la partida suma más que sus capítulos, lo que no puede deberse a consolidación. El 86% coincide con una alta, baja o traslado de un servicio de esa partida: el archivo de partidas incorpora al servicio nuevo hasta varios meses antes que el de capítulos (mediana 1 mes). Los casos se concentran en 2017-2020; no hay desde 2021.

**Criterio.** Consolidar solo elimina flujos internos: el nivel alto nunca puede superar la suma del bajo. Evento asociado: misma partida, desde 1 mes antes hasta 6 después.

**Evidencia.** `20_estructura_institucional.py → descuadres_partida_capitulo.csv; 06_validar.py check 10`

**Alcance.** Quedan 8 casos sin explicar, la mayoría del primer año de datos (sin mes anterior para comparar). Detalle en CALIDAD_FUENTE.md.

### CAL-2 · Los archivos de DIPRES requieren correcciones puntuales para leerse completos

**Condición.** Al consolidar se repararon 32 filas con ";" dentro de un nombre (antes se descartaban sin aviso) y se descartaron 7 líneas de ley repetidas con el monto exacto al doble (la mayor: Primera Categoría, enero 2020, 8.255.573 millones de $ repetidos como 16.511.146). Filas que no se pudieron reparar: 0.

**Criterio.** Una fila válida tiene tantos campos como el encabezado, códigos numéricos y montos con formato chileno. Una línea repetida con el doble exacto en ley inicial y vigente es un error de la fuente.

**Evidencia.** `05b_consolidar.py → _log_consolidar_<nivel>.json`

**Alcance.** La regla del doble exacto es conservadora: líneas repetidas con nombres distintos se mantienen (código de asignación reutilizado en 2025). Detalle en CALIDAD_FUENTE.md.
