# Guía: Modificaciones Necesarias y Estrategia de Validación de Eventos

## 1. **ARCHIVOS QUE HAY QUE MODIFICAR**

### **Archivo Principal: `config/config.yaml`**

**Sección a modificar: `processing.events`**

**Cambios necesarios:**
- `gap_pct_threshold`: 10.0 → **5.0** (reduce a la mitad el umbral de gap)
- `rvol_threshold`: 3.0 → **2.0** (hace el filtro RVOL menos restrictivo)
- `rvol_threshold_alt`: 2.5 → **1.8** (rama alternativa más sensible)
- `min_dollar_volume_event`: 2000000 → **500000** ($2M a $500k, 4x más permisivo)

**Otros parámetros que puedes considerar ajustar:**
- `atr_pct_percentile`: Mantener en 95 (está bien)
- `premarket_min_dollar_volume`: Quizá bajar de $300k a $150k (opcional)
- `min_trading_days`: 120 días está bien (evita tickers con datos insuficientes)

**Filosofía del cambio:**
Estás pasando de detectar "mega-explosiones institucionales" (blue-chip style) a detectar "eventos tradables small-cap" (retail/momentum style).

---

### **Archivo Secundario (NO obligatorio): `scripts/processing/detect_events.py`**

**Modificaciones opcionales para mejor diagnóstico:**

1. **Añadir logging más detallado** para ver qué pasa en cada gate:
   - Cuántos días pasan `gate_gap` pero fallan `gate_rvol`
   - Cuántos candidatos se pierden en el filtro `gate_dv` ($500k)
   - Distribución de eventos por mes/año (detectar seasonality)

2. **Exportar métricas intermedias** en un CSV adicional:
   - Por cada símbolo: `n_days_gap_ok`, `n_days_rvol_ok`, `n_days_dv_ok`, `n_events_final`
   - Te permite hacer análisis post-mortem de dónde se pierden eventos

**Pero NO es obligatorio** - con solo cambiar `config.yaml` ya funcionará.

---

## 2. **ESTRATEGIA PARA PROBAR QUE SE GENERAN EVENTOS DE FORMA RAZONABLE**

### **FASE A: Validación Matemática (Pre-descarga)**

**Objetivo:** Verificar que los nuevos umbrales generan ~3,000-6,000 eventos (0.3-0.5% de 1.2M días).

**Pasos:**

1. **Modificar `config.yaml`** con valores "Moderado"
2. **Re-ejecutar detección:**
   ```bash
   python scripts/processing/detect_events.py --use-percentiles
   ```
3. **Analizar output:**
   - Leer `processed/events/events_daily_YYYYMMDD.parquet`
   - Contar `df.filter(pl.col('is_event')==True).height`
   - **Esperado:** 3,000-6,000 eventos

**Validación estadística básica:**

- **Tasa global:** eventos / 1.2M días ≈ 0.3-0.5%
- **Distribución por ticker:**
  - Mediana: 0-1 eventos/ticker/año (muchos tickers sin eventos está ok)
  - P75: 2-3 eventos/ticker/año
  - P95: 5-10 eventos/ticker/año
  - P99: 15-30 eventos/ticker/año (los "hot stocks")

**Señales de alerta:**

- ❌ **< 1,000 eventos:** Aún muy conservador, bajar más los umbrales
- ❌ **> 20,000 eventos:** Demasiado ruido, subir umbrales
- ❌ **90% de eventos en 10% de tickers:** Problema de concentración, revisar filtros

---

### **FASE B: Validación Cualitativa (Sampling Manual)**

**Objetivo:** Verificar que los eventos detectados "tienen sentido" visualmente.

**Método de sampling estratificado:**

1. **Seleccionar 20-30 eventos aleatorios** del parquet
2. **Sampling por categorías:**
   - 10 eventos de tickers "conocidos" (ej: GME, AMC, GEVO si están en tu universo)
   - 10 eventos de tickers "desconocidos" (small-caps obscuros)
   - 10 eventos de diferentes meses/años (evitar sesgo temporal)

3. **Para cada evento, verificar manualmente:**
   - **Gap:** ¿Realmente hay gap visible en daily chart?
   - **RVOL:** ¿Volumen ese día es notablemente superior a días previos?
   - **Dollar Volume:** ¿Es líquido? ($500k+ es tradable para retail)
   - **Contexto:** ¿Hay news, earnings, o es puramente técnico?

**Herramientas para validación manual:**

- **TradingView:** Buscar ticker + fecha, ver si hubo movimiento notable
- **Polygon.io web UI:** Ver barras 1d/1h de ese día
- **StockTwits/Reddit histórico:** Ver si hubo buzz ese día (indica evento real)

**Criterio de aceptación:**

