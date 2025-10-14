# FASE 3.2: Guía de Lanzamiento y Monitoreo

**Fecha**: 2025-10-14
**Script**: [download_trades_quotes_intraday_v2.py](../../scripts/ingestion/download_trades_quotes_intraday_v2.py)
**Manifest**: [manifest_core_20251014.parquet](../../processed/events/manifest_core_20251014.parquet)

---

## 📋 PRE-REQUISITOS

### 1. Verificar Manifest Congelado + Hash

```bash
python -c "
import polars as pl
import json
import hashlib
from pathlib import Path

# Verificar manifest
manifest_file = Path('processed/events/manifest_core_20251014.parquet')
df = pl.read_parquet(manifest_file)
print(f'✓ Manifest cargado: {len(df):,} eventos')
print(f'✓ Símbolos únicos: {df[\"symbol\"].n_unique()}')

# Calcular hash SHA-256 del manifest (integridad)
with open(manifest_file, 'rb') as f:
    manifest_hash = hashlib.sha256(f.read()).hexdigest()
print(f'✓ Manifest hash (SHA-256): {manifest_hash[:16]}...')

# Verificar event_id únicos (detectar duplicados)
event_ids = [f\"{row['symbol']}_{row['event_type']}_{row['timestamp']}\" for row in df.iter_rows(named=True)]
if len(event_ids) == len(set(event_ids)):
    print(f'✓ Event IDs únicos: {len(event_ids):,} (sin duplicados)')
else:
    print(f'⚠️  WARNING: {len(event_ids) - len(set(event_ids))} event_id duplicados detectados')

# Verificar metadata
with open('processed/events/manifest_core_20251014.json') as f:
    meta = json.load(f)
print(f'✓ Manifest ID: {meta[\"manifest_id\"]}')
print(f'✓ Profile: {meta[\"profile\"]}')
print(f'✓ Config hash: {meta[\"config_hash\"]}')
print()
print('Distribución por sesión:')
for session, data in meta['session_distribution'].items():
    print(f'  {session}: {data[\"count\"]:>5,} eventos ({data[\"percentage\"]:>5.1f}%)')
"
```

**Output esperado:**
```
✓ Manifest cargado: 10,000 eventos
✓ Símbolos únicos: 1,034
✓ Manifest hash (SHA-256): a3f2c8b4e1d6f9a7...
✓ Event IDs únicos: 10,000 (sin duplicados)
✓ Manifest ID: core_20251014_084837
✓ Profile: core_v1
✓ Config hash: 14382c2d3db97410

Distribución por sesión:
  PM:   1,452 eventos ( 14.5%)
  RTH:  8,227 eventos ( 82.3%)
  AH:     321 eventos (  3.2%)
```

**IMPORTANTE:** Guarda el hash del manifest para verificar integridad durante ejecución.

### 2. Verificar API Key

```bash
echo $POLYGON_API_KEY
# O verificar en config.yaml
```

### 3. Verificar Espacio en Disco

```bash
# Necesitas ~352 GB (p90 estimate)
df -h /path/to/data
```

---

## 🚀 LANZAMIENTO - ESTRATEGIA POR OLAS

### Ola 1: PM Events (1,452 eventos) - ~6 horas

**Características:**
- Ventanas completas: [-3, +7] minutos
- Quotes: 5 Hz (alta resolución pre-market)
- Prioridad: ALTA (menor volumen, mayor spread)

**Comando:**
```bash
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave PM \
  --rate-limit 12 \
  --quotes-hz 5 \
  --resume \
  2>&1 | tee logs/fase3.2_wave1_PM.log
```

**Monitoreo:**
```bash
# En otra terminal
tail -f logs/fase3.2_wave1_PM.log | grep -E "HEARTBEAT|events/hour"
```

**Checkpoint:**
```bash
# Progreso guardado en:
logs/checkpoints/fase3.2_PM_progress.json

# Ver progreso
cat logs/checkpoints/fase3.2_PM_progress.json | jq '.completed_events | length'
```

---

### Ola 2: AH Events (321 eventos) - ~1.5 horas

**Características:**
- Ventanas completas: [-3, +7] minutos
- Quotes: 5 Hz (alta resolución after-hours)
- Prioridad: MEDIA (menor volumen que PM)

**Comando:**
```bash
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave AH \
  --rate-limit 12 \
  --quotes-hz 5 \
  --resume \
  2>&1 | tee logs/fase3.2_wave2_AH.log
```

---

### Ola 3: RTH Events (8,227 eventos) - ~41 horas (1.7 días)

