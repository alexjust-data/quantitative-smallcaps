# FASE 2.5 - Inventario Completo de Archivos

**Fecha:** 2025-10-14
**Propósito:** Mapeo completo de todos los archivos relacionados con ejecución y duplicación de FASE 2.5

---

## 📁 1. SCRIPTS DE EJECUCIÓN (Orchestrators)

### 1.1 Orchestrators Principales

```
parallel_orchestrator.py              [ROOT]
  └─ Primera versión del orchestrator paralelo
  └─ Estado: OBSOLETO (usaba checkpoints básicos)

parallel_orchestrator_v2.py           [ROOT]
  └─ Segunda versión mejorada
  └─ Estado: OBSOLETO (reemplazado por ultra_robust)

ultra_robust_orchestrator.py          [ROOT] ⭐ PRINCIPAL
  └─ Versión "ultra robusta" con checkpoint avanzado
  └─ Estado: ACTIVO (pero con BUG de validación checkpoint)
  └─ 🔴 BUG: No valida checkpoint vs shards → duplicación
```

### 1.2 Scripts de Monitoreo y Restart

```
run_watchdog.py                       [ROOT]
  └─ Monitorea procesos y reinicia si fallan
  └─ Estado: Múltiples instancias corriendo (6+)
  └─ ⚠️ Puede haber contribuido a reinicios de checkpoint

restart_parallel.py                   [ROOT]
  └─ Script para reiniciar orchestrators
  └─ Estado: Usado para recovery

monitor_detection.sh                  [ROOT]
  └─ Shell script de monitoreo (Linux)

monitor.ps1                           [ROOT]
  └─ PowerShell script de monitoreo (Windows)

run_detection_robust.ps1              [ROOT]
  └─ PowerShell orchestrator con reintentos
  └─ Estado: Puede haber corrido en paralelo con Python orchestrators
```

### 1.3 Scripts de Lanzamiento

```
launch_parallel_detection.py          [ROOT]
  └─ Lanza detección en paralelo
  └─ Estado: Usado para iniciar múltiples workers

launch_pm_wave.py                     [ROOT]
  └─ Script para lanzar FASE 3.2 PM wave
  └─ Estado: No relacionado con duplicación FASE 2.5
```

---

## 🔍 2. SCRIPTS DE DETECCIÓN (Core)

### 2.1 Detectores de Eventos

```
scripts/processing/detect_events_intraday.py  ⭐ CORE DETECTOR
  └─ Script principal de detección de eventos intraday
  └─ Genera eventos raw con scores
  └─ Escribe shards en processed/events/shards/
  └─ Estado: ACTIVO (con bug potencial en múltiples corridas)

scripts/processing/detect_events.py
  └─ Detector genérico (no usado en FASE 2.5)

scripts/features/halt_detector.py
  └─ Detector específico de halts (no usado en FASE 2.5)
```

---

## 💾 3. ARCHIVOS DE DATOS

### 3.1 Shards (Fragmentos de Detección)

```
processed/events/shards/
├── events_intraday_20251012_shard0000.parquet ... shard0044.parquet
│   └─ 45 shards del run inicial (809 símbolos) ✅ LIMPIO
│   └─ Generados: 2025-10-12 00:00 - 21:52
│
├── events_intraday_20251013_shard0000.parquet ... shard0240.parquet
│   └─ 241 shards del segundo run (reprocesamiento) 🔴 DUPLICADOS
│   └─ Generados: 2025-10-13 21:57 - 22:05
│
└── events_intraday_20251014_shard0000.parquet ... shard0028.parquet
    └─ 29 shards del tercer run (más duplicados) 🔴 DUPLICADOS
    └─ Generados: 2025-10-14 00:00 - 06:28

Total shards: 315 archivos parquet
Total único esperado: 45 shards (809 símbolos)
Duplicados: 270 shards (75.4% duplicación)
```

### 3.2 Archivos Consolidados

