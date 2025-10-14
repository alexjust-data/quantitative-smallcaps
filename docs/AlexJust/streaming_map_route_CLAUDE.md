# STREAMING MAP ROUTE - SMALLCAPS TRADING ANALYTICS

> **Documento generado por Claude (Anthropic AI) - Sesión del 2025-10-13**
> Este documento fue creado como handoff para el siguiente agente de IA que trabajará en la evolución del proyecto hacia un sistema de trading en tiempo real.

---

## 📋 RESPUESTAS A PREGUNTAS CLAVE

### 1. **¿Polygon es buena opción para streaming en tiempo real?**

**SÍ, Polygon es EXCELENTE para este caso:**

✅ **Pros:**
- API WebSocket para datos en tiempo real (barras 1s, 5s, 1m)
- Cobertura completa de small caps (NYSE, NASDAQ, OTC)
- Datos históricos + streaming con la misma API
- Agregados ya calculados (VWAP, volumen, etc.)
- Precio razonable (~$200-400/mes según plan)
- Latencia baja (<100ms típicamente)

❌ **Alternativas:**
- **Alpaca Markets**: Gratis pero solo para cuentas paper/live trading, menos históricos
- **Interactive Brokers**: Requiere cuenta, más complejo de configurar
- **Alpha Vantage**: Limitado para real-time, mejor para EOD

**Recomendación:** Polygon.io es la mejor opción para small caps.

---

### 2. **¿Big Data, Base de Datos Vectorial o Qué?**

Este sistema necesita **ARQUITECTURA HÍBRIDA**:

#### **A) Para Datos Numéricos/Estructurados (Time Series):**
```
TimescaleDB (PostgreSQL con extensión temporal)
o
ClickHouse (columnar, super rápido para agregaciones)
```

**Por qué:**
- 1,996 símbolos × 6.5 meses × 390 mins/día × 5 tipos eventos = ~25-50M eventos
- Necesitas queries tipo: "Dame eventos VWAP break + volume spike en últimos 5 min"
- Agregaciones rápidas: "Promedio de eventos por símbolo por hora"

#### **B) Para Embeddings/Búsqueda Semántica (IA):**
```
Vector Database: Pinecone, Weaviate o Qdrant
```

**Por qué:**
- Buscar empresas similares por comportamiento de precio
- Encontrar patrones históricos parecidos al actual
- Noticias semánticamente relacionadas
- "Dame empresas que se comportan como TSLA pero en sector biotech"

#### **C) Para Features/ML en Tiempo Real:**
```
Feature Store: Feast o Redis con TimeSeries
```

**Por qué:**
- Pre-calcular features: RSI, Bollinger Bands, volumen relativo
- Servir features a modelos ML en <10ms
- Consistencia entre training y producción

---

### 3. **¿Es Big Data?**

**Técnicamente NO (todavía), pero usa stack de Big Data:**

```
Volumen actual:
- ~2,000 símbolos
- ~50M eventos intraday (6 meses)
- ~100GB datos históricos
- ~5-10 MB/s en streaming (real-time)

Esto es "Medium Data" - manejable en una máquina potente
PERO debes arquitecturar como Big Data para escalar
```

**Por qué arquitectura Big Data:**
- Fácil escalar cuando añadas más símbolos/mercados
- Procesamiento paralelo (como acabamos de implementar)
- Fault tolerance (auto-restart implementado)

---

### 4. **Arquitectura Óptima Recomendada**

```
┌─────────────────────────────────────────────────────┐
│           CAPA DE INGESTA (Real-Time)               │
├─────────────────────────────────────────────────────┤
│  Polygon WebSocket → Kafka/Redis Streams           │
│  (trades, quotes, barras 1s/1m)                     │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│        CAPA DE PROCESAMIENTO (Stream)               │
├─────────────────────────────────────────────────────┤
│  Apache Flink / Spark Streaming                     │
│  - Detecta eventos en ventanas 1min                 │
│  - Calcula features (RSI, VWAP, etc.)               │
│  - Filtra por condiciones                           │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│         CAPA DE ALMACENAMIENTO                      │
├─────────────────────────────────────────────────────┤
│  TimescaleDB/ClickHouse → Time series (OLAP)       │
│  PostgreSQL → Metadata, config (OLTP)               │
│  Vector DB (Pinecone) → Embeddings, similarity      │
│  S3/MinIO → Archivos parquet históricos            │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│           CAPA DE INTELIGENCIA (AI/ML)              │
├─────────────────────────────────────────────────────┤
│  Feature Store (Feast) → Features consistentes     │
│  ML Models (XGBoost, LightGBM) → Predicciones      │
│  LLM (GPT-4, Claude) → Análisis narrativo          │
│  Rule Engine → Screeners, alerts                    │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│             CAPA DE APLICACIÓN                      │
├─────────────────────────────────────────────────────┤
│  API REST/GraphQL → Dashboard, alertas             │
│  WebSocket → Notificaciones real-time              │
│  Dashboard (Streamlit/React) → Visualización       │
└─────────────────────────────────────────────────────┘
```

---

# PROYECTO: SMALLCAPS TRADING ANALYTICS - HANDOFF DOCUMENT

## 1. RESUMEN EJECUTIVO

### Objetivo del Proyecto
Construir un sistema de trading analytics para small caps que permita:
- Backtesting con datos históricos de alta resolución (1 minuto)
- Detección de eventos intraday (volume spikes, VWAP breaks, etc.)
- **PRÓXIMA FASE:** Sistema en tiempo real con IA para alertas automáticas y screeners inteligentes

