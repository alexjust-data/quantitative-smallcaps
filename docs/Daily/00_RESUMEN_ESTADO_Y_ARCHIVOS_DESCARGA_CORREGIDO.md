# Estado Actual del Proyecto y Archivos de Descarga (CORREGIDO)

## 📊 **ESTADO ACTUAL DEL PROYECTO**

### ✅ **Completado:**
- **Week 1** (Barras diarias + horarias): 100% completo
  - Daily bars: 5,227 archivos (104.4%)
  - Hourly bars: 5,227 archivos (104.4%)
  - Descarga finalizó: 03:01 AM del 09/10/2025

- **Detección de eventos** (manual): ✅ Completado
  - **323 eventos** detectados de **1,200,818 días** analizados (0.027% tasa de eventos)
  - Archivo: `processed/events/events_daily_20251009.parquet` (40.4 MB)

- **Ranking de tickers** (manual): ✅ Completado
  - 4,878 símbolos ranqueados por frecuencia de eventos
  - Archivo: `processed/rankings/top_2000_by_events_20251009.parquet` (15 KB)

### ⏳ **Pendiente:**
- **Week 2-3**: Descarga de barras de 1 minuto
  - Top-2000: barras completas 3 años (~4 GB)
  - Resto ~2,878: solo ventanas de evento D-2 a D+2 (~1-2 GB)

### 🔧 **Fix aplicado:**
El `auto_continue_after_week1.py` ahora usa el Python del venv (con polars instalado) en lugar del Python global.

### ⚠️ **PROBLEMA CRÍTICO DETECTADO:**
**Solo 323 eventos de 1.2M días (0.027%) es extremadamente bajo para small-caps.**
Los umbrales actuales (Gap≥10%, RVOL≥3, DV≥$2M) son demasiado conservadores y solo detectan "mega-events", no eventos tradables diarios típicos de small-caps.

---

## 📂 **ARCHIVOS REALES DEL SISTEMA**

### **1. Orquestador Principal**

#### [`scripts/ingestion/download_all.py`](scripts/ingestion/download_all.py) ✅ EXISTE
**Qué hace:**
- Script maestro que orquesta toda la descarga en fases
- Contiene TODOS los métodos de descarga (Week 1, 2-3, 4)
- **NO existe `download_week1.py` standalone - todo está aquí**

**Métodos principales:**
- `download_week1_foundation()` - Daily + Hourly bars (5 años, todos los tickers)
- `download_minute_for_topN()` - Minute bars para Top-N (3 años completos)
- `download_event_windows_for_rest()` - Event windows para resto
- `download_week4_complementary()` - Short Interest + Volume

**Uso:**
```bash
# Descargar Week 1 (foundation)
python scripts/ingestion/download_all.py --weeks 1

# Descargar Week 2-3 (minute bars)
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 2000 --events-preset compact

# Todo el pipeline
python scripts/ingestion/download_all.py --weeks 1 2 3 4 --top-n 2000
```

---

### **2. Scripts de Descarga Específicos**

#### [`scripts/ingestion/ingest_polygon.py`](scripts/ingestion/ingest_polygon.py) ✅ EXISTE
**Qué hace:**
- Clase `PolygonIngester` que maneja la comunicación con Polygon.io API
- Métodos: `download_aggregates()`, `download_tickers()`, `download_corporate_actions()`
- Maneja rate limiting, paginación, retry logic
- **NO se ejecuta directamente - es usado por `download_all.py`**

---

#### [`scripts/ingestion/download_event_windows.py`](scripts/ingestion/download_event_windows.py) ✅ EXISTE
**Qué hace:**
- Descarga barras de **1 minuto** SOLO para ventanas de evento (D-2 a D+2)
- Lee el archivo de eventos detectados (`processed/events/events_daily_*.parquet`)
- Filtra tiempo con precisión en timezone America/New_York
- **Cachea días completos** para reutilizar cuando hay múltiples ventanas el mismo día

