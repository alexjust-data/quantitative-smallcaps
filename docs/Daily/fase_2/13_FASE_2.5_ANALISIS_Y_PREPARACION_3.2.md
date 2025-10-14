# FASE 2.5: Análisis de Eventos + Preparación FASE 3.2

**Fecha:** 2025-10-13
**Estado:** 🔄 EN PROGRESO
**Objetivo:** Análisis de eventos detectados mientras termina procesamiento masivo + preparación inmediata de FASE 3.2

---

## 📋 Contexto

Mientras el sistema paralelo completa la detección de eventos intraday en los ~1,231 símbolos restantes (~3 horas), aprovechamos para:

1. **Analizar eventos ya detectados** (~765 símbolos completados)
2. **Generar manifest CORE** en modo dry-run
3. **Preparar launch de FASE 3.2** (descarga de trades/quotes)

**Objetivo:** Cuando termine FASE 2.5, presionar un botón y lanzar FASE 3.2 inmediatamente.

---

## 🎯 Plan de Acción (45-60 minutos)

### **Tarea 1: Análisis Rápido de Eventos Detectados** ⏱️ 20 min

**Objetivo:** Entender qué hemos detectado hasta ahora con 765 símbolos procesados.

**Análisis a realizar:**
1. **Distribución por tipo de evento:**
   - volume_spike
   - vwap_break
   - opening_range_break
   - flush
   - consolidation_break

2. **Distribución por sesión:**
   - PM (pre-market)
   - RTH (regular trading hours)
   - AH (after-hours)

3. **Distribución por dirección:**
   - bullish
   - bearish

4. **Top 20 símbolos con más eventos:**
   - Identificar los más activos
   - Ver distribución temporal

5. **Estadísticas de calidad:**
   - Eventos con strength > 7.0
   - Eventos con strength > 8.0
   - Eventos con strength > 9.0

6. **Distribución temporal (time buckets):**
   - Opening (9:30-10:00)
   - Mid-day (10:00-15:00)
   - Power hour (15:00-16:00)
   - PM/AH

**Output esperado:**
- Tabla resumen con conteos
- Top símbolos
- Insights para ajustar filtros del manifest

---

### **Tarea 2: Generar Manifest CORE (Dry-Run)** ⏱️ 15 min

**Objetivo:** Proyectar cuántos eventos calificarían para descarga de trades/quotes con perfil CORE.

**Filtros CORE (config.yaml):**
```yaml
active_profile: "core"

core:
  intraday_manifest:
    max_events: 10000
    max_per_symbol: 3
    max_per_symbol_day: 1
    min_event_score: 0.60

  liquidity_filters:
    min_dollar_volume_bar: 100000    # $100K por barra
    min_absolute_volume_bar: 10000   # 10K shares
    min_dollar_volume_day: 500000    # $500K día
    rvol_day_min: 1.5                # 1.5x volumen relativo
    max_nbbo_spread_pct: 5.0         # Spread ≤ 5%

  event_tape_windows:
    default_window_before_min: 3
    default_window_after_min: 7
```

**Proceso:**
1. Leer todos los shards ya procesados
2. Aplicar filtros CORE
3. Aplicar diversity caps (max 3 eventos/símbolo, 1 evento/día)
4. Calcular:
   - Total eventos que califican
   - Símbolos únicos
   - Estimación de storage (GB)
   - Estimación de tiempo API

**Output esperado:**
```
=== MANIFEST CORE (DRY-RUN) ===
Eventos totales detectados: XX,XXX
Eventos calificados (post-filters): X,XXX
Símbolos únicos: XXX

Por tipo:
- volume_spike: XXX
- vwap_break: XXX
- opening_range_break: XXX
- flush: XXX
- consolidation_break: XXX

Estimación FASE 3.2:
- Trades a descargar: ~XXX GB
- Quotes a descargar: ~XX GB
- Total storage: ~XXX GB
- Tiempo API (trades): ~X horas
- Tiempo API (quotes): ~X horas
- Total tiempo: ~X-XX horas
```

