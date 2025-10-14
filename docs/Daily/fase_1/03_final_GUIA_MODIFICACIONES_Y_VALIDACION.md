¡Vamos por partes, Alex! Te doy una lectura crítica y “de auditoría” (matemática, metodológica y con referencias a vuestros propios scripts) del estado actual, por qué no estáis viendo suficientes eventos, y un plan de modificaciones + validación en el formato que pides.

# Objetivo ahora mismo

Construir un **detector fiable de “días-Evento” en small caps** (gap/momentum/flush) que:

1. capture una **muestra amplia y representativa** de episodios realmente tradables,
2. **minimice sesgos** (survivorship/look-ahead), y
3. permita luego un **Stage-2 intradía** con 1-min para features/entradas.

Ese detector debe operar sobre vuestros 1d/1h ya descargados y producir un `events_daily_YYYYMMDD.parquet` razonablemente denso (miles de eventos), **antes** de acometer las descargas 1-min masivas.

# Qué está fallando (diagnóstico)

* Con la lógica actual de **triple-gate** [(gap≥10% & RVOL≥3) OR (ATR%≥p95 & RVOL≥2.5)] + **DollarVol ≥ $2M** + filtro opcional de premarket, sólo emergen **323 eventos** sobre ~1.2M días evaluados (≈0.03%) — **demasiado selectivo** para small caps. La implementación confirma esos gates y el filtro de PM desde 1h. 
* Vuestro **checker** refleja que la base 1d/1h está completa, así que el cuello de botella no es la descarga sino la **calibración**. 

En la literatura, los movimientos explotables en microcaps tienen **asimetría de colas y alta dispersión**; exigir percentiles tan altos (ATR p95) y RVOL tan elevados **reduce el recall** y sesga la muestra hacia “mega-eventos” raros, insuficientes para entrenar modelos robustos.

# Qué propone tu texto y el de tu compañero (y mi crítica)

1. **Rebajar umbrales a un preset “Moderado”** (Gap 5%, RVOL 2.0/1.8, DollarVol $500k).
   — Totalmente coherente con small-caps: eleva el **recall** sin hundir la precisión (siguen existiendo filtros de calidad). La guía concreta qué tocar en `config.yaml` (4 números), y sugiere logging/diagnóstico opcional en el detector. 

2. **Mantener la lógica triple-gate + percentiles ATR** pero recalibrada.
   — Bien: conserváis la arquitectura y reducís fricción. El código ya soporta percentiles ATR y el premarket check desde 1h. 

3. **Two-Stage Pipeline (Daily screening → Intradía 1m)**.
   — Correcto metodológicamente y computacionalmente: primero encontráis “días candidatos” (barato), luego refináis en 1-min sólo ahí (caro). Es exactamente el patrón recomendado en investigación de “event studies”.

4. **Validación escalonada (cuantitativa + cualitativa + comparativa)**.
   — Excelente: define rangos objetivo (3k–6k eventos, 0.3–0.5% de días), distribuciones esperadas por ticker, y checks temporales/externos (precision/recall vs. listas públicas). Esto evita autoengaños.

**Matemática esperada tras recalibrar**
Pasar de (10%, 3×, $2M) a (5%, 2×, $500k) multiplica la sensibilidad. Vuestra propia proyección (~12×) llevaría de 323 a ≈3,900 eventos (0.32%), consistente con la densidad objetivo para small caps (y con lo que ves en sala: 5–10 candidatos/día).

# Riesgos / puntos a vigilar

* **Concentración por ticker/regímenes**: si 60–70% de eventos se concentran en unos pocos “hot” símbolos o en meses únicos (COVID, meme 2021), el set entrenará mal. Vuestra guía ya propone métricas para detectarlo y límites de concentración temporal. 
* **Leakage de premarket**: el filtro PM usa 1h del **mismo día**; asegurar que sólo se usa lo **hasta entonces disponible** si vais a etiquetar como “detectable a la apertura”. El código actual calcula PM con 1h y lo usa sólo como **gate** (ok), pero tomad nota cuando defináis targets. 
* **Dollar volume demasiado bajo**: bajar a $500k puede introducir tickers “paper thin”. Está bien para recall, pero monitorizad la **tasa de falsos positivos** y subid a $750k–$1M si hay mucho ruido.

# Estructura y plan (en el mismo formato “guía/roadmap”)

## 1) Archivos a tocar (mínimos y claros)

* **`config/config.yaml` (processing.events)**
  Cambios:
  `gap_pct_threshold: 5.0` · `rvol_threshold: 2.0` · `rvol_threshold_alt: 1.8` · `min_dollar_volume_event: 500000`
  (opcional: `premarket_min_dollar_volume: 150000`) — ver guía. 