- ✅ **≥ 70% de eventos sampled "tienen sentido"** → Calibración ok
- ⚠️ **50-70%** → Ajustar umbrales levemente
- ❌ **< 50%** → Problema serio en lógica de detección

---

### **FASE C: Validación Comparativa (Benchmarking)**

**Objetivo:** Comparar vuestros eventos contra listas públicas de "hot stocks" o "momentum scanners".

**Fuentes de verdad externa:**

1. **Listas públicas de day-trading:**
   - Finviz screener: "Top Gainers" histórico
   - Barchart: "Unusual Volume" daily alerts
   - TradingView: "Trending stocks" archives

2. **Para 5-10 fechas aleatorias en vuestro rango:**
   - Obtener "top movers" de esas fechas desde fuentes públicas
   - Verificar: ¿vuestro detector los capturó?

**Métricas de precisión/recall:**

- **Recall:** De 100 "top gainers +10%" conocidos, ¿cuántos detectasteis?
  - Objetivo: **≥ 60%** (no hace falta 100% porque vuestros filtros de calidad eliminan pump&dumps)
- **Precision:** De 100 eventos que detectasteis, ¿cuántos están en listas públicas?
  - Objetivo: **≥ 40%** (muchos eventos válidos no están en scanners públicos)

**Caso de uso realista:**

Si un día GME hace +50% con RVOL 15x y vuestro detector NO lo captura → hay un bug grave.

---

### **FASE D: Validación de Distribución Temporal**

**Objetivo:** Verificar que eventos están razonablemente distribuidos en el tiempo (no concentrados en crash/2020 COVID).

**Análisis de series temporales:**

1. **Eventos por mes** (60 meses en 5 años):
   - Plot: `events_per_month` vs `time`
   - **Esperado:** Picos en marzo 2020 (COVID), enero 2021 (GME), pero NO debería ser 80% del total

2. **Eventos por día de la semana:**
   - Lunes suele tener más gaps (weekend news)
   - Viernes suele tener menos eventos (profit-taking)
   - **Esperado:** Lunes ~30-35%, Martes-Jueves ~15-20%, Viernes ~10-15%

3. **Eventos por hora (si usáis timestamp intraday en Stage 2):**
   - 9:30-10:00 debería tener ~40-50% de eventos (apertura)
   - 15:30-16:00 otro ~10-15% (cierre)
   - Medio día (11-14h) ~20-30%

**Señal de alerta:**

- ❌ **> 50% de eventos en un solo mes** → Calibración sesgada a régimen específico
- ❌ **> 80% de eventos en 9:30-10:00** → Estáis detectando solo "gap plays", perdiendo intraday moves

---

## 3. **ESTRATEGIA PARA HACER GRÁFICOS DE EVENTOS (POST-DESCARGA)**

### **Arquitectura de Visualización: Two-Stage Approach**

#### **STAGE 1: Overview Dashboard (Daily Resolution)**

**Objetivo:** Vista rápida de TODOS los eventos sin necesidad de 1m bars.

**Datos necesarios:**
- Ya los tenéis: `events_daily_YYYYMMDD.parquet` + `bars/1d/{SYMBOL}.parquet`

**Gráficos a generar:**

1. **Event Calendar Heatmap:**
   - Eje X: días del año (365)
   - Eje Y: años (5 rows)
   - Color: número de eventos ese día
   - **Insight:** Ver clustering temporal (ej: crash days)

2. **Top-20 Event Days:**
   - Ranking de días con más eventos simultáneos
   - Para cada día: lista de tickers + gap% + RVOL
   - **Insight:** Identificar "market-wide events" vs "isolated moves"

3. **Per-Ticker Event Timeline:**
   - Seleccionar 1 ticker (ej: GEVO)
   - Plot daily bars (candlestick) con markers en días de evento
   - Color del marker: tipo de evento (gap+RVOL vs ATR+RVOL)
   - **Insight:** Ver si eventos preceden runs multi-día

4. **Event Distribution Histograms:**
   - Histograma de `gap_pct` (¿cuántos eventos 5-7% vs 15-20%?)
   - Histograma de `rvol` (¿cuántos eventos 2-3x vs 10x+?)
   - Histograma de `dollar_volume`
   - **Insight:** Validar que distribución es "small-cap like"

**Tecnología sugerida:**
- **Plotly** (interactivo, permite zoom/pan)
- **Altair** (declarativo, bueno para dashboards)
- **Matplotlib** (estático pero suficiente para reports)

---

#### **STAGE 2: Detailed Event Analysis (Minute Resolution)**

**Objetivo:** Deep-dive en eventos específicos para entender microestructura.

**Datos necesarios:**
- `bars/1m/{SYMBOL}/date={DATE}.parquet` (solo para eventos detectados)

