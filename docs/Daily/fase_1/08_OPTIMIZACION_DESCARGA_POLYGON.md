# Optimización de Descarga Polygon.io - Análisis Completo

**Fecha**: 2025-10-09
**Objetivo**: Maximizar uso de datos disponibles en Polygon.io sin desperdiciar recursos

---

## 📊 Datos que ACTUALMENTE descargamos

### ✅ Market Data (Stocks)
1. **Aggregate Bars (OHLC+V)**
   - ✅ Daily bars (1d) - Todos los símbolos
   - ✅ Hourly bars (1h) - Todos los símbolos
   - ✅ Minute bars (1m) - Top-2000 full + event windows para resto

### ✅ Reference Data
2. **Tickers Active**
   - ✅ Metadata de tickers activos (type, name, market, etc.)

3. **Corporate Actions**
   - ✅ Splits (para ajustar precios)
   - ❌ Dividends (no descargamos)

4. **Short Interest & Volume**
   - ✅ Short Interest (indicadores de sentiment)
   - ✅ Short Volume (volumen de ventas cortas)

---

## 🚀 Datos ADICIONALES que podríamos descargar

### 🔥 ALTA PRIORIDAD (útiles para trading intraday)

#### 1. **Snapshots (Market-wide)**
**Qué es**: Estado instantáneo de todos los tickers en un momento dado

**Endpoint**: `/v2/snapshot/locale/us/markets/stocks/tickers`

**Incluye**:
- Last trade price
- Bid/Ask spread
- Day's high/low/open/close
- Today's volume
- Today's VWAP
- Prevday close (para calcular gap en tiempo real)

**Uso**:
- Monitoreo en tiempo real de gaps
- Detección de eventos en desarrollo
- Validación de señales pre-entrada

**Frecuencia recomendada**:
- Durante market hours: Cada 1-5 minutos
- Almacenar snapshots de 09:30, 10:00, 12:00, 15:30, 16:00

**Storage estimado**: ~100 KB × 5 snapshots/día × 252 días × 5 años = **~600 MB**

**Rate limit impact**: 1 request por snapshot (muy eficiente)

---

#### 2. **Trades (Tick-by-Tick)**
**Qué es**: Cada trade individual ejecutado

**Endpoint**: `/v3/trades/{ticker}`

**Incluye**:
- Timestamp exacto (nanoseconds)
- Price
- Size (shares)
- Exchange
- Conditions (sale condition codes)

**Uso**:
- Análisis de microestructura de mercado
- Detección de "whale prints" (trades grandes)
- Order flow analysis
- VWAP preciso

**Problema**: **Volumen masivo de datos**

**Ejemplo**:
- Ticker con 1M volume/día = ~10-100k trades
- Top-2000 tickers = ~200M trades/día
- Storage: **~10-50 GB/día sin comprimir**

**Recomendación**:
- ❌ NO descargar para todos los tickers
- ✅ Solo para eventos detectados (D-2 a D+2)
- ✅ Solo para Top-100 tickers más líquidos

**Storage optimizado**: ~50 GB para event windows (acceptable)

---

#### 3. **Quotes (NBBO)**
**Qué es**: National Best Bid & Offer en cada update

**Endpoint**: `/v3/quotes/{ticker}`

**Incluye**:
- Bid price/size
- Ask price/size
- Bid/Ask exchange
- Timestamp

**Uso**:
- Spread analysis (liquidez)
- Order book pressure
- Detectar "quote stuffing"

**Problema**: Volumen aún mayor que trades (100x updates por trade)

**Recomendación**:
- ❌ NO descargar salvo casos muy específicos
- Si necesitas liquidez → Usa bid/ask del snapshot

---

#### 4. **Technical Indicators (Pre-calculados)**
**Qué es**: Polygon calcula SMA, EMA, MACD, RSI por ti

**Endpoint**: `/v1/indicators/sma/{ticker}`, `/v1/indicators/ema/{ticker}`, etc.

**Incluye**:
- SMA (Simple Moving Average)
- EMA (Exponential Moving Average)
- MACD (Moving Average Convergence Divergence)
- RSI (Relative Strength Index)

**Uso**:
- ✅ Ahorra cálculo local
- ✅ Features pre-calculados para ML

**Problema**:
- Requiere 1 request POR indicador POR ticker POR timeframe
- Top-2000 × 4 indicators × 3 timeframes = **24,000 requests/día**

**Recomendación**:
- ❌ NO usar - es más eficiente calcular localmente con Polars/pandas_ta
- Tenemos barras → calcular indicadores toma <1 segundo

---

### 📊 MEDIA PRIORIDAD (útiles para contexto)

#### 5. **Dividends**
**Qué es**: Fechas y montos de dividendos pagados

**Endpoint**: `/v3/reference/dividends`

**Uso**:
- Ajustar precios para backtesting
- Evitar confundir dividend drops con crashes

**Frecuencia**: Descargar mensualmente (eventos poco frecuentes)

**Storage**: ~10 MB total

**Recomendación**: ✅ Descargar trimestralmente

---

#### 6. **Market Holidays & Hours**
**Qué es**: Calendario de días festivos y horarios especiales

**Endpoint**: `/v1/marketstatus/upcoming`

**Uso**:
- Evitar intentar descargar en días cerrados
- Detectar half-days (early close)

**Storage**: <1 MB

**Recomendación**: ✅ Descargar al inicio del año

---

### 🔍 BAJA PRIORIDAD (nice-to-have)

#### 7. **News & Sentiment (Benzinga)**
**Qué es**: Noticias + sentiment scores

**Endpoint**: Partner data (requiere tier especial)

**Uso**:
- Features de sentiment para ML
- Explicar movimientos inesperados

