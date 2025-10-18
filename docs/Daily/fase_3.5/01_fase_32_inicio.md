# Fase 3.2: Price & Momentum Wave Analysis - Inicio

**Fecha de inicio:** 16 de Octubre, 2025
**Estado:** En ejecución
**Fase:** 3.2 - Price & Momentum Wave

---

## Objetivo

Analizar las ondas de precio y momentum post-evento para identificar patrones de continuidad, reversión y calidad de señal de los eventos detectados en Fase 2.5.

### Objetivos Específicos

1. **Detección de Ondas Post-Evento**
   - Identificar movimientos de precio tras cada evento
   - Clasificar ondas por dirección (continuity vs reversal)
   - Medir amplitud y duración de ondas

2. **Análisis de Momentum**
   - Calcular velocidad de movimiento post-evento
   - Detectar aceleración/desaceleración
   - Identificar puntos de inflexión

3. **Métricas de Reversión y Continuidad**
   - Tasa de continuidad por tipo de evento
   - Patrones de reversión temprana
   - Timeframe óptimo de seguimiento

4. **Normalización de Scores**
   - Ajustar scores originales por calidad de wave
   - Incorporar métricas de momentum
   - Generar score compuesto final

---

## Input Dataset

### Archivo de Entrada

**Path:** `processed/final/events_intraday_MASTER_dedup_v2.parquet`

**Certificación:** Validado y aprobado en Fase 2.5 (Ver: `docs/Daily/fase_4/14_validacion_final_dataset_fase_25.md`)

### Especificaciones del Input

| Métrica | Valor |
|---------|-------|
| **Eventos únicos** | 572,850 |
| **Símbolos únicos** | 1,621 |
| **Tipos de evento** | 5 (intraday patterns) |
| **Cobertura temporal** | 3 años (2022-10-10 → 2025-10-09) |
| **Tamaño** | 21.2 MB |
| **Calidad** | 0% duplicados, 0% nulls |
| **Sesiones** | RTH (78.8%), AH (20.7%), PM (0.5%) |

### Tipos de Evento en Input

| Tipo | Eventos | % |
|------|---------|---|
| vwap_break | 266,984 | 46.6% |
| volume_spike | 146,504 | 25.6% |
| opening_range_break | 90,728 | 15.8% |
| flush | 50,490 | 8.8% |
| consolidation_break | 18,144 | 3.2% |

---

## Configuración de Ejecución

### Script de Lanzamiento

**Path:** `scripts/execution/fase32/launch_pm_wave.py`

**Comando ejecutado:**
```bash
cd D:\04_TRADING_SMALLCAPS
python scripts/execution/fase32/launch_pm_wave.py \
  --input "processed/final/events_intraday_MASTER_dedup_v2.parquet"
```

### Parámetros Detectados

Según el output inicial del launcher:

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| **Manifest** | `processed/events/manifest_core_20251014.parquet` | Manifest de eventos core |
| **Wave** | PM | Tipo de onda a analizar |
| **Rate Limit** | 12s | Límite de tasa para API calls |
| **Quotes Hz** | 1 | Frecuencia de quotes |
| **Resume** | Enabled | Capacidad de resumir desde checkpoint |

### Proceso Subyacente

**Script:** `scripts/ingestion/download_trades_quotes_intraday_v2.py`

**Función:** Descargar trades y quotes intraday para análisis de ondas

**Log file:** `logs/fase3.2_pm_wave_running.log`

---

## Arquitectura de Procesamiento

### Flujo de Datos

```
Input: events_intraday_MASTER_dedup_v2.parquet (572,850 eventos)
  ↓
[1] Manifest Generation
  ↓
Manifest: manifest_core_20251014.parquet (eventos core filtrados)
  ↓
[2] Data Ingestion (Wave: PM)
  ↓
Download trades & quotes intraday (rate-limited)
  ↓
[3] Wave Detection
  ↓
Identify price waves post-event
  ↓
[4] Momentum Analysis
  ↓
Calculate velocity, acceleration, reversals
  ↓
[5] Score Normalization
  ↓
Output: events_with_waves_enriched.parquet
```

### Componentes Principales

1. **Manifest Generator**
   - Filtra eventos core del input
   - Genera manifest para procesamiento

2. **Data Ingester**
   - Descarga trades/quotes necesarios
   - Respeta rate limits de API
   - Resume capability habilitado

3. **Wave Detector**
   - Analiza precio post-evento
   - Clasifica ondas (continuity/reversal)
   - Mide amplitud y duración

4. **Momentum Calculator**
   - Calcula velocidad de movimiento
   - Detecta aceleración/desaceleración
   - Identifica puntos de inflexión

5. **Score Normalizer**
   - Ajusta scores por calidad de wave
   - Incorpora métricas de momentum
   - Genera score compuesto

---

## Estado Inicial

### Sistema

**Watchdog Fase 2.5:** Pausado (flag: `RUN_PAUSED.flag`)

**Checkpoint Fase 2.5:** 1,839 / 1,996 (92.1%)

**Dataset validado:** ✅ Certificado para producción

### Lanzamiento

**Fecha/hora:** 16 de Octubre, 2025 ~23:10 UTC

**Estado:** Iniciado

**Log activo:** `logs/fase3.2_pm_wave_running.log`

### Próximos Checkpoints

- [ ] Verificar generación correcta de manifest
- [ ] Confirmar inicio de descarga de datos
- [ ] Monitorear progreso de wave detection
- [ ] Validar métricas de momentum
- [ ] Revisar scores normalizados

---

## Métricas Esperadas de Output

