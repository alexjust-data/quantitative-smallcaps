# Event Detection & Ranking Pipeline

Scripts para detectar eventos de trading y rankear tickers para estrategia Top-2000 + Ventanas de Evento.

## Arquitectura del Pipeline

```
Week 1: Download 1d + 1h for ALL tickers (5,005 small caps)
   ↓
detect_events.py: Detect events with triple-gate logic
   ↓
rank_by_event_count.py: Rank top 2,000 by event count
   ↓
Week 2-3: Download 1m (3y) for Top-2000
   ↓
download_event_windows.py: Download 1m windows (D-2 to D+2) for remaining ~3,000
```

## Scripts

### 1. `detect_events.py`

Detecta eventos usando **triple-gate logic**:

**Lógica:**
- **Branch 1**: `(Gap ≥ 10% AND RVOL ≥ 3)`
- **Branch 2**: `(ATR% ≥ p95 AND RVOL ≥ 2.5)`
- **Filter**: `DollarVolume ≥ $2M`

**Features adicionales:**
- SSR flag (`low ≤ 0.9 * prev_close`)
- Premarket volume filter (opcional, usa 1h bars)
- Percentile-based thresholds para ATR

**Usage:**
```bash
# Detectar eventos para todos los tickers con percentiles
python scripts/processing/detect_events.py --use-percentiles

# Solo símbolos específicos
python scripts/processing/detect_events.py --symbols AAPL TSLA NVDA --use-percentiles

# Custom output directory
python scripts/processing/detect_events.py --use-percentiles --output-dir custom/events
```

**Output:**
- `processed/events/events_daily_YYYYMMDD.parquet`

**Columns:**
- `symbol`, `timestamp`, `open`, `high`, `low`, `close`, `volume`
- `gap_pct`, `rvol`, `atr_pct`, `dollar_volume`
- `is_ssr` (SSR flag)
- `gate_gap`, `gate_rvol`, `gate_rvol_alt`, `gate_atr`, `gate_dv` (gates)
- `is_event` (final event flag)

### 2. `rank_by_event_count.py`

Rankea símbolos por número de eventos históricos.

**Usage:**
```bash
# Rank top 2,000 (default)
python scripts/processing/rank_by_event_count.py

# Top 1,000
python scripts/processing/rank_by_event_count.py --top-n 1000

# Specific events file
python scripts/processing/rank_by_event_count.py --events-file processed/events/events_daily_20251008.parquet
```

**Output:**
- `processed/rankings/top_2000_by_events_YYYYMMDD.parquet`

**Columns:**
- `rank`, `symbol`
- `n_events`, `n_ssr_events`
- `gap_pct_mean`, `gap_pct_max`
- `rvol_mean`, `rvol_max`
- `atr_pct_mean`
- `dollar_volume_mean`
- `total_days`, `event_rate_pct`

### 3. `download_event_windows.py`

Descarga 1-min bars solo para ventanas específicas alrededor de eventos (D-2 a D+2).

**Ventanas (preset "compact"):**
- **D-2**: 09:30-16:00 (RTH completo)
- **D-1**: 09:30-10:30 + 14:00-16:00 (open momentum + late setup)
- **D**: 07:00-16:00 (premarket + RTH)
- **D+1**: 09:30-12:30 (extended for mean revert)
- **D+2**: 09:30-12:30

**Usage:**
```bash
# Download event windows for all symbols with events
python scripts/ingestion/download_event_windows.py --preset compact --resume

# Specific symbols only
python scripts/ingestion/download_event_windows.py --symbols AAPL TSLA --preset compact

# Test with limited symbols
python scripts/ingestion/download_event_windows.py --max-symbols 10 --preset compact --resume

# Custom events file
python scripts/ingestion/download_event_windows.py --events-file processed/events/events_daily_20251008.parquet --preset compact
```

