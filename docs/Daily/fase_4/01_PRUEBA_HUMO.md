# 🧪 PRUEBA DE HUMO - Fixes FASE 2.5

## ✅ Paso 0: COMPLETADO
- Procesos activos: NINGUNO
- Locks limpiados: OK
- Sistema listo para prueba

---

## 🚀 Paso 1: LANZAR PRUEBA (Elige UNA opción)

### OPCIÓN A: Ultra Robust Orchestrator (Recomendada)
```bash
python ultra_robust_orchestrator.py
```

**Qué hace:**
- Lee checkpoint de hoy: `logs/checkpoints/events_intraday_20251014_completed.json`
- Reconcilia con manifests si existen
- Divide símbolos restantes en 3 workers
- Cada worker escribe en su propio subdirectorio: `processed/events/shards/worker_N/`

### OPCIÓN B: Launch Parallel Detection
```bash
python launch_parallel_detection.py
# Responder: yes
```

**Qué hace:**
- Lee checkpoint
- Divide símbolos en 4 workers
- Cada worker escribe en: `processed/events/shards/worker_N/`

**⚠️ IMPORTANTE: Solo ejecutar UNA opción, NUNCA ambas simultáneamente**

---

## 📊 Paso 2: MONITOREAR (En otra terminal)

### Monitor 1: Ver heartbeat en tiempo real
```bash
tail -f logs/detect_events/heartbeat_20251014.log
```

Debe mostrar líneas como:
```
2025-10-14 14:30:15.123    AAPL    1    50    1234    2.34
```

### Monitor 2: Ver shards que se crean
```bash
# Listar shards en worker_* cada 10 segundos
watch -n 10 'ls -lht processed/events/shards/worker_*/*.parquet 2>/dev/null | head -20'
```

Debe mostrar:
```
processed/events/shards/worker_1/events_intraday_20251014_shard0000.parquet
processed/events/shards/worker_2/events_intraday_20251014_shard0001.parquet
processed/events/shards/worker_3/events_intraday_20251014_shard0002.parquet
```

### Monitor 3: Ver manifests que se generan
```bash
watch -n 10 'ls -lt processed/events/manifests/*.json 2>/dev/null | head -15'
```

Debe mostrar:
```
events_intraday_20251014_shard0000.json
events_intraday_20251014_shard0001.json
events_intraday_20251014_shard0002.json
```

### Monitor 4: Ver logs del orchestrator
```bash
tail -f logs/ultra_robust/orchestrator_20251014.log | grep -E "(Reconciled|SAVED|Worker|Completed)"
```

Debe mostrar:
```
[INFO] Reconciled checkpoint with manifests: +0 symbols
[INFO] Worker 1: Assigned 287 symbols
[INFO] Worker 2: Assigned 288 symbols
[INFO] Worker 3: Assigned 288 symbols
[SAVED] Shard 0: 123 events -> events_intraday_20251014_shard0000.parquet
```

---

## ✅ Paso 3: VALIDACIONES CRÍTICAS

### Check 1: Verificar que solo hay UN lock activo
```bash
# Durante escrituras debe existir el lock, luego desaparecer
ls -la processed/events/shards/events_intraday_20251014.lock 2>/dev/null
```

**Esperado:** El archivo aparece brevemente durante escrituras, luego desaparece

### Check 2: Inspeccionar un manifest
```bash
cat processed/events/manifests/events_intraday_20251014_shard0000.json
```

**Esperado:**
```json
{
  "run_id": "events_intraday_20251014",
  "shard": "events_intraday_20251014_shard0000.parquet",
  "symbols": [
    "AAPL",
    "AMD",
    "TSLA"
  ],
  "events": 123,
  "written_at": "2025-10-14T14:30:45.123456"
}
```

### Check 3: Contar shards con merge recursivo
```bash
python3 << 'EOF'
from pathlib import Path
root = Path(".")
shards_dir = root / "processed" / "events" / "shards"

# Método viejo (NO recursivo)
flat = list(shards_dir.glob("events_intraday_20251014_shard*.parquet"))
print(f"glob() [flat]:      {len(flat)} shards")

# Método nuevo (recursivo)
recursive = list(shards_dir.rglob("**/events_intraday_20251014_shard*.parquet"))
print(f"rglob() [recursivo]: {len(recursive)} shards")

print(f"\nDiferencia: {len(recursive) - len(flat)} shards en subdirectorios")

if len(recursive) > len(flat):
    print("✓ OK: El merge recursivo captura shards en worker_*/")
else:
    print("⚠ WARNING: No hay shards en subdirectorios (normal si no hay workers)")
EOF
```

### Check 4: Ejecutar smoke test completo
```bash
python smoke_test_fase25_fix.py
```

**Esperado después de ~5 minutos de ejecución:**
```
[OK] PASS: (a) Single writer
[OK] PASS: (b) Manifests generated  ← Debe cambiar de FAIL a PASS
[OK] PASS: (c) Recursive merge
[OK] PASS: (bonus) Reconciliation
```

---

## 🔍 Paso 4: VALIDACIÓN ANTI-DUPLICACIÓN (Después de completar)

### Cuando terminen los workers (o después de 1-2 horas), ejecutar:

```bash
# 1. Merge manual si es necesario
python3 << 'EOF'
from pathlib import Path
import polars as pl
from datetime import datetime

root = Path(".")
today = datetime.now().strftime("%Y%m%d")
shards_dir = root / "processed" / "events" / "shards"
events_dir = root / "processed" / "events"

# Merge recursivo (incluye worker_*)
files = sorted(shards_dir.rglob(f"**/events_intraday_{today}_shard*.parquet"))
print(f"Merging {len(files)} shards...")

if len(files) == 0:
    print("ERROR: No shards found!")
    exit(1)

final = pl.concat([pl.read_parquet(f) for f in files], how="diagonal")
final = final.sort(["symbol", "timestamp"])

out = events_dir / f"events_intraday_{today}.parquet"
final.write_parquet(out, compression="zstd")
print(f"FINAL: {out}")
print(f"Rows: {len(final):,}")
EOF

# 2. Ejecutar deduplicación DRY-RUN
python scripts/processing/deduplicate_events.py \
    --input processed/events/events_intraday_20251014.parquet \
    --dry-run

# 3. Inspeccionar resultados
```

**RESULTADOS ESPERADOS:**

**ANTES del fix (13 de octubre):**
```
Total events: 786,869
Unique events: 405,886
Duplicate events: 380,983
Duplication rate: 48.4% (realmente 75.4% en análisis detallado)
```

**DESPUÉS del fix (14 de octubre):**
```
Total events: XXXX
Unique events: XXXX (mismo número o muy cercano)
Duplicate events: 0-100 (casi cero)
Duplication rate: 0.0-0.5% (drásticamente menor)
```

**✅ Criterio de ÉXITO:** Duplication rate < 5%

---

## 🚨 Troubleshooting

### Problema: No se crean manifests
```bash
# Verificar que la función existe
grep -n "write_shard_manifest" scripts/processing/detect_events_intraday.py

# Debe aparecer:
# Línea ~1169: def write_shard_manifest(...)
# Línea ~838:  write_shard_manifest(self.manifests_dir, ...)
```

**Si no aparece:** El parche no se aplicó correctamente

### Problema: Shards no están en worker_*/
```bash
# Verificar que los orchestrators pasan --output-dir
grep -n "output-dir" ultra_robust_orchestrator.py launch_parallel_detection.py

# Debe aparecer en ambos archivos
```

**Si no aparece:** El parche no se aplicó correctamente

### Problema: Lock timeout
```bash
# Ver logs de error
grep -i "lock timeout" logs/ultra_robust/*.log logs/detect_events/*.log
```

**Solución:** Aumentar timeout en `file_lock()` de 30 a 60 segundos

### Problema: Sigue habiendo duplicación alta (>10%)
```bash
# Verificar que no hay múltiples orquestadores
ps aux | grep -E "(ultra_robust|launch_parallel)" | grep -v grep

# Debe haber MÁXIMO 1 proceso
```

**Solución:** Matar todos los procesos y relanzar solo UNO

---

## 📝 Checklist Final

Antes de dar por buena la prueba, verificar:

- [ ] Solo hay 1 orchestrator/launcher activo
- [ ] Hay archivos .json en `processed/events/manifests/`
- [ ] Hay shards en `processed/events/shards/worker_*/`
- [ ] Los manifests tienen la estructura correcta (run_id, shard, symbols, events, written_at)
- [ ] El smoke test pasa todos los checks
- [ ] La tasa de duplicación es < 5% (idealmente 0%)
- [ ] El orchestrator loggea "Reconciled checkpoint with manifests"
- [ ] No hay errores de "Lock timeout" en los logs

Si todos los checks pasan: **✅ Los fixes funcionan correctamente**

---

## 🎯 Próximos Pasos

Una vez validado el fix:

1. **Commit el smoke test:**
   ```bash
   git add smoke_test_fase25_fix.py PRUEBA_HUMO.md
   git commit -m "Add smoke test for FASE 2.5 duplication fixes"
   git push origin main
   ```

2. **Limpiar datos corruptos anteriores:**
   ```bash
   # Mover shards del 13 de octubre con duplicación
   mkdir -p archive/corrupted_fase25
   mv processed/events/shards processed/events/shards_20251013_CORRUPTED
   mkdir -p processed/events/shards

   # Limpiar checkpoint antiguo
   mv logs/checkpoints/events_intraday_20251013_completed.json \
      archive/corrupted_fase25/
   ```

3. **Re-ejecutar FASE 2.5 completa:**
   ```bash
   python ultra_robust_orchestrator.py
   # Dejar correr 4-5 días
   # Duplication rate esperada: 0%
   ```

4. **Regenerar manifest CORE limpio:**
   ```bash
   python scripts/processing/deduplicate_events.py \
       --input processed/events/events_intraday_20251014.parquet \
       --output processed/events/events_intraday_dedup_20251014.parquet

   python scripts/processing/generate_core_manifest_dryrun.py
   ```

5. **Continuar con FASE 3.2:**
   ```bash
   python launch_pm_wave.py
   ```

---

**Estado:** ✅ Listo para ejecutar
**Autor:** Claude Code
**Fecha:** 2025-10-14
**Versión:** 1.0
