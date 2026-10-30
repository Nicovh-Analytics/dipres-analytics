# Hoja de ruta — dipres-analytics

> Revisión: 29-10-2026 (bloque A cerrado). Se actualiza al cerrar cada bloque, no a mitad.

## 1. Objetivo (lo que define qué entra)

Auditar desde afuera, solo con datos públicos, **si el presupuesto se ejecuta
como se aprobó** y **si el dato publicado alcanza para fiscalizarlo**.

- Criterio de contraste: la norma (Ley de Presupuestos, DL 1.263, DS 854) y
  terceros independientes (Diario Oficial, CGR), no el mismo productor.
- Resultado: señales de *dónde mirar* (condición, criterio, desviación, sin
  juicio de valor), no veredictos.
- Hallazgo transversal: dónde la información publicada no permite fiscalizar
  (agregación editorial, errores de origen, conciliaciones no publicadas).

**Regla para ideas nuevas:** entra al pipeline solo si responde una de las dos
preguntas de arriba y se cierra en un bloque. Si no, va a §5 (estacionamiento)
con la pregunta formulada y sin código.

## 2. Barrido por archivo

Leyenda: **N** núcleo (responde el objetivo) · **S** soporte · **R** rama
(útil, pero lateral) · **?** decidir.

| Script | Qué hace | Hallazgo | Tipo | Estado |
|---|---|---|---|---|
| 02_descargar / 03_descargar_inv | Descarga datos.gob.cl (ley y ejecución, 4 niveles; inversión) | — | S | Revisión por SHA-256 (`--revisar-contenido`, `--solo`) |
| 04_tipos_cambio | Dólar, euro y UF diarios (mindicador) | — | S | OK; el número se repite con `04_perfilar` (otra etapa): no se renumera |
| 12 | Descarga normativa (LeyChile) | — | S | OK |
| 13_extraer_imagenes_ley | Extrae las imágenes del art. 1 (base64 en el XML de LeyChile) | VAL-2 | S | Mantener; paso manual (OCR/lectura) |
| 05_consolidar / 07_diccionario | Cruces ley × ejecución por nivel; diccionario | CAL | S | 05: 5 ⚠; 07 sin controles |
| 04_perfilar / 06_validar | Perfil de columnas; coherencia entre niveles y duplicados | CAL | S | 06: 6 ❌ a reclasificar; `04` duplicado |
| 14 / 15 validación | ley_inicial vs Ley publicada (art. 1) | VAL-2, VAL-3 | N | OK; escriben en `docs/` a propósito |
| 15b_validar_vs_cgr | Ejecución vs IGFE de Contraloría | VAL | N | 132 ⚠ por revisar |
| 10 conciliacion_gfs | Clasificador → GFS → cifra oficial; TC supuesto vs observado | ING-1, ING-2 | N | Controles agregados; cifra oficial solo 2024 |
| 11 tope_vs_estimacion | ¿ley_inicial es pronóstico o tope? (prueba por patrones) | — | R | A `archivo/`: lo respondió la lectura normativa (11b, 17, 10) |
| 11b tope_endeudamiento | Tope art. 3 leído del texto + ajustes legales | DEU-1 | N | OK |
| 11c bonos_deuda | 52 tablas de los reportes de deuda | DEU-1 | S | OK; 5 ⚠ conocidos |
| 16 modificaciones | Ley inicial → vigente, bruto y neto | MOD-1 | N | 5 ⚠ por revisar |
| 17 ejecución | Ejecución vs vigente, cumplimiento art. 4 | EJE-3 | N | 2 ⚠ por revisar |
| 18 ingresos | Proyección vs real, perímetro FMI | ING-1, ING-2 | N | Sin controles |
| 18b financiamiento | Fuentes de cada año, neteos | FIN-1 | R | OK (descriptivo) |
| 18c cruce_bonos | Bonos vs subt. 14 | DEU-1 | S | OK |
| 18d margen_endeudamiento | Uso estimado del tope art. 3 | DEU-1 | N | OK; cifra oficial pedida por Transparencia |
| 19 aporte_fiscal | Reconstruye el aporte fiscal por ministerio; valida contra art. 2 (2017-2020) | VAL | S | Mantener como validación; salidas = respaldo |
| 20 estructura_institucional | Altas/bajas de servicios y descuadres | EST-3, CAL-1 | N | Controles agregados hoy; usa matplotlib |
| 21 sintesis | Genera `HALLAZGOS.md` | todos | N | OK |
| 22 / 23 gráficos | Hallazgos / análisis | — | S | DEU-1 con rango viejo |
| herramientas/mapa_flujo | Mapa de dependencias | — | S | OK |


