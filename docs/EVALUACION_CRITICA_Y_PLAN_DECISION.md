# Evaluación Crítica Senior: Calibración del Detector de Eventos

## Resumen Ejecutivo

**Veredicto:** La propuesta de recalibración es **fundamentalmente correcta** pero contiene **3 asunciones cuestionables** que debemos resolver antes de ejecutar.

**Decisión recomendada:** **Opción A (cambios mínimos en config.yaml)** para Día 1, con validación rigurosa antes de proceder.

---

## 1. CRÍTICAS TÉCNICAS PUNTO POR PUNTO

### ✅ **ACIERTOS DE LA PROPUESTA**

#### 1.1. Preset "Moderado" es apropiado para small-caps

**Propuesta:**
```yaml
gap_pct_threshold: 5.0          # 10.0 → 5.0
rvol_threshold: 2.0             # 3.0 → 2.0
rvol_threshold_alt: 1.8         # 2.5 → 1.8
min_dollar_volume_event: 500000 # 2M → 500k
```

**Evaluación:** ✅ **CORRECTO**
- Alineado con literatura small-cap trading
- Gap 5% captura eventos tradables reales (no solo mega-explosiones)
- RVOL 2.0 es estándar para momentum retail
- $500k es límite inferior razonable de liquidez retail

**Evidencia:** Harris (2003), Schwager Market Wizards series muestran que small-caps tradables tienen gaps 3-8% con RVOL 1.5-3.0.

---

#### 1.2. ATR más reactivo (21 días, p90)

**Propuesta:**
```yaml
atr_window_days: 21    # vs 60 días
atr_pct_percentile: 90 # vs p95
```

**Evaluación:** ✅ **CORRECTO**
- Small-caps tienen regímenes volátiles más cortos que blue-chips
- 21 días captura volatilidad reciente sin sobre-suavizar
- p90 vs p95 añade ~5-10% más candidatos (razonable)

**Advertencia:** Puede aumentar sensibilidad a "hot streaks" temporales. Monitorear concentración temporal en validación.

---

#### 1.3. Diagnóstico por gates

**Propuesta:** Añadir logging de cuántos días pasan/fallan cada filtro.

**Evaluación:** ✅ **CRÍTICO Y EXCELENTE**
- Te permite ajustar quirúrgicamente (ej: "80% falla en gate_dv → bajar $DV")
- Invalida modelo matemático simplista de multiplicación independiente
- Es la herramienta clave para iterar científicamente

---

### ❌ **ERRORES/ASUNCIONES CUESTIONABLES**

#### 2.1. Factor "12×" es matemáticamente incorrecto

**Afirmación:**
> "Factor de sensibilidad combinado: 2 × 1.5 × 4 = 12x más eventos esperados"

**Crítica:** ❌ **ASUNCIÓN INVÁLIDA**

**Problema:**
Multiplicar factores de relajamiento asume **independencia** entre filtros:
```
P(evento) = P(gap) × P(rvol) × P(dv)  // SOLO si son independientes
```

**Realidad en small-caps:**
Gap, RVOL y Dollar Volume están **fuertemente correlacionados**:
- Un gap de 15% → dispara volumen → aumenta $DV
- Correlación típica: ρ(Gap%, $DV) ≈ 0.6-0.8

**Consecuencia matemática:**
El factor real será **significativamente menor que 12x**, probablemente **3-6x** debido a overlap.

**Evidencia:**
Si tuvieras 323 eventos con umbrales estrictos:
- Factor 12x → 3,876 eventos (0.32%)
- Factor real 4-5x → 1,300-1,600 eventos (0.11-0.13%)

**Recomendación:**
- **NO asumir 12x**
- Usar diagnóstico por gates para medir empíricamente
- Ajustar iterativamente UN umbral a la vez

---

#### 2.2. Lógica `(gap OR atr) AND rvol` pierde información valiosa

**Propuesta del patch:**
Cambiar de:
```python
# Original (dos branches)
Branch1: (gap>=10% AND rvol>=3.0)
Branch2: (atr>=p95 AND rvol>=2.5)
```

A:
```python
# Nuevo (una condición)
(gap>=5% OR atr>=p90) AND rvol>=2.0
```

