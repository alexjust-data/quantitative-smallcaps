# Fase 2.1 - Flat-Base Explosions + Data Enrichment - EJECUTADA

**Fecha**: 2025-10-09
**Status**: ✅ EN EJECUCIÓN (3 procesos en paralelo)

---

## ✅ SCRIPTS CREADOS

### 1. annotate_events_flatbase.py
**Ubicación**: `scripts/processing/annotate_events_flatbase.py`

**Función**: Añade flags de "base plana" y labels de "+100% run" sobre eventos detectados

**Nuevos campos calculados**:
- `had_flat_base_20d` (bool) - True si ATR% < p25 y RVOL < 0.8 durante ≥15 de los últimos 20 días
- `max_run_5d` (float %) - Máximo % de subida en los 5 días posteriores
- `x2_run_flag` (bool) - True si max_run_5d ≥ 100%
- `is_flat_base_breakout` (bool) - True si had_flat_base_20d AND (branch_ire OR branch_vswg)

**Parámetros usados**:
```python
LOOKBACK_D = 20            # ventana para "quietness"
QUIET_ATR_PCT = 25         # percentil para ATR% "bajo"
QUIET_RVOL_MAX = 0.8       # RVOL máximo para días "silenciosos"
QUIET_MIN_DAYS = 15        # #días silenciosos necesarios en 20
RUN_FWD_D = 5              # horizonte para medir el "run" posterior
RUN_X2_THRESHOLD = 100.0   # +100%
```

---

### 2. download_event_news.py
**Ubicación**: `scripts/ingestion/download_event_news.py`

**Función**: Descarga noticias ±1 día alrededor de cada evento

**Datos descargados**:
- published_utc (timestamp)
- title (string)
- description (string)
- source (string)
- article_url, amp_url
- tickers (relacionados)
- sentiment (del campo insights)

**Ventana temporal**: Event date - 1 día hasta Event date + 1 día

**Output**: `processed/news/events_news_20251009.parquet`

---

### 3. download_actions.py
**Ubicación**: `scripts/ingestion/download_actions.py`

**Función**: Descarga splits y dividends por símbolo (una vez por ticker)

**Datos descargados**:

**Splits**:
- execution_date
- split_from, split_to (ratio)

**Dividends**:
- declaration_date
- ex_dividend_date
- pay_date
- cash_amount

**Output**: `processed/reference/corporate_actions_20251009.parquet`

---

## 📊 RESULTADOS DE ANOTACIÓN

### Archivo generado: `processed/events/events_annotated_20251009.parquet`

**Tamaño**: 50 MB
**Total registros**: 1,200,818 (todos los días de todos los símbolos)

### Estadísticas de eventos detectados:

| Métrica | Cantidad | % del Total |
|---------|----------|-------------|
| **Eventos con flat_base** | 26,597 | 2.2% |
| **Eventos con x2_run (>100%)** | 6,095 | 0.5% |
| **Eventos flat_base_breakout** | 353 | 0.03% |

### Interpretación:

1. **26,597 días con "base plana"** (2.2%)
   - Días donde el ticker estuvo "silencioso" los 20 días previos
   - ATR% bajo (< percentil 25)
   - RVOL bajo (< 0.8)
   - ≥15 de 20 días cumplieron criterio

2. **6,095 eventos con run >100%** (0.5%)
   - Eventos donde el precio subió más del 100% en los siguientes 5 días
   - **GOLD LABEL** para ML - estos son los que más nos interesan

3. **353 "flat-base breakouts"** (0.03%)
   - Combinación de ambos:
     - Venía de base plana (20 días quiet)
     - Explosión detectada por IRE o VSWG branch
   - **PLATINUM LABEL** - los más prometedores

---

## 🚀 PROCESOS EN EJECUCIÓN

### Proceso 1: Week 2-3 Download (Background ID: 660f66)
**Status**: 🔄 Running
**Comando**: `python scripts/ingestion/download_all.py --weeks 2 3 --top-n 2000 --events-preset compact`
**Duración estimada**: 4-7 días
**Storage esperado**: ~5 GB

### Proceso 2: Corporate Actions (Background ID: 3be17b)
**Status**: 🔄 Running
**Comando**: `python scripts/ingestion/download_actions.py`
**Duración estimada**: 2-3 horas
**Storage esperado**: ~10 MB

### Proceso 3: Event News (Background ID: 8956b1)
**Status**: 🔄 Running
**Comando**: `python scripts/ingestion/download_event_news.py`
**Duración estimada**: 4-6 horas
**Storage esperado**: ~50-100 MB

---

## 📝 COMANDOS EJECUTADOS (ORDEN CRONOLÓGICO)

