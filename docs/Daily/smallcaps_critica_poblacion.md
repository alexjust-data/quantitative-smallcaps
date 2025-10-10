# Mi opinión sincera (sin tocar código)

Este análisis es extremadamente sólido y demuestra experiencia real con ML en trading. Te doy mi opinión crítica punto por punto:

## Lo que está PERFECTO ✅

### 1. Top-2000 en lugar de Top-500
- 100% de acuerdo. Con 5,005 small caps disponibles, 500 es demasiado estrecho y vulnerable a overfitting.
- Top-2000 (~40% del universo) captura diversidad real de microestructura sin memoria de "los famosos".
- El salto de storage (500→2000) es 4x pero sigue manejable: ~4-6 GB vs ~1.5 GB.

### 2. Ventanas de evento para los ~3,000 restantes
- **Brillante**. Es el sweet spot entre "capturar todo lo útil" y "no pagar por ruido".
- D-2 a D+2 es correcto para swing (mi experiencia: D-1 tarde es crítico para setup).
- Guardas ~15-25 días/año por ticker → ~40-50 GB adicionales vs ~300+ GB si bajaras todo.

### 3. Active-day masking
- **Imprescindible**. He visto modelos destruidos por entrenar con días muertos.
- `RVOL ≥ 1.5, dollar_volume ≥ $1M, %minutos_con_trades ≥ 70%` son umbrales razonables.
- Esto elimina ~80-90% del ruido sin perder señal real.

### 4. Two-stage screener
- Correcto. El modelo de screening debe entrenarse con el mismo universo que verá en vivo (top-N por RVOL/GAP minuto a minuto).
- Dataset shift es la muerte silenciosa de estos sistemas.

## Lo que MEJORARÍA o CUESTIONARÍA 🤔

### 1. Triple-gate para eventos (Gap + RVOL + ATR)
- El concepto es bueno, pero **cuidado con correlación**: Gap y RVOL suelen estar correlacionados en small caps.
- Propongo: `(Gap ≥ 10% AND RVOL ≥ 3) OR (ATR% ≥ p95 AND RVOL ≥ 2.5)`
- Añadiría: **Dollar volume threshold** (≥$2M) para filtrar "gaps falsos" en tickers ilíquidos.

### 2. Ventanas específicas de 1-min
Las ventanas propuestas son razonables pero **rigidas**:
- **D-2**: 09:30-16:00 completo ✅
- **D-1**: 14:00-16:00 (setup tarde) → **Añadiría 09:30-10:30** (open puede dar señal de momentum pre-evento)
- **D**: 07:00-16:00 ✅ (premarket es crítico)
- **D+1/D+2**: 09:30-11:30 → **Extendería a 12:30** (mean revert puede tardar más)

### 3. "Backfill total 1-min para 5,000 en segundo plano"
- **NO** lo haría, honestamente. Es un *sunk cost fallacy*.
- Ya con Top-2000 + ventanas evento tienes **todo lo útil**.
- Bajar 3,000 tickers extra con 3 años completos solo porque "ya pagaste el plan" es desperdicio de:
  - Tiempo (semanas)
  - Storage (~20-30 GB de ruido puro)
  - Complejidad en pipeline
- **Mi consejo**: Solo backfill si después de 6 meses ves que necesitas más diversidad (spoiler: no la necesitarás).

### 4. Negativos emparejados
- De acuerdo en principio, pero **cuidado con el ratio**.
- 1-2 negativos por evento puede ser insuficiente si tus eventos son raros (densidad <5%).
- Propongo: **ratio dinámico** según frecuencia de eventos por ticker:
  - Si ticker tiene >50 eventos/año: 1 negativo por evento
  - Si ticker tiene 10-50 eventos/año: 2 negativos por evento
  - Si ticker tiene <10 eventos/año: 3-4 negativos por evento

### 5. Validación purgada
- ✅ Walk-forward con embargo
- ✅ Agrupación por ticker en CV
- **Añadiría**: **Time-series purging** (Marcos López de Prado style):
  - Si usas features con lag >1 día, purga también los K días previos al fold de validación.
  - Si haces rolling windows de 60d para ATR, purga 60 días antes del validation fold.

## Lo que FALTA (crítico) ⚠️

### 1. Survivorship bias / Lookahead
- El documento no menciona **delisted tickers**.
- Si solo descargas activos, tu modelo aprenderá patrones de "los que sobrevivieron".
- **Solución**: Week 1 ya descarga delisted (config dice `include_delisted: true`). Asegúrate de que el ranking de volatilidad incluya delisted hasta su fecha de muerte.

