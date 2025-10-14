# Estructura de Logging Robusta - Sin Pérdida de Información

**Fecha:** 2025-10-12
**Principio:** Nunca depender de stdout ni redirecciones shell para logs críticos

---

## 🧠 Principio General

**Los logs deben escribirse directamente desde Python**, mediante un logger persistente (Loguru) con:

1. ✅ Salida a archivo rotativo (no a consola)
2. ✅ Flush inmediato (sin buffer)
3. ✅ Modo seguro multiproceso (`enqueue=True`)
4. ✅ Rotación por tamaño
5. ✅ Nivel DEBUG con timestamps precisos

---

## 📂 Estructura de Logs

```
logs/
├── detect_events/
│   ├── detect_events_intraday_20251012_143022.log  ← Principal (TODO)
│   ├── heartbeat_20251012.log                      ← Progreso incremental
│   ├── batches_20251012.log                        ← Confirmación de guardado
│   └── detect_events_intraday_20251012_143022.log.1.zip  ← Rotado/comprimido
├── checkpoints/
│   └── events_intraday_20251012_completed.json     ← Símbolos completados
├── heartbeats/
│   └── events_intraday_20251012_heartbeat.json     ← Estado actual (JSON)
└── ingestion/
    └── polygon_ingestion.log                       ← Descargas Polygon
```

---

## 📋 Logs en Detalle

### 1. **Log Principal** (`detect_events_intraday_YYYYMMDD_HHMMSS.log`)

**Propósito:** Registro completo de toda la actividad del proceso

**Configuración:**
```python
logger.add(
    main_log,
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {process.name}:{thread.name} | {file}:{line} | {message}",
    enqueue=True,        # Multiproceso seguro
    backtrace=True,      # Traceback completo en excepciones
    diagnose=True,       # Contexto adicional en errores
    rotation="50 MB",    # Rota cada 50 MB
    retention="7 days",  # Mantiene logs 7 días
    compression="zip",   # Comprime logs viejos
    mode="a"             # Append si relanzas (resume)
)
```

**Contenido:**
- Todos los niveles: DEBUG, INFO, WARNING, ERROR
- Excepciones con traceback completo
- Información de proceso y thread
- Archivo y línea de código

**Ejemplo:**
```
2025-10-12 14:35:22.123 | INFO     | MainProcess:MainThread | detect_events_intraday.py:867 | [HEARTBEAT] AAPL | batch=5/40 (12.5%) | events=12,450 | RAM=3.24GB
2025-10-12 14:35:22.456 | DEBUG    | MainProcess:MainThread | detect_events_intraday.py:1076 | [RESOURCE] RAM used: 25.3% (3.24/12.8 GB) | CPU: 45.2%
2025-10-12 14:40:15.789 | SUCCESS  | MainProcess:MainThread | detect_events_intraday.py:1061 | [BATCH SAVED] #005 | symbols=50 | events=4,523 | file=events_intraday_20251012_shard0005.parquet | RAM=3.45GB
```

---

### 2. **Heartbeat Log** (`heartbeat_YYYYMMDD.log`)

**Propósito:** Progreso incremental para saber exactamente dónde se detuvo

**Configuración:**
```python
with open(heartbeat_file, "a", encoding="utf-8", buffering=1) as f:
    f.write(f"{timestamp}\t{symbol}\t{batch_num}\t{total_batches}\t{events_count}\t{mem_gb:.2f}\n")
```

**Características clave:**
- ✅ **Sin buffer** (`buffering=1`): cada línea se escribe inmediatamente
- ✅ Formato TSV: fácil de parsear con pandas/polars
- ✅ 1 línea por símbolo procesado
- ✅ Permite reanudar: leer última línea = último símbolo completado

**Formato:**
```
timestamp                 symbol  batch_num  total_batches  events_count  mem_gb
2025-10-12 14:35:22.123  AAPL    5          40             12450         3.24
2025-10-12 14:35:25.456  MSFT    5          40             12523         3.26
2025-10-12 14:35:28.789  TSLA    5          40             12678         3.28
```

**Uso para Resume:**
```python
# Leer último símbolo procesado
df = pl.read_csv("logs/detect_events/heartbeat_20251012.log", separator="\t", has_header=False)
last_symbol = df[-1, 1]  # Segunda columna
print(f"Last processed: {last_symbol}")
```

---

### 3. **Batch Log** (`batches_YYYYMMDD.log`)

**Propósito:** Confirmación de cada batch guardado (shard completado)

