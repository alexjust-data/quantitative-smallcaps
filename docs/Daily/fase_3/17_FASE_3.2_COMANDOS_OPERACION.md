# FASE 3.2: Comandos de Operación - Descarga Trades/Quotes (CORE/PLUS/PREMIUM)

**Fecha**: 2025-10-12
**Estado**: ✅ READY TO RUN

---

## 📋 Resumen del Sistema

Tenemos implementado un sistema completo de descarga inteligente de trades/quotes con 3 perfiles:

- **CORE**: 10K eventos, ventanas cortas [-3,+7] min, NBBO 5Hz → ~30GB, 1-2 días
- **PLUS**: 20K eventos, ventanas [-5,+15] min, NBBO 20Hz → ~100GB, 5-7 días
- **PREMIUM**: 50K eventos, ventanas [-10,+20] min, NBBO 50Hz → ~300GB, 15-20 días

El perfil activo se controla en `config/config.yaml` → `processing.profiles.active_profile`

**Actualmente configurado**: `CORE` (por defecto)

---

## 🚀 Flujo de Operación (3 Pasos)

### **PASO 1: Generar Manifest de Eventos**

El manifest selecciona los mejores eventos según el perfil activo (diversity, time buckets, liquidity).

```bash
# Dry-run: ver cuántos eventos entran
python scripts/processing/build_intraday_manifest.py --summary-only

# Generar manifest real (guardado en processed/events/events_intraday_manifest.parquet)
python scripts/processing/build_intraday_manifest.py
```

**Output esperado (CORE)**:
- ✅ 12 eventos seleccionados (de 64 detectados)
- ✅ 5 símbolos (max 3 eventos por símbolo, 1 por día)
- ✅ Filtros aplicados: score >= 0.6, liquidity >= $100K bar, spread <= 5%
- ✅ Time bucket coverage: opening, mid-day, power hour

---

### **PASO 2: Descargar TRADES**

```bash
# Descargar trades para los eventos del manifest
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --trades-only \
  --resume

# Monitorear progreso (otra terminal)
tail -f logs/ingestion/polygon_ingestion.log
```

**Output esperado (12 eventos CORE)**:
- ✅ Ventanas: [-3, +7] minutos = 10 min por evento
- ✅ Rate limit: 5 req/min (12 sec/request)
- ✅ Tiempo estimado: ~2-5 minutos para 12 eventos
- ✅ Storage: ~10-50 MB trades (depende de liquidez)

**Salida**: `raw/market_data/event_windows/{symbol}/{date}_{time}_trades.parquet`

---

### **PASO 3: Descargar QUOTES (NBBO Light)**

```bash
# Descargar quotes con downsampling CORE (5Hz, by-change-only)
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --quotes-only \
  --resume
```

**Output esperado (12 eventos CORE)**:
- ✅ NBBO downsampled: by-change-only + max 5Hz
- ✅ Storage saving: 3-10x vs full NBBO
- ✅ Tiempo estimado: ~5-10 minutos para 12 eventos
- ✅ Storage: ~30-100 MB quotes

**Salida**: `raw/market_data/event_windows/{symbol}/{date}_{time}_quotes.parquet`

---

## 🔍 Validación Post-Descarga

### Verificar cobertura

```bash
# Ver estadísticas de descarga
python scripts/ingestion/check_download_status.py --event-windows

# Ver talla total
# Windows (PowerShell):
(Get-ChildItem raw/market_data/event_windows -Recurse | Measure-Object -Sum Length).Sum / 1MB

# Linux/Mac:
du -sh raw/market_data/event_windows
```

### Inspeccionar un evento específico

```python
import polars as pl
from pathlib import Path

# Leer trades de un evento
trades = pl.read_parquet("raw/market_data/event_windows/QUBT/20251008_133000_trades.parquet")
print(f"Trades: {len(trades):,}")
print(trades.head())

# Leer quotes
quotes = pl.read_parquet("raw/market_data/event_windows/QUBT/20251008_133000_quotes.parquet")
print(f"\nQuotes: {len(quotes):,}")
print(quotes.head())
```

---

## ⚙️ Cambiar de Perfil (CORE → PLUS → PREMIUM)

### 1. Editar config.yaml

```yaml
# config/config.yaml línea 411
profiles:
  active_profile: "plus"    # ← cambiar aquí: core | plus | premium
```

### 2. Regenerar manifest

