# Plan de Ejecución - Descargas Optimizadas

**Fecha**: 2025-10-10
**Fase**: Phase 2.1 - Data Ingestion
**Objetivo**: Dataset histórico robusto con dual pricing y universo completo

---

## ✅ CONFIGURACIÓN FINAL CONFIRMADA

### **Storage Strategy Optimizada**

```yaml
1d (daily, 5 años):
  - raw/market_data/bars/1d/          ← adjusted (análisis técnico)
  - raw/market_data/bars/1d_raw/      ← raw (filtros precio/cap)

1h (hourly, 5 años):
  - raw/market_data/bars/1h/          ← adjusted (análisis técnico)
  - raw/market_data/bars/1h_raw/      ← raw (filtros precio/cap)

1m (minutely, 3 años, Top-2000):
  - raw/market_data/bars/1m/          ← adjusted ONLY
  - Reconstruible con splits de raw/corporate_actions/splits_*.parquet

Universo:
  - 11,453 tickers total
    - 5,228 activos
    - 6,225 delisted (elimina survivorship bias)
```

### **Volumen Estimado**: ~152 GB (28% ahorro vs dual completo)

**Optimización clave**: 1m solo adjusted (vs dual en todo) ahorra ~85 GB sin perder capacidad de reconstrucción con split factors.

---

## 📋 CHECKLIST PRE-LAUNCH

**Completar ANTES de empezar**:

```bash
# 1. Verificar API key
echo $POLYGON_API_KEY
# ✅ Debe mostrar tu clave, NO vacío

# 2. Verificar espacio en disco
df -h d:
# ✅ Necesitas ≥ 200 GB libres

# 3. Verificar que NO hay procesos Python corriendo
tasklist | findstr python.exe
# ✅ Debe estar VACÍO

# 4. Backup config actual
cp config/config.yaml config/config.yaml.backup_$(date +%Y%m%d)

# 5. Crear directorio de logs de esta sesión
mkdir -p logs/download_$(date +%Y%m%d)
```

---

## 🚀 ORDEN DE EJECUCIÓN

### **Paso 1: Limpieza Opcional** (si empiezas desde cero)

```bash
# ⚠️ ADVERTENCIA: Esto BORRA descargas previas
cd d:/04_TRADING_SMALLCAPS

# Opción A: Limpiar TODO (re-descarga completa)
rm -rf raw/market_data/bars/

# Opción B: Limpiar solo lo que cambió (deja tickers/splits)
rm -rf raw/market_data/bars/1d/
rm -rf raw/market_data/bars/1d_raw/
rm -rf raw/market_data/bars/1h/
rm -rf raw/market_data/bars/1h_raw/
rm -rf raw/market_data/bars/1m/

# Mantener (NO borrar):
# - raw/reference/tickers_*.parquet
# - raw/corporate_actions/splits_*.parquet
```

---

### **Paso 2: Lanzar Week 1** (Universo + Daily + Hourly dual)

```bash
cd d:/04_TRADING_SMALLCAPS

# Lanzar Week 1 con logging
python scripts/ingestion/download_all.py --weeks 1 \
  2>&1 | tee logs/download_$(date +%Y%m%d)/week1_$(date +%H%M%S).log &

# Obtener PID para monitoreo
echo $! > logs/download_$(date +%Y%m%d)/week1.pid
```

**Tiempo estimado**: 24-36 horas

**Output esperado**:
- `raw/reference/tickers_active_*.parquet` (11,832 tickers)
- `raw/reference/tickers_delisted_*.parquet` (22,491 tickers)
- `raw/corporate_actions/splits_*.parquet` (26,611 splits)
- `raw/market_data/bars/1d/` (11,453 símbolos, adjusted)
- `raw/market_data/bars/1d_raw/` (11,453 símbolos, raw)
- `raw/market_data/bars/1h/` (11,453 símbolos, adjusted)
- `raw/market_data/bars/1h_raw/` (11,453 símbolos, raw)

---

### **Paso 3: Monitoreo Week 1**

```bash
# Ver log en tiempo real
tail -f logs/download_$(date +%Y%m%d)/week1_*.log

# Ver progreso (cada 5 min)
watch -n 300 "ls raw/market_data/bars/1d/ | wc -l && ls raw/market_data/bars/1d_raw/ | wc -l"

# Verificar proceso activo
ps aux | grep download_all.py

# Espacio usado
du -sh raw/market_data/bars/
```

