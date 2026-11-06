# Antecedentes: qué estaba reportado y qué agrega este proyecto

> Revisión: 05-11-2026. Búsqueda acotada en fuentes públicas (web). Que no se
> haya encontrado un antecedente no significa que no exista: minutas del
> Congreso o informes internos de la Contraloría pueden contener análisis
> similares que no aparecen en un buscador.

Varios de los temas de este proyecto tienen antecedentes. Lo que no se encontró
es el análisis a nivel de archivo y de dato: tomar lo que DIPRES publica en
datos abiertos y contrastarlo, cifra por cifra, con la norma y con un tercero.

## Por tema

| Tema | Antecedente | Qué agrega este proyecto | Hallazgos |
|---|---|---|---|
| **Modificaciones por decreto** | La Ley de Presupuestos obliga a DIPRES a informar al Congreso, cada trimestre, los decretos de modificación, con un informe consolidado por subtítulo y partida, y a publicarlos (p. ej. Ley 20.798, art. 14). En 2016 se propuso informarlos cada mes y con su fundamento. En 2020 el Consejo Fiscal Autónomo (CFA) recomendó informar las reasignaciones cada trimestre; al 2022 la recomendación no se había acogido. En 2026, diputados pidieron a Hacienda el detalle de todos los decretos del año. | El dataset abierto no distingue lo que se modifica por ley de lo que se modifica por decreto, y los decretos se publican como un PDF por programa, sin vínculo con los datos. Verificar el art. 4 requiere bajar al nivel de programa y a esos PDF. | MOD-1, MOD-2; CALIDAD_FUENTE §15 |
| **Límite de endeudamiento (art. 3)** | No se encontró una publicación del cómputo del uso del límite. Lo más cercano: en 2021 el CFA pidió mayor desagregación de los "otros requerimientos de capital", lo que se acogió en parte. | Estimación del uso del límite con el detalle de cada bono de los reportes de deuda, con su rango de incertidumbre. El cómputo oficial se solicitó por Ley 20.285. | DEU-1, VAL-3 |
| **Clasificador presupuestario y estadísticas del FMI** | DIPRES documenta la reclasificación en sus anexos metodológicos. El CFA ha pedido en varias ocasiones transparentar metodologías (balance estructural, elasticidades). | La suma directa de los subtítulos de ingreso del dataset produce un sesgo de proyección aparente que desaparece con el perímetro del FMI. La conciliación con la cifra oficial queda cuantificada (2024: −0,55%), pero no se publica junto al dato. | ING-1, ING-2, ING-5 |
| **Ejecución: DIPRES y Contraloría** | El Open Budget Survey 2023 califica el informe de auditoría de Chile como "no producido": el Informe de la Gestión Financiera del Estado de la Contraloría existe, pero no es una opinión de auditoría sobre la ejecución. | Diferencias entre la ejecución publicada por DIPRES y la informada por la Contraloría, por partida y año. Se consultó a ambas instituciones por Ley 20.285. | VAL-1, VAL-2 |
| **Integridad de los archivos abiertos** | No se encontró una evaluación de este tipo. Las evaluaciones internacionales miden si los reportes existen y qué contienen: el Open Budget Survey 2023 asigna 96/100 al contenido de los reportes durante el año, y la OCDE (2025) destacó el alto nivel de transparencia presupuestaria de Chile. | Totales que su propio detalle no suma, niveles que no cuadran entre sí, líneas duplicadas y archivos corregidos sin aviso, verificados contra los archivos originales y con su huella (SHA-256). | CAL-1, CAL-2, CAL-4; CALIDAD_FUENTE |

## Contexto

En el Open Budget Survey 2023, Chile obtiene 60/100 en transparencia, bajo el
umbral de 61 que la encuesta usa para considerar suficiente la información
publicada. Es contexto, no evidencia de los hallazgos de este proyecto.

## Fuentes

- [Open Budget Survey 2023 — Chile](https://internationalbudget.org/open-budget-survey/country-results/2023/chile)
- [Ley 20.798, artículo 14](https://iura.cl/20798/14)
- [Consejo Fiscal Autónomo — Recomendaciones en materia de transparencia fiscal (2022)](https://cms.hacienda.cl/cfa/assets/documento/descargar/2140f5cff0136/1686850062)
- [Diario Financiero — Mayor transparencia en las reasignaciones y en la gestión presupuestaria (2016)](https://www.df.cl/opinion/columnistas/mayor-transparencia-en-las-reasignaciones-y-en-la-gestion-presupuestaria)
- [BioBioChile — Diputados exigen a Hacienda revelar todos los decretos (2026)](https://www.biobiochile.cl/noticias/nacional/chile/2026/04/29/diputados-del-fa-exigen-a-hacienda-revelar-todos-los-decretos-acusan-que-los-recortes-ya-estan-hechos.shtml)
- [DIPRES — Recomendaciones de la OCDE (2025)](https://www.dipres.gob.cl/598/w3-article-383604.html)
- [DIPRES — Planillas de decretos de modificación por programa (ejemplo: 2023, programa 08-02-01)](https://www.dipres.gob.cl/597/articles-327581_doc_pdf.pdf)