**Características:**
- Ventanas completas: [-3, +7] minutos
- Quotes: 1-2 Hz OPTIMIZADO (RTH alta liquidez)
- Prioridad: BAJA (volumen masivo, menor spread)

**Comando:**
```bash
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave RTH \
  --rate-limit 12 \
  --quotes-hz 1 \
  --resume \
  2>&1 | tee logs/fase3.2_wave3_RTH.log
```

**Alternativa con 2 Hz para mayor resolución:**
```bash
# Si 1 Hz es insuficiente, probar 2 Hz
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave RTH \
  --rate-limit 12 \
  --quotes-hz 2 \
  --resume \
  2>&1 | tee logs/fase3.2_wave3_RTH_2Hz.log
```

---

## 🔧 OPCIONES AVANZADAS

### Descarga Paralela (Experimental)

**PRECAUCIÓN:** Solo si tienes rate limit suficiente

```bash
# Terminal 1: Trades
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave RTH \
  --trades-only \
  --rate-limit 12 \
  --resume &

# Terminal 2: Quotes (espera 6s offset)
sleep 6
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave RTH \
  --quotes-only \
  --rate-limit 12 \
  --quotes-hz 1 \
  --resume &
```

### Dry-Run (Test)

```bash
# Probar con 5 eventos sin descargar
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave PM \
  --limit 5 \
  --dry-run
```

### Resume (Reanudar)

```bash
# Si el proceso se interrumpe, simplemente ejecuta de nuevo con --resume
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave RTH \
  --resume
```

El script detectará automáticamente los eventos ya descargados y los saltará.

---

## 📊 MONITOREO EN TIEMPO REAL

### 1. Heartbeat Logs

El script imprime un heartbeat cada 100 eventos:

```
================================================================================
HEARTBEAT: 500/8227 events (6.1%)
  Success: 495 | Failed: 3 | Skipped: 2
  Trades: 1,245,890 (avg 2,517/event)
  Quotes: 3,890,120 (avg 7,859/event)
  Size: 18.5 GB (avg 37.4 MB/event)
  Rate: 245.3 events/hour | ETA: 31.5 hours (1.3 days)
================================================================================
```

### 2. Monitorear Checkpoints

```bash
watch -n 60 'cat logs/checkpoints/fase3.2_RTH_progress.json | jq ".completed_events | length"'
```

### 3. Monitorear Storage

```bash
watch -n 300 'du -sh raw/market_data/event_windows/'
```

### 4. Monitorear Logs en Vivo

**Unix/Linux/macOS:**
```bash
# Ver últimas líneas
tail -f logs/fase3.2_wave3_RTH.log

# Filtrar errores + warnings + throttling
tail -f logs/fase3.2_wave3_RTH.log | grep -E "ERROR|429|timeout|FAILED|WARNING"

# Filtrar heartbeats
tail -f logs/fase3.2_wave3_RTH.log | grep HEARTBEAT
```

**PowerShell (Windows):**
```powershell
# Ver últimas líneas
Get-Content -Wait logs\fase3.2_wave3_RTH.log -Tail 50

# Filtrar errores
Get-Content -Wait logs\fase3.2_wave3_RTH.log | Select-String -Pattern "ERROR|429|timeout|FAILED"

# Filtrar heartbeats
Get-Content -Wait logs\fase3.2_wave3_RTH.log | Select-String -Pattern "HEARTBEAT"
```

---

## 🚨 TROUBLESHOOTING

### Issue 1: 429 Rate Limit Exceeded

**Síntomas:**
```
WARNING: 429 Rate limit, retrying in 5s (attempt 1/3)
```

**Solución:**
```bash
# Aumentar rate limit de 12s a 15s
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest ... \
  --rate-limit 15 \
  --resume
```

### Issue 2: Proceso Interrumpido (Ctrl+C, crash, etc.)

**Solución:**
```bash
# Simplemente re-ejecutar con --resume
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave RTH \
  --resume
```

El checkpoint automáticamente saltará eventos ya completados.

### Issue 3: Storage Lleno

**Síntomas:**
```
ERROR: No space left on device
```

**Solución:**
```bash
# Opción A: Liberar espacio y reanudar
rm -rf path/to/temp/files
python scripts/ingestion/download_trades_quotes_intraday_v2.py --resume

# Opción B: Cambiar output directory
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest ... \
  --output-dir /path/to/larger/disk \
  --resume
```

### Issue 4: Event Download Failed

**Síntomas:**
```
ERROR: TSLA: Failed to download trades after retries
```

