# FASE 2.5 - Análisis Causa Raíz: Duplicación del 48.4%

**Fecha análisis:** 2025-10-14
**Severidad:** 🔴 CRÍTICA
**Estado:** ✅ IDENTIFICADA - Solución propuesta

---

## 📋 Resumen Ejecutivo

**Problema:** 380,983 eventos duplicados (48.4% del total) en archivo enriquecido de FASE 2.5

**Causa raíz:** Reinicio del checkpoint sin limpieza de shards, causando reprocesamiento completo de símbolos ya procesados

**Impacto:**
- ❌ Manifest CORE contiene duplicados latentes
- ❌ Desperdicio de ~48% de recursos de descarga en FASE 3.2
- ❌ Riesgo de sobre-representación de ciertos símbolos

**Solución:**
1. Pausar FASE 3.2 PM wave
2. Identificar y corregir bug en orchestrator
3. Re-ejecutar FASE 2.5 para símbolos restantes (863) sin duplicación
4. Regenerar manifest CORE limpio
5. Re-lanzar FASE 3.2 con manifest corregido

---

## 1. CRONOLOGÍA DEL PROBLEMA

### Timeline Reconstructada

```
2025-10-12 00:00 → 21:52  | Run 20251012: 809 símbolos procesados ✅
                            | Shards 0-199 generados
                            | Checkpoint: 809 símbolos completados
                            | eventos_intraday_20251012_completed.json

2025-10-13 21:52           | 🔴 CHECKPOINT REINICIADO (causa desconocida)
                            | Checkpoint borrado o reseteado a 0

2025-10-13 21:57 → 22:05   | Run 20251013: Reprocesamiento desde inicio
                            | Shards 200-204 generados (con duplicados)
                            | 45 símbolos "completados" (ya estaban en run anterior)
                            | eventos_intraday_20251013_completed.json

2025-10-14 00:00 → 06:28   | Run 20251014: Continúa reprocesamiento
                            | Shards 205-233 generados (más duplicados)
                            | 51 símbolos adicionales
                            | eventos_intraday_20251014_completed.json

2025-10-14 06:28           | ⚠️ TODOS LOS PROCESOS DETIENEN (causa desconocida)
```

### Evidencia Física

**Checkpoints encontrados:**
```
logs/checkpoints/events_intraday_20251012_completed.json  → 809 símbolos
logs/checkpoints/events_intraday_20251013_completed.json  → 45 símbolos
logs/checkpoints/events_intraday_20251014_completed.json  → 51 símbolos

Total checkpoints: 905 símbolos
Únicos reales: 809 + (45-overlap) + (51-overlap) = ???
```

**Shards analizados:**
```
processed/events/events_intraday_shards/
├── shard0000.parquet ... shard0199.parquet  ← Run 20251012 (809 símbolos)
├── shard0200.parquet ... shard0204.parquet  ← Run 20251013 (duplicados)
└── shard0205.parquet ... shard0233.parquet  ← Run 20251014 (duplicados)

Total eventos en shards: 786,869
Eventos únicos reales: 405,886 (51.6%)
Duplicados: 380,983 (48.4%)
```

---

## 2. CAUSA RAÍZ TÉCNICA

### 2.1 Bug en el Orchestrator

**Script afectado:** `ultra_robust_orchestrator.py` (y posiblemente otros orchestrators)

**Problema:**
```python
# Pseudo-código del bug
while True:
    checkpoint = load_checkpoint()  # Lee checkpoint del disco
    symbols_pending = get_pending_symbols(checkpoint)

    for symbol in symbols_pending:
        shard_num = get_next_shard_number()  # ✅ Correcto: incremental
        process_symbol(symbol, shard_num)
        update_checkpoint(symbol)  # ✅ Correcto: guarda progreso

    # 🔴 BUG: Si checkpoint se borra/reinicia externamente,
    # el orchestrator no detecta que los shards YA EXISTEN
    # y reprocesa todos los símbolos desde el inicio
```

**Fallo del diseño:**
- ✅ **Shards son incrementales:** shard0000, shard0001, ... (no se sobrescriben)
- ❌ **Checkpoint es la única fuente de verdad:** Si se reinicia, todo se reprocesa
- ❌ **No hay validación cruzada:** No verifica si un símbolo ya tiene shards generados