```bash
# El manifest ahora usará configuración PLUS (20K eventos, ventanas más largas)
python scripts/processing/build_intraday_manifest.py
```

### 3. Descargar con nueva configuración

```bash
# Trades (ventanas más largas, más eventos)
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --trades-only \
  --resume

# Quotes (NBBO 20Hz en vez de 5Hz)
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --quotes-only \
  --resume
```

---

## 🔧 Troubleshooting

### Error 429 (Rate Limit Exceeded)

Aumentar delay en `config.yaml`:

```yaml
polygon:
  rate_limit_delay_seconds: 15  # subir de 12 a 15
```

### Errores 5xx (Server Errors)

El script reintenta automáticamente. Si persisten:

```bash
# Relanzar con --resume (salta ventanas ya descargadas)
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --trades-only \
  --resume
```

### Espacio en disco insuficiente

Pausar descarga de quotes, completar trades primero:

```bash
# 1. Completar trades (más ligeros)
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --trades-only

# 2. Limpiar espacio si hace falta

# 3. Añadir quotes
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --quotes-only
```

### Ver eventos descargados vs pendientes

```bash
# Contar carpetas de eventos
# Windows (PowerShell):
(Get-ChildItem raw/market_data/event_windows -Directory -Recurse).Count

# Linux/Mac:
find raw/market_data/event_windows -type d | wc -l
```

---

## 📊 Métricas Esperadas por Perfil

### CORE (activo ahora)
- **Eventos**: 12 (test), 10K (producción)
- **Ventanas**: [-3, +7] min = 10 min
- **NBBO**: 5Hz, by-change-only
- **Storage**: ~30GB (10K eventos full)
- **Tiempo**: 1-2 días descarga (10K eventos)

### PLUS
- **Eventos**: 20K
- **Ventanas**: [-5, +15] min = 20 min
- **NBBO**: 20Hz
- **Storage**: ~100GB
- **Tiempo**: 5-7 días descarga

### PREMIUM
- **Eventos**: 50K
- **Ventanas**: [-10, +20] min = 30 min
- **NBBO**: 50Hz (full microstructure)
- **Storage**: ~300GB
- **Tiempo**: 15-20 días descarga

---

## 📁 Estructura de Salida

```
raw/market_data/event_windows/
├── QUBT/
│   ├── 20251008_133000_trades.parquet    # [-3min, +7min] trades
│   ├── 20251008_133000_quotes.parquet    # NBBO downsampled 5Hz
│   ├── 20251009_104500_trades.parquet
│   └── 20251009_104500_quotes.parquet
├── SOUN/
│   ├── 20251003_135000_trades.parquet
│   └── 20251003_135000_quotes.parquet
└── ...
```

**Naming convention**: `{date}_{time}_{type}.parquet`
- `date`: YYYYMMDD del evento
- `time`: HHMMSS del timestamp del evento (UTC)
- `type`: trades | quotes

---

## ✅ Next Steps (después de descargar CORE)

1. **Validar calidad**: Check coverage, timestamps, no missing data
2. **Feature engineering**: Calcular microstructure features (tape speed, NBBO spread, order flow)
3. **Labeling**: Triple barrier on trades data
4. **Model training**: Train on CORE dataset first
5. **Escalar a PLUS**: Solo para cohortes ganadoras (winning event types/symbols)

---

## 🎯 Comandos Copy-Paste (CORE Test - 12 eventos)

```bash
# 1. Generar manifest
python scripts/processing/build_intraday_manifest.py

# 2. Descargar trades
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --trades-only \
  --resume

# 3. Descargar quotes
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/events_intraday_manifest.parquet \
  --quotes-only \
  --resume

# 4. Validar
python scripts/ingestion/check_download_status.py --event-windows
```

**Tiempo total esperado**: ~10-15 minutos para 12 eventos
**Storage esperado**: ~50-150 MB

---

## 📝 Notas Importantes

- El script `download_trades_quotes_intraday.py` está **production-ready** (8 fixes aplicados en FASE 3.2)
- `--resume` permite reanudar descargas interrumpidas sin repetir requests
- Rate limit respetado automáticamente (12 sec/request default)
- Compression: zstd (mejor ratio que gzip/snappy)
- Timestamps: UTC (convertidos de ET automáticamente)
- Session pooling: 1 session HTTP reutilizada (más eficiente)

---

**Estado actual**: ✅ Sistema completo implementado y testeado con 12 eventos
**Listo para**: Ejecutar PASO 1-2-3 en cualquier momento