**Solución:**
- El script automáticamente marca el evento como fallido y continúa
- Al final revisa el summary para ver cuántos fallaron
- Si success rate >95%, está OK
- Si success rate <95%, investigar causas específicas

### Issue 5: Quotes Demasiado Grandes (RTH)

**Síntomas:**
```
WARNING: TSLA_volume_spike_...: Size 75.2 MB exceeds budget 50 MB
```

**Solución: Degradación automática de Hz**
```bash
# Si p90 MB/event > 40 MB, bajar de 2 Hz → 1 Hz
python scripts/ingestion/download_trades_quotes_intraday_v2.py \
  --manifest processed/events/manifest_core_20251014.parquet \
  --wave RTH \
  --quotes-hz 1 \
  --resume
```

**Política de budget cut (si aún excede):**
1. Priorizar **trades completos** (nunca recortar)
2. Recortar **quotes** por ventana:
   - Pre-event ([-3, 0] min): Mantener 100% (crítico)
   - Post-event ([0, +7] min): Downsample a 0.5 Hz si necesario

---

### Issue 6: Session Imbalance (PM/AH Fallos)

**Síntomas:**
```
HEARTBEAT: PM events → Success rate 88% (< 95% target)
Session distribution: PM=12.1% (target 14.5% ±2%)
```

**Causa:** Fallos en descarga PM/AH desbalancean distribución final.

**Solución: Priorizar backlog PM/AH**

1. **Pausar RTH wave:**
   ```bash
   # Detener proceso RTH (Ctrl+C)
   ```

2. **Re-ejecutar SOLO PM fallidos:**
   ```bash
   # El checkpoint automáticamente salta completados
   python scripts/ingestion/download_trades_quotes_intraday_v2.py \
     --manifest processed/events/manifest_core_20251014.parquet \
     --wave PM \
     --rate-limit 15 \
     --resume
   ```

3. **Verificar nueva distribución:**
   ```bash
   python -c "
   from pathlib import Path
   from collections import Counter

   output_dir = Path('raw/market_data/event_windows')
   sessions = []
   for event_dir in output_dir.rglob('event=*'):
       if '_PM_' in event_dir.name:
           sessions.append('PM')
       elif '_AH_' in event_dir.name:
           sessions.append('AH')
       else:
           sessions.append('RTH')

   counts = Counter(sessions)
   total = sum(counts.values())
   for session in ['PM', 'RTH', 'AH']:
       pct = counts[session] / total * 100
       print(f'{session}: {counts[session]:>6,} ({pct:>5.1f}%)')
   "
   ```

4. **Si PM ahora en rango ([12.5%, 16.5%]), reanudar RTH:**
   ```bash
   python scripts/ingestion/download_trades_quotes_intraday_v2.py \
     --manifest processed/events/manifest_core_20251014.parquet \
     --wave RTH \
     --resume
   ```

**Tolerancias dinámicas:**
- PM: 14.5% ±2pp → [12.5%, 16.5%] OK
- RTH: 82.3% ±2pp → [80.3%, 84.3%] OK
- AH: 3.2% ±1pp → [2.2%, 4.2%] OK

---

## 📈 KPIs A MONITOREAR

**CRÍTICO:** Todas las timestamps en logs y metadata son **UTC**. Las sesiones (PM/RTH/AH) ya vienen clasificadas en el manifest (no recalcular).

### KPI 1: Success Rate (BOTH = trades + quotes)
**Target:** >95% eventos con ambos archivos completos

```bash
# Ver en FINAL SUMMARY
grep "FINAL SUMMARY" -A 15 logs/fase3.2_wave3_RTH.log
```

**Desglose esperado:**
- `Success (both): 9,500+ / 10,000` → >95% ✓
- `Failed: <500`
- `Skipped: 0` (en primera ejecución)

### KPI 2: Retry Rate (429 + timeouts)
**Target:** <2%

```bash
# Contar 429s
grep "429 Rate limit" logs/fase3.2_wave3_RTH.log | wc -l

# Contar timeouts
grep -i timeout logs/fase3.2_wave3_RTH.log | wc -l

# Calcular retry rate
python -c "
retries = $(grep '429 Rate limit\|timeout' logs/fase3.2_wave3_RTH.log | wc -l)
total_requests = 10000 * 2  # trades + quotes
retry_rate = (retries / total_requests) * 100
print(f'Retry rate: {retry_rate:.2f}%')
if retry_rate < 2.0:
    print('✓ < 2% target')
else:
    print('✗ >= 2% → aumentar rate-limit')
"
```