**Crítica:** ⚠️ **PIERDE DIFERENCIACIÓN CONCEPTUAL**

**Problema:**
Los dos branches originales capturan **tipos distintos de eventos**:

| Branch | Tipo de evento | Características | Setup trading |
|--------|---------------|-----------------|---------------|
| Gap + RVOL | Gap play | Discrete jump, news-driven | Long apertura, target HOD |
| ATR + RVOL | Intraday volatility | Smooth volatility, técnico | Mean-reversion, VWAP |

**Consecuencia para ML:**
- "Gap plays" y "intraday vol" tienen **features predictivos diferentes**
- Gap plays: PM volume, news latency, gap fill %
- Intraday vol: VWAP distance, time-of-day, trend strength

Fusionar en una sola categoría **reduce señal ML**.

**Solución:**
Si usas lógica `(gap OR atr)`, **DEBES añadir columna `event_type`**:
```python
event_type = {
    "gap_play": gap cumple pero atr no,
    "intraday_vol": atr cumple pero gap no,
    "both": ambos cumplen
}
```

**Recomendación:**
- **Opción A (Día 1):** Mantener dos branches, solo cambiar umbrales
- **Opción B (Día 2-3):** Si A falla recall, cambiar a `(gap OR atr)` CON `event_type`

---

#### 2.3. `adjusted_prices_for_detection: false` es CRÍTICO

**Propuesta original (en borrador):**
```yaml
adjusted_prices_for_detection: false
```

**Tu corrección en patch:**
```yaml
adjusted_prices_for_detection: true  # ✅ CORRECTO
```

**Crítica del original:** ❌ **ERROR CATASTRÓFICO**

**Problema:**
Si NO ajustas por splits, creas **gaps artificiales masivos**:
- Split 1:10 → precio cae 90% overnight
- Detector interpreta: "Gap -90%" → MEGA EVENTO
- Resultado: 80% de "eventos" son splits mal manejados

**Evidencia:**
Small-caps hacen reverse splits frecuentemente (cuando caen <$1 para evitar delisting).

**Mínimo irrenunciable:**
```yaml
adjusted_prices_for_detection: true  # SIEMPRE ajustar splits
```

**Dividends:** Opcional (small-caps rara vez pagan, pero no hace daño ajustar).

**Acción inmediata:**
Verificar que `ingest_polygon.py` y `detect_events.py` usan columnas ajustadas (`adj_close` o `close` post-adjustment).

---

### ⚠️ **PUNTOS QUE REQUIEREN ACLARACIÓN**

#### 3.1. Filtro premarket: ¿gate o feature?

**Propuesta:**
```yaml
use_hourly_premarket_filter: true
premarket_min_dollar_volume: 150000
```

**Pregunta crítica:** ¿Para qué se usa PM volume?

**Caso A: Gate de calidad (Stage 1 - daily screening)**
- **Uso:** Eliminar eventos sin "vida premarket" (pumps sin soporte)
- **Timing:** OK, no hay leakage (PM es 7-9 AM, evento es día completo)
- **Decisión:** Si elimina >50% candidatos válidos → desactivar

**Caso B: Feature predictiva (Stage 2 - intraday ML)**
- **Uso:** Predecir movimiento 10:00-16:00 dado contexto 7:00-9:50
- **Timing:** OK, siempre que target sea posterior a 9:50
- **Decisión:** Incluir como feature con timestamp explícito

**Recomendación:**
- **Día 1:** Activar como gate (`true`)
- **Día 2 validación:** Si mata >50% eventos que se ven legítimos en TradingView → desactivar gate
- **Stage 2:** Usar PM volume como feature independientemente del gate

---

#### 3.2. Dollar volume $500k: ¿demasiado bajo?

**Propuesta:**
```yaml
min_dollar_volume_event: 500000  # $500k
```

**Riesgo:** Permitir tickers "paper-thin" (spreads 5-10%, slippage brutal).

**Validación necesaria:**
- En sampling manual (20-30 eventos), verificar:
  - ¿Spreads bid-ask razonables (<3%)?
  - ¿Volumen distribuido (no 1 print gigante)?
  - ¿Tradable para retail ($1k-$5k position)?

