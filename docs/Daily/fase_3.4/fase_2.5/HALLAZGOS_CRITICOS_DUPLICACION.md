# 🔴 FASE 2.5 - Hallazgos Críticos: Duplicación del 75.4%

**Fecha:** 2025-10-14 12:45 UTC
**Severidad:** 🔴 CRÍTICA EXTREMA
**Estado:** ✅ IDENTIFICADO - Requiere acción inmediata

---

## ❌ SITUACIÓN ACTUAL - PEOR DE LO ESTIMADO

### Números Reales (Análisis Completo)

```
Total eventos en archivo enriched:     786,869
Eventos únicos (sin duplicados):       193,920 (24.6%)
Eventos duplicados:                    592,949 (75.4%)

Duplicate groups:                      211,966
Símbolos afectados:                    571 (50.4% de 1,133)
Promedio duplicados/símbolo:           1,038.4 eventos
Máximo duplicados (AAOI):              8,232 eventos
```

### VS Estimación Original

| Métrica | Estimado | Real | Diferencia |
|---------|----------|------|------------|
| % Duplicación | 48.4% | **75.4%** | +56% peor |
| Símbolos afectados | 45-96 | **571** | 6-12x más |
| Eventos duplicados | 380,983 | **592,949** | +56% más |

---

## 🔥 TOP 10 SÍMBOLOS MÁS AFECTADOS

| # | Symbol | Duplicate Groups | Total Duplicates | Avg Copies |
|---|--------|------------------|------------------|------------|
| 1 | AAOI | 1,029 | 8,232 | 8.0x |
| 2 | OPEN | 1,866 | 7,464 | 4.0x |
| 3 | PLUG | 1,677 | 6,708 | 4.0x |
| 4 | ABAT | 796 | 6,368 | 8.0x |
| 5 | OPTT | 1,223 | 6,115 | 5.0x |
| 6 | AAL | 691 | 5,528 | 8.0x |
| 7 | ACHR | 1,256 | 5,024 | 4.0x |
| 8 | PLTR | 1,206 | 4,824 | 4.0x |
| 9 | PGY | 1,155 | 4,620 | 4.0x |
| 10 | PTON | 904 | 4,520 | 5.0x |

**Observación crítica:** Algunos símbolos tienen **8 copias** por evento, sugiriendo que el orchestrator los reprocesó **8 veces completas**.

---

## 📊 IMPACTO EN MANIFEST CORE

### Distribución en Manifest

```
Total eventos en manifest CORE:        10,000
Eventos de símbolos con duplicados:    5,161 (51.6%)
Eventos de símbolos limpios:           4,839 (48.4%)

Símbolos con duplicados en manifest:   522 (50.5% de 1,034)
Símbolos limpios en manifest:          512 (49.5%)

Over-representation ratio:             1.05x
```

### Interpretación

✅ **Buenas noticias:**
- No hay over-representation significativa (solo 5% más)
- El manifest está relativamente balanceado

❌ **Malas noticias:**
- **51.6% de manifest CORE** proviene de símbolos con calidad de datos cuestionable
- Estos símbolos fueron reprocesados 4-8 veces → riesgo de **inconsistencias temporales**
- Si hay bugs en versiones del orchestrator, algunos eventos pueden tener campos incorrectos

---

## 🔍 CAUSA RAÍZ ACTUALIZADA

### Timeline Reconstruida (Actualizada)

```
2025-10-12 00:00-21:52  | Run 1: 809 símbolos ✅
2025-10-13 21:52        | 🔴 Checkpoint reset #1
2025-10-13 21:57-22:05  | Run 2: 45 símbolos (duplicados 2x)
2025-10-14 00:00-06:28  | Run 3: 51 símbolos (duplicados 3x)
                         | ...
                         | 🔴 Checkpoint reset #2, #3, #4, #5, #6, #7
                         | Runs 4-8: Símbolos reprocesados múltiples veces
```

### Hipótesis Revisada

**Causa más probable:** Múltiples orchestrators corriendo SIMULTÁNEAMENTE con conflictos de checkpoint

**Evidencia:**
1. 16 procesos detectados corriendo al mismo tiempo
2. Algunos símbolos con 8 copias exactas → 8 corridas diferentes
3. Timestamps de `enriched_at` muestran procesamiento paralelo

