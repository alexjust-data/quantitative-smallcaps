# Tools - FASE 2.5 Monitoring & Analysis

## 📊 Scripts de Auditoría

### audit_system.sh / audit_system.bat
**Audita el progreso de FASE 2.5 con cálculo CORRECTO de símbolos completados**

Este script ha sido corregido para:
- ✅ Mergear TODOS los checkpoints recientes (últimos 7 días)
- ✅ Calcular correctamente símbolos únicos completados
- ✅ Mostrar progreso real (no solo el último checkpoint)
- ✅ Detectar automáticamente heartbeat y logs más recientes

**Uso:**

Desde CMD/PowerShell:
```cmd
cd D:\04_TRADING_SMALLCAPS\tools
audit_system.bat
```

Desde Git Bash:
```bash
cd /d/04_TRADING_SMALLCAPS/tools
./audit_system.sh
```

**Output esperado:**
```
================================================================================
AUDITORIA DEL SISTEMA FASE 2.5
================================================================================

[2/5] CHECKPOINT - PROGRESO REAL (CORREGIDO)
--------------------------------------------------------------------------------
Merging all recent checkpoints (last 7 days)...

Checkpoint files found: 4
  - events_intraday_20251012_completed.json: 809 symbols (2025-10-12)
  - events_intraday_20251013_completed.json: 45 symbols (2025-10-13)
  - events_intraday_20251014_completed.json: 1016 symbols (2025-10-14)
  - events_intraday_20251015_completed.json: 1870 symbols (2025-10-15)

============================================================
PROGRESO REAL (merged from all checkpoints):
============================================================
Total symbols: 1996
Completed: 1870
Remaining: 126
Progress: 93.7%
============================================================
```

---

## 🔍 Scripts de Análisis de Duplicados

### analyze_duplicates.py / .sh / .bat
**Analiza duplicados en eventos de FASE 2.5 a múltiples niveles**

Características:
- ✅ Analiza todos los shards individuales (últimos 7 días)
- ✅ Analiza archivo merged final
- ✅ Compara checkpoints vs shards
- ✅ Identifica símbolos con duplicados
- ✅ Genera reportes detallados
- ✅ Opción para exportar CSV

**Uso básico:**

Desde CMD/PowerShell:
```cmd
cd D:\04_TRADING_SMALLCAPS\tools
analyze_duplicates.bat
```

Desde Git Bash:
```bash
cd /d/04_TRADING_SMALLCAPS/tools
./analyze_duplicates.sh
```

**Opciones avanzadas:**

```bash
# Análisis detallado
./analyze_duplicates.sh --detailed

# Exportar resultados a CSV
./analyze_duplicates.sh --export-csv

# Solo mergear shards (sin análisis)
./analyze_duplicates.sh --merge-only
```

**Output esperado:**

```
================================================================================
ANALYZING SHARDS (last 7 days)
================================================================================
Found 437 shards to analyze...
✓ Analyzed 437 shards

Total shards analyzed: 437
Total events: 1,539,419
Unique events: 1,539,419
Duplicates: 0
Average dup rate: 0.00%

✓ No duplicates found in any shard!

================================================================================
ANALYZING MERGED FILE
================================================================================
File: events_intraday_20251013.parquet
Total events: 720,663
Unique events: 372,204
Duplicates: 348,459
Duplication rate: 48.35%
Status: ✗ CRITICAL

Top 10 symbols by duplicate count:
  OPEN  : 7,464 duplicate events
  PLUG  : 6,708 duplicate events
  AAOI  : 6,174 duplicate events
  ...

================================================================================
COMPARING CHECKPOINTS VS SHARDS
================================================================================
Checkpoint symbols: 1874
Shard symbols: 1517
Discrepancy: 357

⚠ WARNING: 357 symbols marked complete but no shards found!
```

**Interpretación de resultados:**

- **Shard-level duplicates: 0%** → ✅ Shards actuales son limpios
- **Merged file duplicates: 48%** → ❌ Archivo viejo con duplicados (del 13/10)
- **Checkpoint vs Shards discrepancy: 357** → ⚠️ Símbolos sin shards (posiblemente sin eventos)

---

## 🔬 Script de Diagnóstico Pre-Lanzamiento

### pre_launch_diagnostics.py / .sh / .bat
**Diagnóstico completo del sistema ANTES de lanzar workers**

Detecta problemas que pueden causar cuelgues:
- ✅ Memoria disponible
- ✅ Espacio en disco
- ✅ Locks zombies
- ✅ Procesos activos
- ✅ Heartbeat congelado
- ✅ Símbolos con datos masivos (>500 días)
- ✅ Shards recientes
- ✅ Consistencia de checkpoints

**Uso básico:**

Desde CMD/PowerShell:
```cmd
cd D:\04_TRADING_SMALLCAPS\tools
pre_launch_diagnostics.bat
```

Desde Git Bash:
```bash
cd /d/04_TRADING_SMALLCAPS/tools
./pre_launch_diagnostics.sh
```

**Opciones avanzadas:**

```bash
# Diagnóstico detallado
./pre_launch_diagnostics.sh --detailed

# Auto-eliminar locks zombies
./pre_launch_diagnostics.sh --fix-locks
```

**Output esperado:**

```
================================================================================
[1/8] MEMORIA DISPONIBLE
================================================================================
Total RAM: 16.00 GB
Available: 8.50 GB (53.1%)
✓ INFO: Memoria suficiente: 8.50 GB

================================================================================
[2/8] ESPACIO EN DISCO
================================================================================
Total disk: 500.00 GB
Available: 120.00 GB (24.0%)
✓ INFO: Espacio suficiente: 120.00 GB

================================================================================
[6/8] SÍMBOLOS CON DATOS MASIVOS
================================================================================
⚠️  WARNING: Se encontraron 15 símbolos con >500 días de datos

Top 10 símbolos más grandes:
  GOGO  :  758 días,   250.5 MB
  AAPL  :  720 días,   310.2 MB
  ...

================================================================================
RESUMEN DE DIAGNÓSTICO
================================================================================
❌ ISSUES CRÍTICOS: 0
⚠️  WARNINGS: 2
  - Se encontraron 3 lock files zombies
  - Se encontraron 15 símbolos con >500 días de datos

✅ VEREDICTO: SAFE TO LAUNCH (con precaución)
```

**Interpretación:**
- **0 issues críticos** → ✅ Safe to launch
- **1-3 warnings** → ⚠️ Revisar pero puede lanzarse
- **>3 warnings** → ❌ Resolver antes de lanzar
- **Símbolos masivos** → Considerar procesarlos por separado

---

## 🛠️ Otros Scripts

### seed_checkpoint.py
**Inicializa o corrige checkpoints manualmente**

Uso:
```bash
python tools/seed_checkpoint.py --symbols processed/symbols_list.txt
```

---

## 📝 Notas Importantes

### Auditoría de Progreso
- Los scripts de auditoría manejan correctamente ejecuciones con múltiples workers paralelos
- El progreso se calcula haciendo SET UNION de todos los símbolos en checkpoints recientes
- Si un símbolo aparece en múltiples checkpoints, solo se cuenta una vez

### Análisis de Duplicados
- Los shards NUEVOS (post-fix 14/10) tienen 0% duplicación ✅
- El archivo `events_intraday_20251013.parquet` tiene 48% duplicación (pre-fix) ❌
- Use `--merge-only` para crear un nuevo archivo merged limpio desde shards actuales
- El análisis toma ~2-3 minutos para 437 shards

### Requisitos
- Python 3.8+
- polars (`pip install polars`)
- 2-4 GB RAM disponibles para análisis completo