### Dataset de Salida Esperado

**Nombre sugerido:** `processed/waves/events_with_waves_enriched.parquet`

**Columnas adicionales esperadas:**
- `wave_direction` (continuity/reversal)
- `wave_amplitude` (max move desde evento)
- `wave_duration` (tiempo hasta max/reversal)
- `momentum_velocity` (velocidad de movimiento)
- `momentum_acceleration` (aceleración)
- `reversal_point` (timestamp de reversión si aplica)
- `score_normalized` (score ajustado)
- `wave_quality` (calidad de la onda)

### Métricas de Calidad Esperadas

- **Tasa de continuidad global:** 50-70% (benchmark)
- **Tiempo promedio a wave peak:** 5-30 minutos
- **Amplitud promedio de wave:** 1-5% del precio
- **Tasa de reversión temprana:** <20%

---

## Monitoreo y Logging

### Archivos de Log

**Principal:** `logs/fase3.2_pm_wave_running.log`

**Ubicación:** `D:\04_TRADING_SMALLCAPS\logs\`

**Formato esperado:**
```
[TIMESTAMP] [LEVEL] [COMPONENT] Message
```

### Comandos de Monitoreo

**Ver log en tiempo real:**
```powershell
Get-Content -Path "logs\fase3.2_pm_wave_running.log" -Wait -Tail 50
```

**Verificar progreso:**
```powershell
python scripts/monitoring/check_fase32_progress.py
```

**Estadísticas actuales:**
```powershell
python scripts/analysis/fase32_stats.py
```

---

## Dependencias y Requisitos

### Python Packages

- `polars` >= 0.19.0 (data processing)
- `pandas` >= 2.0.0 (legacy support)
- `numpy` >= 1.24.0 (numerical)
- `requests` >= 2.31.0 (API calls)
- API client configurado (para trades/quotes)

### Datos Externos

**API de mercado:** Configurada para trades & quotes intraday

**Rate limits:** 12s entre llamadas (configurado)

**Cobertura requerida:** Misma del input (2022-10-10 → 2025-10-09)

---

## Documentación de Referencia

### Fase 2.5 (Completada)

1. **Auditoría Final**
   - `docs/Daily/fase_4/12_fase_25_auditoria_final.md`
   - Auditoría inicial + corrección

2. **Consolidación Maestra**
   - `docs/Daily/fase_4/13_fase_25_consolidacion_maestra_FINAL.md`
   - Proceso correcto de consolidación

3. **Validación Final**
   - `docs/Daily/fase_4/14_validacion_final_dataset_fase_25.md`
   - Certificación científica del dataset

### Fase 3.2 (Actual)

**Este documento:** Registro de inicio y configuración

**Próximos documentos:**
- `02_fase_32_progreso.md` (updates de progreso)
- `03_fase_32_resultados.md` (resultados finales)

---

## Notas de Ejecución

### Observaciones Iniciales

1. **Script launcher:** Presenta error de encoding Unicode (checkmark ✓)
   - Error no crítico, ocurre al final del launch
   - Proceso subyacente parece haberse iniciado correctamente

2. **Manifest detectado:** Usando `manifest_core_20251014.parquet`
   - Puede ser un manifest pre-existente
   - Verificar si corresponde al input actual

3. **Wave type:** Iniciado con wave "PM" (Premarket)
   - Puede ser primera fase de análisis
   - Verificar si procesará todas las sesiones (PM/RTH/AH)

### Acciones Pendientes

- [ ] Verificar que el proceso está ejecutándose
- [ ] Confirmar que usa el input correcto (MASTER_dedup_v2)
- [ ] Revisar log inicial para confirmar progreso
- [ ] Validar que manifest corresponde a los 572,850 eventos

---

## Estimaciones Preliminares

### Tiempo de Ejecución Estimado

Basado en:
- 572,850 eventos a procesar
- Rate limit: 12s por llamada
- Múltiples waves (PM/RTH/AH)

**Estimación conservadora:** 6-12 horas

**Factores que afectan tiempo:**
- Disponibilidad de datos en caché
- Tasa de aciertos en resume
- Complejidad de wave detection
- Carga de API externa

### Recursos Estimados

**Storage:** +500 MB - 1 GB (trades/quotes descargados)

**Memory:** 4-8 GB RAM durante procesamiento

**CPU:** Moderado (I/O bound por API calls)

---

## Criterios de Éxito

### Completitud

- [ ] Todos los 572,850 eventos procesados
- [ ] Waves detectadas para >90% de eventos
- [ ] Momentum calculado para todos los eventos con wave
- [ ] Scores normalizados para todos los eventos

### Calidad

- [ ] 0% eventos con datos faltantes en columnas críticas
- [ ] Distribución razonable de continuity vs reversal
- [ ] Métricas de momentum en rangos esperados
- [ ] Scores normalizados correlacionan con calidad de wave

### Validación

- [ ] Muestra visual de waves generadas
- [ ] Estadísticas por tipo de evento
- [ ] Comparación scores original vs normalizado
- [ ] Casos de estudio de eventos de alta calidad

---

## Siguiente Fase

**Fase 4:** Pattern Recognition & Strategy Generation

**Input esperado:** Output de Fase 3.2 (events_with_waves_enriched)

**Objetivo:** Identificar patrones repetibles de alto rendimiento para estrategias de trading

---

**Estado actual:** ⏳ FASE 3.2 EN EJECUCIÓN

**Próxima actualización:** Monitoreo de progreso y primeros resultados

**Fecha de inicio:** 16 de Octubre, 2025 23:10 UTC