**Escenario reconstruido:**
```
Orchestrator A: Procesa símbolo AAOI → escribe checkpoint
Orchestrator B: Lee checkpoint antiguo → reprocesa AAOI → escribe checkpoint
Orchestrator C: Lee checkpoint de B → reprocesa AAOI nuevamente
... (se repite 8 veces)
```

---

## 💰 IMPACTO SI NO CORREGIMOS

### Desperdicio en FASE 3.2

```
Eventos en manifest:                   10,000
Eventos de símbolos duplicados:        5,161 (51.6%)

Asumiendo que 75% de estos son "extras" por duplicación:
Eventos desperdiciados estimados:      3,871

Costo por evento:
  - Tiempo: 24s
  - Storage: 2.5 MB
  - API calls: 2 requests

Desperdicio total:
  - Tiempo: 3,871 × 24s = 25.8 horas
  - Storage: 3,871 × 2.5MB = 9.7 GB
  - API calls: 7,742 requests (~$38-77)
  - Tiempo de análisis posterior: incalculable
```

### Riesgo de Calidad de Datos

**Crítico:** Si el orchestrator tenía bugs entre las 8 corridas:
- Versiones diferentes pueden haber calculado `score` diferente
- Campos `enriched_at`, `session`, `tier` pueden ser inconsistentes
- Selección de "mejor" evento en deduplicación puede haber sido incorrecta

**Ejemplo:**
```
AAOI evento @ 2024-05-31 13:30:
  - Copia 1 (run 1): score=45.3, session=RTH
  - Copia 2 (run 2): score=45.3, session=RTH
  - Copia 3 (run 3): score=45.3, session=RTH  (BUG: mal cálculo)
  - ...
  - Copia 8 (run 8): score=45.3, session=RTH

Deduplicación mantiene: Copia con score más alto + menos nulls
→ Puede haber seleccionado la copia con el BUG
```

---

## ✅ ESTRATEGIA DE CORRECCIÓN REVISADA

### Paso 1: Análisis Adicional (1 hora)

**Verificar inconsistencias entre copias:**
```python
# Script: scripts/analysis/verify_duplicate_consistency.py

# Para cada grupo duplicado, verificar si todas las copias son idénticas
for group in duplicate_groups:
    copies = df.filter(...)

    # Comparar campos críticos
    fields_to_check = ['score', 'session', 'tier', 'dollar_volume', 'rvol_day']

    for field in fields_to_check:
        if copies[field].n_unique() > 1:
            print(f"WARNING: {group} has inconsistent {field}")
            print(copies.select(['symbol', 'timestamp', field]))
```

**Decisión según resultados:**
- ✅ **Si copias son 100% idénticas:** Proceder con deduplicación actual
- ❌ **Si hay inconsistencias:** Re-ejecutar FASE 2.5 completa desde cero

### Paso 2: Decisión GO/NO-GO

**Opción A: Re-ejecutar FASE 2.5 Completa (RECOMENDADO si hay inconsistencias)**

Pros:
- ✅ Dataset completamente limpio
- ✅ Sin riesgo de bugs entre versiones
- ✅ Reproducibilidad garantizada

Cons:
- ⏳ 1,133 símbolos × 12s = ~3.8 horas por corrida × 40 workers = ~2.3 días
- ⏳ Delay total: ~7 días (fix + re-run + FASE 3.2)

**Opción B: Continuar con Deduplicación Actual (SI copias son idénticas)**

Pros:
- ✅ No delay adicional
- ✅ Proceder con FASE 3.2 en ~5 días

Cons:
- ⚠️ Riesgo residual de inconsistencias no detectadas
- ⚠️ Dataset con provenance cuestionable

### Paso 3: Fix del Orchestrator (2-3 horas)

**Bug identificado:**
```python
# ultra_robust_orchestrator.py

# ANTES (BUGGY):
def main():
    checkpoint = load_checkpoint()  # Solo lee del disco

    for symbol in get_pending_symbols(checkpoint):
        process_symbol(symbol)
        update_checkpoint(symbol)

# DESPUÉS (FIXED):
def main():
    checkpoint = load_checkpoint()

    # ✅ VALIDACIÓN CRUZADA
    checkpoint = validate_checkpoint_vs_shards(checkpoint, shards_dir)

    # ✅ LOCK PARA EVITAR CONFLICTOS
    with checkpoint_lock():
        for symbol in get_pending_symbols(checkpoint):
            process_symbol(symbol)
            update_checkpoint(symbol)
```