**Problema**:
- **Requiere plan Benzinga adicional** (no incluido en Basic/Starter)
- Precio alto ($$$)

**Recomendación**: ❌ Skip por ahora

---

#### 8. **Analyst Ratings**
**Qué es**: Upgrades/downgrades de analistas

**Similar a news** - requiere partner tier

**Recomendación**: ❌ Skip por ahora

---

#### 9. **Options Data**
**Qué es**: Opciones sobre acciones (calls/puts)

**Uso**:
- Implied volatility
- Options flow
- Gamma squeeze detection

**Problema**:
- Small-caps tienen opciones muy illiquid
- Data adicional masiva

**Recomendación**: ❌ Skip - enfoque en stocks

---

## 🎯 Recomendaciones Finales

### Agregar AHORA (sin interrumpir descarga actual)

#### 1. ✅ **Snapshots diarios (5 por día)**
```python
# Nuevo endpoint a añadir
def download_daily_snapshots(self, date: str, times: list = ["09:30", "10:00", "12:00", "15:30", "16:00"]):
    """Download market snapshots at key times"""
    for time_str in times:
        snapshot = self.client.get_snapshot_all("stocks")
        # Save to: raw/market_data/snapshots/{date}_{time}.parquet
```

**Beneficio**:
- Validación de gaps en tiempo real
- VWAP intraday
- Bid/Ask spreads (liquidez)

**Cost**: Minimal (5 requests/día × 252 días = 1,260 requests/año)

---

#### 2. ✅ **Dividends (trimestral)**
```python
# Ya existe en tu código pero no está en el pipeline
def download_dividends(self):
    """Download dividend history"""
    return self.download_corporate_actions(action_type="dividends")
```

**Beneficio**: Ajustar precios correctamente

**Cost**: 1 request cada 3 meses

---

### Agregar en PHASE 2 (después de tener 1-min bars)

#### 3. ⏳ **Trades para eventos (Top-100)**
Solo para:
- Top-100 tickers
- Event windows (D-2 a D+2)
- Buscar "whale prints" y order flow

**Implementar**: Después de validar que el modelo funciona con 1-min bars

---

### NO agregar (al menos por ahora)

#### ❌ **Quotes (NBBO)** - Volumen excesivo
#### ❌ **Technical Indicators** - Calcular localmente es más eficiente
#### ❌ **News/Sentiment** - Requiere plan adicional $$
#### ❌ **Options** - Illiquid en small-caps

---

## 📦 Plan de Implementación

### Paso 1: Agregar Snapshots (Esta Semana)
```python
# En download_all.py, añadir después de Week 1:
downloader.download_snapshots_for_daterange(
    from_date="2022-10-01",
    to_date="2025-09-30",
    times=["09:30", "10:00", "12:00", "15:30", "16:00"]
)
```

**Timeline**: 2-3 horas de implementación + 1 día de descarga

---

### Paso 2: Agregar Dividends (Ahora mismo)
```python
# Añadir a Week 1 pipeline:
downloader.ingester.download_corporate_actions(action_type="dividends")
```

**Timeline**: 5 minutos de implementación + 1 request

---

### Paso 3: Trades para Eventos (Phase 2)
Implementar solo si:
1. El modelo ML muestra que necesita más granularidad
2. Tenemos storage disponible (~50 GB adicional)

---

## 💾 Comparación de Storage

| Dataset | Current | With Snapshots | With Trades (events) |
|---------|---------|----------------|---------------------|
| Daily bars | ~50 MB | ~50 MB | ~50 MB |
| Hourly bars | ~500 MB | ~500 MB | ~500 MB |
| Minute bars | ~5 GB | ~5 GB | ~5 GB |
| Snapshots | 0 | ~600 MB | ~600 MB |
| Trades | 0 | 0 | ~50 GB |
| **TOTAL** | **~5.5 GB** | **~6.1 GB** | **~56 GB** |

---

## 🔥 Conclusión

### Lo que DEBES agregar:
1. ✅ **Snapshots** (600 MB, alto valor)
2. ✅ **Dividends** (10 MB, necesario para ajustes)

### Lo que PUEDES agregar después:
3. ⏳ **Trades para eventos Top-100** (50 GB, solo si el modelo lo requiere)

### Lo que NO necesitas:
4. ❌ Quotes (NBBO)
5. ❌ Technical Indicators (calcular local)
6. ❌ News/Sentiment (requiere plan adicional)
7. ❌ Options (illiquid en small-caps)

---

## 🎯 Respuesta Directa a tu Pregunta

**¿Estamos descargando toda la data útil de Polygon?**

**NO** - Nos faltan 2 cosas importantes:

1. **Snapshots** (600 MB) - Alta prioridad, fácil de añadir
2. **Dividends** (10 MB) - Crítico para ajustes de precio

**¿Podemos optimizar?**

**SÍ** - Añadiendo snapshots obtenemos:
- VWAP intraday
- Bid/Ask spreads
- Validación de gaps en tiempo real

Todo esto sin impactar rate limits (solo 5 requests/día extra).

---

## 📝 Acción Recomendada

**Ahora mismo** (sin interrumpir descarga Week 2-3):
```bash
# 1. Añadir dividends (1 request)
python scripts/ingestion/download_dividends.py

# 2. Implementar snapshots (2 horas)
# Crear: scripts/ingestion/download_snapshots.py
# Ejecutar después de Week 2-3
```

**Total tiempo**: 2-3 horas implementación + 1 día descarga snapshots

**Total storage adicional**: ~610 MB

**ROI**: Alto - obtienes 3 features críticos (VWAP, spread, prevday) por casi cero cost.