**Configuración:**
```python
with open(batch_file, "a", encoding="utf-8", buffering=1) as f:
    f.write(f"{timestamp}\t{batch_num}\t{symbols_count}\t{total_events}\t{shard_file}\t{mem_gb:.2f}\n")
```

**Características clave:**
- ✅ Sin buffer: confirmación inmediata
- ✅ Formato TSV
- ✅ 1 línea por batch completado
- ✅ Permite verificar qué shards existen sin leer archivos parquet

**Formato:**
```
timestamp                 batch_num  symbols_count  total_events  shard_file                                     mem_gb
2025-10-12 14:40:15.234  5          50             4523          events_intraday_20251012_shard0005.parquet    3.45
2025-10-12 14:52:30.567  6          50             4678          events_intraday_20251012_shard0006.parquet    3.52
```

**Uso para Verificación:**
```python
# Verificar batches completados vs shards existentes
df = pl.read_csv("logs/detect_events/batches_20251012.log", separator="\t", has_header=False)
completed_batches = df.select(pl.col("column_1").alias("batch_num")).unique()

shards = list(Path("processed/events/shards").glob("events_intraday_20251012_shard*.parquet"))
print(f"Batches logged: {len(completed_batches)}")
print(f"Shards on disk: {len(shards)}")
```

---

### 4. **Heartbeat JSON** (`events_intraday_YYYYMMDD_heartbeat.json`)

**Propósito:** Estado actual en formato estructurado (JSON)

**Actualización:** Cada símbolo procesado (sobrescribe archivo)

**Contenido:**
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

**Uso para Monitoreo:**
```python
# Script de monitoreo
import json
import time

while True:
    with open("logs/heartbeats/events_intraday_20251012_heartbeat.json") as f:
        data = json.load(f)

    print(f"\rProgress: {data['progress_pct']:.1f}% | Symbol: {data['last_symbol']} | RAM: {data['memory_gb']:.2f}GB", end="")
    time.sleep(5)
```

---

### 5. **Checkpoint JSON** (`events_intraday_YYYYMMDD_completed.json`)

**Propósito:** Lista de símbolos completados (para resume)

**Actualización:** Cada batch completado

**Contenido:**
```json
{
  "run_id": "events_intraday_20251012",
  "completed_symbols": [
    "AAPL",
    "MSFT",
    "TSLA",
    ...
  ],
  "total_completed": 250,
  "last_updated": "2025-10-12T14:40:15.234567"
}
```

**Uso para Resume:**
```python
# Cargar checkpoint
with open("logs/checkpoints/events_intraday_20251012_completed.json") as f:
    checkpoint = json.load(f)

completed = set(checkpoint["completed_symbols"])
all_symbols = load_symbols()
remaining = [s for s in all_symbols if s not in completed]

print(f"Completed: {len(completed)}")
print(f"Remaining: {len(remaining)}")
```

---

## 🔍 Comandos de Monitoreo

### **Ver Progreso en Vivo (Heartbeat Log)**

```powershell
# PowerShell - últimas 10 líneas, actualización en vivo
Get-Content logs\detect_events\heartbeat_20251012.log -Tail 10 -Wait
```

```bash
# Bash/WSL - últimas 10 líneas, actualización en vivo
tail -f -n 10 logs/detect_events/heartbeat_20251012.log
```

### **Ver Batches Completados (Batch Log)**

```powershell
Get-Content logs\detect_events\batches_20251012.log -Tail 5 -Wait
```

### **Ver Log Principal (Debug Completo)**

```powershell
Get-Content logs\detect_events\detect_events_intraday_*.log -Tail 50 -Wait
```

### **Analizar Heartbeat (Pandas)**

```python
import pandas as pd

# Leer heartbeat log
df = pd.read_csv(
    "logs/detect_events/heartbeat_20251012.log",
    sep="\t",
    names=["timestamp", "symbol", "batch_num", "total_batches", "events_count", "mem_gb"]
)

# Estadísticas
print(f"Total symbols processed: {len(df)}")
print(f"Average events per symbol: {df['events_count'].diff().mean():.0f}")
print(f"Peak memory: {df['mem_gb'].max():.2f} GB")
print(f"Last symbol: {df.iloc[-1]['symbol']}")

# Progreso por batch
df.groupby("batch_num")["symbol"].count().plot(kind="bar", title="Symbols per Batch")
```

---

## 🚨 Detección de Fallos

### **Si el proceso se detiene sin aviso:**

1. **Ver última línea del heartbeat log:**
   ```powershell
   Get-Content logs\detect_events\heartbeat_20251012.log | Select-Object -Last 1
   ```

   **Output:** `2025-10-12 14:35:28.789	TSLA	5	40	12678	3.28`

   **Interpretación:** El proceso se detuvo mientras procesaba `TSLA` en el batch #5

