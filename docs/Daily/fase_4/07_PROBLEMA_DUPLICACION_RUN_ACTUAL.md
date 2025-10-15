# 🚨 PROBLEMA CRÍTICO: Run 20251014 ESTÁ DUPLICANDO

**Fecha detección:** 2025-10-14 17:45 UTC
**Severidad:** 🔴 CRÍTICA
**Estado:** ⚠️ PROCESO ACTIVO GENERANDO DUPLICADOS

---

## ❓ TUS 3 PREGUNTAS - RESPUESTAS

### **1. ¿El proceso actual está duplicando símbolos?**

**SÍ** ✗

**Evidencia:**
```
Símbolo: OPRX
  - Eventos únicos: 241
  - Aparece en: 3 shards
  - Total eventos: 723 (3 copias × 241)
  - Duplicados: 482

!!! DUPLICACIÓN ACTIVA DETECTADA !!!
```

**Todos los 120 símbolos en shards están duplicados en 3 shards cada uno.**

---

### **2. ¿Identifica cuando un símbolo ya está acabado?**

**SÍ, pero NO FUNCIONA CORRECTAMENTE** ✗

**Checkpoint actual:**
```json
{
  "run_id": "events_intraday_20251014",
  "completed_symbols": 186 símbolos,
  "total_completed": 186,
  "last_updated": "2025-10-14T17:19:37"
}
```

**El checkpoint SÍ guarda símbolos completados, PERO:**
- ❌ Hay 3 workers procesando símbolos simultáneamente
- ❌ Los workers NO consultan el checkpoint antes de procesar
- ❌ Los 3 workers procesan los MISMOS símbolos
- ❌ Resultado: Cada símbolo se procesa 3 veces (1 por worker)

**Discrepancia:**
- Checkpoint: 186 símbolos "completados"
- Shards: 120 símbolos únicos
- Diferencia: 66 símbolos solo en checkpoint (sin shards)

**Esto confirma:** Los workers guardan en checkpoint PERO siguen procesando símbolos ya completados.

---

### **3. ¿Cuáles son los archivos generados para la BBDD?**

**Archivos FÍSICOS generados:**

```
processed/events/shards/
├── events_intraday_20251014_shard0000.parquet (233 KB)
├── events_intraday_20251014_shard0001.parquet (170 KB)
├── events_intraday_20251014_shard0002.parquet (173 KB)
├── ...
├── events_intraday_20251014_shard0027.parquet (136 KB)
└── events_intraday_20251014_shard0028.parquet (119 KB)

Total: 29 shards
Tamaño: 4.58 MB
Eventos: 115,416 (CON DUPLICACIÓN)
Símbolos únicos: 120
```

**Archivos de CONTROL:**

```
logs/checkpoints/
└── events_intraday_20251014_completed.json

processed/events/manifests/
├── events_intraday_20251014_shard0000.json
├── events_intraday_20251014_shard0001.json
├── ...
└── events_intraday_20251014_shard0028.json
```

**Archivos FINALES (cuando termine):**
```
processed/events/
└── events_intraday_20251014.parquet  (merge de shards, PENDIENTE)
```

**PERO ATENCIÓN:** Estos archivos contienen DUPLICACIÓN. NO son válidos para la BBDD hasta deduplicar.

---

## 🔍 CAUSA RAÍZ DEL PROBLEMA

### **¿Por qué está duplicando si aplicamos el "fix"?**

**El "fix" de commit `2a7a745` incluía:**
- ✅ File locks para shard numbering atómico
- ✅ Manifests por shard
- ✅ Reconciliación con manifests

**PERO EL PROBLEMA ES:**

El orchestrator lanzó **3 WORKERS SIMULTÁNEOS** a las 16:23:

```
Worker 1: PID=84076
Worker 2: PID=85708
Worker 3: PID=21396
```

**Cada worker:**
1. Lee la lista completa de símbolos (1,996)
2. Lee checkpoint (53 completados en ese momento)
3. Calcula símbolos pendientes (1,996 - 53 = 1,943)
4. **Los 3 workers procesan los MISMOS 1,943 símbolos**

**No hay coordinación entre workers para dividir símbolos.**

**Resultado:**
- Worker 1 procesa OPRX → genera shard0000
- Worker 2 procesa OPRX → genera shard0012
- Worker 3 procesa OPRX → genera shard0024

**3 copias del mismo símbolo en 3 shards diferentes.**

---

## 📊 ANÁLISIS DETALLADO

### **Evidencia de Duplicación**

**Todos los 120 símbolos en shards aparecen en 3 shards cada uno:**

```
OPRX: 3 shards (shard0000, shard0012, shard0024)
OPTT: 3 shards
ONCY: 3 shards
OR: 3 shards
OPRT: 3 shards
OPEN: 3 shards
... (todos los 120 símbolos)
```

**Pattern:**
- Worker 1: shards 0, 3, 6, 9, 12, 15, 18, 21, 24, 27
- Worker 2: shards 1, 4, 7, 10, 13, 16, 19, 22, 25, 28
- Worker 3: shards 2, 5, 8, 11, 14, 17, 20, 23, 26

**Cada worker genera ~10 shards, pero TODOS procesan los MISMOS símbolos.**

---

### **Timeline del Run 20251014**

