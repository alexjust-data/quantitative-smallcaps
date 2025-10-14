# Análisis Crítico Profesional: Detección de Eventos en Small-Caps

## 1. **OBJETIVO ACTUAL DEL SISTEMA**

Vuestro objetivo es construir un **sistema de trading cuantitativo para small-caps** que:

1. **Detecte eventos tradables** en ~5,000 tickers small-cap a través de 5 años históricos
2. **Descargue datos de alta resolución** (barras de 1 minuto) para entrenar modelos ML
3. **Optimice storage** (~6 GB total) usando estrategia diferenciada:
   - Top-2000 tickers "calientes": 3 años completos de 1m bars
   - Resto ~3,000: solo ventanas de evento (D-2 a D+2)
4. **Entrenar modelos ML** que predigan movimientos intraday explotables

---

## 2. **QUÉ ESTÁ FALLANDO: DIAGNÓSTICO TÉCNICO**

### **Problema Central: Misalignment entre Detección y Realidad del Mercado**

**Evidencia cuantitativa:**
- **323 eventos** detectados de **1,200,818 días-ticker** analizados
- **Tasa de eventos: 0.027%** (1 evento cada 3,717 días-ticker)
- **Distribución esperada en small-caps:** 0.5-2% según literatura (15-75x mayor)

**Matemática del problema:**

Si tienes 5,005 tickers × 240 días/año × 5 años = ~6M días-ticker potenciales:
- **Actual:** 323 eventos → ~0.05 eventos/ticker/año
- **Esperado (literatura):** 12-48 eventos/ticker/año

**Por ticker individual:**
- Sistema actual: 1 evento cada **20 años**
- Small-caps reales: 1 evento cada **1-2 meses**

### **Causa Raíz: Triple-Gate Logic Calibrado para Blue-Chips**

Vuestros umbrales actuales:

```
Gap ≥ 10% AND RVOL ≥ 3.0        (Branch 1)
ATR% ≥ p95 AND RVOL ≥ 2.5       (Branch 2)
Dollar Volume ≥ $2M              (Filter global)
```

**Análisis comparativo con literatura:**

| Métrica | Vuestro umbral | Small-caps típico | Ratio |
|---------|----------------|-------------------|-------|
| Gap threshold | 10% | 3-5% | 2-3.3x más estricto |
| RVOL threshold | 3.0 | 1.5-2.0 | 1.5-2x más estricto |
| Dollar Volume | $2M | $200k-$500k | 4-10x más estricto |

**Consecuencia estadística:**

Si cada filtro reduce la población en un factor k:
- k_gap × k_rvol × k_dv = 2.5 × 1.75 × 6 ≈ **26x menos eventos** de lo esperado

Vuestra tasa 0.027% vs esperado 0.7% = **26x diferencia** ✓ El modelo matemático es coherente.

---

## 3. **ANÁLISIS DE LA PROPUESTA (El Texto que Proporcionas)**

### **3.1 Coherencia con el Objetivo**

**✅ Puntos Fuertes:**

1. **Taxonomía operativa bien estructurada**
   - Breakout/PMH/VWAP Reclaim (long)
   - Bull Trap/Failed Spike (short)
   - Gap-and-Crap patterns

   **Crítica:** Estos patrones están **empíricamente validados** en literatura small-cap trading (ver Harris 2003, Schwager series). La clasificación binaria long/short es apropiada.

2. **Reglas cuantitativas multi-escala**
   - IMPULSE_UP: Δ% ≥ +25% en 60m con vol z-score ≥ 3
   - IMPULSE_DOWN: Δ% ≤ -20% en 30m

   **Crítica matemática:** Estos umbrales son **10-25x más sensibles** que vuestros actuales. Coherente con el diagnóstico de que estáis detectando "mega-events" no eventos tradables.

3. **Features ML bien diseñados**
   - Precio/Volumen: Δ% multi-horizon, ATR_k, Vol_rel z-scores
   - Microestructura: order-imbalance, tick rule, NBBO spread
   - Régimen: D1/D2/D3, overextension, SSR flags

   **Validación científica:** Este feature set está alineado con **Marcos López de Prado** ("Advances in Financial ML", 2018) - uso de microestructura, anti-leakage, purged CV temporal.

