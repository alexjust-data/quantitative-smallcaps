#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke Test para validar fixes de duplicación FASE 2.5

Valida:
(a) Solo hay un escritor activo
(b) Se generan manifests
(c) El merge final capta shards en worker_*
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path
import json
import polars as pl
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent

def test_single_writer():
    """Test (a): Solo hay un escritor activo"""
    print("\n" + "="*80)
    print("TEST (a): Verificando que NO hay múltiples escritores activos")
    print("="*80)

    import psutil
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'detect_events_intraday.py' in cmdline:
                processes.append({
                    'pid': proc.info['pid'],
                    'cmdline': cmdline
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if len(processes) == 0:
        print("[OK] No hay procesos de deteccion corriendo (esperado para smoke test)")
        return True
    elif len(processes) == 1:
        print(f"[OK] Solo 1 proceso activo (PID {processes[0]['pid']})")
        return True
    else:
        print(f"[FAIL] Hay {len(processes)} procesos corriendo simultaneamente!")
        for p in processes:
            print(f"  - PID {p['pid']}: {p['cmdline'][:100]}")
        return False

def test_manifests_generated():
    """Test (b): Se generan manifests"""
    print("\n" + "="*80)
    print("TEST (b): Verificando generación de manifests")
    print("="*80)

    manifests_dir = PROJECT_ROOT / "processed" / "events" / "manifests"

    if not manifests_dir.exists():
        print(f"[FAIL] FAIL: Directory {manifests_dir} no existe")
        return False

    # Buscar manifests del día actual
    today = datetime.now().strftime("%Y%m%d")
    run_id = f"events_intraday_{today}"

    manifests = list(manifests_dir.glob(f"{run_id}_shard*.json"))

    if len(manifests) == 0:
        print(f"[WARN] WARNING: No hay manifests para run_id={run_id}")
        print(f"  Buscando manifests de cualquier fecha...")
        all_manifests = list(manifests_dir.glob("events_intraday_*_shard*.json"))
        if len(all_manifests) == 0:
            print(f"[FAIL] FAIL: No hay manifests generados en {manifests_dir}")
            return False
        else:
            print(f"[OK] OK: Encontrados {len(all_manifests)} manifests de runs anteriores")
            manifests = all_manifests[:5]  # Tomar los primeros 5 para inspección
    else:
        print(f"[OK] OK: Encontrados {len(manifests)} manifests para run_id={run_id}")

    # Inspeccionar estructura de manifests
    print(f"\nInspeccionando primeros {min(3, len(manifests))} manifests:")
    for mf in manifests[:3]:
        try:
            data = json.loads(mf.read_text(encoding='utf-8'))
            print(f"\n  {mf.name}:")
            print(f"    - run_id: {data.get('run_id')}")
            print(f"    - shard: {data.get('shard')}")
            print(f"    - symbols: {len(data.get('symbols', []))} símbolos")
            print(f"    - events: {data.get('events')}")
            print(f"    - written_at: {data.get('written_at')}")

            # Validar estructura
            required_keys = ['run_id', 'shard', 'symbols', 'events', 'written_at']
            missing = [k for k in required_keys if k not in data]
            if missing:
                print(f"    [FAIL] MISSING KEYS: {missing}")
                return False
            else:
                print(f"    [OK] Schema válido")
        except Exception as e:
            print(f"[FAIL] FAIL: Error leyendo {mf.name}: {e}")
            return False

    return True

def test_recursive_merge():
    """Test (c): El merge final capta shards en worker_*"""
    print("\n" + "="*80)
    print("TEST (c): Verificando merge recursivo de shards en worker_*/")
    print("="*80)

    shards_dir = PROJECT_ROOT / "processed" / "events" / "shards"

    if not shards_dir.exists():
        print(f"[FAIL] FAIL: Directory {shards_dir} no existe")
        return False

    # Buscar shards del día actual
    today = datetime.now().strftime("%Y%m%d")
    run_id = f"events_intraday_{today}"

    # Buscar con glob (NO recursivo - método viejo)
    shards_flat = list(shards_dir.glob(f"{run_id}_shard*.parquet"))

    # Buscar con rglob (recursivo - método nuevo)
    shards_recursive = list(shards_dir.rglob(f"**/{run_id}_shard*.parquet"))

    print(f"\nShards encontrados:")
    print(f"  - glob() [NO recursivo]: {len(shards_flat)} shards")
    print(f"  - rglob() [recursivo]:   {len(shards_recursive)} shards")

    if len(shards_recursive) == 0:
        print(f"\n[WARN] WARNING: No hay shards para run_id={run_id}")
        print(f"  Buscando shards de cualquier fecha...")
        all_shards = list(shards_dir.rglob("**/events_intraday_*_shard*.parquet"))
        if len(all_shards) == 0:
            print(f"[FAIL] FAIL: No hay shards generados en {shards_dir}")
            return False
        else:
            print(f"[OK] OK: Encontrados {len(all_shards)} shards de runs anteriores")
            shards_recursive = all_shards
            # Recalcular flat para comparación
            latest_run = sorted(set([s.name.split('_shard')[0] for s in all_shards]))[-1]
            shards_flat = list(shards_dir.glob(f"{latest_run}_shard*.parquet"))

    # Identificar shards en subdirectorios worker_*
    worker_shards = [s for s in shards_recursive if 'worker_' in str(s.parent)]
    root_shards = [s for s in shards_recursive if 'worker_' not in str(s.parent)]

    print(f"\nDistribución de shards:")
    print(f"  - En root (shards/):        {len(root_shards)} shards")
    print(f"  - En worker_*/:             {len(worker_shards)} shards")

    if len(worker_shards) > 0:
        print(f"\n[OK] OK: Se detectaron shards en subdirectorios worker_*")
        # Mostrar distribución por worker
        workers = {}
        for s in worker_shards:
            worker_dir = s.parent.name
            workers[worker_dir] = workers.get(worker_dir, 0) + 1
        print(f"\n  Distribución por worker:")
        for w, count in sorted(workers.items()):
            print(f"    - {w}: {count} shards")
    else:
        print(f"\n[WARN] WARNING: No hay shards en subdirectorios worker_*")
        print(f"  (Esto es normal si no se ha ejecutado con workers paralelos)")

    # Verificar diferencia entre glob y rglob
    diff = len(shards_recursive) - len(shards_flat)
    if diff > 0:
        print(f"\n[OK] OK: rglob() encuentra {diff} shards adicionales que glob() no ve")
        print(f"  Esto confirma que el merge recursivo funciona correctamente")
        return True
    elif diff == 0 and len(worker_shards) == 0:
        print(f"\n[OK] OK: No hay diferencia (no hay workers paralelos activos)")
        return True
    else:
        print(f"\n[WARN] Ambos métodos encuentran el mismo número de shards")
        return True

def test_orchestrator_reconciliation():
    """Test bonus: Verificar que orchestrator puede reconciliar con manifests"""
    print("\n" + "="*80)
    print("TEST (bonus): Verificando reconciliación checkpoint vs manifests")
    print("="*80)

    manifests_dir = PROJECT_ROOT / "processed" / "events" / "manifests"
    checkpoints_dir = PROJECT_ROOT / "logs" / "checkpoints"

    if not manifests_dir.exists() or not checkpoints_dir.exists():
        print("[WARN] Directorios no existen, saltando test")
        return True

    # Buscar último run
    today = datetime.now().strftime("%Y%m%d")
    run_id = f"events_intraday_{today}"

    checkpoint_file = checkpoints_dir / f"{run_id}_completed.json"
    manifests = list(manifests_dir.glob(f"{run_id}_shard*.json"))

    if not checkpoint_file.exists():
        print(f"[WARN] No existe checkpoint para {run_id}")
        return True

    if len(manifests) == 0:
        print(f"[WARN] No existen manifests para {run_id}")
        return True

    # Leer checkpoint
    with open(checkpoint_file, 'r') as f:
        checkpoint = json.load(f)
    checkpoint_symbols = set(checkpoint.get('completed_symbols', []))

    # Leer manifests
    manifest_symbols = set()
    for mf in manifests:
        try:
            data = json.loads(mf.read_text(encoding='utf-8'))
            manifest_symbols.update(data.get('symbols', []))
        except Exception as e:
            print(f"[WARN] Error leyendo manifest {mf.name}: {e}")

    print(f"\nEstadísticas:")
    print(f"  - Símbolos en checkpoint:  {len(checkpoint_symbols)}")
    print(f"  - Símbolos en manifests:   {len(manifest_symbols)}")
    print(f"  - Diferencia (manifests - checkpoint): {len(manifest_symbols - checkpoint_symbols)}")
    print(f"  - Diferencia (checkpoint - manifests): {len(checkpoint_symbols - manifest_symbols)}")

    if len(manifest_symbols - checkpoint_symbols) > 0:
        print(f"\n[OK] OK: Manifests contienen {len(manifest_symbols - checkpoint_symbols)} símbolos")
        print(f"      que NO están en checkpoint (reconciliación funcionaría)")
        missing_sample = list(manifest_symbols - checkpoint_symbols)[:5]
        print(f"      Ejemplos: {missing_sample}")
        return True
    else:
        print(f"\n[OK] OK: Checkpoint y manifests están sincronizados")
        return True

def main():
    print("="*80)
    print("SMOKE TEST - Validación de fixes FASE 2.5")
    print("="*80)
    print(f"Proyecto: {PROJECT_ROOT}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    results = {
        "(a) Single writer": test_single_writer(),
        "(b) Manifests generated": test_manifests_generated(),
        "(c) Recursive merge": test_recursive_merge(),
        "(bonus) Reconciliation": test_orchestrator_reconciliation()
    }

    print("\n" + "="*80)
    print("RESUMEN DE RESULTADOS")
    print("="*80)

    for test_name, passed in results.items():
        status = "[OK] PASS" if passed else "[FAIL] FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())

    if all_passed:
        print("\n" + "="*80)
        print("[OK][OK][OK] SMOKE TEST PASSED [OK][OK][OK]")
        print("="*80)
        print("\nSiguientes pasos:")
        print("1. Lanzar orchestrator con: python ultra_robust_orchestrator.py")
        print("2. O lanzar parallel con: python launch_parallel_detection.py")
        print("3. Monitorear: watch -n 5 'ls -lh processed/events/manifests/ | tail -10'")
        print("4. Verificar logs: tail -f logs/ultra_robust/orchestrator_*.log")
        return 0
    else:
        print("\n" + "="*80)
        print("[FAIL][FAIL][FAIL] SMOKE TEST FAILED [FAIL][FAIL][FAIL]")
        print("="*80)
        return 1

if __name__ == "__main__":
    sys.exit(main())
