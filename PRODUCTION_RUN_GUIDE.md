# Guía de Ejecución en Producción: Detección de Eventos Intradía

**Fecha:** 2025-10-12
**Script:** `scripts/processing/detect_events_intraday.py`
**Estado:** ✅ PRODUCTION-READY con batching, checkpointing y heartbeat

---

## 🎯 Características de Producción Implementadas

### 1. **Batching Inteligente**
- Procesa símbolos en lotes de 50 (configurable)
- Guarda resultados inmediatamente después de cada batch
- Libera memoria automáticamente con `gc.collect()`

### 2. **Checkpointing Automático**
- Guarda progreso cada batch (configurable)
- Resume desde último símbolo completado con `--resume`
- Archivo: `logs/checkpoints/events_intraday_YYYYMMDD_completed.json`

### 3. **Heartbeat en Tiempo Real**
- Actualiza cada símbolo procesado
- Monitorea memoria RAM (GB)
- Archivo: `logs/heartbeats/events_intraday_YYYYMMDD_heartbeat.json`

### 4. **Logging Robusto (Multi-archivo, Sin Buffers)**
- **Logger principal**: `logs/detect_events/detect_events_intraday_YYYYMMDD_HHMMSS.log`
  - Todo: DEBUG, INFO, WARNING, ERROR, excepciones con traceback completo
  - Rotación automática a 50 MB
  - Compresión automática a ZIP después de rotación
  - Thread-safe con `enqueue=True`
  - Modo append (resume seguro)

- **Heartbeat log**: `logs/detect_events/heartbeat_YYYYMMDD.log`
  - Progreso incremental (1 línea por símbolo procesado)
  - Formato TSV: `timestamp\tsymbol\tbatch_num\ttotal_batches\tevents_count\tmem_gb`
  - Sin buffer (`buffering=1`) → cada línea se escribe inmediatamente
  - Útil para saber **exactamente dónde se detuvo** si falla

- **Batch log**: `logs/detect_events/batches_YYYYMMDD.log`
  - Confirmación de cada batch guardado
  - Formato TSV: `timestamp\tbatch_num\tsymbols_count\tevents_count\tshard_file\tmem_gb`
  - Sin buffer → confirmación inmediata en disco
  - Útil para verificar qué shards están completos

### 5. **Sharding**
- Cada batch genera un shard: `processed/events/shards/events_intraday_YYYYMMDD_shardNNNN.parquet`
- Merge final automático al terminar
- Archivo final: `processed/events/events_intraday_YYYYMMDD.parquet`

---

## 📋 Comandos de Ejecución

### **Opción 1: PowerShell (Recomendado para Windows)**

```powershell
# Cambiar a directorio del proyecto
cd D:\04_TRADING_SMALLCAPS

# Ejecutar en primer plano (ventana NO se debe cerrar)
python -u scripts\processing\detect_events_intraday.py `
  --from-file processed\reference\symbols_with_1m.parquet `
  --batch-size 50 `
  --checkpoint-interval 1 `
  --resume
```

**Ventajas:**
- Logger escribe directamente a archivo (no depende de shell)
- Sin redirecciones ni pipes
- Checkpointing automático cada batch
- Si se cae, `--resume` retoma exactamente donde quedó

---

### **Opción 2: Windows Task Scheduler (Para correr desatendido)**

#### Crear Tarea Programada:

1. Abrir **Task Scheduler** (`taskschd.msc`)
2. **Create Basic Task** → Nombre: `Intraday Event Detection`
3. **Trigger:** One time / Immediate
4. **Action:** Start a program

**Configuración de la acción:**

```
Program/script: python.exe

Add arguments:
-u scripts\processing\detect_events_intraday.py --from-file processed\reference\symbols_with_1m.parquet --batch-size 50 --checkpoint-interval 1 --resume

Start in:
D:\04_TRADING_SMALLCAPS\
```

#### Configuración de Settings (IMPORTANTE):

