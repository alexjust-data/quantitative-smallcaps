¡Sí, lo tengo claro! Te hago un “estado de proyecto” y un plan de descarga, concreto y accionable, centrado 100% en Polygon y tus scripts.

# Dónde estamos (hecho ✅)

1. **Base de datos histórica (Week 1)**

   * **Daily (1d) y Hourly (1h)** descargados para **todo el universo small caps** (≈5.2k tickers) en `raw/market_data/bars/1d|1h/*.parquet`.
   * **Reference & Corporate Actions** (tickers activos/delistados, `splits`, `dividends`) descargado y almacenado en `raw/reference` y `raw/corporate_actions`.
   * Ajustes por **splits** preparados para evitar falsos gaps.

2. **Detector diario calibrado**

   * Recalibrado con **Gap≥5%**, **RVOL≥2.0**, **ATR% p90**, **DollarVol≥$500k**.
   * Resultado: **20.695 eventos** (≈**1.72%** de días), correcto para *Stage-1 (recall alto)*.
   * Archivo de eventos: `processed/events/events_daily_YYYYMMDD.parquet`.

3. **Infraestructura de orquestación**

   * `download_all.py` (Week 1 listo, Week 2–3 preparado).
   * Reanuda descargas, paginación, rate-limits, logs y “letters” para paralelizar.

# Qué estamos haciendo ahora (en curso ▶️)

* **Validación rápida** del detector (tasa, muestreo cualitativo >70% plausibles).
* **Ranking por actividad/eventos** con `rank_by_event_count.py` para seleccionar universo **Top-N** de intradía.

# Qué vamos a hacer (siguiente paso 👉)

La meta es **descargar 1-minute** de forma eficiente, usando tu API de Polygon y lo ya detectado:

## Fase 2 — Minute bars completas para Top-N (3 años)

**Por qué**: necesitas la secuencia intradía completa para entrenar modelos de entradas (timing, VWAP, HOD/LOD, etc.).

**Qué descargar**

* **Endpoint**: Aggregates v2 — **1m** (ajustado)
* **Rango**: **3 años** por ticker (ventanas de 30 días para estabilidad)
* **Universo**: **Top-2000** (o Top-1000 si prefieres empezar)

**Cómo** (con tus scripts)

1. Generar ranking desde los eventos:

   ```
   python scripts/processing/rank_by_event_count.py --top-n 2000
   ```

   → salida: `processed/rankings/top_2000_by_events_*.parquet`

2. Lanzar descarga 1-min Top-N:

   ```
   python scripts/ingestion/download_all.py --weeks 2 3 --top-volatile 2000
   ```

   * Usa **windowing** (30 días), **resume**, **rate limit**.
   * Output: `raw/market_data/bars/1m/symbol=XYZ/date=YYYY-MM-DD.parquet`

**Control & monitoreo**

* `scripts/ingestion/check_download_status.py` para progresos y fallos.
* Si hace falta paralelizar: usar `--letters` o dividir el Top-N por lotes (ej. 4 procesos × 500).

## Fase 3 — Minute bars solo en **ventanas de evento** para el resto (~3k)

**Por qué**: maximizar señal sin bajar 3 años completos de todos.

**Qué descargar**

* **Endpoint**: Aggregates v2 — **1m** (pre+RTH)
* **Ventanas**: por cada evento de `processed/events/...` descargar **D-2 a D+2**
  (RTH completo + premarket clave, p. ej., 07:00–16:00)

**Cómo**

```
python scripts/ingestion/download_event_windows.py \
  --events processed/events/events_daily_YYYYMMDD.parquet \
  --window-pre 2d --window-post 2d
```

* Output: `raw/market_data/bars/1m/symbol=XYZ/date=...` (solo fechas de evento)

## Fase 4 — Complementarios (cuando acabe Fase 2–3)

**Short interest & short volume** (si los tenéis implementados ya):

* **Endpoints**: Reference v3 **short_interest**, **short_volume**.
* Descarga bulk por rango (3–5 años) → `raw/short_interest/*.parquet`, `raw/short_volume/*.parquet`.
* Procesado y alineación por **publish_date** → `processed/short/short_features_*.parquet`.

# Resumen de endpoints Polygon (lo esencial para tu proyecto)

* **OHLCV**: `/v2/aggs/ticker/{T}/range/1/minute|hour|day/{from}/{to}` (ajustado, sort=asc, limit=50k)
* **Corporate actions**: `/v3/reference/splits`, `/v3/reference/dividends`
* **Reference**: `/v3/reference/tickers`, `/v3/reference/tickers/{T}` (detalles, shares out, etc.)
* **(Opcional)** Noticias: `/v2/reference/news` (para catalizador)
* **(Opcional)** Short data: `/v3/reference/short_interest`, `/v3/reference/short_volume`

# Filtros & reglas que ya estamos aplicando (y mantener)

* **Universe small caps**: precio 0.5–20$, cap <2B, excluir ETF/ADR/OTC si así lo definiste.
* **Ajustes**: **splits siempre** (evita gaps falsos).
* **Stage-1** (detector diario): Gap≥5% **o** ATR% p90, **y** RVOL≥2.0, **y** $DV≥$500k (PM opcional).
* **Stage-2** (intradía después): features de timing/VWAP/breakout; **sin** L2/quotes por ahora.

# Qué revisar durante la descarga (checks rápidos)

* **Cobertura 1-min Top-N**: % de tickers completos (3 años), reintentos/fallos.
* **Cobertura ventanas evento**: % de eventos con todos los días D-2..D+2 descargados.
* **Calidad**: timestamps ordenados, *NaNs*, cruce con `splits/dividends`, tamaño por símbolo razonable.

# Qué NO hace falta ahora

* No bajar 1-min de **todos** los 5k (no aporta señal vs. coste/tiempo).
* No L2 (Trades/Quotes) aún: primero valida potencia con OHLCV-1m; añade microestructura solo si el baseline queda corto.

---

## En una línea

**Ahora toca**: (1) generar Top-2000 por eventos, (2) descargar **1-min 3y** para esos tickers, (3) descargar **ventanas 1-min** D-2..D+2 para el resto ~3k — todo con tus scripts existentes.
Cuando termine, te digo cómo validar cobertura y pasamos al *Stage-2* (features intradía y etiquetas) antes del primer backtest.