2. **Ver último batch guardado:**
   ```powershell
   Get-Content logs\detect_events\batches_20251012.log | Select-Object -Last 1
   ```

   **Output:** `2025-10-12 14:30:15.234	4	50	4123	events_intraday_20251012_shard0004.parquet	3.15`

   **Interpretación:** El último batch completo fue #4, el batch #5 estaba en progreso

3. **Ver checkpoint:**
   ```powershell
   Get-Content logs\checkpoints\events_intraday_20251012_completed.json
   ```

   **Interpretación:** Lista de símbolos completados hasta el último checkpoint

4. **Relanzar con --resume:**
   ```powershell
   python -u scripts\processing\detect_events_intraday.py --from-file ... --resume
   ```

   **¿Qué hace?**
   - Lee checkpoint
   - Salta todos los símbolos completados
   - Continúa desde el siguiente símbolo pendiente

---

## 💡 Por Qué Esta Estructura Funciona

| Problema | Solución |
|----------|----------|
| **Windows mata proceso sin aviso** | Logger escribe directo a archivo (no stdout) |
| **No sé dónde se detuvo** | Heartbeat log (1 línea por símbolo, sin buffer) |
| **Perdí 2 horas de trabajo** | Batching + shards guardados inmediatamente |
| **No sé si el batch se guardó** | Batch log confirma cada shard |
| **No puedo monitorear sin abrir logs** | Heartbeat JSON con estado actual |
| **Resume no funciona** | Checkpoint con lista completa de símbolos |
| **Logs crecen sin control** | Rotación a 50 MB + compresión ZIP |

---

## 📊 Análisis Post-Mortem

Si el proceso falla, puedes analizar los logs para entender qué pasó:

```python
import polars as pl
from pathlib import Path

# Cargar heartbeat log
heartbeat = pl.read_csv(
    "logs/detect_events/heartbeat_20251012.log",
    separator="\t",
    has_header=False,
    new_columns=["timestamp", "symbol", "batch_num", "total_batches", "events_count", "mem_gb"]
)

# Cargar batch log
batches = pl.read_csv(
    "logs/detect_events/batches_20251012.log",
    separator="\t",
    has_header=False,
    new_columns=["timestamp", "batch_num", "symbols_count", "total_events", "shard_file", "mem_gb"]
)

# Análisis
print("="*60)
print("POST-MORTEM ANALYSIS")
print("="*60)

print(f"\nTotal symbols processed: {len(heartbeat)}")
print(f"Total batches completed: {len(batches)}")

last_heartbeat = heartbeat[-1]
print(f"\nLast symbol processed: {last_heartbeat['symbol'][0]}")
print(f"Last batch: {last_heartbeat['batch_num'][0]}/{last_heartbeat['total_batches'][0]}")
print(f"Memory at failure: {last_heartbeat['mem_gb'][0]:.2f} GB")

# ¿Cuál fue el último batch completado?
if len(batches) > 0:
    last_batch = batches[-1]
    print(f"\nLast batch saved: #{last_batch['batch_num'][0]:03d}")
    print(f"Shard file: {last_batch['shard_file'][0]}")
    print(f"Events in batch: {last_batch['total_events'][0]:,}")

# Memoria usage trend
print(f"\nMemory usage trend:")
print(f"  Min: {heartbeat['mem_gb'].min():.2f} GB")
print(f"  Max: {heartbeat['mem_gb'].max():.2f} GB")
print(f"  Avg: {heartbeat['mem_gb'].mean():.2f} GB")

# ¿Hay fuga de memoria?
mem_trend = heartbeat.select(["batch_num", "mem_gb"]).group_by("batch_num").agg(pl.col("mem_gb").max())
if mem_trend["mem_gb"].is_sorted():
    print("\n⚠️  WARNING: Memory is monotonically increasing (possible leak)")
```

---

## 🎯 Checklist Final

- ✅ Logger principal con rotación y compresión
- ✅ Heartbeat log sin buffer (TSV)
- ✅ Batch log sin buffer (TSV)
- ✅ Heartbeat JSON para monitoreo
- ✅ Checkpoint JSON para resume
- ✅ Nivel DEBUG con timestamps precisos
- ✅ Traceback completo en excepciones
- ✅ Modo append para resume seguro
- ✅ Thread-safe con `enqueue=True`
- ✅ Sin dependencia de stdout ni redirecciones

---

**Con esta estructura, NUNCA perderás información, incluso si Windows mata el proceso sin previo aviso.**