```
04:01 AM - Inicio (primeros shards generados)
06:28 AM - Orchestrator se detuvo (máximo runtime)
06:30 AM - Workers killed
...
16:23 PM - Orchestrator RE-LANZADO
16:26 PM - 3 workers activos
17:19 PM - Último checkpoint guardado (186 símbolos)
17:45 PM - PROBLEMA DETECTADO
```

**Observación:** El orchestrator se detuvo y relanzó. Esto puede explicar parte de la duplicación.

---

## ⚠️ IMPACTO

### **Datos Actuales NO SON VÁLIDOS**

```
Run 20251014:
  Shards: 29 archivos
  Eventos BRUTOS: 115,416
  Símbolos únicos: 120

  Duplicación estimada: 66.7% (2 de cada 3 eventos son duplicados)
  Eventos ÚNICOS estimados: 38,472 (115,416 / 3)
```

**Si el proceso continúa así:**
- 1,996 símbolos × 3 workers = 5,988 procesos de símbolos
- ~1.5M eventos × 3 = ~4.5M eventos brutos (con 66% duplicación)
- Tamaño final: ~150 MB brutos → ~50 MB deduplicados

---

## 🚫 PROCESOS ACTIVOS

**Orchestrator:** Ultra Robust Orchestrator
- Archivo: `logs/ultra_robust/orchestrator_20251014.log`
- Inicio: 16:23:31
- Estado: Desconocido (no hay proceso `ps aux`)

**Workers detectados en logs:**
```
Worker 1: logs/ultra_robust/worker_1_20251014_162630.log (5.7 MB)
Worker 2: logs/ultra_robust/worker_2_20251014_162707.log (5.9 MB)
Worker 3: logs/ultra_robust/worker_3_20251014_162811.log (5.5 MB)
```

**Última actividad:** 17:19 PM (heartbeat)

**Estado actual:** Probablemente DETENIDO (no vimos proceso en `ps aux`)

---

## 🛑 ACCIÓN REQUERIDA INMEDIATA

### **OPCIÓN 1: Detener TODO** (RECOMENDADO)

```bash
# 1. Matar cualquier proceso residual
ps aux | grep -E "(ultra_robust|detect_events)" | awk '{print $2}' | xargs kill -9

# 2. Verificar limpieza
ps aux | grep -E "(ultra_robust|detect_events)" | grep -v grep
```

**Resultado esperado:** No procesos activos

---

### **OPCIÓN 2: Archivar run corrupto y limpiar**

```bash
# 1. Archivar shards corruptos
mkdir -p archive/corrupted_fase25_20251014
mv processed/events/shards/events_intraday_20251014_shard*.parquet \
   archive/corrupted_fase25_20251014/

# 2. Archivar checkpoint
mv logs/checkpoints/events_intraday_20251014_completed.json \
   archive/corrupted_fase25_20251014/

# 3. Archivar logs
mv logs/ultra_robust/*20251014*.log \
   archive/corrupted_fase25_20251014/
```

---

### **OPCIÓN 3: Decidir estrategia**

**A. Usar datos deduplicados existentes (405K eventos)**
- ✅ Ya validados (100% consistencia)
- ✅ Listos YA
- ✅ Podemos lanzar FASE 3.2 HOY
- ⚠️ Solo 1,133 símbolos (no 1,996)

**B. Esperar y arreglar run limpio**
- ❌ Run 20251014 está CORRUPTO
- ❌ Necesita reinicio completo
- ⏳ 11 días para completar 1,996 símbolos
- ✅ Dataset 100% limpio desde origen

**C. Deduplicar run 20251014 cuando termine**
- ⏳ Esperar que termine (si sigue corriendo)
- ✅ Deduplicar eventos (dividir por 3)
- ⚠️ Misma situación que run 20251013 (validar consistencia)

---

## 🎯 RECOMENDACIÓN

**INMEDIATO:**
1. Detener todos los procesos
2. Archivar run 20251014 corrupto
3. Usar datos deduplicados existentes (405K eventos) para FASE 3.2

**Razones:**
- ✅ Datos deduplicados ya validados (100% consistencia)
- ✅ No perdemos más tiempo
- ✅ Podemos lanzar FASE 3.2 HOY
- ✅ Tenemos 1,133 símbolos procesados (suficiente)

**OPCIONAL (en paralelo):**
- Arreglar orchestrator para dividir símbolos correctamente entre workers
- Re-lanzar FASE 2.5 limpia cuando tengamos tiempo
- Usar como dataset alternativo

---

## 📋 ARCHIVOS PARA BBDD (Válidos)

**NO usar:**
```
❌ processed/events/shards/events_intraday_20251014_shard*.parquet
   (CORRUPTOS - con duplicación 66%)
```

**SÍ usar:**
```
✅ processed/events/events_intraday_enriched_dedup_20251014_101439.parquet
   - 405,886 eventos ÚNICOS
   - 1,133 símbolos
   - Validado 100%

✅ processed/events/manifest_core_20251014.parquet
   - 10,000 eventos seleccionados
   - Listo para FASE 3.2
```

---

**Autor:** Claude Code
**Fecha:** 2025-10-14 17:45 UTC
**Prioridad:** 🔴 CRÍTICA - Acción inmediata requerida
