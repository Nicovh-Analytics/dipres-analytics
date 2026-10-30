# Hallazgos — Presupuesto del Gobierno Central de Chile, 2017-2025

> Generado por `21_sintesis.py` el 29-10-2026 desde los reportes del pipeline. No editar a mano: las cifras se regeneran.

## Alcance

**Fuente:** ejecución presupuestaria mensual y Ley de Presupuestos del Gobierno Central publicadas por DIPRES en datos.gob.cl (2017-01 a 2026-08), textos de las leyes de presupuestos 2017-2026, cifras del Informe de Finanzas Públicas, el Informe de la Gestión Financiera del Estado de la Contraloría (2017-2025), los Reportes de Deuda Bruta del Gobierno Central de DIPRES (2016-2025) y los tipos de cambio del Banco Central.

**Seguridad razonable** para los niveles nacional y partida al cierre de cada año: la ley inicial cuadra con los cuadros por partida de cada ley en 5.927 de 5.929 combinaciones partida·subtítulo (las 2 restantes son un error del texto de la ley, CALIDAD_FUENTE.md §10), el presupuesto por partida coincide con el de Contraloría y los ingresos concilian con la cifra oficial. La ejecución por partida difiere de la de Contraloría en líneas puntuales (VAL-2). Los niveles capítulo y programa tienen inconsistencias de publicación documentadas en [CALIDAD_FUENTE.md](CALIDAD_FUENTE.md).

**Lo que el dataset no ve:** leyes dictadas durante el año, gastos excedibles, el destino de cada operación de deuda. Por eso ningún hallazgo concluye "incumple": cuando algo no se explica con los datos, se indica que requiere respaldo legal.

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
| DEU-1 | El endeudamiento estimado cabe en las autorizaciones legales, con varios años en el límite | media |
| EST-1 | Cada año cambia entre el 1% y el 10% de los servicios | alta |
| EST-2 | La Nueva Educación Pública se ve año a año en el presupuesto | alta |
| EST-3 | Las instituciones nuevas pasaron a crearse en enero | media |
| EST-4 | Los traslados a mitad de año dividen el presupuesto entre dos partidas, sin duplicarlo | alta |
| CAL-1 | Los descuadres entre niveles de DIPRES se explican por instituciones creadas a mitad de año | alta |
| CAL-2 | Los archivos de DIPRES requieren correcciones puntuales para leerse completos | alta |
| VAL-1 | El presupuesto publicado por DIPRES coincide con el de Contraloría | alta |
| VAL-2 | La ejecución publicada difiere de la de Contraloría en líneas puntuales, siempre las mismas | media |
| VAL-3 | La emisión de bonos de los reportes de deuda cuadra con el endeudamiento ejecutado | alta |
| FIN-1 | La deuda neta financió entre el 9% y el 19% de cada año | análisis |

## Ingresos: proyección y recaudación

### ING-1 · El sesgo de proyección de ingresos es un efecto de perímetro

**Condición.** Si se suman los subtítulos 01-15 de ingresos, la ley subestima lo recaudado en 9 de 9 años (p = 0,004), con un error medio de +14,9%. Al excluir lo que no es ingreso en sentido económico (endeudamiento, venta de activos financieros, recuperación de préstamos, saldo de caja), el error medio baja a +3,7% y el sesgo deja de ser significativo (subestima 5 años y sobreestima 4, p = 1,000). Solo con las líneas que son pronóstico: +4,1%, p = 1,000. El sesgo desaparece, pero el error no: con el perímetro del FMI el error típico (promedio sin signo) es de 9,3%, con un máximo de +35% en 2022.

**Criterio.** Ley inicial contra ejecución acumulada a diciembre, pesos, años completos (n = 9). Prueba de signos binomial exacta, bilateral. Perímetro de ingreso según el Manual de Estadísticas de Finanzas Públicas (FMI).

**Evidencia.** `18_ingresos.py → ingresos_prueba_signo.csv, ingresos_agregados.csv`

**Alcance.** Solo moneda nacional. La correspondencia con las categorías del manual del FMI está verificada para los subtítulos principales; la de algunos subtítulos menores es inferida (dominio.CONCORDANCIA_GFS). La suma de subtítulos en pesos incluye además las operaciones de cambio (subt. 11, ítem 03): dólares que el Tesoro convierte a pesos y que en moneda nacional se registran como ingreso (ver ING-2 y CALIDAD_FUENTE.md, §12).