### Estado Actual (2025-10-13)
- **Fase 2.5 COMPLETADA:** Ingesta histórica de 1,996 símbolos (6.5 meses de datos 1min)
- **Fase 2.5 EN PROGRESO:** Detección de eventos intraday (sistema paralelo 4 workers)
  - Progreso: ~700 símbolos/hora
  - Tiempo estimado: 1.2 horas para completar
- **Sistema paralelo con auto-recovery implementado y funcionando**

### Próxima Fase
Evolucionar hacia sistema real-time con:
- Streaming desde Polygon WebSocket
- Detección de eventos en tiempo real (<1s latencia)
- Integración de datos adicionales (noticias, macro, sector)
- Modelos ML para predicción y screeners
- Dashboard con alertas automáticas

---

## 2. ARQUITECTURA DE DATOS ACTUAL

### 2.1 Estructura de Directorios

```
D:\04_TRADING_SMALLCAPS\
├── raw/
│   └── market_data/
│       └── bars/
│           └── 1m/                    # Barras 1min raw de Polygon
│               └── {SYMBOL}/
│                   └── date={YYYY-MM-DD}.parquet
│
├── processed/
│   ├── events/
│   │   ├── shards/                    # Eventos detectados (por batch)
│   │   │   └── events_intraday_YYYYMMDD_shardXXXX.parquet
│   │   └── events_intraday_YYYYMMDD.parquet  # Consolidado
│   │
│   └── reference/
│       ├── symbols_with_1m.parquet    # Lista de símbolos disponibles
│       ├── short_interest/            # Short Interest mensual
│       └── institutional_holdings/    # Holdings trimestrales
│
├── scripts/
│   ├── ingestion/                     # Descarga desde Polygon
│   └── processing/
│       └── detect_events_intraday.py  # Detección de eventos
│
├── logs/
│   ├── checkpoints/                   # Checkpoints para resume
│   ├── detect_events/                 # Logs de detección
│   └── parallel_workers/              # Logs workers paralelos
│
└── config/
    └── config.yaml                    # Configuración central
```

### 2.2 Datasets Actuales

#### **A) Barras 1 Minuto (Historical)**
```
Ubicación: raw/market_data/bars/1m/
Formato: Parquet particionado por símbolo y fecha
Período: 2025-04-01 a 2025-10-12 (6.5 meses)
Símbolos: 1,996 small caps
Tamaño: ~100GB

Schema:
- timestamp: datetime64[ns, America/New_York]
- open: float64
- high: float64
- low: float64
- close: float64
- volume: int64
- vwap: float64
- transactions: int32
```

#### **B) Eventos Intraday (Detectados)**
```
Ubicación: processed/events/shards/
Formato: Parquet (shards de 50 símbolos)
Eventos detectados: ~25-50M

Schema:
- event_id: str
- symbol: str
- timestamp: datetime64[ns]
- event_type: str (volume_spike, vwap_break, opening_range_break, flush, consolidation_break)
- session: str (PM, RTH, AH)
- direction: str (bullish, bearish)
- strength: float64
- metadata: struct (campos específicos por evento)
```

#### **C) Reference Data**

**symbols_with_1m.parquet:**
```
- symbol: str
- has_1m_data: bool
- first_date: date
- last_date: date
- total_bars: int64
```

**Short Interest (Mensual):**
```
- symbol: str
- date: date
- short_interest: int64
- days_to_cover: float64
```

**Institutional Holdings (Trimestral):**
```
- symbol: str
- quarter: str
- institution: str
- shares: int64
- value: float64
```

### 2.3 Formatos y Convenciones

**Particionamiento:**
- Por símbolo: `{symbol}/date={YYYY-MM-DD}.parquet`
- Por fecha: `date={YYYY-MM-DD}/symbol={SYMBOL}.parquet`

**Naming:**
- Archivos: snake_case
- Columnas: snake_case
- Constantes: UPPER_CASE

**Timezone:**
- Todos los timestamps en America/New_York (NYSE)
- Conversiones explícitas cuando sea necesario

---

## 3. PIPELINE DE PROCESAMIENTO

### 3.1 Ingesta Histórica (✅ COMPLETADA)

**Script:** `scripts/ingestion/download_1m_bars_bulk.py`

**Características:**
- API: Polygon REST (endpoint /v2/aggs)
- Rate limiting: 5 req/sec (Polygon Starter)
- Checkpoint system: resume después de crashes
- Dual pricing: adjusted + unadjusted
- Survivorship bias fix: descarga símbolos delistados

**Performance:**
- ~1,996 símbolos completados
- ~6.5 meses de historia
- Tiempo total: ~2 semanas (con reintentos)

### 3.2 Detección de Eventos (🔄 EN PROGRESO)

**Script:** `scripts/processing/detect_events_intraday.py`

**Eventos Detectados:**

1. **Volume Spike**: Volumen >3x promedio 20-day
2. **VWAP Break**: Precio cruza VWAP con volumen
3. **Opening Range Break**: Rompe rango primeros 5/15/30 min
4. **Flush**: Caída rápida con capitulación
5. **Consolidation Break**: Rompe rango de consolidación

**Sistema Paralelo (Implementado 2025-10-13):**
```
Orquestador: parallel_orchestrator.py
Workers: 4 procesos independientes
Checkpoint: Por worker (recovery automática)
Performance: ~700 símbolos/hora (46x mejora vs 1 proceso)
Auto-restart: Hasta 10 reinicios por worker
```

**Features:**
- Procesamiento por batches (50 símbolos/batch)
- Checkpoint después de cada batch
- Heartbeat log para monitoreo
- Recovery desde shards (no pierde datos)

### 3.3 Performance Actual

**Sistema Paralelo (4 workers):**
```
Velocidad: 697 símbolos/hora
Progreso actual: ~60 símbolos completados
Restantes: ~816 símbolos
Tiempo estimado: 1.2 horas

vs Sistema Anterior (1 proceso):
Velocidad: 15 símbolos/hora
Mejora: 46x más rápido
```

