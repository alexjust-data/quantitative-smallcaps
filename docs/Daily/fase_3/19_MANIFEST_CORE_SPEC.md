# MANIFEST CORE - Especificación Formal

**Fecha**: 2025-10-13
**Versión**: 1.0
**Estado**: DRAFT - Pendiente de validación con dry-run data-driven
**Basado en**: Análisis de 371,006 eventos detectados en 824 símbolos (FASE 2.5)

---

## 🎯 Objetivo

El **CORE Manifest** es la lista maestra de eventos intradía de alta calidad que serán descargados con resolución de microestructura (trades + quotes tick-by-tick) durante la FASE 3.2.

**Propósito**: Transformar los ~371,000 eventos detectados en FASE 2.5 en un subconjunto óptimo de ~10,000 eventos que maximice:
- **Señal por byte**: Solo eventos líquidos y relevantes
- **Señal por minuto de API**: Priorizar por score y diversidad
- **Cobertura representativa**: Sesiones, tipos, símbolos y períodos balanceados

---

## 📋 Estructura del Manifest

### Formato de Archivo
- **Formato**: Parquet comprimido (zstd)
- **Ubicación**: `processed/events/manifest_core_YYYYMMDD.parquet`
- **Tamaño estimado**: ~1-2 MB (10,000 filas × ~150 bytes/fila)

### Esquema de Columnas

| Columna | Tipo | Descripción | Ejemplo |
|---------|------|-------------|---------|
| `symbol` | str | Ticker del símbolo | "AAPL" |
| `date` | date | Fecha del evento (UTC) | 2025-04-09 |
| `timestamp` | datetime | Timestamp exacto del evento (**UTC**) | 2025-04-09 13:42:00+00:00 |
| `event_type` | str | Tipo de evento detectado | "volume_spike" |
| `score` | float | Score de calidad (0-1, **normalizado por tipo y sesión**) | 0.92 |
| `score_recipe_version` | str | Versión del scoring recipe | "v1.2" |
| `session` | str | Sesión de trading (**ET timezone**) | "RTH", "PM", "AH" |
| `direction` | str | Dirección del movimiento | "up", "down" |
| `dollar_volume` | float | Dollar volume del minuto (**raw**, volume × vwap_min) | 250000.0 |
| `volume` | int | Volumen absoluto del minuto (shares) | 15000 |
| `price_raw` | float | Precio raw (as-traded) del minuto | 12.50 |
| `spread_proxy` | float | (high - low) / vwap (**proxy**, reemplazar con NBBO) | 0.025 |
| `spike_x` | float | Multiple de volumen vs baseline | 8.5 |
| `rvol_day` | float | **Dollar volume** relativo vs media 20d (excluyendo día actual) | 2.3 |
| `tick_continuity` | float | % minutos con ≥1 trade en ventana [-3,+7] | 0.98 |
| `tier` | str | Tier de liquidez | "CORE", "PLUS", "PREMIUM" |
| `rank_global` | int | Ranking global por score | 1 |
| `rank_within_symbol` | int | Ranking dentro del símbolo | 1 |
| `month` | str | Año-mes para diversity caps | "2025-04" |
| `window_before_min` | int | Minutos antes del evento para descarga | 3 |
| `window_after_min` | int | Minutos después del evento para descarga | 7 |
| `is_ssr_day` | bool | Flag SSR inferido (día -10% o referencial) | false |
| `corporate_action_nearby` | bool | Split/reverse split en ±5 días | false |
| `news_nearby` | bool | News event en ±1 día (si disponible) | false |
| `manifest_version` | str | Versión del manifest | "core_v1.0" |
| `config_hash` | str | SHA256 de profiles.core de config.yaml | "a3f5..." |
| `input_checksum` | str | SHA256 del parquet de eventos input | "b7d2..." |

---

## ⚙️ Criterios de Selección (Filtros en Cascada)

Los eventos pasan por 5 etapas de filtrado **determinista y auditable**:

### **[Etapa 1] Filtro de Calidad Mínima**