### ING-2 · La mayor parte del error no es error de pronóstico

**Condición.** De la diferencia total entre ley y recaudación 2017-2025, el 76% proviene de líneas que en la ley son autorizaciones (permisos para endeudarse o vender activos), no estimaciones: Venta de Activos Financieros (subt. 11): 57,6% del error con 2,8% de la ley; Endeudamiento (subt. 14): 18,6% del error con 16,4% de la ley. Las líneas de pronóstico aportan el 18% y las discrecionales el 6%. Dentro de Venta de Activos Financieros, las operaciones de cambio (ítem 03) suman 50,2 billones de pesos en el período, el 98% de su desvío: son dólares que el Tesoro convierte a pesos, que en moneda nacional se registran como ingreso y en dólares como ingreso negativo. Sin ellas, el aporte del subtítulo 11 al error sería de 1%.

**Criterio.** Aporte de cada subtítulo a la suma de (ejecutado − inicial) de todos los años, sin saldo de caja ni aporte fiscal.

**Evidencia.** `18_ingresos.py → ingresos_contribucion.csv`

**Alcance.** La naturaleza (pronóstico, autorización, discrecional) es una clasificación del proyecto (dominio.NATURALEZA_INGRESO). La ley inicial no se publica por ítem, así que la parte de las operaciones de cambio se mide con lo ejecutado (18b_financiamiento.py → financiamiento_activos.csv). El endeudamiento se contrasta con el art. 3 en DEU-1.

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

**Condición.** Los ingresos 2024 con perímetro del manual del FMI calculados desde el dataset (67.651.877 millones de $) difieren en -0,55% de la cifra oficial de DIPRES (67.283.221 millones): el dataset queda 368.656 millones por sobre la cifra oficial.

**Criterio.** Informe de Finanzas Públicas 4T24, ingresos del Gobierno Central Total. Dólares convertidos al observado promedio (943,6 $/US$).

**Evidencia.** `10_conciliacion_gfs.py → conciliacion_ingresos.csv`

**Alcance.** Un solo año con cifra oficial cargada. Con el dólar supuesto (832) la brecha es -0,17%.

**Explicación de la diferencia.** La diferencia es menor al 1% y no es cambiaria: el tipo de cambio que la cerraría (780 $/US$) no es plausible. Causas posibles, no verificadas: (1) la cifra oficial es del Gobierno Central Total, que suma al presupuestario las operaciones extrapresupuestarias; si estas son positivas, la diferencia del componente presupuestario es mayor que la mostrada; (2) DIPRES aplica la clasificación del FMI a nivel de ítem, y aquí se ajusta por subtítulo completo, así que partidas que DIPRES reclasifica dentro de un subtítulo (por ejemplo, como financiamiento) quedan dentro del cálculo; (3) los dólares se convierten al promedio anual y no al tipo de cambio de cada operación. Para acotarla: comparar contra la cifra del Gobierno Central Presupuestario del mismo informe.

### ING-6 · La proyección del dólar falla en una sola dirección

**Condición.** En 9 años, el dólar observado superó al supuesto del presupuesto en 5. Los desvíos grandes son todos al alza: 2019 (+10%), 2020 (+17%), 2022 (+18%), 2024 (+13%), 2025 (+7%). El mayor desvío a la baja es -3,1%. Desvío medio absoluto: 8,1%.

**Criterio.** Supuesto: tipo de cambio promedio del Informe de Finanzas Públicas del 3er trimestre del año anterior. Observado: promedio anual del Banco Central.

**Evidencia.** `10_conciliacion_gfs.py → tipo_cambio_desvio.csv; valores en dominio.TC_SUPUESTO (IFP, ingresado a mano) y TC_OBSERVADO (promedio de la serie diaria del Banco Central, 04_tipos_cambio.py)`

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

### DEU-1 · El endeudamiento estimado cabe en las autorizaciones legales, con varios años en el límite

**Condición.** Uso estimado del margen del art. 3 (entre paréntesis, base sobre el tope): dentro del tope aun con la cota alta: 2022 (64%), 2023 (98%), 2024-2025 (98%); dentro con las autorizaciones de leyes especiales (Ley 21.225 en 2020 y bolsa de la Ley 21.288 para 2020-2022): 2020 (109%), 2021 (133%); en el límite (la base o la cota alta superan el tope, pero no el tope ampliado con la autorización para bonos de reconocimiento): 2018 (100%), 2019 (102%); 2017 supera el tope ampliado por 93 millones de US$ (+0,8%), menos que el margen de error de la estimación.

