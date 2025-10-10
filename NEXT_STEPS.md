# 📋 Próximos Pasos - Pipeline de Datos

## Estado Actual (2025-10-08 21:19)

**Week 1 - Foundation:** 🔄 **34.5% completo**

| Dataset | Progreso | Archivos | Storage | Estado |
|---------|----------|----------|---------|--------|
| Daily bars (1d) | ✅ 100% | 5,227 | 48.8 MB | **Completo** |
| Hourly bars (1h) | 🔄 34.5% | 1,729 / 5,005 | 12.1 MB | **En progreso** |
| **Restante** | - | **3,276** | ~18 MB | ~33 horas |

**Último archivo:** `FDUS.parquet` (21:19:46)

---

## Siguiente Paso Automático

### Opción 1: Monitoreo Automático (Recomendado)

Este script **monitorea** Week 1 y lanza automáticamente los siguientes pasos cuando complete:

```bash
# En terminal separada (mantener abierta)
python scripts/ingestion/auto_continue_after_week1.py --top-n 2000 --events-preset compact --auto-start-week23
```

**Qué hace:**
1. ✅ Monitorea cada 5 minutos el progreso de Week 1
2. ✅ Cuando Week 1 llega a 95%+ ejecuta automáticamente:
   - `detect_events.py --use-percentiles`
   - `rank_by_event_count.py --top-n 2000`
   - `download_all.py --weeks 2 3` (Top-2000 + event windows)

**Parámetros opcionales:**
```bash
# Sin auto-start (solo detect + rank, no download Week 2-3)
python scripts/ingestion/auto_continue_after_week1.py --top-n 2000 --events-preset compact

# Intervalo de chequeo personalizado (default: 300s = 5min)
python scripts/ingestion/auto_continue_after_week1.py --check-interval 600

# Top-1000 en lugar de Top-2000
python scripts/ingestion/auto_continue_after_week1.py --top-n 1000 --events-preset compact --auto-start-week23
```

### Opción 2: Manual (Paso a Paso)

#### Paso 1: Verificar que Week 1 completó

```bash
python scripts/ingestion/check_download_status.py
```

Busca: `Week 1 Status: ✅ COMPLETE`

#### Paso 2: Detectar eventos

```bash
python scripts/processing/detect_events.py --use-percentiles
```

**Output:** `processed/events/events_daily_YYYYMMDD.parquet`

**Tiempo estimado:** 5-10 minutos

#### Paso 3: Rankear por eventos

```bash
python scripts/processing/rank_by_event_count.py --top-n 2000
```

**Output:** `processed/rankings/top_2000_by_events_YYYYMMDD.parquet`

**Tiempo estimado:** 1-2 minutos

#### Paso 4: Descargar Week 2-3 (Top-2000 + Event Windows)

```bash
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 2000 --events-preset compact
```

**Tiempo estimado:** 3-4 días (Top-2000: 48-72h + Event windows: 24-48h)

---

## Verificar Progreso en Cualquier Momento

```bash
# Status completo con colores y emojis
python scripts/ingestion/check_download_status.py

# Versión verbose con más detalles
python scripts/ingestion/check_download_status.py --verbose
```

---

## Timeline Completo Estimado

| Fase | Tiempo | Storage | Estado Actual |
|------|--------|---------|---------------|
| **Week 1** (1d + 1h) | 10-15h | ~110 MB | 🔄 34% (1d ✅, 1h 🔄) |
| **Detect Events** | 5-10m | ~10 MB | ⏳ Pendiente |
| **Rank Top-2000** | 1-2m | ~1 MB | ⏳ Pendiente |
| **Week 2-3 Top-2000** (1m full) | 48-72h | ~3.4 GB | ⏳ Pendiente |
| **Week 2-3 Rest** (event windows) | 24-48h | ~40-50 GB | ⏳ Pendiente |
| **Week 4** (Short data) | 2-4h | ~50 MB | ⏳ Pendiente |
| **TOTAL** | **5-7 días** | **~45-55 GB** | - |

---

## Configuración de Event Windows

Actualmente usando preset **"compact"** definido en `config/config.yaml`:

```yaml
events_windows:
  preset: "compact"
  compact:
    d_minus_2: [["09:30","16:00"]]               # D-2: market hours
    d_minus_1: [["09:30","10:30"], ["14:00","16:00"]]  # D-1: open + close
    d:         [["07:00","16:00"]]               # D: premarket + market
    d_plus_1:  [["09:30","12:30"]]               # D+1: morning session
    d_plus_2:  [["09:30","12:30"]]               # D+2: morning session
```

Para cambiar a **"extended"** (más storage pero más datos):

```bash
python scripts/ingestion/auto_continue_after_week1.py --events-preset extended --auto-start-week23
```

---

## Logs y Debugging

### Ver logs en tiempo real

```bash
# Windows
Get-Content logs\download_all.log -Wait -Tail 50

# Linux/Mac
tail -f logs/download_all.log
```

### Tickers fallidos

Los tickers que fallen se guardan en:

```
logs/
├── failed_week1_daily_YYYYMMDD.txt       # Fallidos en daily bars
├── failed_week1_hourly_YYYYMMDD.txt      # Fallidos en hourly bars
├── failed_topN_1m_YYYYMMDD.txt           # Fallidos en Top-N minute bars
```

Para reintentar fallidos:

```bash
python scripts/ingestion/download_all.py --retry-failed
```

---

## FAQ

### ¿Puedo pausar y reanudar?

✅ Sí. Todos los scripts tienen **resume capability**. Si interrumpes:

```bash
# Continúa donde quedó (skippea archivos ya descargados)
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 2000 --events-preset compact
```

### ¿Cómo cambio el Top-N?

Usa `--top-n` en cualquier script:

```bash
# Top-500 en lugar de Top-2000
python scripts/ingestion/auto_continue_after_week1.py --top-n 500 --auto-start-week23

# Top-1000
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 1000 --events-preset compact
```

### ¿Qué pasa si veo errores 429 (rate limiting)?

1. El script tiene sleeps automáticos (`time.sleep(0.25)`)
2. Si persisten, aumenta el sleep en `download_all.py`:
   - Busca `time.sleep(0.25)` → cambia a `time.sleep(0.35)` o `0.5`
3. No ejecutes múltiples descargas en paralelo
4. Verifica tu plan de Polygon.io

### ¿Puedo testear con un subset pequeño?

✅ Sí:

```bash
# Solo 100 símbolos para event windows (testing)
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 100 --max-rest-symbols 50

# Solo tickers que empiezan con A, B
python scripts/ingestion/download_all.py --weeks 2 3 --letters A B --top-n 50
```

### ¿Cómo reviso si los datos están bien?

Después de descargar:

```bash
# Status general
python scripts/ingestion/check_download_status.py

# Validación de completitud (TODO: crear este script)
python scripts/validation/check_completeness.py

# Ver eventos detectados
python scripts/processing/generate_event_report.py
```

---

## Recursos

- [Pipeline Completo](scripts/ingestion/README_ORCHESTRATOR.md) - Documentación del orquestador
- [Event Detection](scripts/processing/README.md) - Triple-gate logic y ranking
- [Config Reference](config/config.yaml) - Todas las configuraciones

---

**Última actualización:** 2025-10-08 21:20
**Próxima acción recomendada:** Ejecutar `auto_continue_after_week1.py` en terminal separada