**Implementación:**
```python
def validate_checkpoint_vs_shards(checkpoint, shards_dir):
    """
    Cross-validate checkpoint against existing shards
    If shards exist for symbols NOT in checkpoint, rebuild checkpoint
    """
    import polars as pl
    from pathlib import Path

    # Get symbols from shards
    shard_symbols = set()
    for shard_file in Path(shards_dir).glob("shard*.parquet"):
        df_shard = pl.read_parquet(shard_file)
        shard_symbols.update(df_shard['symbol'].unique().to_list())

    # Get symbols from checkpoint
    checkpoint_symbols = set(checkpoint.get('completed_symbols', []))

    # Find missing symbols
    missing_in_checkpoint = shard_symbols - checkpoint_symbols

    if missing_in_checkpoint:
        logger.warning(f"Checkpoint missing {len(missing_in_checkpoint)} symbols found in shards!")
        logger.warning(f"Rebuilding checkpoint from shards...")

        # Rebuild checkpoint
        checkpoint['completed_symbols'] = list(shard_symbols)
        checkpoint['last_validated'] = datetime.now().isoformat()
        checkpoint['validation_source'] = 'shards'

        # Save corrected checkpoint
        save_checkpoint(checkpoint)

    return checkpoint


def checkpoint_lock():
    """
    File-based lock to prevent multiple orchestrators from conflicting
    """
    import fcntl
    import tempfile
    from contextlib import contextmanager

    lock_file = Path(tempfile.gettempdir()) / "fase25_checkpoint.lock"

    @contextmanager
    def _lock():
        with open(lock_file, 'w') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                yield
            except BlockingIOError:
                raise RuntimeError("Another orchestrator is already running! Use --force to override.")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return _lock()
```

### Paso 4: Testing del Fix (1 hora)

```bash
# Test con 5 símbolos
python ultra_robust_orchestrator_fixed.py --test-symbols 5

# Verificar que no genera duplicados
python scripts/analysis/verify_no_duplicates.py

# Test con múltiples orchestrators simultáneos (debería fallar con lock)
python ultra_robust_orchestrator_fixed.py &
python ultra_robust_orchestrator_fixed.py &  # Debería fallar inmediatamente
```

---

## 🎯 DECISIÓN REQUERIDA

**¿Qué hacemos?**

### Opción 1: Verificar Consistencia Primero (1h) → Decidir

```bash
python scripts/analysis/verify_duplicate_consistency.py

# Si 100% idénticas → Opción A
# Si hay inconsistencias → Opción B
```

### Opción 2A: Deduplicar y Continuar (5 días total)

1. ✅ Usar deduplicated file actual
2. ✅ Fix orchestrator para FASE 2.6+
3. ✅ Proceder con FASE 3.2 (re-launch PM wave)

### Opción 2B: Re-ejecutar FASE 2.5 Completa (7 días total)

1. ✅ Fix orchestrator
2. ✅ Limpiar shards antiguos
3. ✅ Re-ejecutar FASE 2.5 desde cero (1,133 símbolos)
4. ✅ Regenerar manifest CORE
5. ✅ Lanzar FASE 3.2 con dataset limpio

---

## 📝 PRÓXIMOS PASOS INMEDIATOS

1. **AHORA:** Crear script `verify_duplicate_consistency.py`
2. **30 min:** Ejecutar verificación
3. **Decisión:** Según resultados de consistencia
4. **2h:** Fix orchestrator
5. **1h:** Testing
6. **GO:** Re-ejecutar FASE 2.5 o continuar con deduplicación

---

**Autor:** Claude (Anthropic)
**Fecha:** 2025-10-14 12:45 UTC
**Archivos generados:**
- `analysis/duplicates/symbols_with_duplicates_20251014_124307.csv`
- `analysis/duplicates/duplicate_groups_20251014_124307.parquet`
- `docs/Daily/fase_2.5/ANALISIS_CAUSA_RAIZ_DUPLICADOS.md`

**Estado:** ✅ ANÁLISIS COMPLETO - Esperando decisión para continuar