**Criterio.** Base = bonos emitidos a valor nominal en US$ (reportes de deuda de DIPRES) − prepagos de deuda de años anteriores − bonos emitidos y vencidos el mismo año (inciso 4°). Cota alta = base + residuo en dólares del cruce con el subt. 14 (créditos con organismos). Tope = incisos 1 y 2 del art. 3 (+ Ley 21.225 en 2020); tope ampliado = tope + autorización aparte para bonos de reconocimiento. Conversión con el dólar, euro y UF promedio del periodo de cada emisión.

**Evidencia.** `11b_tope_endeudamiento.py, 11c_bonos_deuda.py, 18c_cruce_bonos.py, 18d_margen_endeudamiento.py → margen_endeudamiento.csv`

**Alcance.** No se puede medir con datos públicos: cuánto se usó de la autorización para bonos de reconocimiento, la deuda emitida y vencida entre dos reportes de deuda, ni el tipo de cambio de cada operación. 2024 y 2025 se evalúan juntos porque los reportes de 2024 no permiten separar la emisión local. El cómputo oficial se pidió por Ley 20.285.

**Explicación de la diferencia.** La versión anterior de este hallazgo, que acotaba el endeudamiento entre el subt. 14 bruto y neto de amortizaciones, marcaba sobre el tope 2017, 2019. Cambió al medir los bonos a valor nominal (el subt. 14 registra lo recibido en caja, con el premio de colocación), descontar los prepagos y los bonos emitidos y vencidos el mismo año, sumar la autorización para bonos de reconocimiento y la Ley 21.225 (art. quinto: US$4.000 millones para 2020).

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

**Evidencia.** `05_consolidar.py → _log_consolidar_<nivel>.json`

**Alcance.** La regla del doble exacto es conservadora: líneas repetidas con nombres distintos se mantienen (código de asignación reutilizado en 2025). Detalle en CALIDAD_FUENTE.md.

## Validación externa

### VAL-1 · El presupuesto publicado por DIPRES coincide con el de Contraloría

**Condición.** Por partida, 2017-2025: el presupuesto inicial cuadra en 305 de 310 partida·año·moneda y el actualizado en 296 de 310. Las demás diferencias no superan 4.499 millones de $ o miles de US$. Las excepciones son Ministerio de Educación (2018: dataset − CGR -12.921 millones de $); Tesoro Público (2018: dataset − CGR -1.058.809 miles de US$); Tesoro Público (2020, 2021: dataset − CGR entre 357.403 y 560.156 millones de $), sin explicación en los informes.

**Criterio.** Informe de la Gestión Financiera del Estado (IGFE) de la Contraloría, estado de situación presupuestaria de gastos por partida, que elimina solo las transferencias dentro de cada partida, igual que cruce_partida. Gastos 21-34 a diciembre; tolerancia ±2 millones de $ o miles de US$ por redondeo.

**Evidencia.** `15b_validar_vs_cgr.py → validacion_cgr.csv, cgr_partidas.csv`

**Alcance.** La CGR recibe los datos desde SIGFE, el mismo sistema de origen que DIPRES, pero los compila y valida por su cuenta. La prueba verifica la agregación que publica DIPRES, no el registro de cada servicio. Los tribunales, el CPLT, el INDH y la Defensoría de la Niñez figuran en el IGFE pero no como partida en datos.gob.cl.

### VAL-2 · La ejecución publicada difiere de la de Contraloría en líneas puntuales, siempre las mismas

**Condición.** El devengado por partida cuadra en 200 de 310 partida·año·moneda. En las diferencias (sin Gobiernos Regionales), el dataset informa menos que la CGR en 97 de 107 casos, y en 84 la diferencia es menor al 1% de la partida. De los 85 partida·año con diferencia que tienen desglose por subtítulo en el IGFE, en 74 el 80% o más se concentra en un solo grupo. Se repite en los mismos lugares: Ministerio de Defensa Nacional, inversiones (US$) (8 años); Ministerio de Salud, transferencias (7 años); Ministerio de Relaciones Exteriores, inversiones (7 años); Ministerio de Educación, transferencias (5 años). La propia CGR corrigió en informes posteriores el devengado de 17 partida·año (el mayor: Ministerio de Obras Públicas 2018, 133.994 millones de $); la comparación usa la cifra corregida.