---

## 4. SIGUIENTE FASE: SISTEMA REAL-TIME

### 4.1 Requisitos Funcionales

**A) Ingesta en Tiempo Real:**
- WebSocket connection a Polygon
- Recibir trades/quotes/aggregates en streaming
- Buffer y procesamiento por ventanas (1min, 5min)

**B) Detección de Eventos Live:**
- Mismo algoritmo que histórico
- Latencia objetivo: <1 segundo
- Procesar 2,000 símbolos simultáneamente

**C) Alertas Automáticas:**
- Email, SMS, push notifications
- Filtros configurables por usuario
- Priorización por strength/probabilidad

**D) Screener Dinámico:**
- "Empresas con volume spike + VWAP break últimos 5 min"
- "Small caps con momentum similar a {SYMBOL}"
- "Setups pre-market con alta probabilidad"

**E) Análisis con IA/LLM:**
- Resumen narrativo de eventos
- Explicación de movimientos inusuales
- Correlaciones entre símbolos
- Hipótesis de causas (earnings, noticias, sector)

### 4.2 Requisitos No Funcionales

```
Performance:
- Latencia end-to-end: <1 segundo (evento → alerta)
- Throughput: 2,000 símbolos × 1 update/min = 33 updates/sec
- Escalabilidad: Soportar 10,000+ símbolos

Disponibilidad:
- Uptime: 99.9% durante horas de mercado
- Failover automático
- Zero data loss

Mantenibilidad:
- Logs estructurados
- Métricas de performance
- Alertas de sistema
```

### 4.3 Datos Adicionales Necesarios

**A) Noticias y Sentiment:**
```
Fuentes:
- Polygon News API
- Twitter/X (vía API)
- SEC EDGAR (8-K, 10-Q, 13-F)
- Reddit WallStreetBets

Procesamiento:
- NLP para sentiment scoring
- Entity recognition (empresas mencionadas)
- Clasificación de relevancia
```

**B) Datos Macroeconómicos:**
```
Fuentes:
- FRED (Federal Reserve Economic Data)
- Yahoo Finance (índices, VIX)
- Treasury yields

Indicadores:
- SPY, QQQ, IWM (momentum general)
- VIX (volatilidad)
- Treasury 10Y (risk-on/risk-off)
```

**C) Sector/Industry Classification:**
```
Fuentes:
- Polygon company details API
- NAICS codes
- Custom clustering

Uso:
- Correlaciones sector vs símbolo
- Rotación sectorial
- Relative strength analysis
```

**D) Opciones Flow:**
```
Fuentes:
- Unusual Whales
- FlowAlgo
- Polygon Options API

Indicadores:
- Volumen inusual de calls/puts
- Gamma exposure
- Max pain
```

---

## 5. ARQUITECTURA PROPUESTA

### 5.1 Stack Tecnológico Recomendado

#### **Ingesta y Streaming:**
```
- Polygon WebSocket Client (Python)
- Message Queue: Apache Kafka (o Redis Streams para empezar)
- Buffer: Redis (in-memory, sub-ms latency)
```

#### **Procesamiento Stream:**
```
- Apache Flink (stateful streaming)
  o alternativa: Spark Structured Streaming
- Ventanas temporales: tumbling/sliding windows
- State management: RocksDB backend
```

#### **Almacenamiento:**
```
Time Series:
- TimescaleDB (PostgreSQL + extensión)
  o alternativa: ClickHouse (columnar, más rápido)

Metadata:
- PostgreSQL (OLTP)

Vector Database:
- Pinecone (embeddings, búsqueda semántica)
  o alternativa: Weaviate, Qdrant (self-hosted)

Data Lake:
- S3 / MinIO (archivos parquet históricos)
```

#### **ML/AI:**
```
Feature Store:
- Feast (online + offline features)

ML Models:
- XGBoost / LightGBM (clasificación)
- Prophet / ARIMA (time series forecasting)
- scikit-learn (clustering, PCA)

LLM:
- OpenAI GPT-4 (análisis narrativo)
- Anthropic Claude (este agente)
- Embeddings: text-embedding-3-large
```

#### **Frontend:**
```
Dashboard:
- Streamlit (prototipo rápido)
- React + Recharts (producción)

API:
- FastAPI (REST)
- GraphQL (consultas complejas)
- WebSocket (real-time push)
```

### 5.2 Diseño de Base de Datos

#### **A) TimescaleDB Schema (Time Series)**

```sql
-- Tabla principal: barras 1min
CREATE TABLE bars_1m (
    timestamp TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    open NUMERIC(10,2),
    high NUMERIC(10,2),
    low NUMERIC(10,2),
    close NUMERIC(10,2),
    volume BIGINT,
    vwap NUMERIC(10,2),
    transactions INTEGER
);

-- Convertir a hypertable (TimescaleDB)
SELECT create_hypertable('bars_1m', 'timestamp',
    chunk_time_interval => INTERVAL '1 day');

-- Índice compuesto
CREATE INDEX idx_bars_symbol_time ON bars_1m (symbol, timestamp DESC);

-- Tabla de eventos
CREATE TABLE events_intraday (
    event_id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    session TEXT,
    direction TEXT,
    strength NUMERIC(5,2),
    metadata JSONB
);

SELECT create_hypertable('events_intraday', 'timestamp');
CREATE INDEX idx_events_symbol ON events_intraday (symbol, timestamp DESC);
CREATE INDEX idx_events_type ON events_intraday (event_type, timestamp DESC);

-- Tabla de features (pre-calculados)
CREATE TABLE features_realtime (
    timestamp TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    rsi_14 NUMERIC(5,2),
    bb_upper NUMERIC(10,2),
    bb_lower NUMERIC(10,2),
    volume_ratio_20d NUMERIC(8,2),
    price_vs_vwap NUMERIC(6,4),
    -- ... más features
    PRIMARY KEY (timestamp, symbol)
);

SELECT create_hypertable('features_realtime', 'timestamp');
```