* **`scripts/processing/detect_events.py` (opcional, diagnóstico)**
  Añadir contadores por gate y dumps intermedios para entender **dónde se pierden candidatos** (no cambia la lógica). 
  *La lógica triple-gate con percentiles ATR y filtro PM ya está implementada.* 

*(No es necesario tocar downloader ni estructura de datos: están correctos.)* 

## 2) Estrategia de validación (paso a paso)

### Fase A — Validación matemática (Día 1)

* Ejecutar detección con preset “Moderado”:
  `python scripts/processing/detect_events.py --use-percentiles`
* Métricas de aceptación:
  **Eventos totales** 3k–6k (≈0.3–0.5%) · **Mediana** 0–1 evento/ticker/año · **p95** 5–10.
  Si <1k → bajar umbrales; si >20k → subirlos. 

### Fase B — Validación cualitativa (Día 1)

* **Muestreo estratificado**: 20–30 eventos (tickers conocidos vs. obscuros, meses distintos).
* Revisar en charting externo si **“tiene sentido”** (gap visible, RVOL crecido, liquidez mínima).
* Aprobado si **≥70%** son plausibles. 

### Fase C — Validación comparativa (Día 2)

* Para 5–10 fechas aleatorias, comparar con “Top gainers / Unusual volume” públicos (histórico).
* Objetivos: **Recall ≥60%** (capturáis la mayoría de movers), **Precision ≥40%** (no todo ruido). 

### Fase D — Validación temporal (Día 2)

* **Eventos/mes** y **día de la semana**; evitar concentración extrema (p. ej., >50% en un mes).
* Abrir “red flag” si 80% caen 9:30–10:00 (sólo gap plays) o si COVID/meme dominan. 

*(Si todo esto pasa → detector calibrado.)*

## 3) Estrategia de descarga/ejecución posterior (sin código ahora)

* **Ranking actualizado** con los nuevos eventos: `rank_by_event_count.py` (Top-2000).
  Confirmad distribución tipo **power-law** (pocos muy activos, cola larga). 
* **Week 2–3**:

  * **Top-2000** → descargar 1-min (3 años).
  * **Resto (~3k)** → **ventanas de evento** (D-2 a D+2 con horarios que acordamos).
    Supervisar con `check_download_status.py` (secciones 1m y events). 
* **Stage-2** (intraday) sobre los días-Evento: extraer features de timing (minutos desde open), VWAP reclaim/reject, etc., **sin tocar aún microestructura** (trades/quotes) hasta ver la señal de Tier-1/2.

## 4) Timeline de trabajo (realista y accionable)

* **Día 1 (hoy):** Cambiar 4 umbrales en `config.yaml` → correr detección → validar A/B/C/D.
  **Criterio de salida:** 3k–6k eventos y ≥70% plausibles.
* **Día 2:** Generar ranking → sanity-check Top-20 → lanzar Week 2–3 (Top-2000 1-min).
* **Días 3–5:** Descargar 1-min Top-2000; en paralelo, preparar specs de Stage-2 features (sin L2).
* **Días 6–7:** Descarga de **ventanas** para el resto (~3k); QA de cobertura.
* **Semana 2:** Visualizaciones intradía de muestra, y baseline ML (Purged K-Fold) con Tier-1/2.
  **Criterio de salida:** señales útiles (p. ej., Sharpe post-costs ≳1.5 en validación).

## 5) Métricas de éxito (lo que define “listo para ML”)

* **Eventos totales**: 3k–6k; **recall externo** ≥60%; **concentración temporal** razonable. 
* **Cobertura 1-min**: Top-2000 completa + ventanas correctas en resto (spot-checks con charts).
* **Sin sesgos graves**: delisted incluidos desde Week 1; PM filter usado coherentemente; nada de leakage del futuro. (El script de eventos ya usa sólo datos **hasta el día** y gates definidos; mantened esa disciplina al etiquetar Stage-2.) 

---

## Conclusión

* **Sí, el enfoque es coherente**: mantenéis la arquitectura, **ajustáis calibración** (el problema real), y definís una validación por niveles que **cierra el bucle científico** (cuantitativo, cualitativo y comparativo).
* **Qué descartar**: microestructura L2/quotes por ahora; “20 años × 13k” (overkill).
* **Qué aprovechar**: todo lo de la guía (cambiar 4 umbrales y validar), vuestra lógica triple-gate y el pipeline de descargas/monitoreo ya operativo.

Cuando me digas, pasamos a **modificar sólo `config.yaml` y (si queréis) el logging de `detect_events.py`** para hacer la primera corrida de validación con el preset “Moderado”.