### KPI 3: Session Distribution (eventos completos)
**Target:** PM=14.5% ±2%, RTH=82.3% ±2%, AH=3.2% ±1%

**Usar script de validación completa (sección "Validación Post-Descarga")**

### KPI 4: Size per Event (p50/p90)
**Target p90:** <40 MB/event

```bash
# Ver en heartbeat logs (promedio móvil)
grep "avg.*MB/event" logs/fase3.2_wave3_RTH.log | tail -10

# Calcular p50/p90 final
python -c "
from pathlib import Path
import statistics

sizes_mb = []
output_dir = Path('raw/market_data/event_windows')
for event_dir in output_dir.rglob('event=*'):
    trades_file = event_dir / 'trades.parquet'
    quotes_file = event_dir / 'quotes.parquet'
    if trades_file.exists() and quotes_file.exists():
        size_mb = (trades_file.stat().st_size + quotes_file.stat().st_size) / 1024 / 1024
        sizes_mb.append(size_mb)

if sizes_mb:
    p50 = statistics.quantiles(sizes_mb, n=100)[49]
    p90 = statistics.quantiles(sizes_mb, n=100)[89]
    print(f'Size p50: {p50:.1f} MB')
    print(f'Size p90: {p90:.1f} MB')
    if p90 < 40:
        print('✓ p90 < 40 MB target')
    else:
        print(f'⚠️  p90 excede target por {p90-40:.1f} MB')
"
```

### KPI 5: Download Rate
**Target:** >200 events/hour

```bash
# Ver en heartbeat logs (últimos 5 heartbeats)
grep "events/hour" logs/fase3.2_wave3_RTH.log | tail -5
```

**Ejemplo output esperado:**
```
Rate: 245.3 events/hour | ETA: 31.5 hours (1.3 days)
Rate: 238.1 events/hour | ETA: 29.2 hours (1.2 days)
Rate: 251.7 events/hour | ETA: 27.8 hours (1.2 days)
```

---

## ✅ VALIDACIÓN POST-DESCARGA

### 1. Verificar Completitud (Eventos COMPLETOS = Trades + Quotes)

**CRÍTICO:** Un evento solo cuenta como exitoso si tiene AMBOS archivos (trades.parquet Y quotes.parquet) no vacíos.

```bash
# Unix/Linux/macOS
python -c "
import polars as pl
from pathlib import Path
from collections import defaultdict

# Cargar manifest
df_manifest = pl.read_parquet('processed/events/manifest_core_20251014.parquet')
print(f'Manifest: {len(df_manifest):,} eventos')
print()

# Analizar eventos descargados
output_dir = Path('raw/market_data/event_windows')
events_complete = 0
events_trades_only = 0
events_quotes_only = 0
events_missing = 0

# Stats por sesión
by_session = defaultdict(lambda: {'complete': 0, 'incomplete': 0, 'size_mb': 0.0})

for event_dir in output_dir.rglob('event=*'):
    trades_file = event_dir / 'trades.parquet'
    quotes_file = event_dir / 'quotes.parquet'

    has_trades = trades_file.exists() and trades_file.stat().st_size > 0
    has_quotes = quotes_file.exists() and quotes_file.stat().st_size > 0

    if has_trades and has_quotes:
        events_complete += 1
        # Detectar sesión del nombre del evento
        session = 'RTH'  # Default
        if '_PM_' in event_dir.name or event_dir.name.startswith('PM'):
            session = 'PM'
        elif '_AH_' in event_dir.name or event_dir.name.startswith('AH'):
            session = 'AH'

        by_session[session]['complete'] += 1
        size_mb = (trades_file.stat().st_size + quotes_file.stat().st_size) / 1024 / 1024
        by_session[session]['size_mb'] += size_mb
    elif has_trades and not has_quotes:
        events_trades_only += 1
    elif has_quotes and not has_trades:
        events_quotes_only += 1
    else:
        events_missing += 1

events_incomplete = events_trades_only + events_quotes_only

print('='*80)
print('EVENTOS COMPLETOS (ambos: trades + quotes)')
print('='*80)
print(f'Completos:         {events_complete:>6,} / {len(df_manifest):,} ({events_complete/len(df_manifest)*100:>5.1f}%)')
print(f'Solo trades:       {events_trades_only:>6,}')
print(f'Solo quotes:       {events_quotes_only:>6,}')
print(f'Incompletos total: {events_incomplete:>6,} ({events_incomplete/len(df_manifest)*100:>5.1f}%)')
print(f'Missing:           {events_missing:>6,}')
print()

print('Por sesión (solo completos):')
for session in ['PM', 'RTH', 'AH']:
    data = by_session[session]
    count = data['complete']
    size_mb = data['size_mb']
    avg_mb = size_mb / count if count > 0 else 0
    print(f'  {session:6s}: {count:>6,} eventos | {size_mb:>8.1f} MB total | {avg_mb:>5.1f} MB/evento (avg)')

print()
print('VEREDICTO:')
if events_complete / len(df_manifest) >= 0.95:
    print('  ✓ SUCCESS RATE >= 95% → GO')
else:
    print('  ✗ SUCCESS RATE < 95% → REVISAR')
"
```