**Criterio.** Devengado del IGFE (cifra más reciente publicada por la CGR para cada año) contra ejecución acumulada a diciembre de cruce_partida, total y por grupo de subtítulos (tabla de gastos devengados por partida y subtítulo del IGFE).

**Evidencia.** `15b_validar_vs_cgr.py → validacion_cgr.csv, validacion_cgr_subtitulo.csv, cgr_revisiones.csv`

**Alcance.** Ambas fuentes cubren los mismos servicios en las partidas revisadas (conteo de servicios del IGFE vs capítulos del dataset). La CGR consolida datos recibidos hasta febrero o marzo del año siguiente. Los IGFE no explican las diferencias ni concilian con DIPRES, y la CGR no publica cifras bajo el nivel partida, por lo que la línea exacta no se puede identificar desde afuera. Gobiernos Regionales se excluye: la CGR obtiene su ejecución de otra fuente (información por región).

**Explicación de la diferencia.** Tres tipos, según dónde cae la diferencia: (1) consolidación: en Salud la CGR elimina menos transferencias internas que DIPRES (queda entre la partida consolidada y la suma de capítulos); (2) registros que el dataset no tiene en ningún nivel: RREE inversiones y Trabajo prestaciones (2017-2018), donde partida y suma de capítulos coinciden y aun así la CGR registra más; (3) posible neteo: Poder Judicial informa préstamos negativos en el dataset y positivos en la CGR. Pendiente: consulta por Ley 20.285 a DIPRES y a la CGR con estos casos.

### VAL-3 · La emisión de bonos de los reportes de deuda cuadra con el endeudamiento ejecutado

**Condición.** El subtítulo 14 queda sobre la emisión de bonos entre +0,7% y +8,2% en la sección en dólares, todos los años, y entre +5,0% y +14,8% en la de pesos, salvo 2022 (-10,7%).

**Criterio.** Bonos emitidos por serie según los Reportes de Deuda Bruta del Gobierno Central (diferencia de monto colocado entre reportes), convertidos a la moneda de cada sección (UF a pesos, euros a dólares) con el promedio del periodo, contra el subtítulo 14 ejecutado a diciembre.

**Evidencia.** `11c_bonos_deuda.py, 18c_cruce_bonos.py → deuda_cruce_subt14.csv`

**Alcance.** El subt. 14 incluye créditos con organismos que no son bonos y registra lo recibido en caja, no el valor nominal. Los bonos emitidos y vencidos entre dos reportes no se ven. Los reportes de deuda tienen inconsistencias entre ediciones, documentadas en CALIDAD_FUENTE.md, §13; las 52 tablas leídas cuadran con su total.

**Explicación de la diferencia.** En dólares la diferencia positiva es la esperada por los créditos. En pesos, hipótesis sin verificar: el bono colocado sobre la par (tasa de mercado bajo el cupón) entrega más caja que su valor nominal, y bajo la par menos; en 2022 las tasas superaron los cupones de varias series. Verificarlo requiere el precio de cada colocación (resultados de licitación de Hacienda).

## Análisis descriptivo (no son hallazgos de auditoría)

### FIN-1 · La deuda neta financió entre el 9% y el 19% de cada año

**Condición.** De las fuentes de financiamiento ejecutadas de cada año, los ingresos (perímetro FMI) aportaron entre el 65% y el 83%. La deuda neta (endeudamiento menos amortizaciones del año) aportó entre el 9% (2023) y el 19% (2021). La deuda que solo paga vencimientos pasó del 2% en 2017 al 13% en 2025. En 2022 (-10%) el año ahorró en títulos y depósitos en vez de usarlos.

**Criterio.** Fuentes ejecutadas a diciembre, pesos y dólares (convertidos al dólar observado promedio), sin aporte fiscal ni saldo inicial de caja. Endeudamiento (subt. 14) separado con las amortizaciones del subt. 34; títulos neteados (11.01 − 30.01); sin operaciones de cambio (11.03).

**Evidencia.** `18b_financiamiento.py → financiamiento_fuentes.csv`

**Alcance.** Describe cómo se financió cada año; no evalúa si estuvo bien. Los retiros de los fondos soberanos no se identifican por separado en el dato.