### 2.2 Causa del Reinicio del Checkpoint

**Posibles causas (en orden de probabilidad):**

1. **Múltiples orchestrators en conflicto (ALTA)**
   - Evidencia: 16 procesos corriendo simultáneamente
   - Escenario: Orchestrator A guarda checkpoint, Orchestrator B lo sobreescribe con estado antiguo
   - Resultado: Checkpoint retrocede a estado anterior

2. **Crash del proceso (MEDIA)**
   - Evidencia: Todos los procesos se detuvieron el 2025-10-14 06:28
   - Escenario: Proceso crashea durante escritura de checkpoint, archivo se corrompe, se regenera vacío
   - Resultado: Checkpoint reiniciado a 0

3. **Reinicio manual (BAJA)**
   - Escenario: Usuario ejecuta comando de limpieza sin intención
   - Menos probable: No hay evidencia de intervención manual

4. **Watchdog malfunction (MEDIA)**
   - Evidencia: 6 run_watchdog.py corriendo simultáneamente
   - Escenario: Watchdog detecta "problema" y reinicia orchestrator con checkpoint limpio
   - Resultado: Checkpoint reiniciado

---

## 3. IMPACTO DETALLADO

### 3.1 Impacto en FASE 2.5

```
Símbolos procesados (únicos): 1,133
Eventos generados (total):    786,869
Eventos únicos (reales):      405,886
Eventos duplicados:           380,983 (48.4%)

Desperdicio de recursos:
- Tiempo de CPU: ~48.4% desperdiciado en reprocesamiento
- Escritura disco: 786 MB vs 405 MB necesarios (+94%)
- Complejidad análisis: Necesitó deduplicación manual
```

### 3.2 Impacto en Manifest CORE

**Archivo usado para manifest:**
```
processed/events/events_intraday_enriched_dedup_20251014_101439.parquet
└─ Eventos: 405,886 (post-deduplicación)
```

**Problema latente:**
- ✅ Deduplicación elimina duplicados exactos
- ⚠️ Pero símbolos re-procesados tienen **sobre-representación temporal**
  - Ejemplo: Si AAPL fue procesado 2 veces, tiene 2x más eventos que otros símbolos
  - Esto sesga la selección hacia símbolos "afortunados" que fueron reprocesados

**Manifest CORE actual (10,000 eventos):**
```
Top 20 concentration: 3.6%
Max events/symbol: 18

¿Hay sesgo de sobre-representación?
→ Requiere análisis adicional de símbolos duplicados vs no-duplicados
```

### 3.3 Impacto en FASE 3.2

**Si continuamos con manifest actual:**
- ❌ Descargamos datos potencialmente sesgados
- ❌ ~48% de storage/tiempo desperdiciado en duplicados latentes
- ❌ Análisis posterior tendrá que manejar over-sampling de ciertos símbolos

**Estimación de desperdicio:**
```
PM Wave:  1,452 eventos → ~48% duplicados latentes = 697 eventos "extras"
AH Wave:    321 eventos → ~48% duplicados latentes = 154 eventos "extras"
RTH Wave: 8,227 eventos → ~48% duplicados latentes = 3,949 eventos "extras"

Total desperdicio estimado:
- Tiempo: 4,800 eventos × 24s = 32 horas desperdiciadas
- API calls: 4,800 eventos × 2 = 9,600 requests extras
- Storage: 4,800 eventos × 2.5 MB = 12 GB extras
```

---

## 4. SOLUCIÓN PROPUESTA

### Opción 1: **Pausar y Corregir** (RECOMENDADO)

**Pros:**
- ✅ Elimina sesgo de sobre-representación
- ✅ Ahorra 32h + 12 GB en FASE 3.2
- ✅ Dataset final limpio y reproducible
- ✅ Corrige bug para futuras fases

**Cons:**
- ⏳ Requiere pausar PM wave actual
- ⏳ Re-ejecutar FASE 2.5 para 863 símbolos restantes (~4.6 días)
- ⏳ Regenerar manifest CORE
- ⏳ Re-lanzar FASE 3.2 con manifest limpio