**PowerShell (Windows):**
```powershell
python -c \"
import polars as pl
from pathlib import Path
from collections import defaultdict

# [mismo código que arriba, escapar comillas dobles]
\"
```

### 2. Verificar Sample de Eventos

```python
import polars as pl
from pathlib import Path

# Pick random event
output_dir = Path('raw/market_data/event_windows')
trades_file = list(output_dir.rglob('trades.parquet'))[0]
quotes_file = trades_file.parent / 'quotes.parquet'

# Load and inspect
df_trades = pl.read_parquet(trades_file)
df_quotes = pl.read_parquet(quotes_file)

print(f"Event: {trades_file.parent.name}")
print(f"Trades: {len(df_trades):,} rows")
print(f"Quotes: {len(df_quotes):,} rows")
print(f"\nTrades schema:")
print(df_trades.head())
print(f"\nQuotes schema:")
print(df_quotes.head())
```

### 3. Verificar Storage Total

```bash
du -sh raw/market_data/event_windows/
# Esperado: ~114 GB (p50) a ~352 GB (p90)
```

---

## 📝 TIMELINE ESPERADO

### Resumen por Ola

| Ola | Eventos | Quotes Hz | ETA (p90) | Storage (p90) |
|-----|---------|-----------|-----------|---------------|
| **Wave 1: PM** | 1,452 | 5 Hz | 6 horas | ~51 GB |
| **Wave 2: AH** | 321 | 5 Hz | 1.5 horas | ~11 GB |
| **Wave 3: RTH** | 8,227 | 1-2 Hz | 41 horas | ~290 GB |
| **TOTAL** | 10,000 | - | ~48.5 horas (~2 días) | ~352 GB |

### Ejecución Secuencial

```
Día 1:
  09:00 - 15:00: PM wave (6h)
  15:00 - 16:30: AH wave (1.5h)
  16:30 - 23:00: RTH wave parcial (6.5h, ~1,310 eventos)

Día 2:
  00:00 - 24:00: RTH wave parcial (24h, ~4,900 eventos)

Día 3:
  00:00 - 10:30: RTH wave final (10.5h, ~2,017 eventos)
  10:30: COMPLETADO
```

### Ejecución Paralela (Experimental)

```
Día 1:
  09:00 - 15:00: PM wave
  15:00 - 16:30: AH wave
  16:30 →       RTH trades (paralelo)

Día 2:
  → 16:30:      RTH quotes (paralelo con offset)
  COMPLETADO en ~24h con workers coordinados
```

---

## 🎯 CHECKLIST FINAL

Antes de considerar FASE 3.2 completa:

- [ ] **Ola 1 (PM):** 1,452/1,452 eventos descargados (100%)
- [ ] **Ola 2 (AH):** 321/321 eventos descargados (100%)
- [ ] **Ola 3 (RTH):** 8,227/8,227 eventos descargados (100%)
- [ ] **Success rate:** >95% eventos completos (trades + quotes)
- [ ] **Session balance:** PM=14.5% ±2%, RTH=82.3% ±2%, AH=3.2% ±1%
- [ ] **Storage total:** 114-352 GB (dentro de rango estimado)
- [ ] **429 rate:** <0.5% de requests
- [ ] **Sample validation:** 50-100 eventos verificados manualmente
- [ ] **Logs archivados:** fase3.2_wave*.log guardados
- [ ] **Checkpoints archivados:** fase3.2_*_progress.json guardados

---

## 📞 SIGUIENTE: Análisis de Microestructura

Una vez completada la descarga:

1. **Análisis de calidad:** Validar spread, depth, trade imbalance
2. **Estadísticas por sesión:** PM vs RTH vs AH
3. **Outliers:** Identificar eventos con microestructura anómala
4. **Features engineering:** Extraer features para ML
5. **Documentación:** FASE 3.3 - Análisis de Tape Reading

---

**Documento creado**: 2025-10-14
**Autor**: Claude (Anthropic)
**Versión**: 1.0
**Status**: Ready for execution
