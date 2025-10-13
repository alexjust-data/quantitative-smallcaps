# FASE 3.2 - Roadmap Completo: De Eventos a Microestructura

**Fecha**: 2025-10-13
**Estado**: En preparación (FASE 2.5 en curso 15.8%)
**Objetivo**: Descargar ventanas de trades+quotes para ~10K eventos intraday de alta calidad

---

## 📋 Pipeline Completo

```
FASE 2.5 (Detección)
    ↓
Enriquecimiento (métricas diarias)
    ↓
Dry-Run CORE (validación)
    ↓
Manifest CORE (selección final)
    ↓
FASE 3.2 (descarga trades+quotes)
```

---

## 1️⃣ FASE 2.5 - Detección de Eventos Intraday

### Estado Actual
- **Progreso**: 315/1,996 símbolos (15.8%)
- **Sistema**: Ultra Robust Orchestrator (3 workers)
- **ETA**: ~2.8 días
- **Output**: `processed/events/shards/events_intraday_20251013_shard*.parquet`

### Eventos Detectados (hasta ahora)
- **Total**: ~697K eventos
- **Símbolos**: 1,073 únicos
- **Periodo**: 2022-10-10 a 2025-10-09 (3 años)

### Tipos de Eventos
- Volume Spike
- VWAP Break (reclaim/rejection)
- Price Momentum
- Consolidation Break
- Opening Range Break
- Flush Detection

---

## 2️⃣ Enriquecimiento - Métricas de Liquidez Diaria

### Propósito
Agregar métricas diarias necesarias para filtros CORE que no están en eventos raw:
- `dollar_volume_day` - Volumen diario × VWAP diario (RAW)
- `rvol_day` - Volumen relativo vs media 20 días (sin look-ahead)
- Recalcular sesiones PM/RTH/AH en timezone ET

### Script
```bash
python scripts/processing/enrich_events_with_daily_metrics.py
```

### Input
- `processed/events/shards/events_intraday_*_shard*.parquet`
- `raw/market_data/bars/1d_raw/*.parquet` (daily bars RAW)

### Output
`processed/events/events_intraday_enriched_YYYYMMDD.parquet`

### Esquema Completo

#### Clave y Tiempo
- `symbol` (str) - Ticker
- `timestamp_utc` (datetime[UTC]) - Timestamp exacto evento
- `timestamp_et` (datetime[America/New_York]) - Mismo instante en ET
- `date_et` (date) - Fecha trading en ET
- `session` (enum: PM|RTH|AH) - Sesión horaria ET

#### Identidad del Evento
- `event_type` (str) - Tipo: volume_spike | vwap_break | etc.
- `score` (float32) - Score 0-1
- `rank_in_symbol_day` (uint16) - Ranking por (symbol, date_et)
- `rank_in_symbol_month` (uint16) - Ranking por (symbol, year, month)

#### Métricas Intradía (minuto del evento)
- `open_min`, `high_min`, `low_min`, `close_min` (float32)
- `vwap_min` (float32) - VWAP o TYP=(H+L+C)/3
- `volume_min` (int32)
- `dollar_volume_bar` (float64) - volume_min × vwap_min
- `spread_proxy` (float32) - (high-low)/vwap

#### Métricas Diarias (RAW)
- `open_d`, `high_d`, `low_d`, `close_d` (float32)
- `vwap_d` (float32) - VWAP diario o TYP
- `volume_d` (int64)
- `dollar_volume_day` (float64) - **volume_d × vwap_d**
- `rvol_day` (float32) - **dv_day / mean(20d previos)**
- `rvol_day_missing` (bool) - true si <20 días previos

#### Guard-rails y Trazabilidad
- `price_raw` (float32) - vwap_min sin clip
- `price_clipped` (float32) - clip [1.0, 200.0]
- `event_bias` (str) - up/down/neutral
- `close_vs_open` (float32) - (close-open)/open
- `tier_hint` (str) - CORE|PLUS|PREMIUM
- `source_shard` (str) - origen
- `enrichment_version` (str) - v1.0
- `config_hash` (str) - reproducibilidad

### Notas Críticas
- **Join diario**: usar `date_et` (no UTC)
- **rvol_day**: rolling 20 días `closed='left'` (sin look-ahead)
- **Sesiones ET**: PM 04:00-09:30, RTH 09:30-16:00, AH 16:00-20:00

---

## 3️⃣ Dry-Run CORE - Validación Pre-Manifest

### Propósito
Proyectar cuántos eventos calificarían con filtros CORE completos ANTES de generar manifest real.

### Estado Actual
✅ **Dry-run con proxies completado** (parcial, sin dv_day ni rvol_day):
- Input: 697K eventos
- Output: 8.7K eventos (dentro rango 8-12K)
- **Sesiones recalculadas**: PM 18.2%, RTH 79.0%, AH 2.8%