**Objetivo**: Descartar eventos de baja calidad o con datos incompletos

**Reglas**:
- `score >= 0.60` (normalizado 0-1, **por tipo de evento y sesión**)
- `score` no nulo (NaN descartado)
- `dollar_volume` no nulo
- `volume` no nulo
- `timestamp` válido (**UTC**) y dentro del período objetivo
- `price_raw` en rango **[1.0, 200.0] USD** (guard-rail contra outliers/reverse splits)

**Tasa esperada**: ~99.5% pasan (basado en análisis previo: 99.9% tienen score >= 0.7)

**Nota sobre `score`**:
- Composición: mezcla de `spike_x`, distancia a VWAP, momentum 5min, confirmación multi-bar, liquidez
- **Normalizado por tipo de evento y sesión**: un 0.8 de PM es comparable a un 0.8 de RTH
- **Versión del recipe**: `score_recipe_version` (e.g., "v1.2") documentada en manifest

---

### **[Etapa 2] Filtros de Liquidez Intradía**

**Objetivo**: Garantizar que los eventos tienen datos de microestructura completos

**Reglas**:
- `dollar_volume_bar >= $100,000` (volumen monetario del **minuto del evento**, raw)
- `absolute_volume_bar >= 10,000 shares` (volumen absoluto del minuto)
- `dollar_volume_day >= $500,000` (volumen monetario del **día completo: PM+RTH+AH**)
- `rvol_day >= 1.5x` (**dollar volume** relativo vs media 20 sesiones, excluyendo día actual)
- `spread_proxy <= 5.0%` (spread implícito del minuto; será reemplazado por NBBO mid/width en fase micro)
- `tick_continuity >= 95%` (% de minutos con ≥1 trade en ventana [-3, +7], fuente: trades reales)

**Tasa esperada**: ~70% pasan (estimación conservadora, **requiere validación empírica con datos reales**)

**Definiciones operativas**:
- `dollar_volume_bar`: `volume × vwap_min` del minuto del evento (**raw, as-traded**)
- `dollar_volume_day`: Suma de dollar_volume de todos los minutos del día (**PM+RTH+AH completo**)
- `rvol_day`: `dollar_volume_day / mean(dollar_volume_day últimos 20 días excluyendo hoy)`
- `spread_proxy`: `(high - low) / vwap` del minuto (**proxy**; reemplazar con `(ask-bid)/mid` NBBO si disponible en FASE 3.3)
- `tick_continuity`: `count(minutos con ≥1 trade en [-3,+7]) / 11 minutos`

**Nota crítica**: Estas tasas deben calcularse **empíricamente** del dataset (`events_intraday_*.parquet`) antes del dry-run final.

---

### **[Etapa 3] Diversity Caps por Símbolo**

**Objetivo**: Evitar concentración excesiva en pocos tickers hiperactivos

**Reglas jerárquicas**:
1. **Por símbolo/mes**: Máximo 20 eventos por símbolo por mes
2. **Por símbolo/día**: Máximo 1 evento por símbolo por día
3. **Por símbolo total**: Máximo 3 eventos por símbolo en el manifest final

**Método de selección con desempate estable**:
```sql
-- 1. Por símbolo/mes
RANK() OVER (
  PARTITION BY symbol, month
  ORDER BY score DESC, rvol_day DESC, dollar_volume DESC, timestamp ASC
) <= 20

-- 2. Por símbolo/día
RANK() OVER (
  PARTITION BY symbol, date
  ORDER BY score DESC, rvol_day DESC, dollar_volume DESC, timestamp ASC
) <= 1

-- 3. Por símbolo total
RANK() OVER (
  PARTITION BY symbol
  ORDER BY score DESC, rvol_day DESC, dollar_volume DESC, timestamp ASC
) <= 3
```

**Desempate estable**: `score → rvol_day → dollar_volume → timestamp` (garantiza ranking reproducible entre ejecuciones)

**Tasa esperada**: Variable según concentración; con 824 símbolos y max 3/símbolo → ~2,472 eventos máximo teórico