---

### **Tarea 3: Preparar Launch FASE 3.2** ⏱️ 10 min

**Objetivo:** Script listo para ejecutar cuando termine FASE 2.5.

**Componentes:**

#### **A) Consolidar shards finales**
```bash
# Cuando termine detección, consolidar todos los shards
python scripts/processing/consolidate_shards.py \
  --input processed/events/shards/ \
  --output processed/events/events_intraday_20251013.parquet
```

#### **B) Generar manifest CORE**
```bash
# Generar manifest con eventos seleccionados
python scripts/processing/build_intraday_manifest.py \
  --input processed/events/events_intraday_20251013.parquet \
  --output processed/events/events_intraday_manifest.parquet \
  --profile core
```

#### **C) Launch descarga trades**
```bash
# Descargar trades para eventos del manifest
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --trades-only \
  --resume \
  --batch-size 10
```

#### **D) Launch descarga quotes**
```bash
# Descargar quotes (NBBO) para eventos del manifest
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --quotes-only \
  --resume \
  --batch-size 10
```

#### **E) Verificar status**
```bash
# Monitorear progreso de descarga
python scripts/ingestion/check_download_status.py --event-windows
```

**Output esperado:**
- Scripts validados y listos
- Comando único que ejecuta toda la secuencia
- Validaciones pre-flight (espacio en disco, API key, etc.)

---

## 📊 Estado Actual del Sistema

### Sistema Paralelo (Ultra Robust Orchestrator)

**Inicio:** 2025-10-13 16:52:53
**Estado:** RUNNING

**Workers activos:**
- Worker 1 (PID 17756): RUNNING, 0 restarts
- Worker 2 (PID 17604): RUNNING, 0 restarts
- Worker 3 (PID 14632): RUNNING, 1 restart

**Progreso:**
- Símbolos completados (en shards): 765
- Símbolos completados (checkpoint actual): 164
- Símbolos restantes: ~1,231
- Velocidad promedio: ~318 símbolos/hora
- Tiempo estimado restante: ~3.9 horas

**Logs:**
- Orchestrator: `logs/ultra_robust/orchestrator_20251013.log`
- Workers: `logs/ultra_robust/worker_N_20251013_165253.log`

**Eventos detectados hasta ahora:**
- Total único en shards: ~765 símbolos
- Total de shards: 89
- Estimación eventos: ~25,000-50,000 (pendiente análisis exacto)

---

## 🔍 Análisis Detallado (A Completar)

### 1. Distribución por Tipo de Evento

```
[PENDIENTE - A completar con datos reales]

Tipo                      | Count  | %
--------------------------|--------|------
volume_spike              | X,XXX  | XX%
vwap_break                | X,XXX  | XX%
opening_range_break       | X,XXX  | XX%
flush                     | X,XXX  | XX%
consolidation_break       | X,XXX  | XX%
--------------------------|--------|------
TOTAL                     | XX,XXX | 100%
```

### 2. Distribución por Sesión

```
[PENDIENTE - A completar con datos reales]

Sesión | Count  | %
-------|--------|------
PM     | X,XXX  | XX%
RTH    | XX,XXX | XX%
AH     | X,XXX  | XX%
-------|--------|------
TOTAL  | XX,XXX | 100%
```

### 3. Distribución por Dirección

```
[PENDIENTE - A completar con datos reales]

Dirección | Count  | %
----------|--------|------
bullish   | XX,XXX | XX%
bearish   | XX,XXX | XX%
----------|--------|------
TOTAL     | XX,XXX | 100%
```

### 4. Top 20 Símbolos con Más Eventos

```
[PENDIENTE - A completar con datos reales]

Rank | Symbol | Events | Top Event Type    | Avg Strength
-----|--------|--------|-------------------|-------------
1    | XXXX   | XXX    | volume_spike      | X.XX
2    | XXXX   | XXX    | vwap_break        | X.XX
...
```

