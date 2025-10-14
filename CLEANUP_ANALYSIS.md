# Análisis de Limpieza del Proyecto - Archivos a Eliminar

## 📋 Archivos Identificados para Eliminación

### 1. ❌ EVENTOS DE PRUEBA (processed/events/)

#### **events_intraday_20251008.parquet** (7.3 KB)
- **Razón**: Archivo de prueba viejo
- **Contenido**: 26 eventos de 5 símbolos de prueba (MTEK, CCLD, SOUN, AEMD, NERV)
- **Fecha**: 11 oct 23:32
- **Acción**: ELIMINAR ✅

#### **events_intraday_20251012.parquet** (6.8 KB)
- **Razón**: Archivo de prueba, mismo contenido que el anterior
- **Contenido**: 26 eventos (archivos viejos de test runs)
- **Fecha**: 11 oct 23:39
- **Acción**: ELIMINAR ✅

#### **events_intraday_manifest.parquet** (6.2 KB)
- **Razón**: Manifest de prueba, no corresponde a detección masiva
- **Contenido**: 12 eventos de prueba
- **Fecha**: 12 oct 10:25
- **Acción**: ELIMINAR ✅

**Archivos a MANTENER**:
- ✅ `events_daily_20251009.parquet` (47 MB) - Eventos diarios válidos (FASE 2.0)
- ✅ `events_annotated_20251009.parquet` (51 MB) - Eventos anotados válidos (FASE 2.0)

---

### 2. ❌ LOGS ROTADOS DE INGESTION (logs/ingestion/)

**Total logs rotados**: ~258 MB en múltiples archivos `.log` con timestamps

Logs con timestamps específicos (archivos rotados automáticamente):
- `polygon_ingestion.2025-10-07_18-31-05_480000.log` (10 MB)
- `polygon_ingestion.2025-10-08_15-37-38_660000.log` (10 MB)
- `polygon_ingestion.2025-10-08_17-43-05_570000.log` (10 MB)
- ... (20+ archivos similares)

**Acción**: COMPRIMIR y ARCHIVAR o ELIMINAR logs rotados viejos
- Mantener solo el log principal activo
- Libera ~250 MB

---

### 3. ❌ TICKERS DUPLICADOS/DESACTUALIZADOS (raw/reference/)

#### **Tickers Active Duplicados**:
- `tickers_active_20251007.parquet` (372 KB) - ❌ ELIMINAR (desactualizado)
- `tickers_active_20251008.parquet` (373 KB) - ❌ ELIMINAR (desactualizado)
- ✅ `tickers_active_20251010.parquet` (376 KB) - **MANTENER** (más reciente)

#### **Tickers Delisted Duplicados**:
- `tickers_delisted_20251007.parquet` (706 KB) - ❌ ELIMINAR (desactualizado)
- `tickers_delisted_20251008.parquet` (707 KB) - ❌ ELIMINAR (desactualizado)
- ✅ `tickers_delisted_20251010.parquet` (707 KB) - **MANTENER** (más reciente)

**Razón**: Solo necesitamos la versión más reciente, las anteriores son snapshots viejos

---

### 4. ❌ LOGS DE DETECCIÓN FALLIDOS/INTERMEDIOS

#### **detect_events_20251012.log** (1.4 MB)
- **Razón**: Log de proceso que se colgó/falló
- **Contenido**: Solo procesó 17 símbolos antes de fallar
- **Fecha**: 12 oct (proceso fallido)
- **Acción**: ELIMINAR (el proceso fue relanzado como `_v2`)

**Archivo a MANTENER**:
- ✅ `detect_events_20251012_v2.log` (128 KB actual, creciendo) - Log activo del proceso corriendo

---

### 5. ❌ LOGS MISCELÁNEOS VIEJOS

- `actions_relaunch.log` (128 KB) - Log de relanzamientos, puede eliminarse
- `news_fixed.log` (256 KB) - Log de fix de news, completado
- `news_relaunch.log` (256 KB) - Log de relaunch de news, completado
- `failed_week1_hourly_20251012.txt` (128 KB) - Lista de fallos, ya procesado

**Acción**: ELIMINAR logs completados/viejos

---

### 6. ✅ ARCHIVOS A MANTENER (IMPORTANTES)

**Processed Events** (válidos):
- ✅ `events_daily_20251009.parquet` (47 MB) - Eventos diarios FASE 2.0
- ✅ `events_annotated_20251009.parquet` (51 MB) - Eventos anotados FASE 2.0

**Processed Rankings**:
- ✅ `top_2000_by_events_20251009.parquet` (85 KB) - Ranking válido

**Processed Reference**:
- ✅ `corporate_actions_20251009.parquet` (55 KB) - Acciones corporativas
- ✅ `symbols_with_1m.parquet` (6.4 KB) - Lista de símbolos con datos 1m (NUEVO)
- ✅ `symbols_missing_1m.parquet` (502 B) - Lista de símbolos sin datos 1m (NUEVO)

**Raw Reference** (actuales):
- ✅ `ticker_details_all.parquet` (1.9 MB) - Detalles de tickers completo
- ✅ `tickers_active_20251010.parquet` (376 KB) - Más reciente
- ✅ `tickers_delisted_20251010.parquet` (707 KB) - Más reciente
- ✅ `exchanges.parquet`, `holidays_upcoming.parquet`, `ticker_types.parquet`, etc.