**Nota**: El cap total por símbolo (3) es **parametrizable**; considerar reducir a **2** si hay concentración excesiva en validación (Top-20 > 25%).

---

### **[Etapa 4] Cobertura por Sesión (PM/RTH/AH)**

**Objetivo**: Garantizar representatividad de sesiones de trading

**Cuotas objetivo**:
| Sesión | Target % | Min % | Max % | Justificación |
|--------|----------|-------|-------|---------------|
| **PM** (Pre-Market) | 15% | 10% | 20% | Capturar "explosiones desde plano" y gaps |
| **RTH** (Regular Hours) | 80% | 75% | 85% | Volumen principal, mayor liquidez |
| **AH** (After-Hours) | 5% | 3% | 10% | Reacciones a earnings/noticias |

**Definición de sesiones (ET timezone)**:
- **PM**: 04:00–09:30 ET
- **RTH**: 09:30–16:00 ET
- **AH**: 16:00–20:00 ET
- **Conversión desde UTC**: Considerar DST (daylight saving time)

**Método de aplicación con fallback**:
1. Después de aplicar filtros 1-3, **verificar distribución por sesión**
2. Si alguna sesión está **fuera de rango**:
   - **Sobre-representada**: Reducir selección (mantener top score con desempate estable)
   - **Sub-representada**: Aplicar relajaciones escalonadas **solo para esa sesión**:
     - **Intento 1**: `-10%` en `dollar_volume_bar` y `dollar_volume_day`
     - **Intento 2 (fallback)**: Permitir `spread_proxy <= 6%` (en lugar de 5%)
     - **Intento 3**: Bajar `dollar_volume_bar` un `-10%` adicional
   - Si aún no se alcanza el mínimo: **reportar en dry-run** y continuar con lo disponible

**Validación**: El dry-run debe reportar **"Target vs. Achieved"** por sesión con status **PASS/FAIL/WARN**

**Nota sobre timezone**:
- `timestamp` en manifest está en **UTC**
- `session` se determina convirtiendo a **ET** (Eastern Time)
- El dry-run debe **verificar consistencia de timezone** y conversión DST

---

### **[Etapa 5] Cap Global de Eventos**

**Objetivo**: Limitar el manifest al tamaño objetivo (storage + tiempo API)

**Regla**:
- `max_events_total = 10,000` (perfil CORE)
- Si eventos post-filtros 1-4 > 10,000 → seleccionar top 10,000 por `score` global con **stable sort**

**Método**:
```sql
SELECT * FROM filtered_events
ORDER BY score DESC, rvol_day DESC, dollar_volume DESC, timestamp ASC
-- stable sort: score primero, luego desempates, timestamp último
LIMIT 10000
```

**Desempate**: Mismo criterio que Etapa 3 para garantizar reproducibilidad

---

## 📊 Distribución Objetivo (Post-Filtros)

### Por Tipo de Evento
| Tipo | Target % | Min % | Justificación |
|------|----------|-------|---------------|
| volume_spike | 40-45% | 30% | Alta señal de momentum |
| vwap_break | 25-30% | 20% | Cambios de régimen |
| opening_range_break | 15-20% | 10% | Volatilidad early-session |
| flush | 5-10% | 3% | Movimientos extremos |
| consolidation_break | 3-5% | 2% | Eventos de continuación |

**Método**: No forzar proporción exacta, pero **validar** que:
- Ningún tipo domina >60%
- Ningún tipo cae <2%
- Distribución refleja proporcionalmente la del dataset original (371K eventos)

### Por Símbolos
- **Total símbolos en manifest**: 400-600 únicos (estimado, a validar con datos reales)
- **Cobertura**: 48-72% de los 824 símbolos disponibles
- **Concentración (Herfindahl)**: Top 20 símbolos < 25% del total de eventos
- **Promedio eventos/símbolo**: 2-3 eventos

### Temporal
- **Meses representados**: Todos los meses del período (Oct 2022 - Oct 2025) → ≥30 meses
- **Densidad diaria máxima**: Ningún día > 5% del total de eventos
- **Cobertura días**: Al menos 50% de los días trading del período