⚠️ **Pendiente**: Dry-run completo con eventos enriquecidos (5/5 filtros)

### Filtros CORE Completos

#### 1. Calidad Mínima
- `score ≥ 0.60`
- Sin NaN en: dollar_volume_bar, volume_min, spread_proxy, dollar_volume_day, rvol_day
- `rvol_day_missing == false`

#### 2. Liquidez Intradía
- `dollar_volume_bar ≥ $100K`
- `volume_min ≥ 10K shares`
- `spread_proxy ≤ 5%`

#### 3. Liquidez Diaria
- `dollar_volume_day ≥ $500K`
- `rvol_day ≥ 1.5x`

#### 4. Diversidad
- **1 evento mínimo por símbolo** (cobertura amplia)
- **Fill hasta máx 5 por símbolo** (calidad por score)
- **Máx 1 por (símbolo, date_et)**
- **Máx 20 por (símbolo, mes)**

#### 5. Cuotas de Sesión (ENFORCE)
- **PM**: 10-20% (target 15%)
- **RTH**: 75-85% (target 80%)
- **AH**: 3-10% (target 5%)

**Mecanismo de enforce**:
- Si PM < 10%: relajar en PM -10% dollar_volume_bar o -0.1 rvol_day
- Si AH > 10%: recortar por score en AH hasta rango

#### 6. Cap Global
- Seleccionar **top 10,000 eventos**
- Orden estable: (score DESC, rvol_day DESC, dollar_volume_bar DESC, timestamp ASC)

### Comando
```bash
python scripts/analysis/generate_core_manifest_dryrun.py \
  --input processed/events/events_intraday_enriched_YYYYMMDD.parquet \
  --profile core
```

---

## 4️⃣ Manifest CORE - Selección Final

### Propósito
Generar lista definitiva de 10K eventos para descargar en FASE 3.2.

### Criterios de GO/NO-GO

**DEBE PASAR TODO** antes de lanzar 3.2:

- [ ] **Sanity checks**:
  - 8-12K eventos seleccionados
  - ≥400 símbolos únicos
  - Mediana score ≥ 0.70
  - Mediana rvol_day ≥ 2.0x

- [ ] **Sesiones equilibradas**:
  - PM: 10-20%
  - RTH: 75-85%
  - AH: 3-10%

- [ ] **Diversidad**:
  - Top-20 símbolos < 25% concentración

- [ ] **Estimaciones operativas**:
  - Storage p90 < 250 GB
  - Time p90 < 3 días

- [ ] **Calidad de datos**:
  - 0 NaN en métricas clave
  - rvol_day_missing == false para todos

- [ ] **Reproducibilidad**:
  - config_hash presente
  - enrichment_version documentado

### Comando
```bash
python scripts/processing/build_intraday_manifest.py \
  --input processed/events/events_intraday_enriched_YYYYMMDD.parquet \
  --output processed/events/manifest_core_YYYYMMDD.parquet \
  --profile core --enforce-quotas
```

### Output
`processed/events/manifest_core_YYYYMMDD.parquet`

Contiene ~10K filas con todas las columnas enriquecidas más:
- `manifest_rank` (int) - posición en manifest (1-10000)
- `selection_reason` (str) - "coverage" o "fill_by_score"
- `session_quota_met` (bool) - si cumplió cuotas

---

## 5️⃣ FASE 3.2 - Descarga Trades + Quotes

### Propósito
Descargar ventanas de microestructura ([-3min, +7min]) para cada evento en manifest.

### Comando
```bash
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/manifest_core_YYYYMMDD.parquet \
  --resume
```

### Parámetros de Ventana
- **Antes**: 3 minutos
- **Después**: 7 minutos
- **Total**: 11 minutos (660 segundos)

### Output Structure
```
raw/market_data/event_windows/
  symbol=AAPL/
    event_20230515_093247_volume_spike/
      trades.parquet
      quotes.parquet
      metadata.json
  symbol=TSLA/
    event_20230620_141523_vwap_break/
      trades.parquet
      quotes.parquet
      metadata.json
```

### Features
- **Resume**: Detecta ventanas ya descargadas (skip si existe)
- **Retry logic**: 3 reintentos con backoff exponencial
- **Rate limiting**: Respeta 429 de Polygon
- **Checkpointing**: Guarda progreso cada 100 eventos
- **Parallelism**: 3 workers concurrentes

### Estimaciones (por evento)
- **Storage**:
  - Trades: p50=8.5MB, p90=25MB
  - Quotes: p50=3.2MB, p90=12MB
  - Total p90: ~37MB/evento
- **Tiempo**: p50=12s, p90=18s por evento
- **Total proyectado**: ~370GB, ~50 horas (2.1 días) para 10K eventos

---