**Raw Market Data**:
- ✅ TODO en `raw/market_data/bars/` (1d, 1h, 1m) - Datos principales del proyecto

---

## 📊 Resumen de Limpieza

| Categoría | Archivos | Tamaño | Acción |
|-----------|----------|--------|--------|
| Eventos prueba | 3 archivos | ~20 KB | ❌ ELIMINAR |
| Logs rotados ingestion | ~20 archivos | ~250 MB | ❌ ELIMINAR/COMPRIMIR |
| Tickers duplicados | 4 archivos | ~2.3 MB | ❌ ELIMINAR |
| Logs fallidos | 5 archivos | ~2 MB | ❌ ELIMINAR |
| **TOTAL LIMPIEZA** | **~32 archivos** | **~254 MB** | |

**Espacio liberado estimado**: ~254 MB

---

## 🗑️ Comandos de Limpieza Sugeridos

### Paso 1: Backup de seguridad (opcional)
```bash
# Crear backup antes de eliminar
mkdir -p d:/04_TRADING_SMALLCAPS/backup_cleanup_20251012
cp d:/04_TRADING_SMALLCAPS/processed/events/events_intraday_*.parquet d:/04_TRADING_SMALLCAPS/backup_cleanup_20251012/ 2>/dev/null
```

### Paso 2: Eliminar eventos de prueba
```bash
rm d:/04_TRADING_SMALLCAPS/processed/events/events_intraday_20251008.parquet
rm d:/04_TRADING_SMALLCAPS/processed/events/events_intraday_20251012.parquet
rm d:/04_TRADING_SMALLCAPS/processed/events/events_intraday_manifest.parquet
```

### Paso 3: Eliminar tickers duplicados (mantener solo 20251010)
```bash
rm d:/04_TRADING_SMALLCAPS/raw/reference/tickers_active_20251007.parquet
rm d:/04_TRADING_SMALLCAPS/raw/reference/tickers_active_20251008.parquet
rm d:/04_TRADING_SMALLCAPS/raw/reference/tickers_delisted_20251007.parquet
rm d:/04_TRADING_SMALLCAPS/raw/reference/tickers_delisted_20251008.parquet
```

### Paso 4: Comprimir logs rotados de ingestion
```bash
# Opción A: Comprimir y archivar
cd d:/04_TRADING_SMALLCAPS/logs/ingestion
tar -czf logs_archive_20251012.tar.gz polygon_ingestion.2025-*.log
rm polygon_ingestion.2025-*.log

# Opción B: Eliminar directamente (si no necesitas historial)
rm d:/04_TRADING_SMALLCAPS/logs/ingestion/polygon_ingestion.2025-*.log
```

### Paso 5: Limpiar logs viejos
```bash
rm d:/04_TRADING_SMALLCAPS/logs/detect_events_20251012.log
rm d:/04_TRADING_SMALLCAPS/logs/actions_relaunch.log
rm d:/04_TRADING_SMALLCAPS/logs/news_fixed.log
rm d:/04_TRADING_SMALLCAPS/logs/news_relaunch.log
rm d:/04_TRADING_SMALLCAPS/logs/failed_week1_hourly_20251012.txt
```

---

## ⚠️ IMPORTANTE: NO ELIMINAR

**Archivos críticos que NO deben tocarse**:

1. ❌ NO TOCAR: `raw/market_data/bars/` (1d, 1h, 1m) - Datos principales
2. ❌ NO TOCAR: `events_daily_20251009.parquet` (47 MB) - Eventos válidos FASE 2.0
3. ❌ NO TOCAR: `events_annotated_20251009.parquet` (51 MB) - Eventos válidos FASE 2.0
4. ❌ NO TOCAR: `top_2000_by_events_20251009.parquet` - Ranking actual
5. ❌ NO TOCAR: `ticker_details_all.parquet` - Referencia completa
6. ❌ NO TOCAR: `detect_events_20251012_v2.log` - Log del proceso ACTIVO
7. ❌ NO TOCAR: `symbols_with_1m.parquet` / `symbols_missing_1m.parquet` - Listas nuevas útiles
8. ❌ NO TOCAR: `config/` - Configuraciones del proyecto
9. ❌ NO TOCAR: `scripts/` - Código fuente

---

## 📝 Verificación Post-Limpieza

Después de la limpieza, verificar que el proyecto sigue funcionando:

```bash
# Verificar estructura de datos esenciales
ls d:/04_TRADING_SMALLCAPS/raw/market_data/bars/1m | wc -l  # Debe mostrar ~1996
ls d:/04_TRADING_SMALLCAPS/processed/events/*.parquet  # Debe mostrar solo events_daily y events_annotated

# Verificar que el proceso de detección sigue corriendo
tail -10 d:/04_TRADING_SMALLCAPS/logs/detect_events_20251012_v2.log
```

---

## 🎯 Estado Final Esperado

**Después de la limpieza**:
- ✅ Solo eventos válidos de producción (FASE 2.0)
- ✅ Solo tickers de la fecha más reciente
- ✅ Logs rotados archivados o eliminados
- ✅ ~254 MB de espacio liberado
- ✅ Proyecto limpio y organizado
- ✅ Sin archivos de prueba o temporales

**El proceso de detección activo (detect_events_20251012_v2) NO se verá afectado y continuará normalmente.**
