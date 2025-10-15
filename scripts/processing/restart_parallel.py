#!/usr/bin/env python3
"""
Kill all detection/watchdog/orchestrator processes and (optionally) relaunch the parallel launcher.

Usage:
    # Only kill/blockers & clean locks
    python restart_parallel.py

    # Kill then start launcher immediately with flags
    python restart_parallel.py --start --workers 4 --batch-size 50 --yes
"""

import argparse
import psutil
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]

KILL_PATTERNS = [
    "run_watchdog",                 # watchdog script
    "detect_events_intraday.py",    # detector
    "ultra_robust_orchestrator.py", # orchestrator
    "launch_parallel_detection.py", # launcher (avoid double-launch)
]

PID_FILES = [
    PROJECT_ROOT / "logs" / "detect_events" / "watchdog.pid",
    PROJECT_ROOT / "logs" / "detect_events" / "detection_process.pid",
]

def kill_processes() -> tuple[int, int]:
    print("Killing detection/orchestrator/watchdog processes...")
    killed = 0
    errors = 0

    for proc in psutil.process_iter(['pid', 'cmdline', 'name']):
        try:
            cmdline = proc.info.get("cmdline") or []
            cmd = " ".join(cmdline).lower()
            if any(pat.lower() in cmd for pat in KILL_PATTERNS):
                print(f"  Killing PID {proc.pid}: {cmdline}")
                proc.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            errors += 1
            continue

    # Give OS time to reap
    time.sleep(2)

    # Verify none remain
    remaining = 0
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = proc.info.get("cmdline") or []
            cmd = " ".join(cmdline).lower()
            if any(pat.lower() in cmd for pat in KILL_PATTERNS):
                remaining += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if remaining > 0:
        print(f"WARNING: {remaining} matching processes are still running.")
    else:
        print(f"OK. Killed {killed} process(es).")

    return killed, remaining

def clean_locks_and_pids():
    print("Cleaning PID files and run locks...")

    # Remove PID files
    for pf in PID_FILES:
        try:
            if pf.exists():
                pf.unlink()
                print(f"  Removed {pf}")
        except Exception as e:
            print(f"  WARN: could not remove {pf}: {e}")

    # Remove today's locks
    today = datetime.now().strftime("%Y%m%d")
    locks = [
        PROJECT_ROOT / "logs" / "checkpoints" / f"events_intraday_{today}.lock",
        PROJECT_ROOT / "processed" / "events" / "shards" / f"events_intraday_{today}.lock",
    ]
    for lf in locks:
        try:
            if lf.exists():
                lf.unlink()
                print(f"  Removed {lf}")
        except Exception as e:
            print(f"  WARN: could not remove {lf}: {e}")

def relaunch_launcher(workers: int, batch_size: int, checkpoint_interval: int, assume_yes: bool,
                      start_date: str | None, end_date: str | None):
    print("\nStarting parallel launcher...")
    cmd = [
        sys.executable, "-u",
        str(PROJECT_ROOT / "launch_parallel_detection.py"),
        "--workers", str(workers),
        "--batch-size", str(batch_size),
        "--checkpoint-interval", str(checkpoint_interval),
    ]
    if assume_yes:
        cmd.append("--yes")
    if start_date:
        cmd += ["--start-date", start_date]
    if end_date:
        cmd += ["--end-date", end_date]

    print("  Exec:", " ".join(cmd))
    return subprocess.call(cmd, cwd=PROJECT_ROOT)

def main():
    parser = argparse.ArgumentParser(description="Restart helper: kill processes, clean locks, (optionally) relaunch launcher")
    parser.add_argument("--start", action="store_true", help="Start launcher after cleanup")
    parser.add_argument("--workers", type=int, default=4, help="Workers for launcher (default: 4)")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for launcher (default: 50)")
    parser.add_argument("--checkpoint-interval", type=int, default=1, help="Launcher checkpoint interval (default: 1)")
    parser.add_argument("--yes", action="store_true", help="Assume yes for launcher")
    parser.add_argument("--start-date", help="Optional YYYY-MM-DD for launcher")
    parser.add_argument("--end-date", help="Optional YYYY-MM-DD for launcher")
    args = parser.parse_args()

    kill_processes()
    clean_locks_and_pids()

    if args.start:
        rc = relaunch_launcher(
            workers=args.workers,
            batch_size=args.batch_size,
            checkpoint_interval=args.checkpoint_interval,
            assume_yes=args.yes,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        return rc

    print("\nDone. To start now, run:")
    print(f"  python {PROJECT_ROOT / 'launch_parallel_detection.py'} --workers {args.workers} --batch-size {args.batch_size} --checkpoint-interval {args.checkpoint_interval} --yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