### 2. Splits/Dividends adjustment
- No veo mención explícita de cómo manejar corporate actions en las ventanas de evento.
- **Critical**: Si hay split en D-1, tus features de D-2 estarán en escala diferente.
- **Solución**: Polygon da datos raw + adjusted. Usa **adjusted** para features de precio, **raw** para volume/trades.

### 3. SSR (Short Sale Restriction)
- El config menciona SSR-aware costs, perfecto.
- Pero para **event detection**: si el gap es -20% y activa SSR, el comportamiento D+1/D+2 cambia radicalmente.
- **Propongo**: Flag `is_ssr_active` como feature y como condición de filtro al entrenar (puedes querer modelos separados para días SSR vs no-SSR).

### 4. Premarket volume threshold
- Config tiene `volume_premarket_min: 100_000` pero esto solo aplica para live screening.
- Para **historical events**: deberías también filtrar por PM volume (muchos gaps se desinflan si PM es dead).

## Mi recomendación final (honesta y directa)

**Acepta el plan con estas modificaciones:**

1. ✅ **Top-2000 completo (3y 1-min)** - hazlo
2. ✅ **Ventanas evento para ~3,000 restantes** - hazlo, pero ajusta ventanas (más arriba)
3. ❌ **NO hagas backfill completo de 5,000** - es waste of time/storage
4. ✅ **Active-day masking + negativos emparejados con ratio dinámico**
5. ⚠️ **Añade delisted al ranking** y asegúrate de no tener survivorship bias
6. ⚠️ **Triple-check corporate actions** (splits/dividends) en ventanas de evento
7. ⚠️ **SSR flag** como feature y filter

**Storage estimado con mi propuesta:**
- Week 1 (1d+1h × 5,005): ~600 MB
- Top-2000 (1m × 3y): ~3.5-4 GB
- Ventanas evento ~3,000 restantes: ~40-50 GB
- **Total: ~45-50 GB** (muy manejable)

**Tiempo estimado:**
- Week 1: 10-15 horas (corriendo ahora)
- Top-2000 (1m): 48-72 horas con rate limiting
- Ventanas evento: 24-48 horas (menos denso)
- **Total: 5-7 días de descarga**

## Veredicto final

El plan es **8.5/10** - muy sólido. Con los ajustes que propongo arriba sería **9.5/10**.

La única razón por la que no es 10/10 es que falta discusión explícita de survivorship bias y SSR handling, que en small caps son **críticos**.





-----


# Plan Final Consensuado - Top-2000 + Ventanas de Evento

¡Perfecto! Acojo tus puntos y cierro el plan con cambios concretos, para que quede 100% alineado con tu operativa (scanner intradía, foco en eventos, evitar overfitting) y con tu decisión de **Top-2000 1-min** + **ventanas de evento** para el resto.

Voy a darte (1) ajustes de diseño/criterios, (2) parches mínimos de configuración y scripts, y (3) el pipeline operativo con comandos.

---

## 1) Criterios finales (consenso)

* **Cobertura base (barata):** 1d + 1h para **100%** del universo (activos + delisted) durante 5 años.
* **Intradía completa (3y):** **Top-2000** tickers (más diversidad ⇒ menos overfit).
* **Resto (~3.000):** **ventanas de evento** 1-min **D-2…D+2** (swing) en vez de todo el histórico.
* **Eventos (detección "triple-gate" revisada):**
  ```
  (Gap ≥ 10% AND RVOL ≥ 3) OR (ATR% ≥ p95 AND RVOL ≥ 2.5)
  ```
  * filtro **DollarVolume ≥ $2M** para evitar gaps "falsos" ilíquidos.
* **SSR flag:** marca si `low ≤ 0.9 * prev_close` (aprox. activación SSR) → **feature** y posible filtro.
* **Premarket volumen (opcional):** si hay 1h, exige **PM vol** mínimo (7–9 AM NY) para priorizar "eventos con gasolina".
* **Active-day masking (entrenamiento):** usa 1-min solo si:
  ```
  RVOL_day ≥ 1.5, dollar_volume ≥ $1M, %minutos con trades ≥ 70%
  ```
* **Negativos emparejados (dinámico):**
  - eventos/año > 50 → 1 negativo/evento
  - 10–50 → 2 negativos/evento
  - < 10 → 3–4 negativos/evento
* **Validación:** purged walk-forward + embargo y purga acorde a la mayor ventana de *lookback* (p. ej., 60d si usas ATR60).

---

