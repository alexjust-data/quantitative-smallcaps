# Tools - Micro-Scripts para Ingesta y Backup

Herramientas para gestionar la descarga masiva de Polygon (Fase 3.2) con granularidad fina, idempotencia y auditoría.

---

## 📋 Índice de Scripts

| Script | Descripción | Uso |
|--------|-------------|-----|
| `make_manifest.py` | Genera manifest para ingesta | `python tools/make_manifest.py` |
| `launch_polygon_ingest.py` | Lanza descarga de Polygon | `python tools/launch_polygon_ingest.py` |
| `verify_ingest.py` | Verifica progreso de descarga | `python tools/verify_ingest.py` |
| `backup_snapshot.ps1` | Backup con hashes SHA256 | `powershell -File tools/backup_snapshot.ps1` |
| `watchdog_parallel.py` | Supervisor con auto-recovery | `python tools/watchdog_parallel.py` |

---

## 🚀 Orden de Ejecución

### 1. Generar Manifest

Crea el manifest (universo de símbolos + ventanas temporales) a partir del dataset MASTER dedup:

```powershell
# Full history (recomendado)
python tools\make_manifest.py

# Acotar a últimos 3 años (opcional)
$start = (Get-Date).AddYears(-3).ToUniversalTime() | % {[int]([DateTimeOffset]$_).ToUnixTimeSeconds()}
$end   = (Get-Date).ToUniversalTime()               | % {[int]([DateTimeOffset]$_).ToUnixTimeSeconds()}
python tools\make_manifest.py --start-epoch $start --end-epoch $end --output processed\events\manifest_core_3y.parquet
```

**Output:** `processed/events/manifest_core_FULL.parquet`

---

### 2. Lanzar Ingesta de Polygon

Descarga masiva de trades & quotes con resume automático:

```powershell
# Ingesta full (usa manifest_core_FULL.parquet)
python tools\launch_polygon_ingest.py

# Con parámetros custom
python tools\launch_polygon_ingest.py `
  --manifest processed\events\manifest_core_FULL.parquet `
  --rate-limit 10 `
  --quotes-hz 1

# Con fechas específicas
python tools\launch_polygon_ingest.py `
  --manifest processed\events\manifest_core_3y.parquet `
  --rate-limit 8 `
  --quotes-hz 1 `
  --extra-args "--start-date 2022-10-01 --end-date 2025-10-16"
```

**Proceso en background:** Escribe logs en `logs/polygon_ingest_YYYYMMDD_HHMMSS.log`

**Monitoreo en tiempo real:**
```powershell
# Ver últimas 50 líneas y seguir
Get-Content logs\polygon_ingest_*.log | Select-Object -Last 1 | % { Get-Content $_ -Wait -Tail 50 }
```

---

### 3. Verificar Progreso

Compara checkpoint vs archivos reales en `raw/`:

```powershell
# Verificación estándar
python tools\verify_ingest.py

# Con parámetros custom
python tools\verify_ingest.py --run-date 20251017 --sample 20
```

**Output:**
- Símbolos completados (checkpoint)
- Símbolos con raw data en disco
- Símbolos en progreso
- Distribución de archivos por símbolo
- Porcentaje de progreso global

---

### 4. Watchdog (Opcional pero Recomendado)

Supervisor que relanza automáticamente si hay crashes o estancamiento:

```powershell
# Iniciar watchdog en background
python tools\watchdog_parallel.py &

# O usar el launcher
powershell -File tools\watchdog_start.ps1
```

**Funcionalidad:**
- Detecta crashes (exit code 3221225478 y otros)
- Relanza con `--resume` (no duplica datos)
- Backoff exponencial si hay fallos repetidos
- Logs en `logs/watchdog.log`

**Parar:**
```powershell
# Crear flag de pausa
New-Item -ItemType File -Path RUN_PAUSED.flag

# O usar el script
powershell -File tools\watchdog_stop.ps1
```

---

### 5. Backup con Verificación

Snapshot reproducible con inventory + hashes SHA256:

```powershell
# Backup estándar (D:\BACKUPS_SMALLCAPS)
powershell -ExecutionPolicy Bypass -File tools\backup_snapshot.ps1

# Custom location y label
powershell -ExecutionPolicy Bypass -File tools\backup_snapshot.ps1 `
  -DestRoot "E:\Backups" `
  -Label "pre_fase32"
```

**Output:** `D:\BACKUPS_SMALLCAPS\snapshot_YYYYMMDD_HHMMSS\`

**Contenido:**
- `processed/final/` - Dataset MASTER
- `processed/events/` - Consolidados + manifests
- `raw/trades/`, `raw/quotes/` - Datos crudos de Polygon
- `logs/checkpoints/` - Checkpoints para resume
- `docs/Daily/` - Documentación completa
- `INVENTORY_YYYYMMDD_HHMMSS.csv` - Lista completa de archivos
- `HASHES_YYYYMMDD_HHMMSS.txt` - SHA256 de archivos críticos
- `README.txt` - Instrucciones de restauración

---

## 🔍 Ejemplos de Uso Completo

### Caso 1: Ingesta Full History

```powershell
# 1. Generar manifest
python tools\make_manifest.py