#### **B) Vector Database Schema (Embeddings)**

```python
# Pinecone index structure
index = pinecone.Index("smallcaps-patterns")

# Vector metadata
{
    "id": "AAPL_2025-10-13_pattern_001",
    "vector": [0.123, -0.456, ...],  # 1536 dims (OpenAI)
    "metadata": {
        "symbol": "AAPL",
        "date": "2025-10-13",
        "pattern_type": "volume_spike_vwap_break",
        "outcome": "bullish",  # next 1h return
        "features": {
            "volume_ratio": 4.5,
            "price_change": 0.025,
            "sector": "technology"
        }
    }
}
```

#### **C) Feature Store Schema (Feast)**

```python
# Feature definitions
from feast import Entity, Feature, FeatureView, Field
from feast.types import Float32, Int64

symbol = Entity(name="symbol", join_keys=["symbol"])

# Feature view: Technical indicators
technicals_fv = FeatureView(
    name="technicals",
    entities=[symbol],
    schema=[
        Field(name="rsi_14", dtype=Float32),
        Field(name="volume_ratio_20d", dtype=Float32),
        Field(name="bb_upper", dtype=Float32),
        Field(name="bb_lower", dtype=Float32),
        Field(name="macd", dtype=Float32),
    ],
    source=...,  # TimescaleDB
    ttl=timedelta(minutes=1),
)

# Feature view: Events recientes
recent_events_fv = FeatureView(
    name="recent_events",
    entities=[symbol],
    schema=[
        Field(name="volume_spikes_1h", dtype=Int64),
        Field(name="vwap_breaks_1h", dtype=Int64),
        Field(name="last_event_strength", dtype=Float32),
    ],
    source=...,
    ttl=timedelta(hours=1),
)
```

### 5.3 Flujo de Datos Real-Time

```
┌──────────────────────────────────────────────────┐
│  1. INGESTA                                      │
│  Polygon WebSocket → Kafka Topic "market.bars"  │
│  Schema: {symbol, timestamp, ohlcv, vwap}       │
└────────────────┬─────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────┐
│  2. BUFFER & ENRICHMENT                          │
│  Kafka Consumer → Redis (ventana 1min)          │
│  Enriquece con: prev_close, avg_volume, etc.    │
└────────────────┬─────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────┐
│  3. EVENT DETECTION (Flink/Spark)               │
│  Window: Tumbling 1min                           │
│  UDF: detect_volume_spike()                      │
│  UDF: detect_vwap_break()                        │
│  Output: Kafka Topic "events.detected"          │
└────────────────┬─────────────────────────────────┘
                 │
                 ├─────────────────┐
                 ▼                 ▼
┌────────────────────────┐  ┌──────────────────┐
│  4a. STORAGE           │  │  4b. ALERTING    │
│  TimescaleDB           │  │  Filter rules    │
│  - bars_1m             │  │  Notify users    │
│  - events_intraday     │  │  (email/SMS/push)│
└────────────────────────┘  └──────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────┐
│  5. FEATURE COMPUTATION                          │
│  Feast Feature Store                             │
│  - RSI, Bollinger Bands, etc.                    │
│  - Cache en Redis (serving <10ms)               │
└────────────────┬─────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────┐
│  6. ML INFERENCE                                 │
│  Model Server (FastAPI)                          │
│  - Fetch features from Feast                     │
│  - Predict: bullish/bearish/neutral              │
│  - Confidence score                              │
└────────────────┬─────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────┐
│  7. DASHBOARD (WebSocket Push)                   │
│  Frontend: React + WebSocket                     │
│  Real-time updates: eventos, predicciones        │
└──────────────────────────────────────────────────┘
```

---

## 6. MODELOS DE IA/ML PROPUESTOS

### 6.1 Screeners Inteligentes

#### **A) Momentum Breakout Predictor**
```
Objetivo: Predecir probabilidad de continuación después de breakout

Features:
- Volume ratio (actual vs 20-day avg)
- Price change magnitude
- VWAP position
- Recent events (last 1h, 4h, 1d)
- Sector momentum
- Time of day
- Market condition (SPY trend)

Target:
- Binary: breakout continúa (>2% next 30min) o no
- Regression: expected return next 30min

Model:
- XGBoost Classifier
- Training: 6 months historical
- Re-train: Weekly
```

#### **B) Volume Surge Classifier**
```
Objetivo: Clasificar causa de volume surge

Classes:
- News-driven (earnings, FDA, etc.)
- Technical breakout
- Short squeeze
- Pump & dump
- Unknown

Features:
- Volume characteristics (spike magnitude, duration)
- Price pattern (up/down/choppy)
- Social media mentions (Twitter, Reddit)
- News presence (last 1h)
- Options activity (if available)

Model:
- Multi-class classifier (Random Forest o LightGBM)
```

#### **C) Gap Fill Probability**
```
Objetivo: Predecir probabilidad de gap fill (pre-market gap)

Features:
- Gap size (%)
- Gap direction (up/down)
- Pre-market volume
- Catalyst present (news/earnings)
- Historical gap behavior (symbol-specific)
- Sector gap correlation

Target:
- Probability of gap fill within RTH
- Time to fill (minutes)

Model:
- Gradient Boosting (XGBoost)
```