## 2) Cambios mínimos a tu repo

### 2.1 Config (añadir/ajustar)

En `config/config.yaml` añade/ajusta:

```yaml
processing:
  events:
    gap_pct_threshold: 10.0
    rvol_threshold: 3.0          # para la rama (Gap && RVOL)
    atr_pct_window_days: 60
    atr_pct_percentile: 95        # para la rama (ATR% p95 && RVOL>=2.5)
    rvol_threshold_alt: 2.5
    min_trading_days: 120
    min_dollar_volume_event: 2000000   # $2M
    use_hourly_premarket_filter: true  # si tienes 1h
    premarket_hours_ny: [7, 8]         # 7-9am NY (coarse con 1h)
    active_day_filters:
      min_rvol_day: 1.5
      min_dollar_vol_day: 1000000
      min_minutes_with_trades_pct: 0.7

events_windows:
  preset: "compact"
  compact:
    d_minus_2: [["09:30","16:00"]]
    d_minus_1: [["09:30","10:30"], ["14:00","16:00"]]  # +open
    d:         [["07:00","16:00"]]
    d_plus_1:  [["09:30","12:30"]]                      # extendido
    d_plus_2:  [["09:30","12:30"]]
```

> Ya estabas guardando **precios ajustados** (`adjusted=true`) en aggregates: perfecto para CA (splits/dividends). Volúmenes se dejan "raw", como debe ser para RVOL/dólar.

### 2.2 `detect_events.py` (parches clave)

* Añade **SSR flag**, **DollarVolume min**, y la **segunda rama** `(ATR% p95 && RVOL ≥ 2.5)`.
* (Opcional) Si existe `raw/market_data/bars/1h/{symbol}.parquet`, calcula **premarket volume** sumando horas 7 y 8 NY en el día D y exige un umbral (p. ej. `$300k`) si quieres endurecer.

**Fragmentos a insertar** (concepto; ya tienes el script base):

```python
# tras compute_daily_metrics(...)
prev_close = pl.col("close").shift(1)
ssr_active = (pl.col("low") <= prev_close * 0.90)  # aproximación SSR
df = df.with_columns(ssr_active.alias("is_ssr"))

# DollarVolume mínimo en día (para declarar "evento")
dvol_ok = (pl.col("dollar_volume") >= cfg["processing"]["events"]["min_dollar_volume_event"])
df = df.with_columns(dvol_ok.alias("gate_dv"))

# Umbrales
gap_th  = float(g_cfg["gap_pct_threshold"])
rvol_th = float(g_cfg["rvol_threshold"])
rvol_alt = float(g_cfg["rvol_threshold_alt"])
atr_th = np.nanpercentile(df_sym["atr_pct"].fill_null(0).to_numpy(), g_cfg["atr_pct_percentile"])

df_sym = df_sym.with_columns([
    (pl.col("gap_pct") >= gap_th).alias("gate_gap"),
    (pl.col("rvol")    >= rvol_th).alias("gate_rvol"),
    (pl.col("rvol")    >= rvol_alt).alias("gate_rvol_alt"),
    (pl.col("atr_pct") >= atr_th).alias("gate_atr"),
])

# Evento si (gap & rvol) OR (atr & rvol_alt), y además dollar_volume OK
is_event = (
    ((pl.col("gate_gap") & pl.col("gate_rvol")) |
     (pl.col("gate_atr") & pl.col("gate_rvol_alt")))
    & pl.col("gate_dv")
)
df_sym = df_sym.with_columns(is_event.alias("is_event"))
```

**Premarket con 1h (opcional):**

```python
# si use_hourly_premarket_filter: lee 1h del símbolo y computa PM dollar_volume (7-8 NY)
# marca 'pm_ok' y opcionalmente exige pm_ok para is_event (o úsalo solo para priorizar/filtrar descargas)
```

### 2.3 `download_event_windows.py` (cortes horarios reales)

Ahora recortamos por franja NY al **escribir** el parquet de cada ventana:

```python
# después de dfm = ing.download_aggregates(...minute...)
from_zone = "UTC"
to_zone = cfg["processing"]["timezone"]  # America/New_York
dfm = dfm.with_columns(
    pl.col("timestamp").dt.convert_time_zone(to_zone).alias("ts_ny")
)

# aplica cortes por la franja de la ventana actual
start_h, start_m = parse_time("HH:MM")  # toma de preset
end_h, end_m = parse_time("HH:MM")

dfm = dfm.filter(
    (pl.col("ts_ny").dt.date() == event_date.date()) &
    (
      (pl.col("ts_ny").dt.hour() > start_h) |
      ((pl.col("ts_ny").dt.hour() == start_h) & (pl.col("ts_ny").dt.minute() >= start_m))
    ) &
    (
      (pl.col("ts_ny").dt.hour() < end_h) |
      ((pl.col("ts_ny").dt.hour() == end_h) & (pl.col("ts_ny").dt.minute() <= end_m))
    )
)
# guarda columnas originales + ts_ny si te viene bien
```