---

### **Paso 4: Validación Week 1**

```bash
# Cuando Week 1 termine, validar:

# 1. Conteo de archivos
echo "Adjusted daily:" && ls raw/market_data/bars/1d/*.parquet | wc -l
echo "Raw daily:" && ls raw/market_data/bars/1d_raw/*.parquet | wc -l
echo "Adjusted hourly:" && ls raw/market_data/bars/1h/*.parquet | wc -l
echo "Raw hourly:" && ls raw/market_data/bars/1h_raw/*.parquet | wc -l
# ✅ Todos deben ser ~11,453

# 2. Verificar splits descargados
python -c "import polars as pl; df=pl.read_parquet('raw/corporate_actions/splits_*.parquet'); print(f'Splits: {len(df)}')"
# ✅ Debe mostrar ~26,611

# 3. Spot-check de símbolo aleatorio
python scripts/ingestion/check_download_status.py
```

**Criterios de calidad Week 1**:
- [ ] `1d/` y `1d_raw/` tienen **mismo nº de archivos** (~11,453)
- [ ] `1h/` y `1h_raw/` tienen **mismo nº de archivos** (~11,453)
- [ ] Splits downloaded: ~26,611 records
- [ ] Sample check: AAPL adjusted vs raw muestra ratio 4:1 en 2020-01-02 (verificación de split)
- [ ] Premarket data presente en hourly/daily

---

### **Paso 5: Re-run Event Detection** (con universo completo)

```bash
# Ejecutar detección de eventos con nuevo universo (activos + delisted)
python scripts/detect_events.py --input raw/market_data/bars/1d/ \
  --output processed/events/events_$(date +%Y%m%d).parquet \
  2>&1 | tee logs/download_$(date +%Y%m%d)/event_detection.log

# Verificar output
python -c "import polars as pl; df=pl.read_parquet('processed/events/events_*.parquet'); print(f'Events detected: {len(df)}'); print(df.head())"
```

**Criterios de calidad Event Detection**:
- [ ] Events detectados: > 50,000 eventos (depende de calibración)
- [ ] No NaN en columnas críticas (symbol, date, event_type)
- [ ] Tasa de eventos en rango esperado (~0.5-2% de días-símbolo)

---

### **Paso 6: Generar Ranking Top-2000**

```bash
# Generar ranking de Top-2000 para 1-min bars
python scripts/rank_events.py \
  --input processed/events/events_*.parquet \
  --output processed/rankings/top_2000_$(date +%Y%m%d).parquet \
  --top-n 2000

# Verificar
python -c "import polars as pl; df=pl.read_parquet('processed/rankings/top_2000_*.parquet'); print(f'Top symbols: {len(df)}'); print(df.head())"
```

**Criterios de calidad Ranking**:
- [ ] Exactamente 2,000 símbolos en ranking
- [ ] No NaN en ranking metrics
- [ ] Incluye mix de activos y delisted (verificar manualmente sample)

---

### **Paso 7: Lanzar Week 2-3** (1-min bars Top-2000, solo adjusted)

```bash
# Lanzar Week 2-3 con ranking generado
python scripts/ingestion/download_all.py \
  --weeks 2 3 \
  --top-n 2000 \
  --ranking-file processed/rankings/top_2000_$(date +%Y%m%d).parquet \
  2>&1 | tee logs/download_$(date +%Y%m%d)/week23_$(date +%H%M%S).log &

echo $! > logs/download_$(date +%Y%m%d)/week23.pid
```

**Tiempo estimado**: 12-18 horas

**Output esperado**:
- `raw/market_data/bars/1m/symbol=*/` (2,000 símbolos, particionado por fecha)
- Solo adjusted (NO `1m_raw/` directory)

---

### **Paso 8: Validación Final**

