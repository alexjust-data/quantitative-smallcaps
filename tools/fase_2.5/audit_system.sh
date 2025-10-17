#!/bin/bash
# ================================================================================
# AUDIT SYSTEM - FASE 2.5 Status Monitor (FIXED)
# ================================================================================
# This script now correctly merges multiple checkpoints to show real progress

# Change to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT" || exit 1

echo ""
echo "================================================================================"
echo "AUDITORIA DEL SISTEMA FASE 2.5"
echo "================================================================================"
echo "Working directory: $PROJECT_ROOT"
echo "Fecha: $(date)"
echo ""

echo "--------------------------------------------------------------------------------"
echo "[1/5] PROCESOS ACTIVOS"
echo "--------------------------------------------------------------------------------"
ps aux | grep -E "(detect_events|watchdog|launch_parallel)" | grep python | grep -v grep || echo "No hay procesos activos"

echo ""
echo "--------------------------------------------------------------------------------"
echo "[2/5] CHECKPOINT - PROGRESO REAL (CORREGIDO)"
echo "--------------------------------------------------------------------------------"
echo "Merging all recent checkpoints (last 7 days)..."
echo ""

python << 'EOF'
import json
from pathlib import Path
from datetime import datetime, timedelta

# Find all checkpoint files from last 7 days
checkpoint_dir = Path("logs/checkpoints")
today = datetime.now()
cutoff = today - timedelta(days=7)

all_completed = set()
checkpoint_files = []

for ckpt_file in sorted(checkpoint_dir.glob("events_intraday_*_completed.json")):
    try:
        # Extract date from filename: events_intraday_YYYYMMDD_completed.json
        date_str = ckpt_file.stem.replace("events_intraday_", "").replace("_completed", "")
        file_date = datetime.strptime(date_str, "%Y%m%d")

        if file_date >= cutoff:
            data = json.load(open(ckpt_file))
            symbols = set(data.get("completed_symbols", []))
            checkpoint_files.append((file_date, ckpt_file.name, len(symbols)))
            all_completed.update(symbols)
    except Exception as e:
        print(f"Warning: Failed to parse {ckpt_file.name}: {e}")
        continue

total_symbols = 1996
completed = len(all_completed)
remaining = total_symbols - completed
progress = (completed / total_symbols) * 100 if total_symbols > 0 else 0

print(f"Checkpoint files found: {len(checkpoint_files)}")
for date, name, count in checkpoint_files:
    print(f"  - {name}: {count} symbols ({date.strftime('%Y-%m-%d')})")

print(f"\n{'='*60}")
print(f"PROGRESO REAL (merged from all checkpoints):")
print(f"{'='*60}")
print(f"Total symbols: {total_symbols}")
print(f"Completed: {completed}")
print(f"Remaining: {remaining}")
print(f"Progress: {progress:.1f}%")
print(f"{'='*60}")

if checkpoint_files:
    latest_date, latest_file, _ = checkpoint_files[-1]
    print(f"\nLast checkpoint: {latest_file}")
    print(f"Last updated: {latest_date.strftime('%Y-%m-%d')}")
EOF

echo ""
echo "--------------------------------------------------------------------------------"
echo "[3/5] HEARTBEAT - ULTIMAS 30 LINEAS"
echo "--------------------------------------------------------------------------------"
# Find most recent heartbeat file
HEARTBEAT_FILE=$(ls -t logs/detect_events/heartbeat_*.log 2>/dev/null | head -1)
if [ -z "$HEARTBEAT_FILE" ]; then
    echo "No heartbeat file found"
else
    echo "File: $HEARTBEAT_FILE"
    echo ""
    tail -30 "$HEARTBEAT_FILE"
fi

echo ""
echo "--------------------------------------------------------------------------------"
echo "[4/5] ESTADISTICAS DE ACTIVIDAD"
echo "--------------------------------------------------------------------------------"
python << 'EOF'
import json
from pathlib import Path
from datetime import datetime

# Find most recent heartbeat
hb_files = sorted(Path("logs/detect_events").glob("heartbeat_*.log"), reverse=True)
if hb_files:
    hb_file = hb_files[0]
    with open(hb_file) as f:
        lines = f.readlines()

    print(f"Heartbeat file: {hb_file.name}")
    print(f"Total heartbeat entries: {len(lines)}")

    if lines:
        last_line = lines[-1]
        ts = last_line.split('\t')[0]
        print(f"Last activity: {ts}")

# Calculate remaining based on merged checkpoints
checkpoint_dir = Path("logs/checkpoints")
all_completed = set()

for ckpt_file in checkpoint_dir.glob("events_intraday_*_completed.json"):
    try:
        data = json.load(open(ckpt_file))
        symbols = data.get("completed_symbols", [])
        all_completed.update(symbols)
    except:
        continue

remaining = 1996 - len(all_completed)
workers = 4
symbols_per_hour_per_worker = 10

if remaining > 0:
    hours_remaining = remaining / (workers * symbols_per_hour_per_worker)
    print(f"\nEstimated completion:")
    print(f"  Remaining symbols: {remaining}")
    print(f"  Active workers: {workers}")
    print(f"  Speed: ~{symbols_per_hour_per_worker} sym/h per worker")
    print(f"  ETA: ~{hours_remaining:.1f} hours")
else:
    print("\n✅ All symbols completed!")
EOF

echo ""
echo "--------------------------------------------------------------------------------"
echo "[5/5] LOGS DE WORKERS (ultimas 10 lineas c/u)"
echo "--------------------------------------------------------------------------------"

for i in 1 2 3 4; do
    echo ""
    echo "=== WORKER $i ==="

    # Try multiple log file patterns
    LOG_FILE=""
    if [ -f "logs/worker_${i}_detection.log" ]; then
        LOG_FILE="logs/worker_${i}_detection.log"
    elif [ -f "logs/detect_events/worker_${i}_detection.log" ]; then
        LOG_FILE="logs/detect_events/worker_${i}_detection.log"
    else
        # Find most recent worker log
        LOG_FILE=$(find logs -name "*worker_${i}*.log" -type f -mtime -1 2>/dev/null | head -1)
    fi

    if [ -n "$LOG_FILE" ] && [ -f "$LOG_FILE" ]; then
        tail -10 "$LOG_FILE"
    else
        echo "No recent log file found"
    fi
done

echo ""
echo "================================================================================"
echo "AUDITORIA COMPLETADA"
echo "================================================================================"
echo ""