# 2. Lanzar ingesta
python tools\launch_polygon_ingest.py

# 3. (Opcional) Watchdog en paralelo
python tools\watchdog_parallel.py &

# 4. Monitorear progreso cada 30 min
while ($true) {
    python tools\verify_ingest.py
    Start-Sleep -Seconds 1800
}
```

### Caso 2: Ingesta de Últimos 3 Años

```powershell
# 1. Manifest acotado
$start = (Get-Date).AddYears(-3).ToUniversalTime() | % {[int]([DateTimeOffset]$_).ToUnixTimeSeconds()}
$end   = (Get-Date).ToUniversalTime()               | % {[int]([DateTimeOffset]$_).ToUnixTimeSeconds()}
python tools\make_manifest.py --start-epoch $start --end-epoch $end --output processed\events\manifest_core_3y.parquet

# 2. Ingesta con rate limit conservador
python tools\launch_polygon_ingest.py `
  --manifest processed\events\manifest_core_3y.parquet `
  --rate-limit 8

# 3. Verificar progreso
python tools\verify_ingest.py
```

### Caso 3: Backup Post-Ingesta

```powershell
# 1. Verificar ingesta completa
python tools\verify_ingest.py

# 2. Backup con timestamp
powershell -ExecutionPolicy Bypass -File tools\backup_snapshot.ps1

# 3. Verificar integridad
$backupDir = Get-ChildItem D:\BACKUPS_SMALLCAPS | Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content "$backupDir\HASHES_*.txt"
Get-FileHash "$backupDir\processed\final\events_intraday_MASTER_dedup_v2.parquet" -Algorithm SHA256
```

---

## 🛡️ Garantías de Seguridad

### Idempotencia
- **`--resume`** en todos los scripts de ingesta
- **Checkpoints granulares** previenen reprocesamiento
- **Lock files** evitan ejecuciones paralelas del mismo símbolo

### Observabilidad
- **Logs timestamped** para cada run
- **verify_ingest.py** muestra progreso real vs checkpoint
- **PID files** para tracking de procesos

### Reintentos Inteligentes
- **Watchdog** con backoff exponencial
- **Rate limiting** configurable (evita bans de API)
- **Graceful degradation** si hay símbolos problemáticos

### Auditoría
- **SHA256 hashes** de archivos críticos
- **Inventory CSV** completo
- **README** con métricas en cada snapshot

---

## 📊 Métricas Esperadas

### Tiempo de Ejecución (Estimado)

| Símbolos | Rate Limit | Tiempo Estimado |
|----------|------------|-----------------|
| 1,621 | 10s | 4-6 horas |
| 1,621 | 12s | 5-8 horas |
| 1,621 | 8s | 3-5 horas |

**Factores que afectan:**
- Disponibilidad de datos en caché de Polygon
- Volumen de datos por símbolo
- Carga de API en ese momento
- Reintentos por crashes

### Storage Esperado

| Componente | Tamaño Aprox |
|------------|--------------|
| `raw/trades/` | 8-10 GB |
| `raw/quotes/` | 1-2 GB |
| `processed/events/` | 500 MB |
| `processed/final/` | 21 MB |
| **Total** | **~10-12 GB** |

---

## 🔧 Troubleshooting

### Problema: Ingesta estancada

```powershell
# Verificar proceso
Get-Process python | Where-Object {$_.MainWindowTitle -like "*polygon*"}

# Ver log actual
Get-Content logs\polygon_ingest_*.log | Select-Object -Last 1 | % { Get-Content $_ -Tail 100 }

# Relanzar con resume (no duplica)
python tools\launch_polygon_ingest.py
```

### Problema: Símbolos sin datos

```powershell
# Verificar cuáles faltan
python tools\verify_ingest.py --sample 50

# Revisar log de errores
Get-Content logs\polygon_ingest_*.log | Select-String "ERROR"
```

### Problema: Espacio en disco

```powershell
# Ver uso actual
Get-ChildItem raw -Recurse | Measure-Object -Property Length -Sum | % {[math]::Round($_.Sum/1GB, 2)}

# Backup comprimido si es necesario
Compress-Archive -Path raw\* -DestinationPath raw_backup.zip
```

---

## 📚 Documentación de Referencia

- **Fase 2.5 Audit:** `docs/Daily/fase_4/12_fase_25_auditoria_final.md`
- **Consolidación:** `docs/Daily/fase_4/13_fase_25_consolidacion_maestra_FINAL.md`
- **Validación:** `docs/Daily/fase_4/14_validacion_final_dataset_fase_25.md`
- **Fase 3.2 Inicio:** `docs/Daily/fase_5/01_fase_32_inicio.md`

---

**Última actualización:** 2025-10-17
**Versión:** 1.0
