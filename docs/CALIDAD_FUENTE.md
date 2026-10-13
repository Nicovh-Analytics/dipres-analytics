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

**Reproducir:** `python scripts/20_estructura_institucional.py`, que lista cada alta, baja, traslado y renombre de capítulo, y asocia cada descuadre con el cambio de estructura más cercano.

## 2. Línea de ley duplicada al doble

En la ley de 2020-01 (programa), la misma línea aparece dos veces y la segunda trae exactamente el doble del monto:

```
2020;Enero;PESOS;50;...;01;Impuestos a la Renta;001;Primera Categoría;8.255.573.027;8.255.573.027
2020;Enero;PESOS;50;...;01;Impuestos a la Renta;001;Primera Categoría;16.511.146.054;16.511.146.054
```

Lo mismo ocurre en 2020-01 con la Subsecretaría de Energía (aporte fiscal: 96.006.997 / 192.013.994) y entre 2017-08 y 2017-12 con una asignación de la partida 05 (141.153 / 282.306).

**Regla de `05b`:** si una clave y sus nombres están repetidos y una copia trae el doble exacto en ley inicial y en ley vigente (con tolerancia de 1), se descarta la doble. Cada línea descartada queda en `_log_consolidar_programa.json`. Con nombres distintos, las líneas se conservan (ver caso 3).

**Efecto:** sin la regla, la ejecución de 2020-01 del Tesoro a nivel programa superaba al capítulo en 41.924.866, porque el cruce duplicaba la fila.

## 3. Código de asignación reutilizado

En 2025, la partida 50, subtítulo 28, ítem 04, asignación 20 identifica a dos instituciones distintas: la Dirección de Obras Hidráulicas y la Subdirección de Servicios Sanitarios Rurales. Son líneas reales: no se juntan. El check 2 del `06` las reporta como duplicado de clave.

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

## Pendientes

Inconsistencias internas de la Ley de Presupuestos: (a) 2020, el artículo 1 es 60.273.744 menor que la suma de los cuadros por partida en el subtítulo 32 (gastos) y en el 12 (ingresos); el dataset calza con los cuadros por partida (600/600). (b) 2018, el cuadro de la partida 09 repite el subtítulo 34; la segunda línea (43.109) corresponde al 35, como la registra el dataset. En ambos casos el dataset es correcto.