```bash
# 1. Anotar eventos con flat-base + x2_run labels
python scripts/processing/annotate_events_flatbase.py

# 2. Lanzar descarga de corporate actions (background)
python scripts/ingestion/download_actions.py &

# 3. Lanzar descarga de noticias (background)
python scripts/ingestion/download_event_news.py &
```

---

## 🔍 MONITOREO DE PROGRESO

### Verificar descarga de acciones corporativas:
```bash
# Método 1: Ver output del proceso
# (usar herramienta BashOutput con ID: 3be17b)

# Método 2: Verificar archivo
ls -lh processed/reference/corporate_actions_*.parquet
```

### Verificar descarga de noticias:
```bash
# Método 1: Ver output del proceso
# (usar herramienta BashOutput con ID: 8956b1)

# Método 2: Verificar archivo
ls -lh processed/news/events_news_*.parquet
```

### Verificar Week 2-3 download:
```bash
python scripts/ingestion/check_download_status.py
```

---

## 🎯 PRÓXIMOS PASOS (Cuando terminen descargas)

### 1. Validar Cobertura
Crear script: `scripts/processing/check_event_enrichment.py`

**Verificar**:
- % eventos con noticias (esperado: 40-60%)
- % símbolos con acciones corporativas (esperado: ~100%)
- Distribución de flat_base vs x2_run

### 2. Generar Reporte
Output: `docs/Daily/11_FLATBASE_SUMMARY.md`

**Incluir**:
- Distribución de eventos por branch
- Top-50 tickers con más flat_base_breakouts
- Análisis temporal (¿cuándo ocurren más?)
- Correlación flat_base → x2_run

### 3. Feature Engineering Tier 1-2
**Fusionar**:
- events_annotated.parquet
- 1-minute bars (cuando Week 2-3 termine)
- events_news.parquet
- corporate_actions.parquet

**Calcular features**:
- Precio/volumen (VWAP, volume profile, microstructure)
- Timing (time_since_news, time_since_action)
- Sentiment (news_count, avg_sentiment)

### 4. Triple-Barrier Labeling
Para cada evento:
- `ret_15m`, `ret_30m`, `ret_60m`, `ret_120m`
- `max_adverse_excursion` (MAE)
- `max_favorable_excursion` (MFE)
- `hit_barrier` (profit/stop/timeout)

---

## 📊 ESTRUCTURA DE DATOS FINAL

```
processed/
├── events/
│   ├── events_daily_20251009.parquet           # Original (7,288 eventos)
│   └── events_annotated_20251009.parquet       # Con flat_base + x2_run labels ✅
├── news/
│   └── events_news_20251009.parquet            # Noticias ±1d eventos 🔄
├── reference/
│   └── corporate_actions_20251009.parquet      # Splits + Dividends 🔄
└── rankings/
    └── top_2000_by_events_20251009.parquet     # Top-2000 símbolos ✅
```

---

## ⚠️ NOTAS IMPORTANTES

1. **NO INTERRUMPIR** procesos en background - tienen checkpointing automático

2. **Storage actual**: ~6 GB usados (Week 1 + eventos + anotaciones)
   **Storage esperado final**: ~11-12 GB (Week 2-3 + news + actions)

3. **Rate limits**: Polygon.io tiene límite de ~300 requests/min
   - Actions download: ~50 requests (splits) + ~50 (dividends) = 100 total
   - News download: Variable (depende de cuántas noticias por evento)
   - Week 2-3: Maneja rate limiting automáticamente

4. **Archivos generados tienen timestamp** - fácil identificar versión más reciente

5. **Flat-base detection es conservador** (QUIET_MIN_DAYS=15)
   - Si quieres más eventos flat_base → bajar a 12-13 días
   - Si quieres más selectivo → subir a 17-18 días

---

## ✅ RESUMEN EJECUTIVO

### Lo que se logró:
1. ✅ **Script de anotación** creado y ejecutado (annotate_events_flatbase.py)
2. ✅ **353 flat-base breakouts** identificados (0.03% - muy selectivos)
3. ✅ **6,095 eventos con run >100%** etiquetados (0.5%)
4. ✅ **Descarga de news** lanzada en background
5. ✅ **Descarga de actions** lanzada en background
6. ✅ **Week 2-3 download** continúa en background

### Lo que está en progreso:
- 🔄 Descarga de noticias (4-6 horas)
- 🔄 Descarga de acciones corporativas (2-3 horas)
- 🔄 Descarga de 1-minute bars Week 2-3 (4-7 días)

### Siguiente milestone:
- **Cuando news + actions terminen**: Generar reporte de cobertura
- **Cuando Week 2-3 termine**: Feature engineering + Triple-barrier labeling

---

**STATUS ACTUAL**: ✅ **FASE 2.1 EN EJECUCIÓN - 3 PROCESOS PARALELOS**