**Gráficos a generar:**

1. **Intraday Event Chart (por evento individual):**
   - Candlestick 1m bars desde 9:00 a 16:00
   - Overlays:
     - VWAP (línea)
     - PMH/PML (líneas horizontales)
     - Volumen (barras abajo)
   - Markers:
     - Evento timestamp (línea vertical roja)
     - Entry/Exit hipotéticos según reglas
   - **Insight:** Validar si patrones descritos (breakout, failed spike) son visibles

2. **Multi-Event Comparison Grid:**
   - 3×3 grid de 9 eventos aleatorios
   - Cada subplot: intraday chart simplificado (precio + volumen)
   - **Insight:** Ver variabilidad de eventos, identificar subtipos

3. **VWAP Reclaim/Reject Detector:**
   - Para eventos donde precio cruza VWAP:
   - Plot precio vs VWAP con colores:
     - Verde: reclaim exitoso (precio sostiene VWAP)
     - Rojo: reject (precio falla bajo VWAP)
   - Volumen normalizado abajo
   - **Insight:** Validar si "VWAP reclaim" es señal útil

4. **Volume Profile Intraday:**
   - Para cada evento: volume-by-price histogram (lado derecho del chart)
   - Identifica:
     - **POC** (Point of Control): precio con más volumen
     - **Value Area:** 70% del volumen
   - **Insight:** Ver si eventos tienen "absorption zones" predecibles

5. **Performance Decay Analysis:**
   - Seleccionar evento
   - Plot returns post-evento: [+5m, +15m, +30m, +60m, +4h]
   - Boxplot de returns en esos horizontes para N eventos
   - **Insight:** Validar mean-reversion timing (para short setups) o continuation (long)

---

### **Herramientas y Librerías Específicas**

**Para Candlestick Charts:**
- **mplfinance** (Matplotlib wrapper para finance)
  - Ventaja: Candlesticks + volumen built-in
  - Desventaja: Estático

- **Plotly Graph Objects** (go.Candlestick)
  - Ventaja: Interactivo, zoom, crosshair
  - Desventaja: Más código

**Para Dashboards Interactivos:**
- **Streamlit**
  - Deploy local dashboard
  - Filtros: fecha, ticker, tipo_evento
  - Regenera gráficos on-the-fly

- **Jupyter Notebooks**
  - Análisis exploratorio rápido
  - Widgets ipywidgets para interactividad

**Para Reports Estáticos:**
- **Matplotlib + Seaborn**
  - Genera PDF con 20-50 eventos
  - Para review manual offline

---

## 4. **WORKFLOW COMPLETO RECOMENDADO**

### **DÍA 1: Recalibración y Validación Matemática**

1. ✏️ Modificar `config.yaml` (5 minutos)
2. ▶️ Re-ejecutar `detect_events.py` (15-30 minutos)
3. 📊 Analizar output:
   - Contar eventos: ¿3k-6k? ✅
   - Distribución por ticker: ¿razonable? ✅
4. 🔍 Sampling manual: 20 eventos aleatorios → TradingView
   - ¿≥70% tienen sentido? ✅

**Criterio de salida:** Si todo ✅ → continuar Día 2. Si no → iterar umbrales.

---

### **DÍA 2: Generar Rankings y Validar Top-2000**

1. ▶️ Re-ejecutar `rank_by_event_count.py`
2. 📋 Revisar Top-20 tickers:
   - ¿Son conocidos small-caps volátiles? (GME, AMC, MARA, RIOT, etc.)
   - ¿O son obscuros pump&dumps? (señal de ruido)
3. 📊 Plot: eventos por ticker (log scale)
   - ¿Power law distribution? (pocos tickers con muchos eventos, muchos con pocos)
   - **Esperado:** p50 = 0-1, p95 = 5-10, p99 = 15-30

**Criterio de salida:** Top-20 deben ser mayormente "legit" (70%+). Si salen puro spam → ajustar filtros.

---

### **DÍA 3-4: Descargar 1m Bars para Top-2000**

1. ▶️ Lanzar `download_all.py --weeks 2 --top-n 2000`
2. ⏳ Esperar descarga (puede tomar horas/días según rate limit)
3. 📊 Monitorear con `check_download_status.py`

**Durante la descarga:** Ya puedes empezar análisis daily (Stage 1 visualizations).

---

### **DÍA 5-7: Visualizaciones y Validación Cualitativa**

1. 📊 Generar Dashboard Overview (daily resolution):
   - Event calendar heatmap
   - Top-20 event days
   - Distribution histograms
2. 🔍 Seleccionar 30-50 eventos para deep-dive:
   - Sampling estratificado (hot tickers, obscure tickers, diferentes meses)
3. 📊 Generar Intraday Charts (minute resolution):
   - Candlestick + VWAP + volumen
   - VWAP reclaim/reject analysis