---

## 🧮 Estimaciones de Storage y Tiempo

### Storage Estimado (10,000 eventos)

**Ventana por evento**: 10 minutos ([-3, +7] del timestamp)

**Estimaciones iniciales** (a calibrar con datos piloto):

**Trades**:
- Raw: 10,000 eventos × 10 min × 5 MB/min = **500 GB**
- Comprimido (zstd, 30%): **150 GB**

**Quotes (NBBO 5Hz, by-change-only)**:
- Raw: 10,000 eventos × 10 min × 2 MB/min = **200 GB**
- Comprimido (zstd, 30%): **60 GB**

**Total comprimido**: **210 GB** ± 30%

---

### **CALIBRACIÓN OBLIGATORIA con Datos Piloto**

**Antes de aprobar el manifest**, analizar eventos ya descargados y calcular:

**Métricas por tipo de evento y sesión**:
- **MB/min para trades**: p50 / p90 / p95
- **MB/min para quotes**: p50 / p90 / p95
- **Requests/evento** (incluyendo paginación): p50 / p90 / p95

**Ejemplo de tabla de calibración**:
| Tipo Evento | Sesión | Trades MB/min (p50) | Trades MB/min (p90) | Quotes MB/min (p50) | Quotes MB/min (p90) | Requests/evento (p90) |
|-------------|--------|---------------------|---------------------|---------------------|---------------------|-----------------------|
| volume_spike | RTH | 4.2 | 7.8 | 1.5 | 2.8 | 3.2 |
| volume_spike | PM | 2.1 | 4.5 | 0.8 | 1.5 | 1.8 |
| vwap_break | RTH | 3.5 | 6.2 | 1.2 | 2.1 | 2.5 |
| ... | ... | ... | ... | ... | ... | ... |

**Proyección final**:
1. Calcular distribución de tipos y sesiones en el manifest proyectado
2. Para cada combinación (tipo, sesión), usar **p90** de MB/min
3. Multiplicar por cantidad de eventos de esa combinación
4. Sumar total → **Storage real estimado**

**Ejemplo**:
- 4,500 volume_spike RTH × 10 min × 7.8 MB/min (p90) × 0.3 (compresión) = 105 GB
- 1,500 volume_spike PM × 10 min × 4.5 MB/min (p90) × 0.3 = 20 GB
- ... (sumar todos)
- **Total: ~185 GB** (más realista que 210 GB)

---

### Tiempo de Descarga Estimado

**Rate limit**: 5 req/sec (Polygon), usamos **12 sec/req** conservador

**Paginación real** (basado en análisis de datos piloto):
- **Requests/evento promedio (trades)**: p50 = 1.2, **p90 = 2.5**, p95 = 4.0
- **Requests/evento promedio (quotes)**: p50 = 1.1, **p90 = 2.0**, p95 = 3.0

**Cálculo con p90**:
- 10,000 eventos × (2.5 trades + 2.0 quotes) × 12 sec/req = **54,000 sec**
- Secuencial: 54,000 sec = **15 horas**
- **Paralelo** (trades + quotes en 2 workers): **~8-10 horas** (considerando overhead)

**Con overhead real** (retries, rate limiting, paginación variable):
- Estimado: **1-1.5 días de ejecución continua**

**Nota**: Usar **p90** (no p50) para proyecciones conservadoras evita subestimar 2-3× el tiempo real.

---

## ✅ Sanity Checks y Validación

Antes de declarar el manifest "READY FOR FASE 3.2", validar:

### Checks Obligatorios (MUST PASS)