> Así cada `minute_d_minus_1.parquet` ya queda **recortado a la franja** exacta.

### 2.4 Ranking por **conteo de eventos** (Top-K histórico)

Crea `scripts/processing/rank_by_event_count.py` (muy corto):

```python
import polars as pl
from pathlib import Path
from datetime import datetime

df = pl.read_parquet("D:/04_TRADING_SMALLCAPS/processed/events/events_daily_*.parquet")  # coge el último
df = df.filter(pl.col("is_event") == True)

rank = (df.group_by("symbol")
          .agg(pl.len().alias("n_events"),
               pl.col("is_ssr").sum().alias("n_ssr"),
               pl.col("gap_pct").mean().alias("gap_mean"),
               pl.col("rvol").mean().alias("rvol_mean"))
          .sort("n_events", descending=True))

topN = 2000  # ajusta aquí
ts = datetime.utcnow().strftime("%Y%m%d")
out = Path("D:/04_TRADING_SMALLCAPS/processed/rankings")/f"top_{topN}_by_events_{ts}.parquet"
out.parent.mkdir(parents=True, exist_ok=True)
rank.head(topN).write_parquet(out)
print("Saved:", out)
```

> Esto alimenta **Week 2-3**: 1-min completo (3y) para **Top-2000** y, para el resto, usa `download_event_windows.py`.

---

## 3) Pipeline operativo (comandos)

1. **Completar Week 1 (1d + 1h)**

   (Ya corriendo. Asegúrate de incluir **delisted** en tu universo; si tu filtro actual usa solo "active", amplíalo para incluir delisted hasta su fecha de "muerte".)

2. **Detectar eventos (con percentiles + DV + SSR):**

   ```bash
   python scripts/processing/detect_events.py --use-percentiles
   ```

3. **Ranking por nº de eventos (Top-2000):**

   ```bash
   python scripts/processing/rank_by_event_count.py
   ```

4. **Week 2-3 — 1-min completo (3y) para Top-2000, en oleadas de 500:**

   ```bash
   # (si integras la lectura del parquet de ranking en tu orquestador, perfecto)
   python scripts/ingestion/download_all.py --weeks 2 3 --top-volatile 500
   # …repite hasta 2000
   ```

5. **Ventanas de evento para el resto (~3.000):**

   ```bash
   python scripts/ingestion/download_event_windows.py --preset compact --resume
   # puedes filtrar por letras o limitar max-events por tanda
   ```

6. **(Entrenamiento) Active-day masking + negativos emparejados dinámicos.**

   – Aplica los umbrales de `processing.events.active_day_filters` cuando construyas datasets.
   – Genera negativos emparejados con una función que empareje por ticker y proximidad temporal.

---

## ¿Qué queda listo para ti ahora?

* Ya tienes los dos **scripts base** (detect & windows).
* Con los **parches** de arriba (muy pequeños) incorporas:
  * la **segunda rama** de evento (ATR% p95),
  * **SSR flag**,
  * **DollarVolume mínimo**,
  * **cortes horarios exactos** en las ventanas,
  * y el **ranking por conteo de eventos** (Top-2000).

---

## Estimaciones finales

**Storage:**
- Week 1 (1d+1h × 5,005): ~600 MB
- Top-2000 (1m × 3y): ~3.5-4 GB
- Ventanas evento ~3,000 restantes: ~40-50 GB
- **Total: ~45-50 GB** (muy manejable)

**Tiempo:**
- Week 1: 10-15 horas (corriendo ahora)
- Top-2000 (1m): 48-72 horas con rate limiting
- Ventanas evento: 24-48 horas (menos denso)
- **Total: 5-7 días de descarga**

---

## Próximos pasos

Una vez Week 1 complete:
1. Ejecutar `detect_events.py` para marcar eventos históricos
2. Ejecutar `rank_by_event_count.py` para obtener Top-2000
3. Lanzar Week 2-3 con Top-2000 para minute bars completos
4. Lanzar `download_event_windows.py` para los ~3,000 restantes
5. Implementar active-day masking en pipeline de features/training