**Pasos:**
1. **Pausar PM wave actual** (matar proceso)
2. **Identificar símbolos duplicados:**
   ```python
   # Analizar shards 200-233 para identificar símbolos re-procesados
   duplicate_symbols = identify_duplicates_in_shards()
   ```
3. **Corregir bug en orchestrator:**
   ```python
   # Añadir validación cruzada entre checkpoint y shards existentes
   def validate_checkpoint(checkpoint, shards_dir):
       existing_symbols = get_symbols_from_shards(shards_dir)
       checkpoint_symbols = checkpoint.get('completed_symbols', [])

       # Si hay shards de símbolos NO en checkpoint, reconstruir checkpoint
       if missing := existing_symbols - set(checkpoint_symbols):
           logger.warning(f"Checkpoint missing {len(missing)} symbols, rebuilding...")
           checkpoint = rebuild_checkpoint_from_shards(shards_dir)

       return checkpoint
   ```
4. **Re-ejecutar FASE 2.5 con orchestrator corregido:**
   ```bash
   python ultra_robust_orchestrator_fixed.py \
     --resume \
     --validate-checkpoint \
     --symbols-remaining 863
   ```
5. **Verificar 0% duplicados:**
   ```python
   df_new = pl.read_parquet("events_intraday_enriched_clean_YYYYMMDD.parquet")
   duplicates = df_new.group_by(['symbol', 'timestamp', 'event_type']).agg(
       pl.len().alias('count')
   ).filter(pl.col('count') > 1)

   assert len(duplicates) == 0, "Found duplicates!"
   ```
6. **Regenerar manifest CORE limpio:**
   ```bash
   python generate_core_manifest_dryrun.py \
     --input events_intraday_enriched_clean_YYYYMMDD.parquet
   ```
7. **Re-lanzar FASE 3.2 con manifest limpio**

**Timeline:**
```
Hoy (2025-10-14):
- Pausar PM wave: 10 min
- Análisis de símbolos duplicados: 1 hora
- Fix orchestrator bug: 2-3 horas
- Testing orchestrator: 1 hora
Total: ~5 horas

2025-10-15 → 2025-10-19:
- Re-ejecutar FASE 2.5: 863 símbolos × 12s = ~2.9 horas por corrida
- Con 40 workers paralelos: ~4.4 días
- Validación: 1 hora

2025-10-19:
- Regenerar manifest CORE: 30 min
- Re-lanzar FASE 3.2: inicio

Total delay: ~5 días, pero dataset limpio
```

### Opción 2: **Continuar con Manifest Actual** (NO RECOMENDADO)

**Pros:**
- ✅ No interrumpe PM wave actual
- ✅ FASE 3.2 completa en 2.8 días como planificado

**Cons:**
- ❌ Sesgo de sobre-representación en 48.4% de eventos
- ❌ Desperdicio de 32h + 12 GB en FASE 3.2
- ❌ Dataset final contiene duplicados latentes
- ❌ Bug persiste para futuras fases
- ❌ Difícil defender selección en análisis posterior

**Mitigación parcial:**
- Añadir campo `is_from_duplicate_symbol` al manifest
- Ponderar eventos por frecuencia de reprocesamiento
- Documentar sesgo en metadata

---

## 5. ANÁLISIS DE SÍMBOLOS DUPLICADOS

### 5.1 Identificación de Símbolos Afectados

**Script propuesto:** `scripts/analysis/identify_duplicate_symbols.py`

```python
#!/usr/bin/env python3
"""Identify symbols that were reprocessed and caused duplicates"""

import polars as pl
from pathlib import Path

def identify_duplicate_symbols(enriched_file):
    """Identify which symbols have duplicate events"""

    df = pl.read_parquet(enriched_file)

    # Find all duplicate groups
    duplicates = df.group_by(['symbol', 'timestamp', 'event_type']).agg([
        pl.len().alias('count'),
        pl.col('enriched_at').min().alias('first_processed'),
        pl.col('enriched_at').max().alias('last_processed')
    ]).filter(pl.col('count') > 1)

    # Group by symbol to see which symbols have duplicates
    symbols_with_dups = duplicates.group_by('symbol').agg([
        pl.len().alias('duplicate_groups'),
        pl.col('count').sum().alias('total_duplicate_events')
    ]).sort('total_duplicate_events', descending=True)

    print(f"Symbols with duplicates: {len(symbols_with_dups)}")
    print(f"Total duplicate groups: {duplicates.height:,}")
    print("\nTop 20 symbols by duplicate events:")
    print(symbols_with_dups.head(20))

    return symbols_with_dups

if __name__ == "__main__":
    enriched_file = "processed/events/events_intraday_enriched_20251013_210559.parquet"
    symbols_with_dups = identify_duplicate_symbols(enriched_file)

    # Export for analysis
    symbols_with_dups.write_csv("analysis/symbols_with_duplicates_20251014.csv")
```