#### **D) Short Squeeze Detector**
```
Objetivo: Early detection de potencial short squeeze

Features:
- Short interest (% float)
- Days to cover
- Volume surge (>5x avg)
- Price momentum (cumulative intraday)
- Borrow rate (if available)
- Social media mentions spike

Signals:
- High: >80% probability
- Medium: 50-80%
- Low: <50%

Model:
- Ensemble: XGBoost + LSTM (time series component)
```

### 6.2 Análisis con LLM

#### **A) Resumen Multi-Símbolo**
```
Prompt Template:
"Analiza los siguientes eventos de las últimas 2 horas:
- AAPL: volume spike (4.2x), VWAP break bullish
- MSFT: consolidation break, strength 8.5
- TSLA: flush event, -5% in 10min

Contexto del mercado:
- SPY: +0.5% today
- VIX: 15 (bajo)
- Sector Technology: +1.2%

Proporciona:
1. Resumen narrativo (3-4 frases)
2. Causas probables
3. Símbolos a vigilar
4. Riesgo/oportunidad para cada símbolo"

Output: Texto estructurado JSON
```

#### **B) Explicación de Movimientos**
```
Use Case: Usuario pregunta "¿Por qué QUBT subió 15% hoy?"

Proceso:
1. Fetch eventos intraday (volume spikes, etc.)
2. Fetch noticias recientes
3. Fetch opciones flow (si disponible)
4. Fetch sector performance
5. LLM synthesize all data → explicación narrativa

Output:
"QUBT subió 15% impulsado por:
- Anuncio de FDA breakthrough therapy (9:45 AM)
- Volume spike masivo (12x avg) en apertura
- Call options volumen inusual (strike $25)
- Sector Biotech +3% correlacionado
- Short interest alto (40%) → posible squeeze"
```

#### **C) Generación de Hipótesis**
```
Use Case: Patrón inusual detectado

Input: Symbol + unusual pattern description

Proceso:
1. Vector search: Patrones históricos similares
2. Fetch outcomes de esos patrones
3. LLM genera hipótesis posibles

Output:
"Este patrón (volume spike + VWAP reclaim post-flush)
ha ocurrido 23 veces en los últimos 6 meses.
Outcomes:
- 65% cases: Continuó alcista (avg +8% next day)
- 30% cases: Consolidó lateralmente
- 5% cases: Reversed bajista

Hipótesis posibles:
1. Capitulation shake-out seguido de compra institucional
2. News catalyst inminente (check filings)
3. Technical support bounce"
```

### 6.3 Búsqueda Semántica (Vector DB)

#### **A) Similar Companies by Behavior**
```
Query: "Empresas similares a TSLA en sector biotech"

Process:
1. Get embedding de comportamiento TSLA (últimos 3 meses)
   - Features: volatility, volume patterns, price momentum
2. Filter: sector = biotech
3. Vector search: Top 10 más cercanos
4. Rank by: similarity score + market cap + liquidity

Output:
1. MRNAX (similarity: 0.92) - "Alta volatilidad, volume spikes frecuentes"
2. SAVA (similarity: 0.89) - "Momentum driven, news-sensitive"
...
```

#### **B) Historical Pattern Search**
```
Query: "Patrones históricos como [CURRENT_PATTERN]"

Process:
1. Embed current pattern (últimos 5 días de OHLCV + eventos)
2. Vector search en historical_patterns index
3. Return Top 20 matches con outcomes

Output:
"Encontrados 18 patrones similares (similarity >0.85):
- 2025-03-15 AAPL: Mismo setup → +12% next week
- 2025-02-08 NVDA: Mismo setup → -3% next week (reversed)
...

Agregado:
- 67% casos: Bullish outcome (avg +8.2%)
- 22% casos: Neutral
- 11% casos: Bearish"
```

#### **C) News-Driven Event Correlation**
```
Query: "Eventos correlacionados con earnings surprises positivos"

Process:
1. Fetch historical earnings dates + surprises
2. Fetch intraday events (±3 days earnings)
3. Embed event sequences
4. Cluster y identificar patrones comunes

Output:
"Patrones pre-earnings (T-1 a T-0):
- 45% casos: Volume spike día antes
- 38% casos: Consolidation break 2 días antes
- 25% casos: Flush seguido de reclaim

Post-earnings positivo:
- 78% casos: Gap up + sustained momentum
- 15% casos: Gap up + fade
- 7% casos: No gap"
```

---

## 7. PLAN DE IMPLEMENTACIÓN

### 7.1 Fase 3.1: Database Design & Migration (2 semanas)

**Objetivo:** Migrar datos actuales a sistema escalable

**Tareas:**
1. **Diseño de Schema TimescaleDB** (3 días)
   - Schema detallado (barras, eventos, features)
   - Índices y optimizaciones
   - Políticas de retención (compression, drop old chunks)

2. **Setup Infrastructure** (3 días)
   - Deploy TimescaleDB (Docker o managed service)
   - Deploy Redis (caching + pub/sub)
   - Setup S3/MinIO (data lake)

3. **Migración de Datos Históricos** (5 días)
   - Script: Parquet → TimescaleDB (bulk copy)
   - Validación: Row counts, checksums
   - Performance testing: Query latency

4. **Vector DB Setup** (2 días)
   - Deploy Pinecone (o Qdrant)
   - Create indexes (patterns, embeddings)
   - Ingest initial embeddings (sample data)

**Entregables:**
- Schema SQL completo
- Scripts de migración
- Benchmark de queries
- Backup strategy documentada

---

### 7.2 Fase 3.2: Real-Time Ingestion (3 semanas)

**Objetivo:** Ingestar datos streaming desde Polygon

**Tareas:**
1. **Polygon WebSocket Client** (5 días)
   - Python client con reconnection logic
   - Subscribe a: trades, quotes, minute bars
   - Error handling robusto
   - Rate limiting awareness