4. ✅ Validar qualitativamente:
   - ¿Los gráficos muestran patrones tradables?
   - ¿O es puro ruido?

**Criterio de salida:** Si ≥60% de eventos muestran patrones claros → OK para ML. Si no → revisar lógica de detección.

---

### **DÍA 8+: Feature Engineering y ML**

1. Extraer features Tier 1-2 (precio, volumen, timing intraday)
2. Baseline model (LightGBM) con PurgedKFold
3. Backtest con costes realistas
4. **Si Sharpe > 1.5 post-costs** → sistema validado ✅

---

## 5. **MÉTRICAS DE ÉXITO PARA VALIDACIÓN**

### **Cuantitativas:**

- ✅ **Eventos totales:** 3,000-6,000 (0.3-0.5% de días)
- ✅ **P95 eventos/ticker/año:** 5-10
- ✅ **Recall vs public scanners:** ≥60%
- ✅ **Eventos no concentrados temporalmente:** <50% en un mes

### **Cualitativas:**

- ✅ **Sampling manual:** ≥70% eventos "tienen sentido"
- ✅ **Top-20 tickers:** ≥70% son conocidos small-caps volátiles
- ✅ **Intraday patterns:** ≥60% muestran breakout/rejection claro

### **Proceso:**

- ✅ **Pipeline ejecutable end-to-end** sin errores
- ✅ **Gráficos generables** para ≥50 eventos en <10 minutos
- ✅ **Reproducibilidad:** Re-run con config diferente genera resultados coherentes

---

## 6. **SEÑALES DE ALERTA (CUÁNDO PREOCUPARSE)**

### **Red Flags en Detección:**

❌ **< 1,000 eventos:** Umbrales aún muy conservadores
❌ **> 20,000 eventos:** Demasiado ruido, no tradable
❌ **Top-20 tickers son todos penny stocks spam:** Filtros de calidad insuficientes
❌ **80%+ eventos en marzo 2020:** Over-fitted a COVID crash

### **Red Flags en Visualizaciones:**

❌ **Gráficos intraday no muestran patrones claros:** Detección daily está capturando ruido
❌ **VWAP cruces son random walks:** VWAP como feature será inútil
❌ **Volumen bars son flat (no spikes):** RVOL filter no está funcionando

### **Red Flags en ML (posterior):**

❌ **R² < 0.10 con Tier 1-2 features:** Eventos no tienen señal predictiva
❌ **Sharpe < 0.5 post-costs:** Sistema no es tradable (costes dominan)
❌ **Max drawdown > 30%:** Risk management insuficiente

---

## 7. **RESUMEN EJECUTIVO: QUÉ TOCAR Y QUÉ NO TOCAR**

### **✏️ TOCAR (Crítico):**

1. **`config/config.yaml`** → Ajustar 4 umbrales (Gap, RVOL, RVOL_alt, DollarVol)
2. **Re-ejecutar detección + ranking** → Validar ~4k eventos
3. **Sampling manual** → 20-30 eventos en TradingView

### **⚠️ CONSIDERAR (Opcional):**

1. **Añadir logging detallado** en `detect_events.py` → Debugging
2. **Exportar métricas intermedias** → Post-mortem analysis
3. **Ajustar premarket filter** → $300k → $150k (si pierdes eventos válidos)

### **🚫 NO TOCAR (Dejar para después):**

1. **Lógica de triple-gate** → Está bien diseñada, solo mal calibrada
2. **Pipeline de descarga** → Funciona correctamente
3. **Estructura de datos** → Parquets están bien organizados
4. **Two-stage strategy** → Top-2000 + event windows es óptima

---

## 8. **FILOSOFÍA FINAL: ITERACIÓN RÁPIDA**

**Principio de Pareto aplicado:**

- **20% esfuerzo (cambiar 4 números en YAML)** → **80% mejora (12x más eventos)**
- **80% esfuerzo (reescribir detector, microestructura, 20 años data)** → **20% mejora marginal**

**Vuestra prioridad inmediata:**

1. Cambiar `config.yaml` (5 min)
2. Re-run detection (30 min)
3. Validar manualmente 20 eventos (1 hora)
4. **Si funciona** → lanzar Week 2-3 descarga
5. **Si no funciona** → ajustar umbrales y repetir

**NO gastéis tiempo en:**
- Reescribir código existente
- Implementar microestructura L2
- Extender a 20 años de datos
- Dashboards complejos antes de validar datos

**Una vez tengáis 4k eventos validados**, entonces sí:
- Descargar 1m bars
- Hacer visualizaciones deep-dive
- Feature engineering
- ML models

**Bottom line:** Fix calibración primero. Todo lo demás es secundario.