**Ventanas que descarga (preset "compact"):**
```yaml
D-2:  [09:30-16:00]           # Día previo completo
D-1:  [09:30-10:30, 14:00-16:00]  # Apertura + cierre
D:    [07:00-16:00]           # Día del evento completo (incluyendo premarket)
D+1:  [09:30-12:30]           # Morning session
D+2:  [09:30-12:30]           # Morning session
```

**Estructura REAL de archivos generados:**
```
raw/market_data/bars/1m/
  └── symbol=AAPL/
      ├── date=2025-10-01.parquet
      ├── date=2025-10-02.parquet
      └── date=2025-10-03.parquet
```

**⚠️ CORRECCIÓN:** Los archivos NO se llaman `minute_d-2_0930-1600.parquet`.
La estructura real usa **particiones Hive** con formato `symbol={SYMBOL}/date={DATE}.parquet`

**Uso:**
```bash
# Standalone (no recomendado - mejor usar download_all.py)
python scripts/ingestion/download_event_windows.py \
  --events-parquet processed/events/events_daily_20251009.parquet \
  --preset compact
```

---

### **3. Scripts de Procesamiento**

#### [`scripts/processing/detect_events.py`](scripts/processing/detect_events.py) ✅ EXISTE
**Qué hace:**
- Analiza las barras **diarias (1d)** y detecta eventos usando triple-gate logic
- **Branch 1**: `Gap ≥ 10% AND RVOL ≥ 3` (eventos explosivos)
- **Branch 2**: `ATR% ≥ p95 AND RVOL ≥ 2.5` (alta volatilidad)
- **Filtros**: Dollar Volume ≥ $2M, Premarket filter (opcional)
- Detecta SSR (Short Sale Restriction): `low ≤ 0.9 × prev_close`

**Archivos que lee:**
```
raw/market_data/bars/1d/{SYMBOL}.parquet
raw/market_data/bars/1h/{SYMBOL}.parquet (para premarket filter)
```

**Archivos que genera:**
```
processed/events/events_daily_YYYYMMDD.parquet
```

**Columnas del output:**
- `symbol`, `date`, `timestamp`, `event_id`
- `gap_pct`, `rvol`, `atr_pct`, `dollar_volume`
- `is_ssr`, `close`, `volume`, `vwap`
- `gate_gap`, `gate_rvol`, `gate_rvol_alt`, `gate_atr`, `gate_dv`, `is_event`

**Uso:**
```bash
python scripts/processing/detect_events.py --use-percentiles
```

---

#### [`scripts/processing/rank_by_event_count.py`](scripts/processing/rank_by_event_count.py) ✅ EXISTE
**Qué hace:**
- Lee los eventos detectados
- Cuenta cuántos eventos tuvo cada ticker históricamente
- Rankea por frecuencia de eventos (descendente)
- Genera Top-N (default 2000)

**Archivos que lee:**
```
processed/events/events_daily_*.parquet (más reciente)
```

**Archivos que genera:**
```
processed/rankings/top_2000_by_events_YYYYMMDD.parquet
```

**Columnas del output:**
- `symbol`, `n_events`, `n_ssr_events`
- `gap_pct_mean`, `rvol_mean`, `dollar_volume_mean`

**Uso:**
```bash
python scripts/processing/rank_by_event_count.py --top-n 2000
```

---

### **4. Monitores y Utilidades**

#### [`scripts/ingestion/auto_continue_after_week1.py`](scripts/ingestion/auto_continue_after_week1.py) ✅ EXISTE
**Qué hace:**
- Monitorea cada 5 minutos si Week 1 está completo (≥95% hourly bars)
- Cuando detecta completitud, automáticamente lanza:
  1. `detect_events.py`
  2. `rank_by_event_count.py`
  3. `download_all.py --weeks 2 3` (Week 2-3 downloads)

**Uso:**
```bash
# Lanzar monitor en background
python scripts/ingestion/auto_continue_after_week1.py \
  --top-n 2000 \
  --events-preset compact \
  --auto-start-week23 \
  --check-interval 300
```