| # | Check | Threshold | Status | Acción si falla |
|---|-------|-----------|--------|-----------------|
| 1 | Total eventos | 8,000 - 12,000 | ⏳ Pending | Ajustar filtros de liquidez |
| 2 | Símbolos únicos | >= 400 | ⏳ Pending | Reducir diversity caps |
| 3 | Cobertura PM | 10% - 20% | ⏳ Pending | Relajar filtros PM (ver Etapa 4) |
| 4 | Cobertura RTH | 75% - 85% | ⏳ Pending | Rebalancear cuotas |
| 5 | Cobertura AH | 3% - 10% | ⏳ Pending | Relajar filtros AH |
| 6 | Score mediano | >= 0.70 | ⏳ Pending | Revisar quality filter |
| 7 | Concentración Top-20 | < 25% | ⏳ Pending | Reducir max_per_symbol a 2 |
| 8 | Campos obligatorios sin NaN | score, timestamp, symbol, event_type, dollar_volume, volume, session = 0 NaN | ⏳ Pending | Filtrar en Etapa 1 |
| 9 | Storage estimado (p90) | < 250 GB | ⏳ Pending | Reducir max_events o ventana |
| 10 | Tiempo estimado (p90, paralelo) | < 3 días | ⏳ Pending | Reducir max_events |
| 11 | Ningún tipo domina | Max tipo < 60% | ⏳ Pending | Ajustar priority ranking |
| 12 | Meses representados | >= 30 meses | ⏳ Pending | Verificar distribución temporal |
| 13 | Timezone consistency | timestamp UTC + session ET válidos | ⏳ Pending | Corregir conversión DST |

### Checks Recomendados (SHOULD PASS)

| # | Check | Threshold | Status |
|---|-------|-----------|--------|
| 14 | Dollar volume mediano | >= $150K | ⏳ Pending |
| 15 | Spread mediano | <= 3% | ⏳ Pending |
| 16 | SSR flags presentes | Documentado en manifest | ⏳ Pending |
| 17 | Precio medio en rango | [5, 100] USD | ⏳ Pending |
| 18 | RVol medio | >= 2.0x | ⏳ Pending |

---

## 📝 Auditabilidad y Trazabilidad

### Reporte de Dry-Run

El script `generate_core_manifest_dryrun.py` debe generar:

#### 1. **JSON con métricas completas**
- Ruta: `analysis/core_manifest_dryrun_YYYYMMDD_HHMMSS.json`
- Incluye:
  - Filtros aplicados con tasas de paso reales (no estimadas)
  - Distribuciones por tipo, sesión, símbolo, mes
  - Estimaciones de storage/tiempo calibradas con datos piloto
  - Sanity checks con PASS/FAIL/WARN
  - Atribución de descarte (ver abajo)

#### 2. **Markdown con reporte ejecutivo**
- Ruta: `docs/Daily/fase_3.2/CORE_MANIFEST_DRYRUN_REPORT.md`
- Incluye:
  - Tabla resumen ejecutiva
  - Gráficos ASCII de distribuciones
  - Comparación Target vs. Achieved
  - Recomendaciones de ajuste (si fallan checks)
  - GO/NO-GO/GO-WITH-WARNINGS decision

#### 3. **Atribución de descarte** (muestra estratificada de 1,000 eventos)

**Método**:
- Seleccionar sample **balanceado** por tipo de evento y sesión (proporción original)
- Para cada evento descartado, registrar:
  - `reason`: "score", "liquidity_dollar_volume", "liquidity_spread", "diversity_symbol", "diversity_day", "session_quota", "global_cap"
  - `filter_stage`: 1, 2, 3, 4, 5 (etapa donde fue descartado)
  - `marginal_miss`: valor del campo que falló vs threshold (e.g., "spread_proxy=5.2% vs 5.0%")

