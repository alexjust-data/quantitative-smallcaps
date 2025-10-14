#!/usr/bin/env python3
"""
Launch parallel intraday event detection across multiple workers
Each worker processes a separate subset of symbols to maximize throughput
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parent

def main():
    # Load all symbols and checkpoint
    symbols_file = PROJECT_ROOT / "processed" / "reference" / "symbols_with_1m.parquet"
    checkpoint_file = PROJECT_ROOT / "logs" / "checkpoints" / "events_intraday_20251013_completed.json"

    # Read all symbols
    all_symbols = pl.read_parquet(symbols_file)["symbol"].to_list()
    print(f"Total symbols: {len(all_symbols)}")

    # Read completed symbols
    if checkpoint_file.exists():
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)
        completed = set(checkpoint.get("completed_symbols", []))
        print(f"Completed symbols: {len(completed)}")
    else:
        completed = set()

    # Calculate remaining symbols
    remaining = [s for s in all_symbols if s not in completed]
    print(f"Remaining symbols: {len(remaining)}")

    if not remaining:
        print("All symbols already processed!")
        return 0

    # Divide into N workers
    num_workers = 4
    chunk_size = len(remaining) // num_workers

    workers = []
    for i in range(num_workers):
        start_idx = i * chunk_size
        if i == num_workers - 1:
            # Last worker gets any remainder
            end_idx = len(remaining)
        else:
            end_idx = (i + 1) * chunk_size

        worker_symbols = remaining[start_idx:end_idx]
        workers.append({
            "worker_id": i + 1,
            "symbols": worker_symbols,
            "count": len(worker_symbols)
        })

    # Display plan
    print("\n" + "="*80)
    print("PARALLEL PROCESSING PLAN")
    print("="*80)
    for w in workers:
        print(f"Worker {w['worker_id']}: {w['count']} symbols ({w['symbols'][0]} ... {w['symbols'][-1]})")
    print("="*80)

    # Ask for confirmation
    response = input("\nStart parallel processing? (yes/no): ")
    if response.lower() not in ['yes', 'y', 'si', 's']:
        print("Aborted.")
        return 0

    # Create symbol list files for each worker
    worker_files = []
    for w in workers:
        worker_file = PROJECT_ROOT / f"worker_{w['worker_id']}_symbols.txt"
        with open(worker_file, 'w') as f:
            for sym in w['symbols']:
                f.write(f"{sym}\n")
        worker_files.append(worker_file)
        print(f"Created: {worker_file}")

    # Launch workers
    print("\n" + "="*80)
    print("LAUNCHING WORKERS")
    print("="*80)

    processes = []
    for i, (w, wfile) in enumerate(zip(workers, worker_files)):
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "processing" / "detect_events_intraday.py"),
            "--from-file", str(wfile),
            "--batch-size", "50",
            "--checkpoint-interval", "1"
            # NOTE: No --resume flag, each worker processes its own fresh list
        ]

        # Open log file for this worker
        log_file = PROJECT_ROOT / "logs" / f"worker_{w['worker_id']}_detection.log"
        log_f = open(log_file, 'w')

        print(f"Worker {w['worker_id']}: Starting...")
        proc = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=PROJECT_ROOT
        )
        processes.append({
            "worker_id": w['worker_id'],
            "proc": proc,
            "log_file": log_file,
            "log_handle": log_f
        })
        print(f"  PID: {proc.pid}")
        print(f"  Log: {log_file}")

    print("\n" + "="*80)
    print(f"All {num_workers} workers launched successfully!")
    print("="*80)
    print("\nMonitoring commands:")
    print("  - Check processes: python check_processes.py")
    print("  - View logs: tail -f logs/worker_N_detection.log")
    print("  - Check progress: tail -f logs/detect_events/heartbeat_20251013.log")
    print("\nPress Ctrl+C to stop all workers...")

    try:
        # Wait for all processes to complete
        for p in processes:
            p["proc"].wait()
            p["log_handle"].close()
            print(f"Worker {p['worker_id']} finished with exit code {p['proc'].returncode}")
    except KeyboardInterrupt:
        print("\n\nStopping all workers...")
        for p in processes:
            try:
                p["proc"].terminate()
                p["proc"].wait(timeout=5)
            except:
                p["proc"].kill()
            p["log_handle"].close()
        print("All workers stopped.")
        return 1

    print("\n" + "="*80)
    print("ALL WORKERS COMPLETED")
    print("="*80)

    # Cleanup worker files
    for wfile in worker_files:
        wfile.unlink()

    return 0

if __name__ == "__main__":
    sys.exit(main())