- ✅ **Conditions:**
  - ❌ Desmarcar "Start the task only if the computer is on AC power"
  - ❌ Desmarcar "Stop if the computer switches to battery power"

- ✅ **Settings:**
  - ❌ Desmarcar "Stop the task if it runs longer than..."
  - ✅ Marcar "If the task fails, restart every 5 minutes"
  - ✅ Marcar "Attempt to restart up to: 99 times"
  - ✅ Marcar "Run task as soon as possible after a scheduled start is missed"

**Ventajas:**
- Ejecuta sin necesidad de tener sesión abierta
- Restart automático si falla
- No depende de que la consola esté abierta

---

### **Opción 3: WSL2 (Linux en Windows) - Máxima Estabilidad**

```bash
# Desde WSL (Ubuntu)
cd /mnt/d/04_TRADING_SMALLCAPS

nohup python -u scripts/processing/detect_events_intraday.py \
  --from-file processed/reference/symbols_with_1m.parquet \
  --batch-size 50 \
  --checkpoint-interval 1 \
  --resume \
  > /dev/null 2>&1 & disown
```

**Ventajas:**
- Proceso completamente desacoplado de la sesión
- No se detiene aunque cierres la terminal
- `nohup` + `disown` = máxima estabilidad

---

## 🔍 Monitoreo en Tiempo Real

### **1. Heartbeat Log (Progreso Símbolo a Símbolo)**

```powershell
# Ver últimas 10 líneas del heartbeat en vivo
Get-Content logs\detect_events\heartbeat_20251012.log -Tail 10 -Wait
```

**Ejemplo de salida:**
```
2025-10-12 14:35:22.123	AAPL	5	40	12450	3.24
2025-10-12 14:35:25.456	MSFT	5	40	12523	3.26
2025-10-12 14:35:28.789	TSLA	5	40	12678	3.28
```

**Formato:** `timestamp\tsymbol\tbatch_num\ttotal_batches\tevents_count\tmem_gb`

### **2. Batch Log (Confirmación de Shards Guardados)**

```powershell
# Ver batches completados
Get-Content logs\detect_events\batches_20251012.log -Tail 5 -Wait
```

**Ejemplo de salida:**
```
2025-10-12 14:40:15.234	5	50	4523	events_intraday_20251012_shard0005.parquet	3.45
2025-10-12 14:52:30.567	6	50	4678	events_intraday_20251012_shard0006.parquet	3.52
```

**Formato:** `timestamp\tbatch_num\tsymbols_count\tevents_count\tshard_file\tmem_gb`

### **3. Heartbeat JSON (Progreso General)**

```powershell
# Ver heartbeat JSON cada 10 segundos
while ($true) {
    Clear-Host
    Get-Content logs\heartbeats\events_intraday_20251012_heartbeat.json
    Start-Sleep -Seconds 10
}
```

**Ejemplo de salida:**
```json
{
  "run_id": "events_intraday_20251012",
  "last_symbol": "AAPL",
  "last_timestamp": "2025-10-12T14:35:22.123456",
  "batch_num": 5,
  "total_batches": 40,
  "progress_pct": 12.5,
  "events_detected": 12450,
  "memory_gb": 3.24,
  "status": "running"
}
```

### **4. Log Principal (Debug Completo)**

```powershell
# Ver log principal en vivo
Get-Content logs\detect_events\detect_events_intraday_*.log -Tail 50 -Wait
```

**Incluye:**
- Todos los mensajes DEBUG, INFO, WARNING, ERROR
- Tracebacks completos de excepciones
- Información de threads y procesos

### **Checkpoint (Símbolos Completados)**

```powershell
Get-Content logs\checkpoints\events_intraday_20251012_completed.json
```

### **Shards Generados**

```powershell
Get-ChildItem processed\events\shards\ -Filter "events_intraday_20251012_shard*.parquet" | Measure-Object -Property Length -Sum
```

