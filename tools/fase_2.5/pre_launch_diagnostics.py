#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FASE 2.5 - Pre-Launch Diagnostics

Diagnóstico completo del sistema ANTES de lanzar workers.
Detecta problemas que pueden causar cuelgues o fallos.

Uso:
    python tools/pre_launch_diagnostics.py
    python tools/pre_launch_diagnostics.py --detailed
    python tools/pre_launch_diagnostics.py --fix-locks
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json
import psutil
import argparse

# Fix Windows console encoding
if sys.platform == "win32":
    os.system("")
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class PreLaunchDiagnostics:
    """Diagnóstico pre-lanzamiento para FASE 2.5"""

    def __init__(self):
        self.project_root = PROJECT_ROOT
        self.issues = []
        self.warnings = []
        self.info = []

    def add_issue(self, msg: str):
        """Add critical issue"""
        self.issues.append(msg)
        print(f"❌ ISSUE: {msg}")

    def add_warning(self, msg: str):
        """Add warning"""
        self.warnings.append(msg)
        print(f"⚠️  WARNING: {msg}")

    def add_info(self, msg: str):
        """Add info"""
        self.info.append(msg)
        print(f"✓ INFO: {msg}")

    def check_memory(self):
        """Check available memory"""
        print(f"\n{'='*80}")
        print(f"[1/8] MEMORIA DISPONIBLE")
        print(f"{'='*80}")

        mem = psutil.virtual_memory()
        mem_available_gb = mem.available / (1024**3)
        mem_total_gb = mem.total / (1024**3)
        mem_percent = mem.percent

        print(f"Total RAM: {mem_total_gb:.2f} GB")
        print(f"Available: {mem_available_gb:.2f} GB ({100-mem_percent:.1f}%)")
        print(f"Used: {mem.used / (1024**3):.2f} GB ({mem_percent:.1f}%)")

        if mem_available_gb < 2:
            self.add_issue(f"Poca memoria disponible: {mem_available_gb:.2f} GB (mínimo recomendado: 2 GB)")
        elif mem_available_gb < 4:
            self.add_warning(f"Memoria justa: {mem_available_gb:.2f} GB (recomendado: 4+ GB)")
        else:
            self.add_info(f"Memoria suficiente: {mem_available_gb:.2f} GB")

    def check_disk_space(self):
        """Check available disk space"""
        print(f"\n{'='*80}")
        print(f"[2/8] ESPACIO EN DISCO")
        print(f"{'='*80}")

        disk = psutil.disk_usage(str(self.project_root))
        disk_free_gb = disk.free / (1024**3)
        disk_total_gb = disk.total / (1024**3)
        disk_percent = disk.percent

        print(f"Total disk: {disk_total_gb:.2f} GB")
        print(f"Available: {disk_free_gb:.2f} GB ({100-disk_percent:.1f}%)")
        print(f"Used: {disk.used / (1024**3):.2f} GB ({disk_percent:.1f}%)")

        if disk_free_gb < 5:
            self.add_issue(f"Poco espacio disponible: {disk_free_gb:.2f} GB (mínimo: 5 GB)")
        elif disk_free_gb < 10:
            self.add_warning(f"Espacio justo: {disk_free_gb:.2f} GB (recomendado: 10+ GB)")
        else:
            self.add_info(f"Espacio suficiente: {disk_free_gb:.2f} GB")

    def check_zombie_locks(self):
        """Check for zombie lock files"""
        print(f"\n{'='*80}")
        print(f"[3/8] LOCKS ZOMBIES")
        print(f"{'='*80}")

        lock_dirs = [
            self.project_root / "logs" / "checkpoints",
            self.project_root / "processed" / "events" / "shards"
        ]

        locks_found = []
        for lock_dir in lock_dirs:
            if lock_dir.exists():
                for lock_file in lock_dir.rglob("*.lock"):
                    locks_found.append(lock_file)

        if locks_found:
            self.add_warning(f"Se encontraron {len(locks_found)} lock files zombies")
            for lock in locks_found[:10]:  # Show first 10
                print(f"  - {lock.relative_to(self.project_root)}")
            if len(locks_found) > 10:
                print(f"  ... y {len(locks_found) - 10} más")
        else:
            self.add_info("No hay lock files zombies")

        return locks_found

    def check_active_processes(self):
        """Check for active detection processes"""
        print(f"\n{'='*80}")
        print(f"[4/8] PROCESOS ACTIVOS")
        print(f"{'='*80}")

        keywords = ["detect_events", "watchdog", "launch_parallel", "ultra_robust"]
        active_processes = []

        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                cmdline = " ".join(proc.info['cmdline'] or [])
                if any(kw in cmdline for kw in keywords):
                    active_processes.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "cmdline": cmdline[:100],
                        "age": datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if active_processes:
            self.add_warning(f"Se encontraron {len(active_processes)} procesos activos")
            for proc in active_processes:
                age_str = str(proc['age']).split('.')[0]  # Remove microseconds
                print(f"  PID {proc['pid']}: {proc['name']} (age: {age_str})")
                print(f"    {proc['cmdline']}")
        else:
            self.add_info("No hay procesos activos (correcto)")

        return active_processes

    def check_heartbeat_freshness(self):
        """Check if heartbeat is recent"""
        print(f"\n{'='*80}")
        print(f"[5/8] HEARTBEAT STATUS")
        print(f"{'='*80}")

        heartbeat_dir = self.project_root / "logs" / "detect_events"
        heartbeat_files = sorted(heartbeat_dir.glob("heartbeat_*.log"), reverse=True)

        if not heartbeat_files:
            self.add_info("No hay heartbeat files (normal si no se ha ejecutado hoy)")
            return

        latest_hb = heartbeat_files[0]
        print(f"Latest heartbeat: {latest_hb.name}")

        try:
            with open(latest_hb) as f:
                lines = f.readlines()

            if lines:
                last_line = lines[-1]
                ts_str = last_line.split('\t')[0]
                last_ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
                age = datetime.now() - last_ts

                print(f"Last activity: {ts_str}")
                print(f"Age: {age}")

                if age > timedelta(minutes=10):
                    self.add_warning(f"Heartbeat detenido hace {age} (workers posiblemente colgados)")
                else:
                    self.add_info(f"Heartbeat reciente ({age} ago)")
            else:
                self.add_warning("Heartbeat file está vacío")

        except Exception as e:
            self.add_warning(f"Error leyendo heartbeat: {e}")

    def check_massive_symbols(self, threshold: int = 500):
        """Check for symbols with massive data"""
        print(f"\n{'='*80}")
        print(f"[6/8] SÍMBOLOS CON DATOS MASIVOS")
        print(f"{'='*80}")
        print(f"Threshold: >{threshold} días de datos")

        bars_dir = self.project_root / "raw" / "market_data" / "bars" / "1m"

        if not bars_dir.exists():
            self.add_warning(f"Directorio de barras no existe: {bars_dir}")
            return []

        massive_symbols = []
        symbol_dirs = sorted(bars_dir.glob("symbol=*"))

        print(f"Scanning {len(symbol_dirs)} symbols...")

        for i, symbol_dir in enumerate(symbol_dirs, 1):
            if i % 200 == 0:
                print(f"  Scanned {i}/{len(symbol_dirs)} symbols...")

            symbol = symbol_dir.name.replace("symbol=", "")
            parquet_files = list(symbol_dir.glob("*.parquet"))
            num_files = len(parquet_files)

            if num_files > threshold:
                # Calculate total size
                total_size = sum(f.stat().st_size for f in parquet_files)
                total_size_mb = total_size / (1024**2)

                massive_symbols.append({
                    "symbol": symbol,
                    "days": num_files,
                    "size_mb": total_size_mb
                })

        massive_symbols.sort(key=lambda x: x['days'], reverse=True)

        if massive_symbols:
            self.add_warning(f"Se encontraron {len(massive_symbols)} símbolos con >{threshold} días de datos")
            print(f"\nTop 10 símbolos más grandes:")
            for sym in massive_symbols[:10]:
                print(f"  {sym['symbol']:6s}: {sym['days']:4d} días, {sym['size_mb']:7.1f} MB")

            if len(massive_symbols) > 10:
                print(f"  ... y {len(massive_symbols) - 10} más")

            print(f"\n⚠️  Estos símbolos pueden causar cuelgues si se procesan con poca RAM")
        else:
            self.add_info(f"No hay símbolos con >{threshold} días de datos")

        return massive_symbols

    def check_recent_shards(self):
        """Check recently generated shards"""
        print(f"\n{'='*80}")
        print(f"[7/8] SHARDS RECIENTES")
        print(f"{'='*80}")

        shards_dir = self.project_root / "processed" / "events" / "shards"

        if not shards_dir.exists():
            self.add_warning("Directorio de shards no existe")
            return

        # Find shards from last 24 hours
        cutoff = datetime.now() - timedelta(hours=24)
        recent_shards = []

        for shard in shards_dir.rglob("*.parquet"):
            mtime = datetime.fromtimestamp(shard.stat().st_mtime)
            if mtime >= cutoff:
                recent_shards.append((shard, mtime))

        recent_shards.sort(key=lambda x: x[1], reverse=True)

        print(f"Shards generados en las últimas 24h: {len(recent_shards)}")

        if recent_shards:
            print(f"\nÚltimos 5 shards:")
            for shard, mtime in recent_shards[:5]:
                age = datetime.now() - mtime
                age_str = str(age).split('.')[0]
                print(f"  {shard.name} ({age_str} ago)")

            latest_mtime = recent_shards[0][1]
            age_latest = datetime.now() - latest_mtime

            if age_latest > timedelta(hours=1):
                self.add_warning(f"Último shard hace {age_latest} (workers posiblemente detenidos)")
            else:
                self.add_info(f"Shards generándose recientemente (último hace {age_latest})")
        else:
            self.add_warning("No se han generado shards en las últimas 24h")

    def check_checkpoint_consistency(self):
        """Check checkpoint consistency"""
        print(f"\n{'='*80}")
        print(f"[8/8] CONSISTENCIA DE CHECKPOINTS")
        print(f"{'='*80}")

        checkpoint_dir = self.project_root / "logs" / "checkpoints"

        if not checkpoint_dir.exists():
            self.add_warning("Directorio de checkpoints no existe")
            return

        # Load all recent checkpoints
        all_completed = set()
        checkpoint_files = []

        for ckpt_file in sorted(checkpoint_dir.glob("events_intraday_*_completed.json")):
            try:
                data = json.load(open(ckpt_file))
                symbols = set(data.get("completed_symbols", []))
                all_completed.update(symbols)
                checkpoint_files.append((ckpt_file.name, len(symbols)))
            except Exception as e:
                self.add_warning(f"Error leyendo checkpoint {ckpt_file.name}: {e}")
                continue

        if not checkpoint_files:
            self.add_warning("No se encontraron checkpoints")
            return

        print(f"Checkpoints encontrados: {len(checkpoint_files)}")
        print(f"Símbolos únicos completados: {len(all_completed)}")

        # Show recent checkpoints
        print(f"\nÚltimos 3 checkpoints:")
        for name, count in checkpoint_files[-3:]:
            print(f"  {name}: {count} symbols")

        expected_total = 1996
        remaining = expected_total - len(all_completed)
        progress = len(all_completed) / expected_total * 100

        print(f"\nProgreso: {len(all_completed)}/{expected_total} ({progress:.1f}%)")
        print(f"Restantes: {remaining}")

        if remaining < 10:
            self.add_info(f"Casi completo: solo {remaining} símbolos restantes")
        elif remaining < 100:
            self.add_info(f"Progreso avanzado: {remaining} símbolos restantes")

    def generate_report(self):
        """Generate final diagnostic report"""
        print(f"\n{'='*80}")
        print(f"RESUMEN DE DIAGNÓSTICO")
        print(f"{'='*80}")

        print(f"\n❌ ISSUES CRÍTICOS: {len(self.issues)}")
        for issue in self.issues:
            print(f"  - {issue}")

        print(f"\n⚠️  WARNINGS: {len(self.warnings)}")
        for warning in self.warnings:
            print(f"  - {warning}")

        print(f"\n✓ INFO: {len(self.info)}")
        if len(self.info) <= 5:
            for info in self.info:
                print(f"  - {info}")
        else:
            print(f"  ({len(self.info)} items - todo OK)")

        print(f"\n{'='*80}")
        if self.issues:
            print(f"❌ VEREDICTO: NO LANZAR - Resolver issues críticos primero")
            return False
        elif len(self.warnings) > 3:
            print(f"⚠️  VEREDICTO: PRECAUCIÓN - Revisar warnings antes de lanzar")
            return False
        else:
            print(f"✅ VEREDICTO: SAFE TO LAUNCH")
            return True

    def run(self, detailed: bool = False, fix_locks: bool = False):
        """Run full diagnostics"""
        print(f"\n{'='*80}")
        print(f"FASE 2.5 - PRE-LAUNCH DIAGNOSTICS")
        print(f"{'='*80}")
        print(f"Project root: {self.project_root}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

        # Run all checks
        self.check_memory()
        self.check_disk_space()
        zombie_locks = self.check_zombie_locks()
        active_procs = self.check_active_processes()
        self.check_heartbeat_freshness()
        massive_symbols = self.check_massive_symbols(threshold=500)
        self.check_recent_shards()
        self.check_checkpoint_consistency()

        # Fix locks if requested
        if fix_locks and zombie_locks:
            print(f"\n{'='*80}")
            print(f"ELIMINANDO LOCKS ZOMBIES")
            print(f"{'='*80}")
            for lock in zombie_locks:
                try:
                    lock.unlink()
                    print(f"✓ Eliminado: {lock.relative_to(self.project_root)}")
                except Exception as e:
                    print(f"✗ Error eliminando {lock.name}: {e}")

        # Generate report
        safe_to_launch = self.generate_report()

        # Additional recommendations
        if massive_symbols:
            print(f"\n{'='*80}")
            print(f"RECOMENDACIONES PARA SÍMBOLOS MASIVOS")
            print(f"{'='*80}")
            print(f"Símbolos con >500 días detectados: {len(massive_symbols)}")
            print(f"Considera:")
            print(f"  1. Aumentar RAM disponible (cerrar otras apps)")
            print(f"  2. Procesarlos por separado con --limit 1")
            print(f"  3. Excluirlos temporalmente y procesarlos al final")

        if active_procs:
            print(f"\n{'='*80}")
            print(f"RECOMENDACIÓN: MATAR PROCESOS ACTIVOS")
            print(f"{'='*80}")
            print(f"Ejecutar: python restart_parallel.py")

        return safe_to_launch


def main():
    parser = argparse.ArgumentParser(
        description="Pre-launch diagnostics for FASE 2.5"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed information"
    )
    parser.add_argument(
        "--fix-locks",
        action="store_true",
        help="Automatically remove zombie lock files"
    )

    args = parser.parse_args()

    diagnostics = PreLaunchDiagnostics()
    safe = diagnostics.run(detailed=args.detailed, fix_locks=args.fix_locks)

    sys.exit(0 if safe else 1)


if __name__ == "__main__":
    main()
