# Tools - FASE 2.5 Utilities

## ⭐ NUEVO: Análisis de Datos y Duplicados (RECOMENDADO)

**Usar PowerShell/CMD Nativo (RECOMENDADO)**

Abre PowerShell o CMD fuera de VS Code y ejecuta:

```sh
cd D:\04_TRADING_SMALLCAPS
.\tools\analyze_data_duplicates.bat

Verás el progreso en tiempo real sin problemas:

Procesados 50 shards...
Procesados 100 shards...
Procesados 150 shards...
...

### Análisis Completo 100% Verificable
```bash
# Windows
tools\analyze_data_duplicates.bat

# Linux/Mac
./tools/analyze_data_duplicates.sh
```

**Uso:** Análisis definitivo que muestra DATOS REALES en disco
**Tiempo:** ~30-60 segundos
**Output:**
- **Escaneo físico de shards** (símbolos únicos reales)
- **Eventos totales guardados** (100% verificado)
- **Duplicados en shards** (análisis por run)
- **Checkpoints vs Realidad** (discrepancias)
- **Heartbeat en tiempo real** (procesamiento activo)

**Este es el análisis que debes usar** para saber exactamente qué datos tienes.

### Quick Mode (sin heartbeat)
```bash
python tools/analyze_data_duplicates.py --quick
```
Más rápido, solo datos físicos y checkpoints.

---

## Análisis de Duplicados (Legacy)

### Quick Check (Rápido - Solo Heartbeat)
```bash
# Windows
tools\quick_check.bat

# Linux/Mac
python tools/analyze_duplicates.py --heartbeat-only
```

**Uso:** Análisis rápido del heartbeat log para detectar duplicados en tiempo real.
**Tiempo:** ~1 segundo
**Output:** 
- Progreso actual (checkpoint)
- Tasa de duplicación en últimas 500 entradas
- Top símbolos duplicados

---

### Análisis Completo
```bash
# Windows
tools\analyze_duplicates.bat

# Linux/Mac
python tools/analyze_duplicates.py
```

**Uso:** Análisis completo de:
1. Heartbeat log (procesamiento en tiempo real)
2. Checkpoint actual (progreso persistido)
3. Shards individuales (últimos 7 días)
4. Archivo merged (si existe)
5. Comparación checkpoint vs shards

**Tiempo:** ~30-60 segundos (depende de cantidad de shards)

---

### Opciones Avanzadas

#### Análisis detallado por shard
```bash
python tools/analyze_duplicates.py --detailed
```

#### Exportar a CSV
```bash
python tools/analyze_duplicates.py --export-csv
```

#### Analizar más líneas del heartbeat
```bash
python tools/analyze_duplicates.py --heartbeat-only --tail 1000
```

#### Solo merge (sin análisis)
```bash
python tools/analyze_duplicates.py --merge-only
```

---

## Output Ejemplo

### Quick Check
```
================================================================================
HEARTBEAT ANALYSIS RESULTS
================================================================================
Total entries analyzed: 500
Unique symbols: 388
Symbols with duplicates: 112
Total duplicate entries: 165
Duplication rate: 9.30%

Status: ✓ GOOD

Top 20 symbols with most duplications:
  REKR    :  5 times (duplicated 4 times)
  RVYL    :  3 times (duplicated 2 times)
  QUIK    :  3 times (duplicated 2 times)
  ...

================================================================================
PROGRESS SUMMARY
================================================================================
Total symbols in universe: 1,996
Completed: 1,765 (88.4%)
Remaining: 231

Progress: [████████████████████████████████████████████░░░░░] 88.4%
```

---

## Interpretación de Resultados

### Tasa de Duplicación

| Tasa | Status | Acción |
|------|--------|--------|
| < 5% | ✓ EXCELLENT | Sistema funcionando perfectamente |
| 5-10% | ✓ GOOD | Duplicación aceptable (debido a crashes/relaunches) |
| 10-20% | ⚠ WARNING | Revisar watchdog y workers |
| > 20% | ✗ CRITICAL | Problema grave - detener y revisar |

### Causas Comunes de Duplicación

1. **Workers crashean durante procesamiento** (0.5-10%)
   - Normal con ACCESS_VIOLATION errors
   - Watchdog relanza → símbolo se reprocesa
   - Deduplicación final lo resuelve

2. **Falta de checkpoint compartido** (50-75%)
   - Workers no usan checkpoint
   - Cada worker procesa todos los símbolos
   - **Solución:** Usar `launch_parallel_detection.py --resume`

3. **Race condition en shard numbering** (<1%)
   - File locks fallan
   - Dos workers escriben mismo shard
   - **Solución:** Ya implementado en detector

---

## Notas

- El análisis del heartbeat muestra duplicación **en tiempo real** (puede ser diferente del archivo final)
- Los duplicados son **copias idénticas** - deduplicación los elimina sin pérdida
- Duplicación < 10% es **aceptable** con watchdog auto-recovery
- Para análisis histórico, usar análisis completo (no solo heartbeat)

---

## Troubleshooting

### "No heartbeat log found"
- El proceso no ha iniciado hoy
- Buscar log de días anteriores: `logs/detect_events/heartbeat_*.log`

### "No checkpoint found"
- Primera ejecución del día
- Checkpoint se crea al completar primer símbolo

### "Polars not installed"
```bash
pip install polars
```

---

**Última actualización:** 2025-10-16

# Seguimos para restaurar el proceso Fase_2.5

**1️⃣ Limpieza (SIEMPRE primero)**

```sh
cd D:\04_TRADING_SMALLCAPS
python scripts/processing/restart_parallel.py
```

**2️⃣ Seedear Checkpoint (RECOMENDADO - evita duplicación)**

```sh
# Esto marca los 1,517 símbolos ya procesados como "completados"
python tools/seed_checkpoint.py events_intraday_20251012 events_intraday_20251016
python tools/seed_checkpoint.py events_intraday_20251013 events_intraday_20251016  
python tools/seed_checkpoint.py events_intraday_20251014 events_intraday_20251016
```

**3️⃣ Lanzar con Watchdog (Auto-recovery)**

python tools/watchdog_parallel.py