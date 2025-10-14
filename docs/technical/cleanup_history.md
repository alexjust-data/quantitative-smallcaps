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
# CLEANUP ANALYSIS - EXTENDED (Root Files)

**Fecha**: 2025-10-12
**Análisis**: Archivos del directorio root + análisis previo

---

## RESUMEN EJECUTIVO

### Archivos ya eliminados (Análisis previo)
- ✅ 38 archivos eliminados (~227 MB liberados)
- ✅ Logs rotados archivados en `logs_archive_20251012.tar.gz` (234 MB → 11 MB)

### Archivos adicionales encontrados en root (Este análisis)
- 🔍 9 archivos identificados
- 📦 6 archivos de prueba/temporales a eliminar (~28 KB)
- 📄 3 archivos de documentación OBSOLETA a mover/consolidar (~27 KB)

---

## CATEGORÍA 1: Scripts de Prueba/Testing (Root)

Estos son scripts únicos creados para pruebas puntuales durante desarrollo.

### 1.1 Scripts de Testing (6 archivos - ~13 KB)

| Archivo | Tamaño | Fecha | Razón para eliminar |
|---------|--------|-------|---------------------|
| `check_qubt_nov13.py` | 1.1 KB | Oct 9 | Script de prueba para verificar evento específico de QUBT. Ya validado. |
| `explore_data.py` | 6.0 KB | Oct 8 | Script de exploración inicial. Output guardado en `data_exploration_output.txt`. |
| `launch_week23_direct.py` | 843 B | Oct 9 | Script temporal para lanzar Week 2-3 sin validación. Ya no se usa. |
| `test_dual_download.py` | 2.6 KB | Oct 10 | Test de descarga adjusted vs raw prices. Ya validado en código principal. |
| `test_hourly_quick.py` | 2.7 KB | Oct 8 | Test rápido de descarga 1d+1h para 3 símbolos. Ya completado. |
| `data_exploration_output.txt` | 23 KB | Oct 8 | Output del script `explore_data.py`. Solo útil como snapshot inicial. |

**Acción**: ✅ ELIMINAR (scripts de prueba one-time)

**Comando**:
```bash
rm d:/04_TRADING_SMALLCAPS/check_qubt_nov13.py
rm d:/04_TRADING_SMALLCAPS/explore_data.py
rm d:/04_TRADING_SMALLCAPS/launch_week23_direct.py
rm d:/04_TRADING_SMALLCAPS/test_dual_download.py
rm d:/04_TRADING_SMALLCAPS/test_hourly_quick.py
rm d:/04_TRADING_SMALLCAPS/data_exploration_output.txt
```

---

## CATEGORÍA 2: Documentación OBSOLETA/REDUNDANTE (Root)

### 2.1 Documentos de Fase 3.2 (2 archivos - ~21 KB)

| Archivo | Tamaño | Fecha | Razón para mover |
|---------|--------|-------|------------------|
| `FASE_3.2_COMANDOS_OPERACION.md` | 8.2 KB | Oct 12 | Guía operativa FASE 3.2. Debería estar en `docs/`. |
| `FASE_3.2_RESUMEN_IMPLEMENTACION.md` | 13 KB | Oct 12 | Resumen técnico FASE 3.2. Debería estar en `docs/`. |

**Acción**: 🔄 MOVER a `docs/fase_3.2/` para organización

**Razón**: Documentación importante pero desorganizada. No debe estar en root.

**Comando**:
```bash
mkdir -p d:/04_TRADING_SMALLCAPS/docs/fase_3.2
mv d:/04_TRADING_SMALLCAPS/FASE_3.2_COMANDOS_OPERACION.md d:/04_TRADING_SMALLCAPS/docs/fase_3.2/
mv d:/04_TRADING_SMALLCAPS/FASE_3.2_RESUMEN_IMPLEMENTACION.md d:/04_TRADING_SMALLCAPS/docs/fase_3.2/
```

### 2.2 Documentos Obsoletos (1 archivo - ~6.4 KB)

| Archivo | Tamaño | Fecha | Razón para eliminar |
|---------|--------|-------|---------------------|
| `NEXT_STEPS.md` | 6.4 KB | Oct 8 | Pipeline guidance OBSOLETO. Sistema cambió completamente en FASE 2.5/3.2. Información desactualizada. |

**Acción**: ✅ ELIMINAR (contenido obsoleto)

**Razón**:
- Fecha: Oct 8 (antes de arquitectura FASE 2.5)
- Menciona sistema Week 1/2/3 que fue reemplazado por sistema events-first
- Pipeline descrito ya no es válido (detect → rank → download cambió a detect intraday → manifest → micro download)
- Información confusa que podría causar errores

**Comando**:
```bash
rm d:/04_TRADING_SMALLCAPS/NEXT_STEPS.md
```

---

## CATEGORÍA 3: Documentos a CONSERVAR (Root)

### 3.1 Documentación Core del Proyecto (3 archivos)