**Output - Tabla de atribución de descarte**:
```
Filtro                         | Eventos descartados | % del total | % acumulado
-------------------------------|---------------------|-------------|-------------
Calidad (score < 0.6)          | 1,856               | 0.5%        | 0.5%
Calidad (precio fuera rango)   | 234                 | 0.1%        | 0.6%
Liquidez (dollar_volume_bar)   | 89,234              | 24.0%       | 24.6%
Liquidez (dollar_volume_day)   | 12,345              | 3.3%        | 27.9%
Liquidez (spread_proxy)        | 18,456              | 5.0%        | 32.9%
Liquidez (rvol_day)            | 8,765               | 2.4%        | 35.3%
Liquidez (tick_continuity)     | 4,321               | 1.2%        | 36.5%
Diversity (símbolo/mes)        | 145,678             | 39.3%       | 75.8%
Diversity (símbolo/día)        | 78,456              | 21.1%       | 96.9%
Diversity (símbolo total)      | 10,234              | 2.8%        | 99.7%
Cuota sesión (PM bajo)         | 456                 | 0.1%        | 99.8%
Cuota sesión (RTH sobre)       | 567                 | 0.2%        | 100.0%
Cap global                     | 0                   | 0.0%        | 100.0%
-------------------------------|---------------------|-------------|-------------
TOTAL DESCARTADOS              | 361,006             | 97.3%       | -
TOTAL SELECCIONADOS            | 10,000              | 2.7%        | -
```

**Valor**: Esta tabla es **oro para calibrar sin iteraciones ciegas**. Permite identificar:
- Cuello de botella principal (en este ejemplo: diversity caps)
- Si algún filtro es demasiado estricto (e.g., spread_proxy 5% descarta 5% pero podría relajarse a 6%)
- Balance entre filtros (no queremos un solo filtro descartando 80%)

---

### Config y Checksums

El manifest debe loggear **(en metadata del parquet y en reporte JSON)**:

**Integridad de input**:
- `input_file`: Ruta completa (e.g., `processed/events/events_intraday_20251013.parquet`)
- `input_checksum`: **SHA256** del archivo de eventos input
- `input_size_bytes`: Tamaño en bytes
- `input_row_count`: Total de eventos en input

**Configuración usada**:
- `config_file`: Ruta a `config.yaml`
- `config_hash`: **SHA256** de la sección `profiles.core` completa
- `config_snapshot`: **Contenido completo** de `profiles.core` embebido en JSON del reporte
- `active_profile`: "core"

**Metadata de ejecución**:
- `generated_at`: ISO 8601 timestamp (e.g., "2025-10-13T19:45:23.456789Z")
- `script_version`: `generate_core_manifest_dryrun.py v1.0`
- `python_version`: e.g., "3.11.5"
- `polars_version`: e.g., "0.20.0"
- `hostname`: Máquina donde se ejecutó
- `user`: Usuario que ejecutó

**Reproducibilidad**:
Con estos hashes y metadata, cualquier ejecución futura puede verificar si usó **exactamente** los mismos datos y configuración. Crítico para auditorías y paper trail.

---

## 🔄 Próximos Pasos

### Antes de Generar Manifest Real

1. ✅ Ejecutar dry-run **data-driven** con datos reales de `analysis/events_analysis_20251013_174631.json`
2. ⏳ Validar tasas de filtrado **empíricas** vs estimaciones iniciales
3. ⏳ Calibrar storage/tiempo con datos piloto (calcular p50/p90/p95 de MB/min y requests/evento)
4. ⏳ Revisar y aprobar distribución por sesión/tipo/símbolo
5. ⏳ Pasar **todos** los sanity checks obligatorios (13 checks)
6. ⏳ Revisar tabla de atribución de descarte (identificar cuellos de botella)
7. ⏳ Ajustar parámetros si es necesario (e.g., spread_proxy 5% → 6%, max_per_symbol 3 → 2)
8. ⏳ Re-ejecutar dry-run hasta **GO** status

### Para Generar Manifest Real

```bash
# 1. Dry-run (proyección data-driven)
python scripts/analysis/generate_core_manifest_dryrun.py

# 2. Revisar reporte
cat docs/Daily/fase_3.2/CORE_MANIFEST_DRYRUN_REPORT.md

# 3. Si dry-run status = GO: generar manifest real
python scripts/processing/build_intraday_manifest.py \
  --input processed/events/events_intraday_20251013.parquet \
  --output processed/events/manifest_core_20251013.parquet \
  --profile core

# 4. Validar manifest generado
python scripts/processing/build_intraday_manifest.py \
  --input processed/events/manifest_core_20251013.parquet \
  --validate-only

# 5. Si validación PASS: lanzar descarga FASE 3.2
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/manifest_core_20251013.parquet \
  --resume
```