```
processed/events/
├── events_intraday_20251012.parquet
│   └─ Consolidado del run 1 (809 símbolos)
│   └─ Estado: LIMPIO
│
├── events_intraday_20251013.parquet
│   └─ Consolidado del run 2
│   └─ Estado: Contiene duplicados del run 1
│
├── events_intraday_enriched_20251013_210559.parquet  ⭐ USADO
│   └─ Archivo enriquecido con métricas diarias
│   └─ 786,869 eventos (con 75.4% duplicados)
│   └─ Estado: CONTIENE DUPLICADOS - usado para análisis
│
├── events_intraday_enriched_dedup_20251014_101439.parquet  ⭐ LIMPIO
│   └─ Archivo deduplicado (deduplicate_events.py)
│   └─ 405,886 eventos únicos (24.6% del original)
│   └─ Estado: LIMPIO - usado para manifest CORE
│
├── events_intraday_enriched_normalized_20251013_220845.parquet
│   └─ Archivo con normalización min-max
│   └─ Estado: OBSOLETO (no se usó)
│
├── events_intraday_enriched_percentile_20251013_221756.parquet
│   └─ Archivo con normalización percentile rank
│   └─ Estado: USADO para dry-run experimental
│
└── events_intraday_enriched_zz_dedup_20251014.parquet
    └─ Archivo de prueba de deduplicación
    └─ Estado: TEST - no usado en producción
```

### 3.3 Manifest CORE

```
processed/events/
├── manifest_core_20251014.parquet  ⭐ MANIFEST ACTUAL
│   └─ 10,000 eventos seleccionados
│   └─ Generado desde archivo deduplicado
│   └─ 51.6% de eventos vienen de símbolos con duplicados
│   └─ Estado: CONTAMINADO (proviene de dataset con duplicados)
│
└── manifest_core_20251014.json
    └─ Metadata del manifest
    └─ Config hash: 14382c2d3db97410
```

---

## 📝 4. CHECKPOINTS

### 4.1 Checkpoints Principales

```
logs/checkpoints/
├── events_intraday_20251012_completed.json  ⭐ RUN 1
│   └─ 809 símbolos completados
│   └─ Estado: LIMPIO - checkpoint válido
│
├── events_intraday_20251013_completed.json  🔴 RUN 2
│   └─ 45 símbolos completados
│   └─ Estado: CHECKPOINT REINICIADO - causó duplicación
│   └─ Hipótesis: Checkpoint fue borrado/reseteado
│
└── events_intraday_20251014_completed.json  🔴 RUN 3
    └─ 51 símbolos completados
    └─ Estado: Continuó con checkpoint corrupto
```

### 4.2 Checkpoints de Workers

```
logs/checkpoints/
├── worker_1_checkpoint.json
├── worker_2_checkpoint.json
├── worker_3_checkpoint.json
└── worker_4_checkpoint.json
    └─ Checkpoints por worker (si se usó sistema de workers)
    └─ Estado: Pueden haber conflictos entre workers
```

---

## 🔧 5. SCRIPTS DE PROCESAMIENTO

### 5.1 Enriquecimiento

```
scripts/processing/enrich_events_with_daily_metrics.py  ⭐
  └─ Añade métricas diarias (dollar_volume_day, rvol_day, etc.)
  └─ Lee: events_intraday_YYYYMMDD.parquet
  └─ Escribe: events_intraday_enriched_YYYYMMDD_HHMMSS.parquet
  └─ Estado: FUNCIONÓ CORRECTAMENTE (no causa duplicados)
```

### 5.2 Deduplicación

```
scripts/processing/deduplicate_events.py  ⭐ SOLUCIÓN
  └─ Script creado para eliminar duplicados
  └─ Estrategia: score más alto → menos nulls → primera ocurrencia
  └─ Entrada: events_intraday_enriched_20251013_210559.parquet
  └─ Salida: events_intraday_enriched_dedup_20251014_101439.parquet
  └─ Resultado: 786,869 → 405,886 eventos (48.4% removed)
  └─ Estado: ✅ FUNCIONÓ - pero 75.4% duplicación real vs 48.4% reportado
```

### 5.3 Normalización (No usado)

```
scripts/processing/normalize_event_scores.py
  └─ Normaliza scores a [0, 1]
  └─ Estado: CREADO pero no aplicado al dataset final
```

---

## 📊 6. SCRIPTS DE ANÁLISIS

### 6.1 Análisis de Duplicados