**Output structure:**
```
raw/market_data/events/
  AAPL/
    20240115/  (event date)
      minute_d-002.parquet
      minute_d-001.parquet
      minute_d+000.parquet
      minute_d+001.parquet
      minute_d+002.parquet
    20240322/
      minute_d-002.parquet
      ...
  TSLA/
    ...
```

**Resume capability**: `--resume` flag skips already downloaded windows.

## Pipeline Completo

### Paso 1: Completar Week 1 (corriendo ahora)

Wait for Week 1 to complete downloading 1d + 1h for all 5,005 small caps.

**Status check:**
```bash
ls raw/market_data/bars/1d/*.parquet | wc -l
ls raw/market_data/bars/1h/*.parquet | wc -l
```

### Paso 2: Detectar eventos

```bash
python scripts/processing/detect_events.py --use-percentiles
```

**Expected output:** ~40-80 eventos/mes across universe

### Paso 3: Rankear Top-2000

```bash
python scripts/processing/rank_by_event_count.py --top-n 2000
```

### Paso 4: Download Week 2-3 (minute bars Top-2000)

Modify `download_all.py` or use manual approach:

```bash
# Read top 2000 symbols from ranking file
python scripts/ingestion/download_all.py --weeks 2 3 --top-volatile 2000
```

### Paso 5: Download event windows para resto (~3,000)

```bash
# Get symbols NOT in top 2000
# Then download event windows only
python scripts/ingestion/download_event_windows.py --preset compact --resume
```

## Configuración

Ver `config/config.yaml` sección `processing.events`:

```yaml
processing:
  events:
    gap_pct_threshold: 10.0
    rvol_threshold: 3.0
    atr_pct_window_days: 60
    atr_pct_percentile: 95
    rvol_threshold_alt: 2.5
    min_trading_days: 120
    min_dollar_volume_event: 2000000
    use_hourly_premarket_filter: true
    premarket_hours_ny: [7, 8]
    premarket_min_dollar_volume: 300000

  events_windows:
    preset: "compact"
    compact:
      d_minus_2: [["09:30","16:00"]]
      d_minus_1: [["09:30","10:30"], ["14:00","16:00"]]
      d:         [["07:00","16:00"]]
      d_plus_1:  [["09:30","12:30"]]
      d_plus_2:  [["09:30","12:30"]]
```

## Estimaciones de Storage

**Week 1 (actual):**
- 1d × 5,227: ~654 MB
- 1h × ~5,000: ~600 MB
- **Total: ~1.2 GB**

**Week 2-3 (Top-2000):**
- 1m × 2,000 × 3y: ~3.5-4 GB

**Event Windows (~3,000):**
- ~40-50 GB (15-25 días/año × ~3,000 tickers)

**Total estimado: ~45-55 GB** (muy manejable)

## Tiempo Estimado

- Week 1: 10-15 horas ✅ (corriendo ahora)
- detect_events.py: ~5-10 minutos
- rank_by_event_count.py: ~1 minuto
- Week 2-3 (Top-2000 1m): 48-72 horas
- Event windows (~3,000): 24-48 horas

**Total: 5-7 días** de descarga total

## Troubleshooting

**Error: "No events files found"**
- Run `detect_events.py` first

**Error: "No daily bars found for symbol"**
- Ensure Week 1 completed successfully
- Check `raw/market_data/bars/1d/` directory

**Low event count**
- Adjust thresholds in `config.yaml`
- Check `gap_pct_threshold`, `rvol_threshold`, `min_dollar_volume_event`

**Rate limiting (429 errors)**
- download_event_windows.py has built-in rate limiting
- Reduce concurrent downloads if needed

## Next Steps

After completing this pipeline:

1. **Feature Engineering**: Use event data for features
2. **Active-Day Masking**: Apply filters during training
3. **Negative Sampling**: Generate matched negatives (dynamic ratio)
4. **Validation**: Purged walk-forward + embargo
5. **SSR Handling**: Separate models for SSR vs non-SSR days