**⚠️ Fix aplicado (09/10/2025):** Ahora usa venv Python en lugar de Python global.

---

#### [`scripts/ingestion/check_download_status.py`](scripts/ingestion/check_download_status.py) ✅ EXISTE
**Qué hace:**
- Genera reporte visual del estado de todas las fases del pipeline
- Muestra: archivos descargados, % completitud, storage usado, última descarga

**Uso:**
```bash
python scripts/ingestion/check_download_status.py
```

**Output real (09/10/2025 11:49:38):**
```
======================================================================
DOWNLOAD STATUS REPORT
======================================================================

📊 WEEK 1: Foundation Data
----------------------------------------------------------------------
  ✅ Daily bars (1d):     5,227 / 5,005 (104.4%)
     Size: 48.8 MB
     Latest: ZYME.parquet (2025-10-08 16:57:30)

  ✅ Hourly bars (1h):    5,227 / 5,005 (104.4%)
     Size: 36.8 MB
     Latest: ZYXI.parquet (2025-10-09 03:01:30)

  Week 1 Status: ✅ COMPLETE

📈 PROCESSING: Event Detection
----------------------------------------------------------------------
  ✅ Events detected:  1 files, 40.4 MB
     Latest: events_daily_20251009.parquet
  ✅ Rankings:         1 files, 15.0 KB
     Latest: top_2000_by_events_20251009.parquet

⚡ WEEK 2-3: Minute Bars (Top-N)
----------------------------------------------------------------------
  📁 Symbols:          2
  📄 Files:            15
  💾 Size:             178.3 KB

💾 TOTAL STORAGE
----------------------------------------------------------------------
  Raw data:            10,477 files, 222.9 MB
  Processed data:      2 files, 40.4 MB
```

---

## 🎯 **RESUMEN DEL FLUJO DE DATOS (CORREGIDO)**

```
┌─────────────────────────────────────────────────────────────┐
│                    WEEK 1 (FOUNDATION)                      │
├─────────────────────────────────────────────────────────────┤
│  download_all.py --weeks 1                                  │
│    ↓                                                        │
│  Método: download_week1_foundation()                        │
│    ↓                                                        │
│  5,227 tickers × [1d bars + 1h bars] × 5 years            │
│    ↓                                                        │
│  raw/market_data/bars/1d/*.parquet                         │
│  raw/market_data/bars/1h/*.parquet                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                 EVENT DETECTION & RANKING                   │
├─────────────────────────────────────────────────────────────┤
│  detect_events.py (lee 1d bars)                            │
│    ↓                                                        │
│  323 eventos detectados (0.027% de 1.2M días)              │
│  ⚠️ TASA EXTREMADAMENTE BAJA - umbrales muy conservadores  │
│    ↓                                                        │
│  processed/events/events_daily_20251009.parquet (40.4 MB)  │
│                                                             │
│  rank_by_event_count.py (lee events)                       │
│    ↓                                                        │
│  Top-2000 tickers ranqueados por frecuencia de eventos     │
│    ↓                                                        │
│  processed/rankings/top_2000_by_events_20251009.parquet    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    WEEK 2-3 (MINUTE BARS)                   │
├─────────────────────────────────────────────────────────────┤
│  download_all.py --weeks 2 3 (lee ranking + events)        │
│    ↓                                                        │
│  ├─ Top-2000: 3y minute bars completos (~4 GB)            │
│  │    Método: download_minute_for_topN()                  │
│  │    raw/market_data/bars/1m/symbol={SYMBOL}/...         │
│  │                                                         │
│  └─ Resto ~2,878: solo event windows (~1-2 GB)            │
│       Método: download_event_windows_for_rest()           │
│       raw/market_data/bars/1m/symbol={SYMBOL}/            │
│         date={DATE}.parquet                                │
└─────────────────────────────────────────────────────────────┘
```

---