## 3. Lectura honesta de la alineación

- **Lo central está cubierto**: modificaciones (16), ejecución (17), ingresos
  (18) y validación contra la ley publicada (14/15) responden directamente al
  objetivo.
- **El bloque de deuda (11b–11c–18c–18d) creció más que su peso.** Se justifica
  porque es cumplimiento normativo (art. 3) con fuente independiente, pero
  ya se cerró: lo que falta es la respuesta de DIPRES, no más código.
- **FIN-1 es descriptivo.** Está bien que viva en "Análisis" y no como hallazgo.
  No ampliarlo.
- **Deuda técnica pequeña y conocida**: 11, 13 y 19 sin destino claro; dos
  `04`; tipo de cambio en dos fuentes (`TC_OBSERVADO` a mano y `anual.csv`).
- **Riesgo principal: la publicación, no el análisis.** El repo tiene 23
  hallazgos y casi ningún gráfico en el README. Para portafolio, lo que falta
  es mostrarlo.

## 4. Hoja de ruta

### Bloque A — Cerrar deuda técnica ✓ (29-10-2026)
1. ✓ Controles en todos los scripts de `pipeline/` (10, 20 y 06 reclasificado:
   ❌ solo si no se lee o no reconcilia).
2. ✓ 11 a `archivo/`; 13 y 19 se quedan como soporte y validación.
3. ✓ El `04` repetido está en dos etapas distintas: no se renumera (los números
   identifican el script dentro de su etapa; el 18d y los docs los citan).
4. ✓ `matplotlib` en `pyproject.toml`.
5. ✓ Hallazgo nuevo de la fuente al reclasificar el 06: CALIDAD_FUENTE §14
   (ley de programa con detalle incompleto 2024-2025; programa 2019-11 desfasado).

### Bloque B — Publicable (hasta el checkpoint de fines de noviembre)
1. ✓ Gráfico DEU-1 rehecho con el 18d (base, cota alta y tope ampliado por ventana).
2. Ajustes de diseño de MOD-1, EJE-3, EST-3.
3. Insertar los gráficos en README y HALLAZGOS.
4. Revisión del usuario de los textos ING-2, DEU-1 y VAL-3.
5. Enviar la consulta de Transparencia a DIPRES sobre el art. 3 y registrarla
   en `consultas_transparencia.md`.
6. ~13-nov: incorporar las respuestas de CGR/DIPRES (las ya enviadas).

### Bloque C — Reproducibilidad (después de B, solo lo que afecte resultados)
1. ✓ A3: `herramientas/manifiesto.py` → `docs/manifiesto_datos.csv` (1.429 archivos,
   SHA-256) y `02 --revisar-contenido`. Falta: reanudar descargas cortadas
   (ejecución de programa 2017-02 y 2017-03 sin verificar).
2. ✓ B1: `TC_OBSERVADO` se calcula de la serie diaria del Banco Central
   (`04`); los valores a mano quedan como control (`TC_OBSERVADO_BDE`).
   `TOPE_AJUSTES` y `TOPE_PLURIANUAL` en `dominio`. Efecto: ING-5 se mueve
   1.305 millones (0,002%); el resto sin cambios.
3. B2: ✓ años de corte en `config` (`PRIMER_ANIO`, `ANIO_EN_CURSO`,
   `ULTIMO_ANIO_CERRADO`); el alcance de HALLAZGOS lee la cobertura del dato.
   Pendiente: encoding uniforme de CSV.
4. Cifra oficial de ingresos (IFP 4T) para más años en el 10; hoy solo 2024.
5. C2 (opcional): `ENTRADAS`/`SALIDAS` declaradas por script.

## 5. Estacionamiento (no se toca hasta cerrar B)

| Idea | Pregunta | Por qué espera |
|---|---|---|
| Proyección deuda t+n | ¿Cuánto vence por año según la emisión? | Análisis nuevo, no responde ejecución vs ley |
| Extrapresupuestario y FET | ¿El gasto de emergencia se volvió permanente? | Requiere datos que no se descargaron |
| Contraste con informes CGR (paper) | ¿El método detecta lo que CGR detectó? | Proyecto aparte; checkpoint propio en noviembre |
| Dashboard Streamlit | — | Presentación; después de publicar |
| Iniciativas de inversión (geográfico) | — | Fuente distinta |