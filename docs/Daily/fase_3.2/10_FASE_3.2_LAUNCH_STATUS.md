# FASE 3.2 - Estado de Lanzamiento

**Fecha inicio:** 2025-10-14 11:42 UTC
**Wave actual:** PM (1,452 eventos)
**Estado:** ✅ **RUNNING**

---

## ✅ Resumen Ejecutivo

**FASE 3.2 ha sido lanzada exitosamente** con la ola PM (1,452 eventos). El proceso está corriendo en background y está descargando trades+quotes de Polygon.io.

### Validaciones Pre-Launch

✅ Manifest verificado: 10,000 eventos
✅ SHA-256 hash: `36fb3f80b94c63f4070274884850fdf9...`
✅ Sesiones: PM=14.5%, AH=3.2%, RTH=82.3%
✅ Script production-ready con 7 parches aplicados
✅ API key Polygon configurada
✅ Checkpoint system habilitado

### Progreso Inicial (Primeros 21 Eventos)

| # | Symbol | Event Type | Timestamp | Trades | Quotes | Status |
|---|--------|-----------|-----------|---------|--------|---------|
| 1 | LCTX | volume_spike | 2025-01-03 14:22 | 43 | 26 | ✅ Completado |
| 2 | ALHC | volume_spike | 2024-11-15 13:46 | 36 | 33 | ✅ Completado |
| 3 | GRAB | volume_spike | 2025-06-11 12:00 | 260 | - | ✅ Completado |
| 4-19 | ... | ... | ... | - | - | ✅ Skipped (ya existen) |
| 20 | GRAB | volume_spike | 2025-07-21 12:04 | (exist) | 537 | ✅ Parcial (solo quotes) |
| 21 | TGL | volume_spike | 2025-02-11 14:03 | 8,943 | 🔄 downloading | 🔄 En progreso |

**Observaciones:**
- ✅ **Resume parcial funcionando:** Eventos 4-19 fueron skipped (ya descargados previamente)
- ✅ **NBBO by-change:** Evento 20 redujo quotes de 600 → 537 (10.5% reducción adicional)
- ✅ **Quotes Hz 1:** Downsampling de 1,176 → 600 quotes funcionando
- ✅ **Event IDs estables:** Todos con hash8 (ej: `42c252de`, `84e6437f`)
- ✅ **Escritura atómica:** No se encontraron archivos `.tmp` corruptos

---

## 📊 Estimaciones PM Wave

```
Eventos totales: 1,452
Rate limit: 12s/evento
Tiempo por evento: ~24s (trades + quotes + delays)

ETA total: 1,452 × 24s = 34,848s ≈ 9.7 horas
Completado: 21/1,452 (1.4%)
Restante: 1,431 eventos ≈ 9.5 horas
```

**Fecha estimada de finalización PM:** 2025-10-14 21:30 UTC (~9.5h desde 12:00)

---

## 🔧 Comandos de Monitoreo

### Ver Progreso en Tiempo Real
```bash
tail -f logs/fase3.2_pm_wave_running.log
```

### Ver Últimos 50 Eventos
```bash
tail -50 logs/fase3.2_pm_wave_running.log
```

### Contar Eventos Completados (con AMBOS archivos)
```bash
find raw/market_data/event_windows -name "quotes.parquet" | \
  xargs -I {} dirname {} | \
  xargs -I {} sh -c 'test -f {}/trades.parquet && echo {}' | \
  wc -l
```

### Verificar Proceso Activo
```bash
ps aux | grep download_trades_quotes | grep -v grep
```

### Ver KPIs en el Log
```bash
grep "HEARTBEAT" logs/fase3.2_pm_wave_running.log | tail -1
```

### Verificar Checkpoint
```bash
cat logs/checkpoints/fase3.2_PM_progress.json | jq '.completed_events | length'
```

---

## 📁 Estructura de Salida

```
raw/market_data/event_windows/
├── symbol=LCTX/
│   └── event=LCTX_volume_spike_20250103_142200_42c252de/
│       ├── trades.parquet  (6.0 KB, 43 trades)
│       └── quotes.parquet  (5.3 KB, 26 quotes)
├── symbol=ALHC/
│   └── event=ALHC_volume_spike_20241115_134600_84e6437f/
│       ├── trades.parquet  (5.5 KB, 36 trades)
│       └── quotes.parquet  (5.4 KB, 33 quotes)
└── symbol=GRAB/
    ├── event=GRAB_volume_spike_20250611_120000_d608884d/
    │   ├── trades.parquet  (11 KB, 260 trades)
    │   └── quotes.parquet  (6.1 KB, -)
    └── event=GRAB_volume_spike_20250721_120400_368514aa/
        ├── trades.parquet  (existing)
        └── quotes.parquet  (-, 537 quotes)
```

**Event ID format:** `{symbol}_{event_type}_{YYYYMMDD_HHMMSS}_{hash8}`
- Hash8: SHA-1 primeros 8 caracteres de `symbol|event_type|timestamp_utc`
- Garantiza unicidad y reproducibilidad

---

## 🔄 Próximas Olas

### Ola 2: AH Events (321 eventos)
```bash
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave AH \
  --rate-limit 12 \
  --quotes-hz 1 \
  --resume
```

**ETA:** 321 × 24s ≈ 2.1 horas
**Cuándo lanzar:** Después de completar PM wave