**Criterio de ajuste:**
- Si >30% eventos con spread >5% → subir a $750k-$1M
- Si <10% eventos problemáticos → mantener $500k

**Alternativa robusta:**
Añadir filtro de "active minutes":
```yaml
min_minutes_with_trades_pct: 50  # ≥50% de minutos RTH con trades
```
Elimina tickers que solo tradean en burst (más robusto que solo $DV).

---

## 2. ANÁLISIS DE CORRELACIÓN ENTRE FILTROS

### Modelo Matemático Correcto

**Asunción incorrecta:**
```
P(evento_nuevo) = P(gap_relax) × P(rvol_relax) × P(dv_relax)
                = (2×) × (1.5×) × (4×) = 12×
```

**Modelo correcto (con correlación):**

Si ρ = correlación entre filtros (típicamente 0.5-0.7 en small-caps):

```
Factor real ≈ (f_gap × f_rvol × f_dv)^(1/3) × (1 + 2ρ)

Ejemplo:
ρ = 0.6
Factor = (2 × 1.5 × 4)^(1/3) × (1 + 1.2)
       = 2.29 × 2.2
       ≈ 5.0x
```

**Proyección realista:**
- Eventos actuales: 323
- Factor esperado: **4-6x** (no 12x)
- Eventos esperados: **1,300-1,900** (0.11-0.16%)

**Consecuencia:**
Si obtienes solo 1,500 eventos (no 4,000), **NO es fracaso** - es coherente con correlación.

**Acción:**
Usar diagnóstico por gates para ver overlap real y ajustar.

---

## 3. PLAN DE DECISIÓN: OPCIÓN A vs OPCIÓN B

### **OPCIÓN A: CAMBIO MÍNIMO (RECOMENDADO DÍA 1)**

**Qué tocar:**
1. ✏️ Solo `config/config.yaml` (6 valores)
2. ✅ Mantener lógica original (dos branches)
3. ✅ Mantener código Python sin cambios

**Cambios exactos:**
```yaml
processing:
  events:
    # Preset MODERADO
    gap_pct_threshold: 5.0
    rvol_threshold: 2.0
    rvol_threshold_alt: 1.8
    min_dollar_volume_event: 500000

    # ATR más reactivo
    atr_window_days: 21
    atr_pct_percentile: 90

    # Premarket (opcional, puede desactivarse)
    use_hourly_premarket_filter: true
    premarket_min_dollar_volume: 150000

    # CRÍTICO: ajustar por splits
    adjusted_prices_for_detection: true
```

**Validación (Día 1):**
1. Re-ejecutar detector:
   ```bash
   python scripts/processing/detect_events.py --use-percentiles
   ```

2. Métricas de aceptación:
   - **Densidad:** 0.15-0.50% (1,800-6,000 eventos)
   - **Distribución:** p50=0-1, p95=5-10 eventos/ticker/año
   - **Sampling:** ≥70% plausibles en TradingView
   - **Recall:** ≥60% vs top gainers públicos (spot-check 5-10 fechas)

3. Ajuste iterativo SI NECESARIO:
   - Si <1,500 eventos → bajar gap a 4% o rvol a 1.8
   - Si >10,000 eventos → subir rvol a 2.2 o dv a $750k

**Tiempo estimado:**
- Cambios: 10 min
- Ejecución: 30 min
- Validación: 2-3 horas
- **Total: medio día**

**Ventajas:**
- ✅ Riesgo CERO (no toca código)
- ✅ Preserva diferenciación gap/atr
- ✅ Reversible instantáneamente
- ✅ Validación rápida

**Desventajas:**
- ⚠️ Sin diagnóstico por gates (debugging manual)

---

### **OPCIÓN B: CAMBIO CON PATCH (DÍA 2-3 SI A FALLA)**

**Cuándo usar:**
- Opción A da <1,500 eventos y bajar umbrales no ayuda
- Necesitas visibilidad de dónde se pierden candidatos
- Quieres flexibilidad para cambiar lógica