| Archivo | Tamaño | Fecha | Razón para conservar |
|---------|--------|-------|----------------------|
| `README.md` | 16 KB | Oct 7 | Documentación principal del proyecto. CRÍTICO. |
| `requirements.txt` | 805 B | Oct 7 | Dependencias Python. CRÍTICO. |
| `CLEANUP_ANALYSIS.md` | 7.8 KB | Oct 12 | Análisis de limpieza previo (logs, eventos test, tickers). ÚTIL. |

**Acción**: ✅ CONSERVAR (documentación esencial)

---

## RESUMEN DE ACCIONES

### Eliminar (7 archivos - ~34 KB)
```bash
# Scripts de testing
rm d:/04_TRADING_SMALLCAPS/check_qubt_nov13.py
rm d:/04_TRADING_SMALLCAPS/explore_data.py
rm d:/04_TRADING_SMALLCAPS/launch_week23_direct.py
rm d:/04_TRADING_SMALLCAPS/test_dual_download.py
rm d:/04_TRADING_SMALLCAPS/test_hourly_quick.py
rm d:/04_TRADING_SMALLCAPS/data_exploration_output.txt

# Documentación obsoleta
rm d:/04_TRADING_SMALLCAPS/NEXT_STEPS.md
```

### Mover a docs/ (2 archivos - ~21 KB)
```bash
# Crear directorio FASE 3.2
mkdir -p d:/04_TRADING_SMALLCAPS/docs/fase_3.2

# Mover documentos
mv d:/04_TRADING_SMALLCAPS/FASE_3.2_COMANDOS_OPERACION.md d:/04_TRADING_SMALLCAPS/docs/fase_3.2/
mv d:/04_TRADING_SMALLCAPS/FASE_3.2_RESUMEN_IMPLEMENTACION.md d:/04_TRADING_SMALLCAPS/docs/fase_3.2/
```

### Conservar (3 archivos - ~24 KB)
- `README.md` (documentación principal)
- `requirements.txt` (dependencias)
- `CLEANUP_ANALYSIS.md` (análisis previo)

---

## RESULTADO ESPERADO

### Directorio Root (Después de limpieza)

```
d:/04_TRADING_SMALLCAPS/
├── .git/                           # Control de versiones
├── config/                         # Configuración
├── data/                          # Datos
├── docs/                          # Documentación
│   └── fase_3.2/                  # [NUEVO] Documentos FASE 3.2
│       ├── COMANDOS_OPERACION.md
│       └── RESUMEN_IMPLEMENTACION.md
├── logs/                          # Logs
├── processed/                     # Datos procesados
├── raw/                           # Datos crudos
├── scripts/                       # Scripts del proyecto
├── README.md                      # [CONSERVAR] Documentación principal
├── requirements.txt               # [CONSERVAR] Dependencias
└── CLEANUP_ANALYSIS.md            # [CONSERVAR] Análisis previo
```

**Root limpio**: Solo 3 archivos esenciales (README, requirements, análisis)

---

## VALIDACIÓN POST-LIMPIEZA

### Verificar que archivos críticos permanecen:
```bash
ls -lh d:/04_TRADING_SMALLCAPS/README.md
ls -lh d:/04_TRADING_SMALLCAPS/requirements.txt
ls -lh d:/04_TRADING_SMALLCAPS/CLEANUP_ANALYSIS.md
```

### Verificar que archivos se movieron correctamente:
```bash
ls -lh d:/04_TRADING_SMALLCAPS/docs/fase_3.2/
```

### Verificar que archivos de prueba se eliminaron:
```bash
ls d:/04_TRADING_SMALLCAPS/*.py 2>/dev/null
# Debe retornar: (vacío) o solo scripts operativos principales
```

---

## ANÁLISIS COMPLETO DE LIMPIEZA

### Total Eliminado (Todo el proyecto)

| Categoría | Archivos | Espacio Liberado |
|-----------|----------|------------------|
| **Análisis Previo** | | |
| - Eventos de prueba | 3 | ~20 KB |
| - Tickers duplicados | 4 | ~2.3 MB |
| - Logs fallidos | 5 | ~2 MB |
| - Logs rotados | 26 | ~223 MB (234→11) |
| **Análisis Actual** | | |
| - Scripts de testing | 6 | ~34 KB |
| - Documentación obsoleta | 1 | ~6.4 KB |
| **TOTAL** | **45** | **~227 MB** |

### Documentos Reorganizados
- 2 archivos FASE 3.2 movidos a `docs/fase_3.2/`

---

## ESTADO FINAL DEL PROYECTO

✅ **Proyecto limpio y organizado**
- Sin archivos de prueba en root
- Documentación organizada en `docs/`
- Logs archivados (234 MB → 11 MB)
- Solo archivos esenciales en root (README, requirements, análisis)

✅ **Archivos críticos conservados**
- Todos los datos de producción intactos
- Eventos detectados preservados
- Rankings actuales preservados
- Logs de procesos activos preservados

✅ **Espacio liberado**: ~227 MB

---

**Fecha de análisis**: 2025-10-12 13:30
**Proceso de detección activo**: ✅ Running (detect_events_20251012_v2.log)
**Archivos de producción**: ✅ Todos conservados
# Cleanup History Consolidated

See also: ANALISIS_LIMPIEZA_ROOT_20251014.md for final cleanup execution