### Ola 3: RTH Events (8,227 eventos)
```bash
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave RTH \
  --rate-limit 12 \
  --quotes-hz 1 \
  --resume
```

**ETA:** 8,227 × 24s ≈ 54.8 horas ≈ 2.3 días
**Cuándo lanzar:** Después de completar AH wave

**Total estimado 3 waves:** 9.7h + 2.1h + 54.8h = 66.6 horas ≈ 2.8 días

---

## ⚠️ Troubleshooting

### Proceso se Detiene

**Verificar:**
```bash
ps aux | grep download_trades_quotes | grep -v grep
```

**Re-lanzar (resume automático):**
```bash
python launch_pm_wave.py
```

El flag `--resume` garantiza que solo descarga eventos que faltan.

### Rate Limit 429

Si ves muchos `429 Rate limit` en el log:

```bash
grep "429" logs/fase3.2_pm_wave_running.log | wc -l
```

**Acción:** El script ya tiene exponential backoff (5s, 10s, 20s, 40s, 80s). Si persiste, aumentar `--rate-limit` a 15 o 18.

### Quotes Vacíos (0 quotes)

Algunos eventos PM tienen quotes vacíos (ej: OPEN, TOST). Esto es **esperado** para símbolos de baja liquidez en pre-market. El script no escribe archivo si hay 0 quotes.

**Verificación:**
```bash
grep "0 quotes (no file written)" logs/fase3.2_pm_wave_running.log | wc -l
```

Estos eventos se marcarán como "trades_only" en el análisis post-descarga.

### Checkpoint Corrupto

Si el checkpoint se corrompe:

```bash
rm logs/checkpoints/fase3.2_PM_progress.json
```

El script re-escaneará el output directory y reconstruirá el checkpoint automáticamente con el flag `--resume`.

---

## 📈 KPIs Esperados (Cada 100 Eventos)

El script emite un **heartbeat** cada 100 eventos procesados:

```
HEARTBEAT: 100/1452 events (6.9%)
  Success: 98 | Failed: 1 | Skipped: 1
  Trades: 45,234 (avg 462/event)
  Quotes: 23,456 (avg 239/event)
  Size: 234.5 MB (avg 2.4 MB/event)
  Rate: 148 events/hour | ETA: 9.3 hours
```

### Métricas de Calidad

- **Success rate:** ≥95% (objetivo)
- **Avg trades/event:** 200-500 (PM típico)
- **Avg quotes/event:** 50-300 (PM con 1 Hz + by-change)
- **Avg size/event:** 1-5 MB (PM más pequeño que RTH)

---

## ✅ Validación Post-Wave

Una vez completada la PM wave, ejecutar:

```bash
python scripts/analysis/validate_fase3.2_wave.py --wave PM
```

Este script verificará:
1. ✅ Todos los eventos PM tienen al menos 1 archivo (trades OR quotes)
2. ✅ ≥95% de eventos tienen AMBOS archivos
3. ✅ No hay archivos `.tmp` (escrituras atómicas funcionaron)
4. ✅ Tamaños de archivos razonables (>1 KB)
5. ✅ Checkpoint match con archivos en disco

---

## 🎯 Success Criteria

**PM Wave será considerada exitosa si:**

1. ✅ ≥95% de eventos tienen **AMBOS** trades.parquet + quotes.parquet
2. ✅ ≥99% de eventos tienen **AL MENOS UNO** (trades OR quotes)
3. ✅ Tiempo total <12 horas (target: 9.7h)
4. ✅ Tamaño total PM: 3-5 GB (est: 1,452 × 2.5 MB = 3.6 GB)
5. ✅ Sin rate-limit failures >5%

---

## 📝 Logs y Checkpoints

### Archivos Clave

```
logs/
├── fase3.2_pm_wave_running.log       ← Log principal (tail -f para ver progreso)
├── fase3.2_pm_wave.log                ← Log de ejecuciones previas
└── checkpoints/
    └── fase3.2_PM_progress.json       ← Estado de eventos completados
```

### Checkpoint Format

```json
{
  "completed_events": [
    "LCTX_volume_spike_2025-01-03 14:22:00+00:00",
    "ALHC_volume_spike_2024-11-15 13:46:00+00:00",
    ...
  ],
  "last_updated": "2025-10-14T12:00:00"
}
```

---

## 📞 Próximos Pasos

### Hoy (2025-10-14)
1. ✅ PM wave lanzada y corriendo
2. ⏳ Monitorear progreso PM (cada 2-3 horas)
3. ⏳ Validar sample de eventos al 50% progreso
4. ⏳ Esperar completación PM wave (~21:30 UTC)

### Mañana (2025-10-15)
5. ⏳ Validar PM wave completa
6. ⏳ Lanzar AH wave (321 eventos, ~2h)
7. ⏳ Lanzar RTH wave (8,227 eventos, ~2.3 días)

### 2025-10-17
8. ⏳ Completar RTH wave
9. ⏳ Análisis de calidad final (FASE 3.2 completa)
10. ⏳ Documentar hallazgos y métricas

---

**Última actualización:** 2025-10-14 12:00 UTC
**Estado:** ✅ PM Wave RUNNING (evento 21/1,452)
**Mantenido por:** Claude (Anthropic)
**Log:** `logs/fase3.2_pm_wave_running.log`