### **Log en Tiempo Real**

```powershell
Get-Content -Path "logs\processing\detect_events_intraday_*.log" -Tail 50 -Wait
```

---

## ⚠️ Si el Proceso se Detiene

### **Paso 1: Verificar última actividad**

```powershell
# Ver heartbeat
Get-Content logs\heartbeats\events_intraday_20251012_heartbeat.json

# Ver checkpoint
Get-Content logs\checkpoints\events_intraday_20251012_completed.json
```

### **Paso 2: Relanzar con --resume**

```powershell
python -u scripts\processing\detect_events_intraday.py `
  --from-file processed\reference\symbols_with_1m.parquet `
  --batch-size 50 `
  --checkpoint-interval 1 `
  --resume
```

**¿Qué hace `--resume`?**
- Carga el checkpoint: `events_intraday_YYYYMMDD_completed.json`
- Salta todos los símbolos ya completados
- Continúa desde el siguiente símbolo pendiente
- Usa la misma numeración de shards (no sobrescribe)

### **Paso 3: Verificar shards generados**

```powershell
Get-ChildItem processed\events\shards\ | Select-Object Name, Length
```

**¿Qué hacer si hay shards?**
- ✅ Los shards se preservan automáticamente
- ✅ Al terminar, se fusionan en el archivo final
- ✅ Si quieres fusionar manualmente ahora:

```python
# Desde Python
import polars as pl
from pathlib import Path

shards = sorted(Path("processed/events/shards").glob("events_intraday_20251012_shard*.parquet"))
df = pl.concat([pl.read_parquet(f) for f in shards])
df = df.sort(["symbol", "timestamp"])
df.write_parquet("processed/events/events_intraday_20251012.parquet", compression="zstd")
print(f"Merged {len(shards)} shards → {len(df):,} events")
```

---

## 🎯 Parámetros de Configuración

### **--batch-size** (default: 50)
- Símbolos por shard
- **Menor (25)**: Más shards, menos RAM, checkpoints más frecuentes
- **Mayor (100)**: Menos shards, más RAM, checkpoints menos frecuentes
- **Recomendado:** 50 para balance RAM/performance

### **--checkpoint-interval** (default: 1)
- Cada cuántos batches guardar checkpoint
- **1**: Guarda después de cada batch (máxima seguridad, overhead mínimo)
- **5**: Guarda cada 5 batches (reduce I/O, pero pierdes más progreso si falla)
- **Recomendado:** 1 (el overhead es negligible)

### **--resume**
- Si se proporciona: carga checkpoint y salta símbolos completados
- Si NO se proporciona: empieza desde cero (sobrescribe checkpoint anterior)

### **--limit** (testing)
- Procesa solo los primeros N símbolos
- Útil para testing rápido

**Ejemplo de test:**
```powershell
python -u scripts\processing\detect_events_intraday.py `
  --from-file processed\reference\symbols_with_1m.parquet `
  --limit 10 `
  --batch-size 5