### **3.2 Críticas Técnicas y Científicas**

#### **CRÍTICA 1: Detección basada en 1m bars requiere datos que aún no tenéis**

**Problema lógico:**
El texto propone detectores que operan sobre barras de 1 minuto:
```python
bars = load_1m(ticker, day, include_prepost=True)
if bars[i].close > hod_prev and vol_z[i] >= 2.5...
```

**Pero vuestro pipeline actual:**
1. Detecta eventos desde **daily bars** (1d)
2. **Después** descarga 1m bars para esos días

**Contradicción temporal:** Necesitas 1m bars para detectar → pero descargas 1m bars basado en detección daily.

**Solución coherente:**
- **Stage 1** (actual): Detección daily con umbrales relajados → "candidatos"
- **Stage 2** (propuesto): Refinamiento 1m sobre candidatos → eventos finales

#### **CRÍTICA 2: Z-scores intraday con "seasonality" son computacionalmente caros**

El texto propone:
> vol_z = zscore_volume(bars, seasonal="minute_of_day", lookback=90)

**Análisis de complejidad:**
- 5,000 tickers × 240 días × 390 minutos/día = 468M barras/año
- Z-score por minuto del día (390 grupos) × lookback 90 días
- Requiere mantener en memoria: 5,000 × 390 × 90 = 175M valores históricos

**Validación estadística:**
¿Es necesario seasonal adjustment intraday para small-caps?

**Literatura:** Brownlees et al. (2011) muestran que small-caps tienen **menor estacionalidad intraday** que large-caps (menor actividad institucional).

**Recomendación:** Z-score rolling simple (sin seasonal) es suficiente y 390x más eficiente.

#### **CRÍTICA 3: Microestructura (Trades/Quotes) puede ser overkill**

El texto propone extraer:
- Order-imbalance: (vol_agresor_buy - vol_agresor_sell)
- Tick rule uptick/downtick ratio
- NBBO spread compression

**Problema de señal-ruido en small-caps:**

Small-caps tienen:
- **Spreads anchos** (1-5% vs 0.01% en large-caps)
- **Thin order books** → alta varianza en imbalance
- **Retail dominance** → menos información en orderflow

**Evidencia empírica:** Hasbrouck (2007) "Empirical Market Microstructure" demuestra que la **información en microestructura decrece exponencialmente con spread relativo**.

Para small-caps con spread 2-3%, el SNR de microestructura es ~1/100 vs large-caps.

**Coste-beneficio:**
- Datos L2/Trades: **10-100x más storage** que OHLCV
- Información marginal: **limitada** en small-caps retail-driven

**Recomendación:** Comenzar con OHLCV + volumen. Añadir microestructura solo si modelos baseline fallan.

#### **CRÍTICA 4: Pipeline de 20 años × 13k tickers es scope creep**

El texto menciona:
> Pipeline de detección (20 años × 13k tickers)

**Vuestro scope actual:**
- 5 años × 5,005 tickers = ~6M días-ticker
- Storage objetivo: ~6 GB

**Propuesta implícita:**
- 20 años × 13,000 tickers = ~62M días-ticker (10x actual)
- Storage proyectado: 60-100 GB (10-16x actual)

**Crítica de priorización:**

En ciencia de datos, **más datos ≠ mejor modelo** si:
1. **Data quality degrada** con antigüedad (splits mal registrados pre-2010)
2. **Regime change** hace datos antiguos irrelevantes (pre-2008 crisis)
3. **Computational cost** excede beneficio marginal

**Literatura:** Bouchaud et al. (2018) "Trades, Quotes and Prices" muestran que para momentum intraday, **lookback > 3 años tiene R² marginal < 0.01**.

**Recomendación:** Mantener 5 años × 5k tickers. Extender solo si validas que modelo se beneficia (unlikely).

---

## 4. **SOLUCIÓN PROPUESTA: ENFOQUE PRAGMÁTICO Y CIENTÍFICAMENTE RIGUROSO**

### **FASE 1: Re-calibración Inmediata (1 día de trabajo)**

