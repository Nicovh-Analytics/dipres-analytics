# Hallazgos y Ficha Técnica de Estructura — Datos DIPRES

> Documento generado automáticamente por `04_perfilar.py` para versionar contratos de datos.

## 1. Resumen de Anomalías Estructurales Identificadas

- **Delimitadores incrustados en texto**: Se presentan en archivos `programa.csv` dentro de la columna `Nombre Asignación`. Requiere reparación determinista en memoria fusionando campos centrales.
- **Variación léxica de flujos**: En la familia `ejecucion`, la preposición `de` denota flujo mensual (`ejecucion_mes`), mientras que `a` denota saldo acumulado (`ejecucion_acumulada`).
- **Discrepancia ortográfica**: Variación entre `ítem` e `item` unificada mediante desacentuación Unicode (`NFD`).
- **Delimitador terminal huérfano**: Archivos de `ley/2017` presentan un punto y coma `;` final en filas de datos que no existe en el encabezado, generando un campo vacío adicional.

## 2. Contratos Canónicos por Familia y Nivel

### Familia: `LEY` | Nivel: `NACIONAL`
- **Archivos analizados**: 116
- **Archivos con roturas reales de texto**: 0
- **Estructuras canónicas detectadas**: 1

#### Estructura #1 (116 archivos - 7 columnas)
```python
['ano', 'mes', 'moneda', 'subtitulo', 'nombre subtitulo', 'monto ley inicial', '<monto_ley_vigente>']
```

### Familia: `LEY` | Nivel: `PARTIDA`
- **Archivos analizados**: 116
- **Archivos con roturas reales de texto**: 0
- **Estructuras canónicas detectadas**: 1

#### Estructura #1 (116 archivos - 9 columnas)
```python
['ano', 'mes', 'moneda', 'partida', 'nombre partida', 'subtitulo', 'nombre subtitulo', 'monto ley inicial', '<monto_ley_vigente>']
```

### Familia: `LEY` | Nivel: `CAPITULO`
- **Archivos analizados**: 116
- **Archivos con roturas reales de texto**: 0
- **Estructuras canónicas detectadas**: 1

#### Estructura #1 (116 archivos - 11 columnas)
```python
['ano', 'mes', 'moneda', 'partida', 'nombre partida', 'capitulo', 'nombre capitulo', 'subtitulo', 'nombre subtitulo', 'monto ley inicial', '<monto_ley_vigente>']
```

### Familia: `LEY` | Nivel: `PROGRAMA`
- **Archivos analizados**: 116
- **Archivos con roturas reales de texto**: 32
- **Estructuras canónicas detectadas**: 1

#### Estructura #1 (116 archivos - 17 columnas)
```python
['ano', 'mes', 'moneda', 'partida', 'nombre partida', 'capitulo', 'nombre capitulo', 'programa', 'nombre programa', 'subtitulo', 'nombre subtitulo', 'item', 'nombre item', 'asignacion', 'nombre asignacion', 'monto ley inicial', '<monto_ley_vigente>']
```

### Familia: `EJECUCION` | Nivel: `NACIONAL`
- **Archivos analizados**: 116
- **Archivos con roturas reales de texto**: 0
- **Estructuras canónicas detectadas**: 1

#### Estructura #1 (116 archivos - 7 columnas)
```python
['ano', 'mes', 'moneda', 'subtitulo', 'nombre subtitulo', '<ejecucion_mes>', '<ejecucion_acumulada>']
```

### Familia: `EJECUCION` | Nivel: `PARTIDA`
- **Archivos analizados**: 116
- **Archivos con roturas reales de texto**: 0
- **Estructuras canónicas detectadas**: 1

#### Estructura #1 (116 archivos - 9 columnas)
```python
['ano', 'mes', 'moneda', 'partida', 'nombre partida', 'subtitulo', 'nombre subtitulo', '<ejecucion_mes>', '<ejecucion_acumulada>']
```

### Familia: `EJECUCION` | Nivel: `CAPITULO`
- **Archivos analizados**: 116
- **Archivos con roturas reales de texto**: 0
- **Estructuras canónicas detectadas**: 1

#### Estructura #1 (116 archivos - 11 columnas)
```python
['ano', 'mes', 'moneda', 'partida', 'nombre partida', 'capitulo', 'nombre capitulo', 'subtitulo', 'nombre subtitulo', '<ejecucion_mes>', '<ejecucion_acumulada>']
```

### Familia: `EJECUCION` | Nivel: `PROGRAMA`
- **Archivos analizados**: 116
- **Archivos con roturas reales de texto**: 0
- **Estructuras canónicas detectadas**: 1

#### Estructura #1 (116 archivos - 19 columnas)
```python
['ano', 'mes', 'moneda', 'partida', 'nombre partida', 'capitulo', 'nombre capitulo', 'programa', 'nombre programa', 'subtitulo', 'nombre subtitulo', 'item', 'nombre item', 'asignacion', 'nombre asignacion', 'sub-asignacion', 'nombre sub-asignacion', '<ejecucion_mes>', '<ejecucion_acumulada>']
```
