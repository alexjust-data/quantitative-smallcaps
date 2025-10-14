Perfecto, Alex — excelente resumen, esto está exactamente donde debe estar.
Te confirmo: **el pipeline actual está estable, calibrado y descargando correctamente**.
Así que **no se toca nada de lo que ya funciona** (es una base “en producción”).
A partir de aquí, el siguiente paso **no es rehacer**, sino **ampliar y enriquecer** lo que ya está en marcha con las dos líneas nuevas:

---

## 🧭 RESUMEN DE DÓNDE ESTAMOS

| Fase                          | Estado | Descripción                                                                        |
| ----------------------------- | ------ | ---------------------------------------------------------------------------------- |
| **Week 1**                    | ✅      | Daily + Hourly (base histórica completa).                                          |
| **Week 2–3**                  | 🔄     | Descarga en curso Top-2000 1-minute bars (3 años).                                 |
| **Detector Multi-Branch**     | ✅      | Calibrado, validado 71 % precisión.                                                |
| **Validación Manual**         | ✅      | Confirmado con patrones reales (BNAI, LTBR, etc.).                                 |
| **Infraestructura y scripts** | ✅      | `download_all`, `check_status`, `detect_events`, `rank_by_event_count` operativos. |

---

## 🚀 SIGUIENTE BLOQUE — **FASE 2.1 “Flat-Base Explosions + Data Enrichment”**

### 🎯 Objetivo

Aprovechar la descarga en curso y preparar la **ampliación contextual y selectiva**, para que:

1. Detectemos explícitamente los **patrones “plano → explosión”**.
2. Etiquetemos **qué eventos doblan (+100 %) en los días siguientes**.
3. **Descarguemos en paralelo** los datos adicionales (News, Actions, Microestructura) sólo donde vale la pena.

---

### 📋 PASO 1 — Añadir “Flat-Base” y “Explosión +100 %” a los eventos

Esto **no interrumpe** la descarga actual; se hace en paralelo sobre el parquet ya existente.

**Script**: `scripts/processing/annotate_events_flatbase.py` (nuevo)
**Entrada**: `processed/events/events_daily_20251009.parquet`
**Salida**: `processed/events/events_annotated_20251009.parquet`

**Campos nuevos calculados:**

| Campo                   | Descripción                                                          |
| ----------------------- | -------------------------------------------------------------------- |
| `had_flat_base_20d`     | True si ATR% < p25 y RVOL < 0.8 durante ≥ 15 de los últimos 20 días. |
| `quietness_score`       | Ratio de días “silenciosos” en 20 días previos.                      |
| `max_run_5d`            | Máximo % de subida en los 5 días posteriores.                        |
| `x2_run_flag`           | True si `max_run_5d ≥ 100 %`.                                        |
| `is_flat_base_breakout` | True si `had_flat_base_20d and branch_ire == True`.                  |

**Duración estimada:** 1–2 h (solo operaciones sobre daily).

---

### ⚙️ PASO 2 — Lanzar *descargas paralelas de contexto*

Cuando la Week 2-3 termine (o incluso ya en paralelo si tienes ancho de banda):

#### 🧵 Cola A (ya activa)

* **1-minute bars** de Top-2000 y ventanas de resto.
  ✅ Nada que tocar.

#### 📰 Cola B (Nueva) — **News ±1 día de cada evento**

**Script:** `scripts/ingestion/download_event_news.py`
Por cada ticker y evento:

* rango `[event_date−1d, event_date+1d]`
* campos: `published_utc`, `title`, `sentiment`, `source`
* guardar en: `processed/news/events_news.parquet`

**Uso:** etiquetar `has_news = True`, calcular `news_latency_min`.

#### 🧾 Cola C (Nueva) — **Corporate Actions**

**Script:** `scripts/ingestion/download_actions.py`
Descarga *Splits* y *Dividends* una vez por ticker
→ guardar en: `reference/corporate_actions.parquet`
**Uso:** ajustar precios en features y evitar falsos gaps.

#### 💹 Cola D (Opcional, más adelante) — **Trades/Quotes v3**

Solo para eventos con `x2_run_flag == True and is_flat_base_breakout == True`.
Ventana: `[event_ts − 60m, event_ts + 180m]`
Guarda prints/NBBO para microestructura.

---

### 🔍 PASO 3 — Validación y reportes

Cuando acabe la descarga y el enriquecimiento:

1. **Verifica cobertura:**

   ```bash
   python scripts/processing/check_event_enrichment.py
   ```

   Debe mostrar:

   * % eventos con `had_flat_base_20d True` (esperado ≈ 25–30 %).
   * % eventos con `x2_run_flag True` (≈ 10–15 %).
   * % eventos con `has_news True` (≈ 40–60 %).
   * % con acciones corporativas (≈ 100 %).

2. **Reporte Markdown automático** → `docs/Daily/08_FLATBASE_SUMMARY.md`

---

### 🧩 PASO 4 — Preparar Feature Engineering Tier 1-2

Cuando `events_annotated` esté listo:

* Fusionar 1-minute bars + news + actions.
* Calcular features de precio/volumen/timing.
* Labeling *triple-barrier* (`ret_15m`, `ret_60m`, `max_adverse_excursion`).

---

## ⏳ TIMELINE PROPUESTO

| Día                  | Tarea                                                         | Estimado |
| -------------------- | ------------------------------------------------------------- | -------- |
| **Día 0–1 (hoy)**    | Ejecutar `annotate_events_flatbase.py` (añadir flags/labels). | 2 h      |
| **Día 1–5**          | Mantener descarga 1-min (Week 2–3) + lanzar Cola B/C.         | 4–5 días |
| **Día 6–7**          | Verificar integridad + generar `08_FLATBASE_SUMMARY.md`.      | 1 día    |
| **Semana siguiente** | Iniciar Feature Engineering Tier 1–2.                         | —        |

---

## ✅ En resumen

* **No toques** la descarga actual ni los umbrales: ya es base estable.
* **Añade en paralelo** el cálculo de *flat-base* + *100 % run labels* (fase 2.1).
* **Activa** descargas *News* y *Corporate Actions* (bajas, baratas).
* **Guarda** esos flags en los Parquets: servirán para priorizar los eventos y para ML.
* **Trades/Quotes** solo más adelante y solo para `x2_run_flag`.

---

Si confirmas que quieres proceder, te puedo generar ahora el bloque exacto de scripts (`annotate_events_flatbase.py`, `download_event_news.py`, `download_actions.py`) y los comandos de ejecución en el orden correcto, listos para lanzar. ¿Avanzamos con eso?