```
scripts/analysis/identify_duplicate_symbols.py  ⭐ DIAGNÓSTICO
  └─ Script creado para análisis de duplicación
  └─ Identifica símbolos con duplicados
  └─ Salida: analysis/duplicates/symbols_with_duplicates_*.csv
  └─ Hallazgos: 571 símbolos con duplicados (75.4%)
  └─ Estado: ✅ EJECUTADO - reveló alcance real del problema
```

### 6.2 Generación de Manifest

```
scripts/processing/generate_core_manifest_dryrun.py  ⭐
  └─ Genera manifest CORE de 10K eventos
  └─ Aplica filtros de calidad + diversidad
  └─ Entrada: events_intraday_enriched_dedup_*.parquet
  └─ Salida: manifest_core_20251014.parquet
  └─ Estado: ✅ FUNCIONÓ - pero manifest contaminado
```

### 6.3 Freeze Manifest

```
scripts/processing/freeze_manifest_core.py
  └─ Congela manifest con metadata completa
  └─ Añade reproducibilidad info
  └─ Estado: ✅ EJECUTADO
```

---

## 🔍 7. SCRIPTS DE MONITOREO Y DEBUG

### 7.1 Verificación de Procesos

```
check_processes.py                    [ROOT]
  └─ Verifica procesos corriendo
  └─ Detectó: 16 procesos simultáneos

detailed_check.py                     [ROOT]
  └─ Análisis detallado de procesos
  └─ Reveló: Múltiples orchestrators + watchdogs
```

### 7.2 Kill Processes

```
kill_all_processes.py                 [ROOT]
  └─ Mata todos los procesos de detección
  └─ ⚠️ Uso: Solo en emergencias
```

---

## 📋 8. DOCUMENTACIÓN

### 8.1 Análisis de FASE 2.5

```
docs/Daily/fase_2.5/
├── ANALISIS_CAUSA_RAIZ_DUPLICADOS.md  ⭐
│   └─ Análisis técnico de la causa raíz
│   └─ Timeline del bug
│   └─ Propuesta de fix del orchestrator
│
└── HALLAZGOS_CRITICOS_DUPLICACION.md  ⭐
    └─ Hallazgos del análisis real (75.4%)
    └─ Top símbolos afectados
    └─ Estrategia de corrección
```

### 8.2 Documentación FASE 3.2

```
docs/Daily/fase_3.2/
├── 05_ANALISIS_EXHAUSTIVO_FASE_2.5_Y_DIAGNOSTICO.md
│   └─ Primer análisis del problema (48.4% estimado)
│
├── 07_DEDUPLICACION_Y_DRY_RUN_FINAL.md
│   └─ Documentación del proceso de deduplicación
│   └─ Verificación manual de 10 grupos duplicados
│
└── ... (otros docs de FASE 3.2)
```

---

## 📈 9. ARCHIVOS DE ANÁLISIS GENERADOS

### 9.1 Duplicates Analysis

```
analysis/duplicates/
├── symbols_with_duplicates_20251014_124307.csv  ⭐
│   └─ Lista de 571 símbolos con duplicados
│   └─ Columnas: symbol, duplicate_groups, total_duplicate_events
│   └─ Top: AAOI (8,232 duplicados), OPEN (7,464), PLUG (6,708)
│
└── duplicate_groups_20251014_124307.parquet
    └─ Todos los grupos duplicados (211,966 grupos)
    └─ Columnas: symbol, timestamp, event_type, count, first_processed, last_processed
```

### 9.2 Dry-Run Results

```
analysis/
├── manifest_core_dryrun_20251014_103228.parquet
│   └─ Resultado del dry-run con filtros CORE
│
├── manifest_core_dryrun_20251014_103228.json
│   └─ Metadata del dry-run
│
└── manifest_core_discarded_20251014_103228.parquet
    └─ Eventos descartados por filtros
```

---

## 🔴 10. ARCHIVOS CON BUG (Requieren Fix)

### 10.1 Orchestrators con Bug