```bash
# 1. Verificar 1m data
find raw/market_data/bars/1m/ -name "*.parquet" | wc -l
# ✅ Debe haber miles de particiones (2,000 symbols × ~750 días × particiones)

# 2. Verificar tamaño total
du -sh raw/
# ✅ Debe ser ~150-160 GB

# 3. Audit completo
python scripts/ingestion/check_download_status.py --full-audit

# 4. Spot-checks manuales (sample 10 símbolos)
# - Verificar que tienen premarket/postmarket en 1m
# - Verificar que adjusted/raw en 1d/1h tienen mismo nº de registros
# - Verificar que splits explican diferencias entre adj/raw
```

**Criterios de calidad Week 2-3**:
- [ ] 2,000 símbolos con 1m data
- [ ] Particionado por fecha funcionando
- [ ] Premarket/postmarket incluido en 1m
- [ ] Solo adjusted (NO `1m_raw/` directory)
- [ ] Tamaño total ~150-160 GB

---

## 🔧 TROUBLESHOOTING

### **Error: 401 Unauthorized**
```bash
# Verificar API key
echo $POLYGON_API_KEY
# Re-export si necesario
export POLYGON_API_KEY="tu_clave_aqui"
```

### **Error: 429 Rate Limit**
```bash
# El backoff automático maneja esto
# Si persiste, aumentar sleep time en config:
# rate_limit_per_minute: 200 (bajar de 300)
```

### **Proceso se cuelga**
```bash
# Verificar proceso
ps aux | grep download_all

# Si está zombie, matar y relanzar desde símbolo donde falló
# Los resume checks evitan re-descargar
```

### **Espacio en disco insuficiente**
```bash
# Verificar espacio
df -h d:

# Si es crítico, puedes descargar por lotes:
# - Primero activos (5,228)
# - Luego delisted (6,225)
```

---

## ✅ READY TO LAUNCH

### **Comando final para copiar-pegar**:

```bash
# Pre-checks
echo "API Key: $POLYGON_API_KEY"
df -h d: | grep "Avail"
tasklist | findstr python.exe

# Launch Week 1
cd d:/04_TRADING_SMALLCAPS
python scripts/ingestion/download_all.py --weeks 1 \
  2>&1 | tee logs/download_$(date +%Y%m%d_%H%M%S)/week1.log &

# Monitor
tail -f logs/download_*/week1.log
```

---

## 📊 RESUMEN DE MODIFICACIONES IMPLEMENTADAS

### **1. Dual Price Download (Adjusted + Raw)**
- **Archivos modificados**: `ingest_polygon.py`, `download_all.py`
- **Cambio**: Daily/Hourly descargan ambas versiones
- **Beneficio**: Precios adjusted para TA, raw para filtros sin lookahead bias

### **2. Survivorship Bias Fix**
- **Archivo modificado**: `download_all.py:70-96`
- **Cambio**: Concatena tickers activos + delisted
- **Beneficio**: Incluye pump&dumps históricos que quebraron

### **3. Optimización 1m**
- **Archivo modificado**: `download_all.py:269-275, 350-356`
- **Cambio**: Solo adjusted en minutely (NO raw)
- **Beneficio**: Ahorra ~85 GB, reconstruible con splits

### **4. Event Detection**
- **Sin cambios**: Siempre lee `bars/1d/` (adjusted)
- **Mejora**: Universo más grande → Top-2000 de mejor calidad

---

## 🎯 IMPACTO ESPERADO

| Métrica | Antes | Después | Cambio |
|---------|-------|---------|--------|
| **Universo tickers** | 5,228 | 11,453 | +119% |
| **Eventos detectados** | ~50K | ~110K (est.) | +120% |
| **Storage total** | ~212 GB | ~152 GB | -28% |
| **Top-2000 calidad** | Solo activos | Activos + delisted | Mejor |

---

## 📝 NOTAS IMPORTANTES

1. **Event detection NO afectado**: Sigue usando adjusted prices de `bars/1d/`
2. **RAW prices para Phase 3**: Usaremos en feature engineering para market cap real y filtros de precio
3. **Splits críticos**: `raw/corporate_actions/splits_*.parquet` permite reconstruir raw desde adjusted en 1m
4. **Premarket incluido**: Polygon `/v2/aggs` incluye extended hours por defecto con `adjusted=true`
5. **Resume capability**: Si falla, relanzar continúa desde último símbolo exitoso

---

**Autor**: Implementación completada 2025-10-10
**Última revisión**: 2025-10-10