2. **Kafka Setup & Integration** (4 días)
   - Deploy Kafka cluster (3 brokers)
   - Create topics: market.bars, market.trades
   - Producer: WebSocket → Kafka
   - Consumer: Kafka → TimescaleDB

3. **Stream Processing (Básico)** (5 días)
   - Apache Flink job (o Spark Streaming)
   - Windowing: Tumbling 1min
   - Aggregations: OHLCV, VWAP
   - Output: TimescaleDB + Redis cache

4. **Monitoring & Alerting** (2 días)
   - Prometheus metrics (lag, throughput)
   - Grafana dashboards
   - Alertas: latency >1s, consumer lag >1000

**Entregables:**
- WebSocket client production-ready
- Kafka pipeline funcionando
- Flink jobs desplegados
- Monitoring dashboard

---

### 7.3 Fase 3.3: ML Models & Feature Store (4 semanas)

**Objetivo:** Entrenar y desplegar modelos ML

**Tareas:**
1. **Feature Engineering** (7 días)
   - Definir features (100-200 features)
   - Backfill historical features
   - Feature store setup (Feast)
   - Online serving (Redis)

2. **Model Training** (7 días)
   - Momentum Breakout Predictor
   - Volume Surge Classifier
   - Gap Fill Probability
   - Training pipeline (Airflow o Prefect)

3. **Model Serving** (5 días)
   - FastAPI model server
   - Load balancing (NGINX)
   - A/B testing framework
   - Monitoring (latency, accuracy)

4. **Backtesting Framework** (5 días)
   - Simulate trades based on signals
   - Performance metrics (Sharpe, max DD, win rate)
   - Walk-forward validation
   - Report generation

**Entregables:**
- Feature definitions (Feast)
- Trained models (pickle/ONNX)
- Model server API (FastAPI)
- Backtesting results report

---

### 7.4 Fase 3.4: Frontend & Alerts (2 semanas)

**Objetivo:** Dashboard y sistema de alertas

**Tareas:**
1. **API REST** (4 días)
   - FastAPI endpoints:
     - GET /events (filtros: symbol, time, type)
     - GET /screener (condiciones custom)
     - GET /predictions (ML signals)
   - Authentication (JWT)
   - Rate limiting

2. **WebSocket Server** (3 días)
   - Real-time push de eventos
   - Subscriptions por símbolo
   - Heartbeat para mantener conexión

3. **Dashboard** (5 días)
   - Streamlit prototype (o React)
   - Views:
     - Real-time event feed
     - Screener con filtros
     - Charts (TradingView embeds)
     - ML predictions
   - Mobile-responsive

4. **Alert System** (2 días)
   - Email alerts (SendGrid)
   - SMS (Twilio)
   - Push notifications (Firebase)
   - User preferences management

**Entregables:**
- API documentada (OpenAPI/Swagger)
- Dashboard funcional
- Alert system operativo
- User onboarding docs

---

## 8. PREGUNTAS CLAVE PARA EL NUEVO AGENTE

### 8.1 Diseño de Base de Datos

**Q1:** ¿TimescaleDB o ClickHouse para time series?
- Consideraciones: Query patterns, agregaciones, inserts concurrentes
- Trade-offs: PostgreSQL ecosystem vs velocidad pura

**Q2:** ¿Schema óptimo para queries complejas?
```sql
-- Ejemplo query:
SELECT symbol, COUNT(*) as events
FROM events_intraday
WHERE timestamp > NOW() - INTERVAL '1 hour'
  AND event_type IN ('volume_spike', 'vwap_break')
  AND strength > 7.0
GROUP BY symbol
HAVING COUNT(*) >= 2
ORDER BY COUNT(*) DESC;

-- ¿Qué índices necesitamos?
-- ¿Deberíamos denormalizar?
```

**Q3:** ¿Retención de datos históricos?
- Hot data: Últimos 3 meses (SSD, query rápido)
- Warm data: 3-12 meses (HDD, acceptable latency)
- Cold data: >12 meses (S3, archival)

**Q4:** ¿Estrategia de particionamiento?
- Por tiempo: 1 chunk = 1 día (TimescaleDB default)
- Por símbolo: ¿Necesario secondary partition?

---

### 8.2 Arquitectura Real-Time

**Q1:** ¿Kafka vs Redis Streams?

**Kafka:**
- Pros: Durabilidad, particiones, replay
- Cons: Complejidad operativa, overhead

**Redis Streams:**
- Pros: Simplicidad, baja latencia
- Cons: Menos durabilidad, sin backpressure nativo

**Recomendación inicial:** Redis Streams (prototipo), migrar a Kafka (producción)

**Q2:** ¿Flink vs Spark Streaming?

**Flink:**
- Pros: True streaming, state management, exactly-once
- Cons: Learning curve, menos comunidad

**Spark:**
- Pros: Ecosistema, batch + streaming unified
- Cons: Micro-batching (no true streaming)

**Recomendación:** Flink para latencia crítica

**Q3:** ¿Cómo manejar backpressure?**
- Estrategia 1: Drop events (aceptable para algunos casos)
- Estrategia 2: Buffer en Kafka (durabilidad pero latencia)
- Estrategia 3: Scale horizontalmente (más consumers)

**Q4:** ¿Stateful vs Stateless processing?**
```
Stateful necesario para:
- Cálculo de RSI, Bollinger Bands (requiere ventana histórica)
- Detección de patterns (requiere comparar con baseline)

Stateless posible para:
- Volume spikes simples (current vs threshold)
- Price alerts (current > target)
```

---

### 8.3 ML/AI Strategy

**Q1:** ¿Qué modelos para cada use case?**