```

---

## 📊 Estimaciones de Tiempo y Storage

### **Dataset Completo (1,996 símbolos, ~750 días promedio)**

| Métrica | Estimación |
|---------|------------|
| **Symbol-dates** | ~1.5M combinaciones |
| **Eventos esperados** | 500K-800K eventos |
| **Tiempo procesamiento** | 6-8 horas |
| **Memoria pico** | 4-6 GB RAM |
| **Storage shards** | ~2-3 GB (comprimido) |
| **Storage final** | ~1-1.5 GB (merged) |

### **Con batch_size=50:**
- **Batches totales:** 40 batches
- **Shards generados:** 40 archivos
- **Checkpoint cada:** 1 batch (40 checkpoints)
- **Tiempo por batch:** ~10-12 minutos
- **Pérdida máxima si falla:** 1 batch (~50 símbolos, ~10 min)

---

## ✅ Checklist de Verificación Post-Ejecución

### 1. **Verificar heartbeat final**
```powershell
Get-Content logs\heartbeats\events_intraday_20251012_heartbeat.json
```
**Debe decir:** `"status": "completed"`

### 2. **Verificar archivo final**
```powershell
Get-Item processed\events\events_intraday_20251012.parquet
```
**Debe existir** y tener tamaño razonable (>100 MB)

### 3. **Validar conteo de eventos**
```python
import polars as pl
df = pl.read_parquet("processed/events/events_intraday_20251012.parquet")
print(f"Total events: {len(df):,}")
print(f"\nBy type:\n{df.group_by('event_type').len().sort('len', descending=True)}")
```

### 4. **Verificar log final**
```powershell
Select-String -Path "logs\processing\detect_events_intraday_*.log" -Pattern "DETECTION COMPLETE"
```
**Debe existir** línea con `✅ DETECTION COMPLETE`

### 5. **Limpiar shards (opcional)**
```powershell
# Solo DESPUÉS de verificar que el archivo final está OK
Remove-Item processed\events\shards\events_intraday_20251012_shard*.parquet
```

---

## 🚀 Próximos Pasos (FASE 3.2)

Una vez completada la detección:

### **1. Construir Manifest CORE**
```bash
python scripts/processing/build_intraday_manifest.py \
  --config config/config.yaml \
  --out processed/events/events_intraday_manifest_CORE.parquet
```

### **2. Descargar Trades**
```bash
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest_CORE.parquet \
  --trades-only \
  --resume
```

### **3. Descargar Quotes (NBBO)**
```bash
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest_CORE.parquet \
  --quotes-only \
  --resume
```

---

## 📞 Troubleshooting

### **Problema: "ModuleNotFoundError: No module named 'psutil'"**

**Solución:**
```powershell
pip install psutil
```

### **Problema: Proceso se detiene sin error después de ~60 segundos**

**Causa:** Windows + background process + redirección de IO

**Solución:** Usar PowerShell en primer plano O Task Scheduler como se documenta arriba

### **Problema: RAM crece sin control (>8 GB)**

**Solución:** Reducir batch_size:
```powershell
python -u scripts\processing\detect_events_intraday.py `
  --from-file processed\reference\symbols_with_1m.parquet `
  --batch-size 25 `
  --resume
```

### **Problema: "Permission denied" al escribir shards**

**Solución:**
1. Cerrar cualquier programa que tenga abiertos los archivos parquet
2. Excluir carpeta del proyecto del antivirus
3. Ejecutar PowerShell como Administrador

### **Problema: Shards existen pero no se fusionan**

**Solución:** Fusionar manualmente (ver código Python en sección "Si el Proceso se Detiene")

---

## 📝 Notas Finales

### **Por qué este diseño funciona:**
1. ✅ **Sin pipes ni redirecciones**: Logger escribe directo a archivo
2. ✅ **Batching**: Nunca acumula más de 50 símbolos en RAM
3. ✅ **Checkpointing**: Nunca pierde más de 1 batch de progreso
4. ✅ **Heartbeat**: Puedes ver progreso sin abrir el proceso
5. ✅ **Resume**: Relanzar es seguro y eficiente

### **Cuándo usar cada opción:**
- **PowerShell:** Para ejecuciones que puedes monitorear (< 8 horas)
- **Task Scheduler:** Para ejecuciones largas desatendidas (> 8 horas)
- **WSL2:** Si tienes problemas recurrentes con Windows matando procesos

### **Recomendación final:**
Para el dataset completo (1,996 símbolos), usar **Task Scheduler** con los settings indicados arriba. Esto garantiza:
- Ejecución sin interrupciones
- Restart automático si falla
- No depende de sesión de usuario
- Logger y heartbeat funcionan perfectamente

---

**Autor:** Claude + Alex
**Última actualización:** 2025-10-12
**Versión:** 2.0 (Production-grade con batching + checkpointing)
