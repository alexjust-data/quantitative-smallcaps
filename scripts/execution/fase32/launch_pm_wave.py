#!/usr/bin/env python3
"""
Launch FASE 3.2 PM Wave in a subprocess
This keeps the process running even if the parent terminal closes
"""

import subprocess
import sys
from pathlib import Path

print("="*60)
print("LAUNCHING FASE 3.2 - PM WAVE")
print("="*60)
print()
print("Manifest: processed/events/manifest_core_20251014.parquet")
print("Wave: PM (1,452 events)")
print("Rate limit: 12s")
print("Quotes Hz: 1")
print("Resume: enabled")
print()
print("Log file: logs/fase3.2_pm_wave_running.log")
print()
print("="*60)
print()

# Prepare command
cmd = [
    sys.executable,
    "scripts/ingestion/download_trades_quotes_intraday_v2.py",
    "--manifest", "processed/events/manifest_core_20251014.parquet",
    "--wave", "PM",
    "--rate-limit", "12",
    "--quotes-hz", "1",
    "--resume"
]

# Launch subprocess
log_file = Path("logs/fase3.2_pm_wave_running.log")
log_file.parent.mkdir(parents=True, exist_ok=True)

print(f"Launching process...")
print(f"Command: {' '.join(cmd)}")
print()

with open(log_file, 'w') as f:
    process = subprocess.Popen(
        cmd,
        stdout=f,
        stderr=subprocess.STDOUT,
        cwd=Path.cwd()
    )

print(f"✓ Process launched with PID: {process.pid}")
print()
print("To monitor progress:")
print(f"  tail -f {log_file}")
print()
print("To check if running:")
print(f"  ps -p {process.pid}")
print()
print("Process will continue running in background...")
print()