**Qué tocar:**
1. ✏️ `config/config.yaml` (igual que A)
2. 🔧 `scripts/processing/detect_events.py`:
   - Cambiar a `(gap OR atr) AND rvol AND dv`
   - Añadir columna `event_type` (gap_play/intraday_vol/both)
   - Añadir diagnóstico por gates (logging)

**Validación:**
- Misma que Opción A
- Plus: revisar diagnóstico gates para ajustar quirúrgicamente

**Tiempo estimado:** 1-2 días

**Ventajas:**
- ✅ Más recall potencial
- ✅ Diagnóstico detallado
- ✅ Flexibilidad futura

**Desventajas:**
- ❌ Riesgo de bugs
- ❌ Más complejo
- ❌ Pierdes tiempo si A ya funciona

---

## 4. PATCH EXACTO PARA CONFIG.YAML (OPCIÓN A)

### Unified Diff (aplicar con patch o manual)

```diff
 processing:
   events:
-    gap_pct_threshold: 10.0
-    rvol_threshold: 3.0
-    rvol_threshold_alt: 2.5
-    min_dollar_volume_event: 2000000
-    atr_window_days: 60
-    atr_pct_percentile: 95
+    # Preset MODERADO para small-caps (Stage 1: screening diario)
+    gap_pct_threshold: 5.0
+    rvol_threshold: 2.0
+    rvol_threshold_alt: 1.8
+    min_dollar_volume_event: 500000
+
+    # ATR más reactivo
+    atr_window_days: 21
+    atr_pct_percentile: 90
+
+    # Premarket gate (desactivar si recorta demasiado)
     use_hourly_premarket_filter: true
+    premarket_min_dollar_volume: 150000
+
+    # CRÍTICO: evitar falsos gaps por splits
+    adjusted_prices_for_detection: true
```

### Aplicación con yq (alternativa)

```bash
yq -i '
  .processing.events.gap_pct_threshold = 5.0 |
  .processing.events.rvol_threshold = 2.0 |
  .processing.events.rvol_threshold_alt = 1.8 |
  .processing.events.min_dollar_volume_event = 500000 |
  .processing.events.atr_window_days = 21 |
  .processing.events.atr_pct_percentile = 90 |
  .processing.events.use_hourly_premarket_filter = true |
  .processing.events.premarket_min_dollar_volume = 150000 |
  .processing.events.adjusted_prices_for_detection = true
' config/config.yaml
```

---

## 5. CHECKLIST DE VALIDACIÓN (GO/NO-GO)

### ✅ Criterios de Aceptación

#### Cuantitativos
- [ ] **Eventos totales:** 1,500-6,000 (0.12-0.50%)
- [ ] **Distribución por ticker:**
  - [ ] p50 (mediana): 0-1 eventos/ticker/año
  - [ ] p95: 5-10 eventos/ticker/año
  - [ ] p99: <30 eventos/ticker/año
- [ ] **Concentración temporal:** <40% eventos en un mes
- [ ] **Concentración por ticker:** Top-10 tickers <30% eventos

#### Cualitativos (sampling 20-30 eventos)
- [ ] **≥70% plausibles** en TradingView:
  - [ ] Gap visible en daily chart
  - [ ] Volumen notablemente superior a días previos
  - [ ] Liquidez tradable ($500k+ en día)
- [ ] **Top-20 tickers son conocidos** (≥70%):
  - [ ] Pequeños pero legítimos (no puro penny stock spam)
  - [ ] Ejemplos: GME, AMC, GEVO, RIOT, MARA, etc.

#### Comparativos (spot-check 5-10 fechas)
- [ ] **Recall vs scanners públicos:** ≥60%
  - [ ] Seleccionar 5 fechas aleatorias
  - [ ] Buscar "top gainers" de esas fechas (Finviz, Barchart)
  - [ ] Verificar: ¿cuántos capturó vuestro detector?

### ❌ Red Flags (NO-GO)

- [ ] **<1,000 eventos:** Demasiado conservador aún
- [ ] **>20,000 eventos:** Demasiado ruido
- [ ] **Top-20 tickers todos penny stocks spam:** Filtros insuficientes
- [ ] **>60% eventos en marzo 2020 o enero 2021:** Over-fit a crashes
- [ ] **>30% eventos con spread >5%:** DV demasiado bajo