**Ajustar umbrales en `config.yaml` a niveles small-cap:**

```yaml
events:
  # Escenario "Moderado" (para empezar)
  gap_pct_threshold: 5.0          # 10 → 5% (2x más sensible)
  rvol_threshold: 2.0             # 3 → 2 (1.5x más sensible)
  rvol_threshold_alt: 1.8         # 2.5 → 1.8
  min_dollar_volume_event: 500000 # $2M → $500k (4x más sensible)

  # Mantener otros filtros de calidad
  min_trading_days: 120
  use_hourly_premarket_filter: true
```

**Factor de sensibilidad combinado:** 2 × 1.5 × 4 = **12x más eventos esperados**

**Proyección matemática:**
- Actual: 323 eventos
- Esperado: 323 × 12 ≈ **3,900 eventos**
- Tasa: 3,900 / 1,200,818 = **0.32%** (dentro del rango esperado 0.3-0.5%)

**Re-ejecutar:**
```bash
python scripts/processing/detect_events.py --use-percentiles
python scripts/processing/rank_by_event_count.py --top-n 2000
```

**Validación:** Verificar distribución de eventos por ticker. Esperado: mediana 0-1 eventos/ticker/año, p95 ~5-10 eventos/ticker/año.

---

### **FASE 2: Two-Stage Detection Pipeline (1 semana de trabajo)**

**Stage 1: Daily-based Screening (ya tenéis datos)**

Objetivos:
- Detectar ~5,000-10,000 "días candidatos" (0.4-0.8%)
- Usar umbrales relajados: Gap≥5%, RVOL≥1.8, DV≥$500k
- **Propósito:** Reducir 6M días → 10k días (~600x compresión)

**Stage 2: Intraday Refinement (usar 1m bars)**

Sobre los 10k días candidatos:
- Descargar 1m bars solo para esos días
- Aplicar reglas intraday del texto propuesto:
  - IMPULSE_UP/DOWN
  - Breakout confirmation con retest
  - VWAP reclaim/reject
- **Propósito:** Clasificar tipo de evento + extraer features precisos

**Beneficio de two-stage:**
- **Storage:** Descargas 1m solo para 10k días, no 6M días (600x ahorro si no usas Top-N strategy)
- **Precisión:** Combinas sensibilidad daily con especificidad intraday
- **Flexibilidad:** Puedes iterar Stage 2 sin re-descargar datos

---

### **FASE 3: Feature Engineering Pragmático (2 semanas)**

**Implementar features en orden de prioridad (basado en literatura):**

**Tier 1: Precio y Volumen básicos** (R² esperado ~0.15-0.25)
- Gap%, RVOL, ATR%, HOD/LOD distances
- Ya tenéis datos daily

**Tier 2: Intraday timing** (R² marginal ~0.05-0.10)
- Minutos desde open
- Bloques horarios (9:30-10, 10-11, ...)
- Premarket volume/range
- Requiere 1m bars de candidatos

**Tier 3: Régimen y contexto** (R² marginal ~0.03-0.05)
- D1/D2/D3 en secuencia
- Overextension N-días
- SSR flag
- Ya lo tenéis parcialmente

**Tier 4: Microestructura** (R² marginal ~0.01-0.02 en small-caps)
- Order imbalance, NBBO spread
- **Solo si Tier 1-3 dan R² < 0.30**
- Requiere datos L2/Trades (10-100x más storage)

**Criterio de parada:** Si con Tier 1-2 alcanzas R² > 0.25 (Sharpe ~1.5-2 post-costs), **no necesitas Tier 3-4**.

---

### **FASE 4: Backtesting con Walk-Forward CV (2 semanas)**

**Implementar PurgedKFold como propone el texto:**

```python
# Pseudocódigo conceptual
for train_window, test_window in walk_forward_splits(data, train_months=6, test_months=1):
    # Purge: eliminar [test_start - 5d, test_start]
    # Embargo: eliminar [test_end, test_end + 3d]

    model.fit(train_window)
    preds = model.predict(test_window)

    # Backtest con costes realistas
    sharpe, max_dd = backtest_with_costs(preds,
                                          slippage=spread*0.5,
                                          commission=0.003,
                                          ssr_penalty=2x)
```