### 5. Eventos de Alta Calidad (Strength > 7.0)

```
[PENDIENTE - A completar con datos reales]

Strength Range | Count | %
---------------|-------|------
> 9.0 (elite)  | XXX   | X%
8.0-9.0 (high) | X,XXX | XX%
7.0-8.0 (good) | X,XXX | XX%
< 7.0          | XX,XXX| XX%
```

### 6. Distribución Temporal (Time Buckets)

```
[PENDIENTE - A completar con datos reales]

Time Bucket              | Count  | %
-------------------------|--------|------
Opening (9:30-10:00)     | X,XXX  | XX%
Mid-day (10:00-15:00)    | XX,XXX | XX%
Power Hour (15:00-16:00) | X,XXX  | XX%
PM/AH                    | X,XXX  | XX%
```

---

## 📦 Manifest CORE - Proyección

### Filtros Aplicados

**Filtros de liquidez:**
- ✅ Dollar volume bar ≥ $100K
- ✅ Absolute volume bar ≥ 10K shares
- ✅ Dollar volume day ≥ $500K
- ✅ RVol day ≥ 1.5x
- ✅ NBBO spread ≤ 5%

**Filtros de calidad:**
- ✅ Event score ≥ 0.60
- ✅ Max 3 eventos por símbolo
- ✅ Max 1 evento por símbolo por día

**Diversity & Coverage:**
- ✅ Time bucket coverage (opening, mid-day, power hour)
- ✅ Event type diversity

### Estimación de Resultados

```
[PENDIENTE - A completar con análisis]

=== MANIFEST CORE PROJECTION ===

Input:
- Total events detected: XX,XXX
- Symbols processed: 765

After filters:
- Events selected: X,XXX
- Symbols with events: XXX
- Average events/symbol: X.X

Storage estimation (FASE 3.2):
- Trades: ~XXX GB (X,XXX events × 10min × ~XXX KB/min)
- Quotes: ~XX GB (X,XXX events × 10min × ~XX KB/min)
- Total: ~XXX GB

API time estimation:
- Trades: ~X-X hours (X,XXX requests @ 12 sec/req + margin)
- Quotes: ~X-X hours (X,XXX requests @ 12 sec/req + margin)
- Total: ~X-XX hours
```

---

## 🚀 Secuencia de Launch FASE 3.2

### Pre-requisitos

**Validaciones:**
- [ ] FASE 2.5 completada (all workers finished)
- [ ] Shards consolidados correctamente
- [ ] Manifest generado y validado
- [ ] Espacio en disco disponible: XX GB free (necesario: ~XXX GB)
- [ ] API key Polygon válida
- [ ] Rate limit: 5 req/sec disponible

### Secuencia de Ejecución

```bash
#!/bin/bash
# launch_fase_3.2.sh - Script maestro

set -e  # Exit on error

echo "=== FASE 3.2 LAUNCH SEQUENCE ==="
echo ""

# Step 1: Consolidate shards
echo "[1/5] Consolidating shards..."
python scripts/processing/consolidate_shards.py \
  --input processed/events/shards/ \
  --output processed/events/events_intraday_20251013.parquet

# Step 2: Generate manifest
echo "[2/5] Generating CORE manifest..."
python scripts/processing/build_intraday_manifest.py \
  --input processed/events/events_intraday_20251013.parquet \
  --output processed/events/events_intraday_manifest.parquet \
  --profile core

# Step 3: Validate manifest
echo "[3/5] Validating manifest..."
python scripts/processing/build_intraday_manifest.py \
  --summary-only

# Step 4: Launch trades download
echo "[4/5] Launching trades download..."
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --trades-only \
  --resume \
  --batch-size 10 &

TRADES_PID=$!
echo "Trades download PID: $TRADES_PID"

# Step 5: Launch quotes download (parallel)
echo "[5/5] Launching quotes download..."
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --quotes-only \
  --resume \
  --batch-size 10 &

QUOTES_PID=$!
echo "Quotes download PID: $QUOTES_PID"

echo ""
echo "=== LAUNCH COMPLETE ==="
echo "Monitor progress with:"
echo "  python scripts/ingestion/check_download_status.py --event-windows"
echo ""
echo "Background processes:"
echo "  Trades: PID $TRADES_PID"
echo "  Quotes: PID $QUOTES_PID"
```