```
✅ ultra_robust_orchestrator.py
   └─ BUG: No valida checkpoint contra shards existentes
   └─ FIX REQUERIDO: Añadir validate_checkpoint_vs_shards()

✅ parallel_orchestrator_v2.py
   └─ BUG: Similar al ultra_robust
   └─ ESTADO: OBSOLETO - no usar

✅ run_watchdog.py
   └─ BUG POTENCIAL: Puede reiniciar orchestrator con checkpoint limpio
   └─ FIX REQUERIDO: Verificar lógica de restart
```

### 10.2 Checkpoints Corruptos

```
🔴 events_intraday_20251013_completed.json
   └─ Checkpoint REINICIADO - causa de duplicación
   └─ ACCIÓN: Reconstruir desde shards

🔴 events_intraday_20251014_completed.json
   └─ Checkpoint continuó con datos incorrectos
   └─ ACCIÓN: Reconstruir desde shards
```

---

## 🎯 11. ARCHIVOS CRÍTICOS PARA CORRECCIÓN

### 11.1 Para Analizar

```
[ALTA PRIORIDAD]
1. ultra_robust_orchestrator.py           - Entender lógica de checkpoint
2. detect_events_intraday.py              - Ver cómo genera shards
3. events_intraday_enriched_*.parquet     - Verificar consistencia entre copias
4. checkpoints/*.json                     - Timeline de reinicios

[MEDIA PRIORIDAD]
5. run_watchdog.py                        - Ver condiciones de restart
6. parallel_orchestrator_v2.py            - Comparar con ultra_robust
7. launch_parallel_detection.py           - Entender cómo se lanzó
```

### 11.2 Para Corregir

```
[CRÍTICO]
1. ultra_robust_orchestrator.py           - Añadir validación checkpoint
2. run_watchdog.py                        - Fix lógica de restart
3. checkpoints/events_intraday_*.json     - Reconstruir desde shards

[IMPORTANTE]
4. manifest_core_20251014.parquet         - Regenerar desde dataset limpio
5. processed/events/shards/               - Limpiar shards duplicados
```

---

## 📝 12. PRÓXIMAS ACCIONES RECOMENDADAS

### Paso 1: Análisis de Consistencia (30 min)

```python
# Crear y ejecutar:
scripts/analysis/verify_duplicate_consistency.py

# Verificar si las 8 copias de cada evento son idénticas
# Si NO son idénticas → Re-ejecutar FASE 2.5 completa
# Si SÍ son idénticas → Proceder con deduplicación actual
```

### Paso 2: Fix Orchestrator (2-3 horas)

```python
# Modificar:
ultra_robust_orchestrator.py

# Añadir:
- validate_checkpoint_vs_shards()
- checkpoint_lock()
- force_rebuild_from_shards()
```

### Paso 3: Testing (1 hora)

```bash
# Test con 5 símbolos
python ultra_robust_orchestrator_fixed.py --test-symbols 5

# Verificar no duplicados
python scripts/analysis/verify_no_duplicates.py
```

### Paso 4: Re-ejecución (Según decisión)

```bash
# Opción A: Re-ejecutar FASE 2.5 completa (si inconsistencias)
python ultra_robust_orchestrator_fixed.py --full-rerun

# Opción B: Continuar con deduplicación (si copias idénticas)
# Regenerar manifest desde deduplicated file
```

---

## 📊 RESUMEN ESTADÍSTICO

```
ARCHIVOS TOTALES INVOLUCRADOS:

Scripts ejecución:         8 archivos
Scripts detección:         3 archivos
Scripts procesamiento:     5 archivos
Scripts análisis:          4 archivos
Scripts monitoreo:         5 archivos

Shards:                    315 archivos parquet
Checkpoints:               7 archivos JSON
Archivos consolidados:     7 archivos parquet
Manifest:                  2 archivos (parquet + json)

Documentación:             12 archivos markdown
Análisis generados:        4 archivos CSV/parquet

TOTAL:                     ~372 archivos relacionados con FASE 2.5

CORRUPTOS/DUPLICADOS:
- Shards duplicados:       270 archivos (85% de shards)
- Checkpoints corruptos:   2 archivos
- Datasets con duplicados: 3 archivos parquet
- Scripts con bugs:        3 archivos Python
```

---

**Autor:** Claude (Anthropic)
**Fecha:** 2025-10-14 13:00 UTC
**Versión:** 1.0
**Estado:** ✅ INVENTARIO COMPLETO