| Use Case | Modelo Sugerido | Reasoning |
|----------|----------------|-----------|
| Breakout continuation | XGBoost | Tabular features, non-linear |
| Volume surge classification | Random Forest | Multi-class, interpretable |
| Time series forecast | LSTM o Prophet | Sequential dependency |
| Anomaly detection | Isolation Forest | Unsupervised |
| Similarity search | KNN (vector DB) | Embedding-based |

**Q2:** ¿Feature store necesario?**

**SÍ, porque:**
- Consistencia: Mismo feature training vs serving
- Performance: Pre-computar features caros
- Reutilización: Múltiples modelos usan mismas features

**Alternativa sin Feature Store:**
- Compute on-the-fly (latencia)
- Risk de training-serving skew

**Q3:** ¿Cómo integrar LLMs?**

**Estrategia:**
1. **Batch jobs:** Resúmenes diarios (menos crítico latencia)
2. **On-demand:** User query específica
3. **Streaming (cuidado costo):** Análisis de eventos en tiempo real

**Cost optimization:**
- Cache responses (Redis)
- Rate limiting por usuario
- Use cheaper models para queries simples (GPT-3.5)

**Q4:** ¿Vector DB: Pinecone vs Weaviate vs Qdrant?**

| Criterio | Pinecone | Weaviate | Qdrant |
|----------|----------|----------|--------|
| Hosting | Managed (cloud) | Self-hosted o cloud | Self-hosted |
| Performance | Excelente | Muy bueno | Excelente |
| Pricing | $$$ | $ (self-host) | $ (self-host) |
| Integrations | Muchos | LangChain, etc. | Menos |
| Filtrado | Metadata filter | GraphQL queries | JSON filter |

**Recomendación inicial:** Pinecone (rápido setup), evaluar Qdrant (self-host cost savings)

---

## 9. RECURSOS Y CÓDIGO

### 9.1 Archivos Clave

**Scripts de Procesamiento:**
```
scripts/processing/detect_events_intraday.py
- Detección de 5 tipos de eventos
- Sistema de batching y checkpoints
- ~1,200 líneas

parallel_orchestrator.py
- Orquestador de 4 workers paralelos
- Auto-recovery con checkpoints por worker
- Monitoring y restart automático
- ~450 líneas
```

**Schemas (Examples):**
```python
# Schema Polars para barras 1min
bars_schema = {
    "timestamp": pl.Datetime("ns", "America/New_York"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
    "vwap": pl.Float64,
    "transactions": pl.Int32
}

# Schema para eventos
events_schema = {
    "event_id": pl.Utf8,
    "symbol": pl.Utf8,
    "timestamp": pl.Datetime("ns", "America/New_York"),
    "event_type": pl.Utf8,
    "session": pl.Utf8,
    "direction": pl.Utf8,
    "strength": pl.Float64,
    "metadata": pl.Struct(...)  # Dinámico por tipo
}
```

### 9.2 Configuración

**config.yaml (estructura):**
```yaml
data_sources:
  polygon:
    api_key: "${POLYGON_API_KEY}"
    base_url: "https://api.polygon.io"
    rate_limit: 5  # req/sec

processing:
  intraday_events:
    batch_size: 50
    checkpoint_interval: 1
    events:
      volume_spike:
        threshold_multiplier: 3.0
        lookback_days: 20
      vwap_break:
        min_volume_ratio: 1.5
      # ... etc

storage:
  timescaledb:
    host: localhost
    port: 5432
    database: smallcaps

  redis:
    host: localhost
    port: 6379

  s3:
    bucket: smallcaps-historical
```

**Environment Variables:**
```bash
POLYGON_API_KEY=your_key_here
TIMESCALEDB_PASSWORD=secure_password
OPENAI_API_KEY=for_llm_features
PINECONE_API_KEY=for_vector_db
```

### 9.3 Documentación Existente

**Daily Logs (Diario del Proyecto):**
```
docs/Daily/
├── 12_FASE_2.5_INTRADAY_EVENTS.md  # Fase actual (2,668 líneas)
├── 11_FASE_2.4_*.md                 # Fases previas
└── ...
```

**Documentación Técnica:**
```
docs/fase_3.2/
├── FASE_3.2_COMANDOS_OPERACION.md
├── FASE_3.2_RESUMEN_IMPLEMENTACION.md
└── CLEANUP_ANALYSIS.md
```

**Contenido Relevante:**
- Decisiones de arquitectura tomadas
- Problemas encontrados y soluciones
- Performance benchmarks
- Lecciones aprendidas

---

## 10. ANEXOS

### 10.1 Schema Samples

**Ejemplo: Evento Volume Spike**
```json
{
  "event_id": "AAPL_20251013_093145_volume_spike",
  "symbol": "AAPL",
  "timestamp": "2025-10-13T09:31:45-04:00",
  "event_type": "volume_spike",
  "session": "RTH",
  "direction": "bullish",
  "strength": 8.5,
  "metadata": {
    "volume": 2500000,
    "avg_volume_20d": 500000,
    "volume_ratio": 5.0,
    "price_change_pct": 2.3,
    "price_at_event": 175.50,
    "vwap_at_event": 174.20
  }
}
```

**Ejemplo: Evento VWAP Break**
```json
{
  "event_id": "TSLA_20251013_140230_vwap_break",
  "symbol": "TSLA",
  "timestamp": "2025-10-13T14:02:30-04:00",
  "event_type": "vwap_break",
  "session": "RTH",
  "direction": "bearish",
  "strength": 7.2,
  "metadata": {
    "price_before": 242.50,
    "vwap": 244.00,
    "price_after": 241.00,
    "break_magnitude_pct": -1.23,
    "volume_on_break": 850000,
    "volume_ratio": 2.1,
    "held_for_bars": 3
  }
}
```