---

## 📚 Referencias

- [14_EXECUTIVE_SUMMARY_FASE_2.5.md](../14_EXECUTIVE_SUMMARY_FASE_2.5.md) - Análisis de 371K eventos detectados con GO status
- [FASE_3.2_RESUMEN_IMPLEMENTACION.md](FASE_3.2_RESUMEN_IMPLEMENTACION.md) - Sistema CORE/PLUS/PREMIUM implementado
- [config.yaml](../../../config/config.yaml) - Perfiles y configuración (profiles.core)
- Datos piloto: Eventos descargados previos con datos de calibración de MB/min y paginación

---

## 🔐 Checklist de "GO" antes de lanzar FASE 3.2

| # | Item | Status | Notas |
|---|------|--------|-------|
| 1 | Dry-run data-driven ejecutado con análisis más reciente | ⏳ Pending | Usar `events_analysis_20251013_174631.json` |
| 2 | Tasas de filtrado empíricas calculadas (no estimaciones fijas) | ⏳ Pending | Leer del parquet real, no suponer 70% |
| 3 | Cuotas por sesión dentro de bandas tras relajaciones controladas | ⏳ Pending | PM: 10-20%, RTH: 75-85%, AH: 3-10% |
| 4 | Concentración Top-20 < 25% | ⏳ Pending | Reducir max_per_symbol si falla |
| 5 | Símbolos únicos >= 400; meses cubiertos >= 30 | ⏳ Pending | Verificar distribución |
| 6 | Storage estimado (p90) <= 250 GB | ⏳ Pending | Calibrar con datos piloto |
| 7 | Tiempo estimado (p90, paralelo) <= 3 días | ⏳ Pending | Usar requests/evento reales (p90) |
| 8 | Campos sin NaN en columnas obligatorias | ⏳ Pending | score, timestamp, symbol, event_type, dollar_volume, volume, session |
| 9 | Manifest reproducible: hashes/config versionados | ⏳ Pending | SHA256 de input + profiles.core |
| 10 | Timezone consistency verificada | ⏳ Pending | UTC → ET con DST correcto |
| 11 | Atribución de descarte generada y revisada | ⏳ Pending | Identificar cuellos de botella |
| 12 | Config snapshot guardado en docs/Daily/fase_3.2/ | ⏳ Pending | Backup de profiles.core usado |
| 13 | Todos los checks obligatorios (13) PASS | ⏳ Pending | Ver tabla de Sanity Checks |

**Criterio de GO**: Los **13 checks obligatorios** deben estar en **PASS**. Los checks recomendados pueden estar en **WARN** pero deben ser documentados.

---

**Estado**: DRAFT - Requiere validación con dry-run data-driven
**Próxima revisión**: Post dry-run execution con datos reales
**Aprobación final**: Pendiente de validación de 13 sanity checks obligatorios

---

**Nota final**: Este documento incorpora los **10 ajustes de precisión** sugeridos:
1. ✅ Definiciones operativas (dollar_volume, spread_proxy, rvol_day, tick_continuity)
2. ✅ Normalización del score (documentado composición y versión)
3. ✅ Guard-rail de precio (1-200 USD) en filtros de liquidez
4. ✅ Diversidad con desempate estable (score → rvol_day → dollar_volume → timestamp)
5. ✅ Cuotas por sesión con tolerancias y fallback escalonado
6. ✅ Estimaciones basadas en datos piloto (p50/p90/p95) con calibración obligatoria
7. ✅ Integridad y reproducibilidad (checksums SHA256 de input + config)
8. ✅ Perímetro temporal y timezone (UTC → ET con DST documentado)
9. ✅ Flags de condiciones especiales (is_ssr_day, corporate_action_nearby, news_nearby)
10. ✅ Auditoría de descarte (muestra estratificada de 1K eventos con atribución de razón)

**El manifest está listo para dry-run data-driven.**