## 📊 Archivos Clave Generados

### Especificaciones
1. `docs/Daily/fase_3.2/MANIFEST_CORE_SPEC.md` (25KB)
   - Esquema de 25 columnas
   - Filtros de 5 etapas
   - Cuotas de sesión
   - Desempate estable
   - Sanity checks (13 obligatorios)

### Scripts
2. `scripts/processing/enrich_events_with_daily_metrics.py`
   - Agrega dollar_volume_day y rvol_day
   - Recalcula sesiones en ET
   - Join con daily bars RAW

3. `scripts/processing/generate_core_manifest_dryrun_proxy.py`
   - Dry-run con proxies (temporal)
   - Útil para dimensionamiento inicial

4. `scripts/processing/generate_core_manifest_dryrun.py` (pendiente)
   - Dry-run completo sin proxies
   - Usa eventos enriquecidos
   - Enforce de cuotas

5. `scripts/processing/build_intraday_manifest.py` (pendiente)
   - Genera manifest final
   - Implementa selección 1+fill hasta 5
   - Aplica enforce de sesiones

6. `scripts/ingestion/download_trades_quotes_intraday.py` (pendiente)
   - Descarga microestructura
   - Resume + retry logic
   - Checkpointing cada 100 eventos

---

## 🔧 Config.yaml Updates

Agregar bajo `processing:`:

```yaml
processing:
  enrichment:
    enable: true
    daily_dir_raw: "raw/market_data/bars/1d_raw"
    timezone_market: "America/New_York"
    rvol_lookback_days: 20
    require_complete_rvol: true

  core_manifest:
    max_events: 10000
    # Liquidez intradía
    min_dollar_volume_bar: 100000
    min_absolute_volume_bar: 10000
    max_spread_proxy_pct: 5.0
    # Liquidez diaria
    min_dollar_volume_day: 500000
    rvol_day_min: 1.5
    # Diversidad
    max_per_symbol: 5
    max_per_symbol_day: 1
    max_per_symbol_month: 20
    # Sesiones
    quotas:
      PM: { target: 0.15, min: 0.10, max: 0.20 }
      RTH: { target: 0.80, min: 0.75, max: 0.85 }
      AH: { target: 0.05, min: 0.03, max: 0.10 }
    # Ventanas para 3.2
    window_before_min: 3
    window_after_min: 7

  intraday_download:
    enable: true
    data_types: ["trades", "quotes"]
    max_workers: 3
    retry_attempts: 3
    checkpoint_interval: 100
    resume: true
```

---

## 🎯 Timeline Estimado

| Etapa | Duración | Dependencias |
|-------|----------|--------------|
| FASE 2.5 (resto) | ~2.8 días | En curso |
| Enriquecimiento | ~30 min | FASE 2.5 completa |
| Dry-run completo | ~5 min | Enriquecimiento |
| Validación GO/NO-GO | ~10 min | Dry-run |
| Manifest generación | ~2 min | GO aprobado |
| **FASE 3.2 descarga** | **~2.1 días** | Manifest |

**Total desde hoy**: ~5 días calendario

---

## ⚠️ Problemas Resueltos

1. **PM=0% en dry-run inicial** → ✅ Resuelto con recalc sesiones ET (ahora 18.2%)
2. **Métricas de liquidez faltantes** → ✅ Script enriquecimiento creado
3. **Estructura 1d_raw** → ✅ Ajustada a archivos planos por símbolo

---

## 📝 Notas Importantes

### Por Qué Este Orden
- **Enriquecimiento primero**: Evita descargar eventos que caerán por rvol_day/dv_day
- **Dry-run antes de manifest**: Valida hipótesis sin comprometer bandwidth
- **Enforce de sesiones**: Previene sesgo hacia RTH; dataset equilibrado
- **Selección 1+fill**: Garantiza diversidad amplia sin sacrificar calidad

### Riesgos Mitigados
- ✅ Look-ahead bias en rvol_day (rolling left-closed)
- ✅ Sesgo horario (enforce PM/RTH/AH quotas)
- ✅ Sobre-concentración (caps por símbolo/día/mes)
- ✅ Falsos positivos liquidez (filtros 5/5 aplicados)
- ✅ Reproducibilidad (config_hash + enrichment_version)

---

## 🚀 Próximos Pasos Inmediatos

1. ⏳ **Esperar FASE 2.5** (~500-800 símbolos mínimo para batch inicial)
2. ▶️ **Ejecutar enriquecimiento**
3. ▶️ **Dry-run completo** con eventos enriquecidos
4. ✅ **Validar GO/NO-GO** checklist
5. 🚀 **Lanzar FASE 3.2**

---

**Última actualización**: 2025-10-13 20:15 UTC
**Estado Ultra Robust Orchestrator**: 315/1,996 símbolos (15.8%)
