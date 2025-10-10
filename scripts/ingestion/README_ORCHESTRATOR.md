# Pipeline de Descarga Completo - Orquestador Integrado

Este documento describe el **pipeline completo** de ingesta de datos usando el orquestador `download_all.py` con **detección de eventos** y **descarga optimizada por ranking**.

## Arquitectura del Pipeline

```
Week 1 (Foundation)
├── Download tickers (active + delisted)
├── Download corporate actions (splits + dividends)
├── Download 5y daily bars (1d) for all ~5,005 small caps
└── Download 5y hourly bars (1h) for all ~5,005 small caps
    │
    ├─► detect_events.py (triple-gate logic)
    │   └─► Output: processed/events/events_daily_YYYYMMDD.parquet
    │
    ├─► rank_by_event_count.py (rank by historical events)
    │   └─► Output: processed/rankings/top_2000_by_events_YYYYMMDD.parquet
    │
    ▼
Week 2-3 (Minute bars - Top-N)
├── Download 3y minute bars (1m) for Top-2000 (full history)
│   └─► Output: raw/market_data/bars/1m/{symbol}/YYYY-MM-DD.parquet
│
└── Download event windows (D-2 to D+2) for remaining ~3,000
    └─► Output: raw/market_data/events/{symbol}/{event_id}/minute_d{offset}_{HHMM}-{HHMM}.parquet

Week 4 (Complementary)
├── Download Short Interest (5y, semi-monthly)
└── Download Short Volume (3y, daily)
```

## Uso del Orquestador

### 1. Pipeline Completo (Recomendado)

Ejecuta todo el pipeline desde cero:

```bash
python scripts/ingestion/download_all.py --weeks 1 2 3 --top-n 2000 --events-preset compact
```

**Parámetros:**
- `--weeks 1 2 3`: Ejecuta Week 1, 2 y 3
- `--top-n 2000`: Descarga 1-min completo para Top-2000 por eventos
- `--events-preset compact`: Ventanas D-2 a D+2 con preset "compact"

**Tiempos estimados:**
- Week 1: 10-15 horas (5,005 tickers × 1d + 1h)
- Detect + Rank: 5-10 minutos
- Week 2-3 Top-2000: 48-72 horas (2,000 × 3y × 1m)
- Week 2-3 Event Windows: 24-48 horas (~3,000 tickers, solo ventanas)
- **Total: 5-7 días**

### 2. Dry-Run (Planificación)

Revisa el plan sin ejecutar:

```bash
python scripts/ingestion/download_all.py --weeks 1 2 3 --top-n 2000 --events-preset compact --dry-run
```

### 3. Continuar desde Week 2 (Week 1 ya completo)

Si ya tienes Week 1 descargado:

```bash
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 2000 --events-preset compact
```

### 4. Testing con límites

Probar con subconjunto:

```bash
# Solo 100 símbolos para event windows
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 500 --max-rest-symbols 100 --events-preset compact

# Solo tickers que empiezan con A, B, C
python scripts/ingestion/download_all.py --weeks 1 2 3 --letters A B C --top-n 100
```

### 5. Solo Week 4 (Complementary Data)

```bash
python scripts/ingestion/download_all.py --weeks 4
```

## Configuración de Event Windows

Los presets de ventanas de evento se configuran en `config/config.yaml`:

### Preset "compact" (Default)

```yaml
events_windows:
  preset: "compact"
  compact:
    d_minus_2: [["09:30","16:00"]]               # D-2: market hours
    d_minus_1: [["09:30","10:30"], ["14:00","16:00"]]  # D-1: open + close
    d:         [["07:00","16:00"]]               # D: premarket + market
    d_plus_1:  [["09:30","12:30"]]               # D+1: morning session
    d_plus_2:  [["09:30","12:30"]]               # D+2: morning session
```

### Preset "extended" (Opcional)

Para más datos (más storage):

```yaml
extended:
  d_minus_2: [["09:30","16:00"]]
  d_minus_1: [["07:00","16:00"]]                 # Full premarket + market
  d:         [["04:00","20:00"]]                 # Extended hours
  d_plus_1:  [["07:00","16:00"]]
  d_plus_2:  [["09:30","16:00"]]
```

## Estructura de Archivos de Salida

