# Tools - FASE 2.5 Monitoring

## Scripts de Auditoría

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

## Otros Scripts

### seed_checkpoint.py
**Inicializa o corrige checkpoints manualmente**

Uso:
```bash
python tools/seed_checkpoint.py --symbols processed/symbols_list.txt
```

---

## Notas

- Los scripts de auditoría ahora manejan correctamente ejecuciones con múltiples workers paralelos
- El progreso se calcula haciendo un SET UNION de todos los símbolos completados en todos los checkpoints recientes
- Si un símbolo aparece en múltiples checkpoints, solo se cuenta una vez