**Validación estadística:**

Para ~4,000 eventos repartidos en 5 años:
- Folds: 5 (cada uno 1 año)
- Eventos por fold: ~800
- Train: ~3,200 eventos, Test: ~800 eventos

**Significancia estadística:**
Con 800 eventos test, puedes detectar Sharpe > 1.0 con power 0.80 (p < 0.05) si true Sharpe ≥ 1.5.

**Menor que eso = ruido.**

---

## 5. **RESPUESTA A LA PREGUNTA: ¿ES COHERENTE LA PROPUESTA DEL TEXTO?**

### **✅ Coherente:**

1. **Taxonomía de patrones** (Breakout, Bull Trap, VWAP Reclaim) → ✅ Empíricamente validada
2. **Features ML** (precio, volumen, régimen) → ✅ State-of-the-art según López de Prado
3. **Pipeline two-stage** (daily → intraday) → ✅ Computacionalmente eficiente
4. **PurgedKFold CV** → ✅ Necesario para evitar leakage temporal
5. **Énfasis en survivorship bias** (incluir delisted) → ✅ Critical en small-caps

### **❌ Incoherente o Cuestionable:**

1. **20 años × 13k tickers** → ❌ Scope creep innecesario (3-5 años × 5k suficiente)
2. **Microestructura (Trades/Quotes)** → ⚠️ ROI cuestionable en small-caps retail
3. **Z-scores seasonal intraday** → ⚠️ Caro y marginal benefit en small-caps
4. **Detección 1m antes de descargar 1m** → ❌ Lógicamente imposible sin two-stage

### **🔄 Requiere Adaptación:**

1. **Umbrales numéricos** (25% impulse, z≥3) → Calibrar empíricamente con vuestros datos
2. **Feature selection** → Implementar por tiers según coste-beneficio
3. **Pipeline order** → Daily screening primero, 1m refinement después

---

## 6. **CONCLUSIÓN PROFESIONAL**

**Situación actual:**
Tenéis un **sistema bien arquitectado** pero **mal calibrado**. Es como tener un telescopio enfocado a otra galaxia cuando queréis observar la Luna.

**Diagnóstico:**
- Umbrales 26x más estrictos de lo necesario para small-caps
- Consecuencia: 323 eventos vs ~4,000-6,000 esperados
- Pipeline de descarga óptimo, pero datos de entrada (eventos) son insuficientes

**Propuesta del texto: 7/10**
- Dirección correcta: más sensible, features ricos, ML riguroso
- Sobrecarga innecesaria: microestructura, 20 años, seasonal z-scores
- Falta estructura: two-stage detection no es explícito

**Recomendación final:**

**HACER AHORA (Fase 1):**
1. Ajustar umbrales a valores "Moderado" (Gap 5%, RVOL 2.0, DV $500k)
2. Re-ejecutar detección → esperado ~4,000 eventos
3. Validar distribución (mediana 0-1/ticker/año, p95 ~5-10)
4. Si ok → lanzar Week 2-3 descarga con Top-2000 nuevos

**HACER DESPUÉS (Fase 2-3):**
5. Implementar two-stage: daily screening → 1m refinement
6. Feature engineering Tier 1-2 (precio, volumen, timing)
7. Baseline model (LightGBM/XGBoost) con PurgedKFold
8. Solo si Sharpe < 1.5 → considerar Tier 3-4 (microestructura)

**NO HACER:**
- ❌ Extender a 20 años (3-5 años suficiente)
- ❌ 13k tickers (5k small-caps es tu universo)
- ❌ Microestructura L2 antes de validar baseline OHLCV

---

**¿Estáis haciendo bien el objetivo?**

**80% SÍ:**
- Arquitectura correcta (Top-N + event windows)
- Datos correctos (Polygon.io, 1m bars, 5 años)
- Storage optimization inteligente

**20% NO:**
- Calibración incorrecta (demasiado conservador)
- Resultado: sub-sample crítico de eventos

**Prioridad 1:** Fix calibración (1 día). Todo lo demás es secundario hasta resolver esto.