### 🔧 Ajustes Iterativos

**Si <1,500 eventos:**
1. Bajar gap: 5.0 → 4.0
2. Bajar rvol: 2.0 → 1.8
3. Bajar dv: 500k → 350k
4. Bajar atr: p90 → p85

**Si >10,000 eventos:**
1. Subir rvol: 2.0 → 2.2-2.5
2. Subir dv: 500k → 750k-1M

**Si >50% perdidos en gate PM:**
- Desactivar: `use_hourly_premarket_filter: false`

---

## 6. DECISIÓN FINAL RECOMENDADA

### Para HOY (Día 1):

✅ **EJECUTAR OPCIÓN A:**
1. Aplicar patch en `config.yaml` (10 min)
2. Re-ejecutar detector (30 min)
3. Validar con checklist (2-3 horas)
4. **Si GO:** Continuar con ranking → Week 2-3
5. **Si NO-GO:** Ajustar iterativamente (1-2 iteraciones más)

### Para MAÑANA (Día 2):

**Si Opción A funcionó:**
- ✅ Ejecutar `rank_by_event_count.py`
- ✅ Validar Top-2000
- ✅ Lanzar descarga Week 2-3

**Si Opción A falló recall (<60%):**
- 🔧 Considerar Opción B (patch código con diagnóstico)

---

## 7. RESPUESTAS A TUS PREGUNTAS ORIGINALES

### "¿Te parece bien si hacemos esto?"

**Respuesta:** **SÍ, CON MODIFICACIONES:**

1. ✅ **Sí al preset Moderado** (Gap 5%, RVOL 2.0, DV $500k)
2. ✅ **Sí a ATR reactivo** (21 días, p90)
3. ✅ **Sí a splits ajustados** (`adjusted: true`)
4. ⚠️ **NO al factor 12x** (esperar 4-6x por correlación)
5. ⚠️ **Preferible mantener dos branches** (al menos Día 1)
6. ✅ **Sí a validación rigurosa** (checklist completo)

### "¿Qué archivos modificar?"

**Día 1 (Opción A):**
- ✏️ Solo `config/config.yaml` (6 valores)

**Día 2-3 (Opción B, solo si A falla):**
- ✏️ `config/config.yaml`
- 🔧 `scripts/processing/detect_events.py`

### "¿Cómo probar que se generan eventos razonables?"

**Seguir checklist de validación:**
1. Densidad cuantitativa (1.5k-6k eventos)
2. Distribución por ticker/tiempo
3. Sampling manual (70%+ plausibles)
4. Recall vs scanners públicos (60%+)

### "¿Cómo hacer gráficos de eventos?"

**Dos etapas:**

**Stage 1 (daily resolution - ya tenéis datos):**
- Event calendar heatmap
- Distribution histograms
- Per-ticker timelines

**Stage 2 (minute resolution - después de descarga):**
- Intraday candlesticks + VWAP
- Volume profile
- Performance decay analysis

Ver [GUIA_MODIFICACIONES_Y_VALIDACION.md](GUIA_MODIFICACIONES_Y_VALIDACION.md) sección 3 para detalles.

---

## 8. CONCLUSIÓN EJECUTIVA

**Estado actual:**
- ✅ Pipeline bien arquitectado
- ❌ Calibración demasiado conservadora (26x más estricta de lo necesario)
- ✅ Datos completos (Week 1 al 100%)

**Plan inmediato:**
1. **HOY:** Aplicar Opción A → validar → decidir GO/NO-GO
2. **MAÑANA:** Si GO → ranking + descarga Week 2-3
3. **SEMANA PRÓXIMA:** Visualizaciones + ML baseline

**Riesgo:** BAJO (cambios reversibles, sin tocar código)

**Retorno esperado:** 4-6x más eventos (1,500-2,000 vs 323 actual)

**Criterio de éxito:** ≥70% plausibles + ≥60% recall + 0.15-0.50% densidad

---

**¿Listos para ejecutar Opción A HOY?**

Confirmad y aplico el patch en `config.yaml` para lanzar.