**Monitoreo:**
```bash
# Check status cada 5 minutos
watch -n 300 'python scripts/ingestion/check_download_status.py --event-windows'
```

---

## 📈 Métricas de Éxito

### FASE 2.5 (Detección)
- ✅ 1,996 símbolos procesados
- ✅ XX,XXX eventos detectados
- ✅ Sistema paralelo estable (0-1 restarts/worker)
- ✅ Sin pérdida de datos (shards intactos)

### FASE 3.2 (Trades/Quotes)
- [ ] X,XXX eventos con trades descargados
- [ ] X,XXX eventos con quotes descargados
- [ ] XX% completitud (target: >95%)
- [ ] Tiempo total: <XX horas
- [ ] 0 errores críticos de descarga

---

## 🔗 Documentos Relacionados

**Fases anteriores:**
- [12_FASE_2.5_INTRADAY_EVENTS.md](12_FASE_2.5_INTRADAY_EVENTS.md) - Implementación completa FASE 2.5
- [fase_3.2/FASE_3.2_RESUMEN_IMPLEMENTACION.md](fase_3.2/FASE_3.2_RESUMEN_IMPLEMENTACION.md) - Sistema CORE/PLUS/PREMIUM
- [fase_3.2/FASE_3.2_COMANDOS_OPERACION.md](fase_3.2/FASE_3.2_COMANDOS_OPERACION.md) - Guía operativa

**Roadmap streaming:**
- [AlexJust/streaming_map_route_CLAUDE.md](../AlexJust/streaming_map_route_CLAUDE.md) - Arquitectura técnica real-time
- [AlexJust/streameing_mp_route_GPT.md](../AlexJust/streameing_mp_route_GPT.md) - Visión ejecutiva

---

## ✅ Checklist de Tareas

### Inmediato (Hoy - 45-60 min)
- [ ] Análisis exploratorio de eventos (765 símbolos)
- [ ] Generar manifest CORE dry-run
- [ ] Preparar scripts de launch
- [ ] Validar pre-requisitos

### Cuando termine FASE 2.5 (~3 horas)
- [ ] Consolidar shards finales
- [ ] Generar manifest CORE final
- [ ] Validar espacio en disco
- [ ] Launch descarga trades + quotes

### Post FASE 3.2 (~1-2 días)
- [ ] Verificar completitud de descargas
- [ ] Análisis de calidad de trades/quotes
- [ ] Documentar resultados
- [ ] Iniciar diseño FASE 4 (Features extraction)

---

## 📝 Notas

**Decisiones de diseño:**
- Usamos perfil CORE (conservador) para primera iteración
- Paralelizamos trades + quotes (2 procesos simultáneos)
- Batch size 10 para balance speed/stability
- Resume capability para recuperación ante fallos

**Optimizaciones futuras:**
- Incrementar batch size si estabilidad OK
- Evaluar perfil PLUS para más eventos
- Considerar descarga solo de trades (quotes opcionales)
- Implementar parallelización multi-worker

**Riesgos:**
- Espacio en disco insuficiente → Monitorear antes de launch
- API rate limits → Batch size conservador
- Eventos sin datos → Resume capability maneja esto

---

**Estado:** 🔄 Documento en construcción - se actualizará con resultados reales conforme avancemos.

**Última actualización:** 2025-10-13 17:40 (inicio de análisis)