```
raw/
├── reference/
│   ├── tickers_active_YYYYMMDD.parquet
│   ├── tickers_delisted_YYYYMMDD.parquet
│   ├── splits_YYYYMMDD.parquet
│   └── dividends_YYYYMMDD.parquet
│
├── market_data/
│   ├── bars/
│   │   ├── 1d/{symbol}.parquet                 # All ~5,005 symbols
│   │   ├── 1h/{symbol}.parquet                 # All ~5,005 symbols
│   │   └── 1m/{symbol}/YYYY-MM-DD.parquet      # Top-2000 only (partitioned by date)
│   │
│   ├── events/
│   │   └── {symbol}/{event_id}/                # Remaining ~3,000 symbols
│   │       ├── minute_d-2_0930-1600.parquet
│   │       ├── minute_d-1_0930-1030.parquet
│   │       ├── minute_d-1_1400-1600.parquet
│   │       ├── minute_d+0_0700-1600.parquet
│   │       ├── minute_d+1_0930-1230.parquet
│   │       └── minute_d+2_0930-1230.parquet
│   │
│   └── complementary/
│       ├── short_interest_YYYYMMDD.parquet
│       └── short_volume_YYYYMMDD.parquet
│
processed/
├── events/
│   └── events_daily_YYYYMMDD.parquet           # All detected events
│
└── rankings/
    └── top_2000_by_events_YYYYMMDD.parquet     # Top-N ranked by event count
```

## Estimaciones de Storage

### Week 1 (Foundation)
- Daily bars (1d): 5,005 × ~10 KB = **~50 MB**
- Hourly bars (1h): 5,005 × ~12 KB = **~60 MB**
- **Subtotal: ~110 MB**

### Week 2-3 (Minute bars)
- Top-2000 (1m, 3y): 2,000 × ~1.7 MB = **~3.4 GB**
- Event windows (~3,000 tickers):
  - ~15-20 events per ticker
  - ~6-8 windows per event
  - ~50-100 KB per window
  - **~40-50 GB**
- **Subtotal: ~43-53 GB**

### Total: **~45-55 GB**

## Monitoreo del Progreso

### Logs

Los logs se guardan en `logs/`:

```
logs/
├── failed_week1_daily_YYYYMMDD.txt       # Tickers fallidos en daily bars
├── failed_week1_hourly_YYYYMMDD.txt      # Tickers fallidos en hourly bars
├── failed_topN_1m_YYYYMMDD.txt           # Tickers fallidos en Top-N minute bars
└── download_all.log                       # Log completo del orquestador
```

### Progreso en Terminal

El orquestador imprime:

```
===== STARTING FULL HISTORICAL DOWNLOAD =====
Weeks to execute: [1, 2, 3]
Top-N for full minute bars: 2000
Event windows preset: compact

=== WEEK 1: Foundation Data ===
Step 1/5: Downloading ticker universe
Step 2/5: Downloading corporate actions
Step 3/5: Filtering small caps universe
Small caps universe: 5005 tickers
Step 4/5: Downloading 5 years daily bars for 5005 tickers
Progress: 100/5005 tickers (skipped: 0, failed: 0)
...

=== Running event detection and ranking ===
Running detect_events.py --use-percentiles
Total events detected: 85,234
Event rate: 3.42%

Running rank_by_event_count.py --top-n 2000
Top-2000 ranking saved

=== WEEK 2-3: 1-min for Top-2000 ===
Progress: 100/2000 (skipped: 0, failed: 0)
[TopN] Batch 1 complete (500/2000)
...

=== EVENT WINDOWS: Symbols outside Top-N: 3005 ===
[REST] Event windows → 3005 symbols with preset 'compact'
...

===== DOWNLOAD COMPLETE in 132.45 hours =====
```

## Troubleshooting

### Error: "No processed/events/events_daily_*.parquet found"

El script `detect_events.py` no se ejecutó correctamente. Verifica:

```bash
# Ejecutar manualmente
python scripts/processing/detect_events.py --use-percentiles

# Revisar output
ls processed/events/
```

### Error: "Ranking file not found"

El script `rank_by_event_count.py` falló. Verifica:

```bash
# Ejecutar manualmente
python scripts/processing/rank_by_event_count.py --top-n 2000

# Revisar output
ls processed/rankings/
```

### Rate Limiting (429 errors)

Si ves muchos `429 Too Many Requests`:

1. Aumenta sleep time en `download_minute_for_topN()`: `time.sleep(0.25)` → `time.sleep(0.35)`
2. No ejecutes múltiples orquestadores en paralelo
3. Verifica tu plan de Polygon.io

### Disco lleno

Monitorea storage:

```bash
# Linux/Mac
df -h

# Windows
dir /s raw\market_data
```

Si te quedas sin espacio:
- Usa `--top-n 1000` en lugar de 2000
- Usa `--max-rest-symbols 1000` para limitar event windows
- Comprime archivos antiguos

## Próximos Pasos

Después de completar la descarga:

1. **Validación de datos:**
   ```bash
   python scripts/validation/check_completeness.py
   ```

2. **Generar reporte de eventos:**
   ```bash
   python scripts/processing/generate_event_report.py
   ```

3. **Feature engineering:**
   ```bash
   python scripts/processing/compute_features.py
   ```

## Referencias

- [detect_events.py](../processing/detect_events.py) - Triple-gate event detection
- [rank_by_event_count.py](../processing/rank_by_event_count.py) - Ranking por eventos
- [download_event_windows.py](download_event_windows.py) - Descarga de ventanas
- [Pipeline README](../processing/README.md) - Documentación del pipeline de procesamiento