### 10.2 Ejemplos de Queries

**Query 1: Eventos recientes con filtros**
```sql
-- Símbolos con múltiples eventos alcistas última hora
SELECT
    symbol,
    COUNT(*) as event_count,
    AVG(strength) as avg_strength,
    ARRAY_AGG(event_type ORDER BY timestamp) as event_sequence
FROM events_intraday
WHERE timestamp > NOW() - INTERVAL '1 hour'
  AND direction = 'bullish'
  AND strength > 7.0
GROUP BY symbol
HAVING COUNT(*) >= 2
ORDER BY event_count DESC, avg_strength DESC
LIMIT 20;
```

**Query 2: Pattern search (con ventana temporal)**
```sql
-- Detectar "double bottom" pattern
WITH price_windows AS (
    SELECT
        symbol,
        timestamp,
        close,
        LAG(close, 5) OVER (PARTITION BY symbol ORDER BY timestamp) as close_5min_ago,
        LAG(close, 10) OVER (PARTITION BY symbol ORDER BY timestamp) as close_10min_ago
    FROM bars_1m
    WHERE timestamp > NOW() - INTERVAL '1 day'
)
SELECT symbol, timestamp, close
FROM price_windows
WHERE close < close_5min_ago * 0.98  -- Dip 1
  AND close_5min_ago > close_10min_ago * 1.02  -- Recovery between dips
  AND close > close_5min_ago * 0.99  -- Current recovery
ORDER BY timestamp DESC;
```

**Query 3: Feature serving (low latency)**
```sql
-- Features para símbolo (usado por ML model)
SELECT
    symbol,
    rsi_14,
    bb_upper,
    bb_lower,
    volume_ratio_20d,
    price_vs_vwap
FROM features_realtime
WHERE symbol = 'AAPL'
  AND timestamp = (
      SELECT MAX(timestamp)
      FROM features_realtime
      WHERE symbol = 'AAPL'
  );
```

### 10.3 Benchmarks Actuales

**Detección de Eventos (Sistema Paralelo):**
```
Hardware:
- CPU: Intel i7 (8 cores)
- RAM: 32GB
- Disk: SSD NVMe

Performance:
- Throughput: 697 símbolos/hora (4 workers)
- Latencia por símbolo: ~5 segundos (processing 6.5 meses)
- RAM por worker: ~0.11 GB
- CPU utilization: ~60-70% (4 cores)

Scaling estimado:
- 8 workers: ~1,200 símbolos/hora
- 16 workers: ~2,000 símbolos/hora (I/O bound)
```

**Queries TimescaleDB (Estimado - a verificar post-migración):**
```
Target Latency:
- Point query (1 símbolo, 1 día): <10ms
- Range query (1 símbolo, 1 mes): <100ms
- Aggregation (100 símbolos, 1 día): <500ms
- Complex join (eventos + barras): <1s

Índices requeridos:
- (symbol, timestamp DESC) - Para queries por símbolo
- (timestamp, event_type) - Para filtros por tipo
- GIN index en metadata JSONB - Para búsquedas flexibles
```

**Streaming (Target - Real-Time):**
```
Ingestion:
- Polygon WebSocket: ~2,000 símbolos @ 1 update/min = 33 msg/sec
- Kafka throughput needed: 50-100 msg/sec (con margen)
- Redis caching: <1ms GET/SET

Processing:
- Flink windowing: Process 1min window in <1s
- Feature computation: <100ms per symbol
- ML inference: <50ms per prediction

End-to-End Latency Target:
- Event occurrence → User alert: <1 second
```

---

## 11. ESTADO ACTUAL DEL SISTEMA (2025-10-13)

### Progreso Real-Time

**Sistema Paralelo Activo:**
```
Orquestador: parallel_orchestrator.py (PID: running)
Workers: 4 procesos (PIDs: 2796, 50116, 80624, 85416)

Progress:
- Worker 1: 13/219 símbolos (5.9%)
- Worker 2: 4/219 símbolos (1.8%)
- Worker 3: 17/219 símbolos (7.8%)
- Worker 4: 27/222 símbolos (12.2%)
- TOTAL: 61/879 símbolos completados (6.9%)

Performance:
- Velocidad actual: 697 símbolos/hora
- Tiempo restante: ~1.2 horas
- Auto-restart: Funcionando (5 restarts Worker 4)
```

**Próximos Pasos Inmediatos:**
1. ✅ Sistema paralelo completará en ~1.2 horas
2. ⏳ Consolidar shards en archivo final
3. ⏳ Validar datos (row counts, checksums)
4. ⏳ Iniciar Fase 3.1: Database Design

---

## 12. CONTACTO Y RECURSOS ADICIONALES

**Para el Nuevo Agente:**
- **Proyecto:** D:\04_TRADING_SMALLCAPS
- **Documentación:** docs/Daily/12_FASE_2.5_INTRADAY_EVENTS.md
- **Código clave:** parallel_orchestrator.py, detect_events_intraday.py
- **Checkpoint:** logs/checkpoints/worker_N_checkpoint.json
- **Logs:** logs/parallel_workers/worker_N.log

**Stack Actual:**
- Python 3.13
- Polars (dataframes)
- Polygon.io API
- Parquet (almacenamiento)

**Stack Propuesto (Fase 3+):**
- TimescaleDB / ClickHouse
- Kafka / Redis Streams
- Apache Flink / Spark Streaming
- Feast (Feature Store)
- Pinecone (Vector DB)
- FastAPI (API)
- React / Streamlit (Frontend)

---

**FIN DEL DOCUMENTO - READY FOR HANDOFF**

> Este documento proporciona toda la información necesaria para que el próximo agente de IA continúe el desarrollo del sistema hacia arquitectura real-time con ML/AI integrado.