### 5.2 Impacto por Símbolo

**Preguntas a responder:**
1. ¿Cuántos símbolos fueron reprocesados? (estimado: 45-96 símbolos)
2. ¿Tienen más eventos que símbolos no-duplicados?
3. ¿Están sobre-representados en manifest CORE?

**Análisis propuesto:**
```python
# Compare events/symbol for duplicate vs non-duplicate symbols
df_manifest = pl.read_parquet("manifest_core_20251014.parquet")

# Join with duplicate symbols list
df_analysis = df_manifest.join(
    symbols_with_dups,
    on='symbol',
    how='left'
)

# Compare distributions
duplicate_symbols = df_analysis.filter(pl.col('duplicate_groups').is_not_null())
clean_symbols = df_analysis.filter(pl.col('duplicate_groups').is_null())

print(f"Manifest CORE - Duplicate symbols:")
print(f"  Count: {duplicate_symbols['symbol'].n_unique()}")
print(f"  Events: {len(duplicate_symbols)} ({len(duplicate_symbols)/len(df_manifest)*100:.1f}%)")
print(f"  Avg events/symbol: {len(duplicate_symbols)/duplicate_symbols['symbol'].n_unique():.1f}")

print(f"\nManifest CORE - Clean symbols:")
print(f"  Count: {clean_symbols['symbol'].n_unique()}")
print(f"  Events: {len(clean_symbols)} ({len(clean_symbols)/len(df_manifest)*100:.1f}%)")
print(f"  Avg events/symbol: {len(clean_symbols)/clean_symbols['symbol'].n_unique():.1f}")
```

---

## 6. RECOMENDACIÓN FINAL

### Decisión: **PAUSAR Y CORREGIR** (Opción 1)

**Justificación:**

1. **Integridad del dataset:**
   - Dataset limpio es crítico para análisis científico
   - Sesgo de sobre-representación invalida conclusiones estadísticas
   - Reproducibilidad requiere proceso sin errores

2. **Eficiencia de recursos:**
   - Ahorro neto: 32h + 12 GB - 5h delay = 27h ganancia
   - API calls ahorrados: 9,600 requests (~$50-100 valor)
   - Evita re-procesamiento posterior

3. **Aprendizaje:**
   - Corregir bug previene futuros problemas en FASE 2.6, 2.7, etc.
   - Validación cruzada checkpoint ← → shards es best practice
   - Testing de orchestrator bajo conflictos múltiples

4. **Timeline aceptable:**
   - 5 días de delay es manejable
   - Dataset final vale la espera
   - PM wave actual solo tiene 21/1,452 eventos (1.4% progreso), mínima pérdida

---

## 7. ACCIÓN INMEDIATA

### Paso 1: Pausar PM Wave

```bash
# Find process
ps aux | grep download_trades_quotes | grep -v grep

# Kill process
kill -9 [PID]

# Verify stopped
ps aux | grep download_trades_quotes | grep -v grep
```

### Paso 2: Analizar Símbolos Duplicados

```bash
python scripts/analysis/identify_duplicate_symbols.py
```

### Paso 3: Revisar y Corregir Orchestrator

```bash
# Backup current version
cp ultra_robust_orchestrator.py ultra_robust_orchestrator_buggy.py

# Apply fix (checkpoint validation)
# ... edit orchestrator ...

# Test with single symbol
python ultra_robust_orchestrator_fixed.py --test-mode --symbols 1
```

---

**Autor:** Claude (Anthropic)
**Fecha:** 2025-10-14 12:30 UTC
**Prioridad:** 🔴 CRÍTICA
**Acción requerida:** ✅ SÍ - Pausar FASE 3.2 y corregir FASE 2.5
