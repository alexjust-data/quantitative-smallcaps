#!/usr/bin/env python3
"""
Launch parallel intraday event detection across multiple workers
- Partitions symbols into disjoint subsets (no overlap)
- Forces --resume
- Isolates shard outputs per worker: processed/events/shards/worker_{id}
- Logs per worker

Usage:
    python launch_parallel_detection.py
    python launch_parallel_detection.py --workers 4 --batch-size 50 --yes
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def load_all_symbols(symbols_source: Path) -> list[str]:
    if symbols_source.suffix.lower() == ".parquet":
        df = pl.read_parquet(symbols_source)
        # Accept either single-column symbol list or a column named 'symbol'
        cols = df.columns
        if "symbol" in cols:
            symbols = df["symbol"].unique().to_list()
        else:
            # first column fallback
            symbols = df.select(pl.all().first()).to_series().to_list()
        return [str(s) for s in symbols]
    elif symbols_source.suffix.lower() in (".txt", ".csv"):
        return [line.strip() for line in symbols_source.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        raise ValueError(f"Unsupported symbols file: {symbols_source}")

def read_checkpoint_completed(run_id: str, checkpoint_file: Path) -> set[str]:
    if not checkpoint_file.exists():
        return set()
    try:
        data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        return set(data.get("completed_symbols", []))
    except Exception:
        return set()

def main():
    parser = argparse.ArgumentParser(description="Parallel launcher for detect_events_intraday")
    parser.add_argument("--symbols-file",
                        default=str(PROJECT_ROOT / "processed" / "reference" / "symbols_with_1m.parquet"),
                        help="Path to symbols list (parquet/txt/csv). Default: processed/reference/symbols_with_1m.parquet")
    parser.add_argument("--workers", type=int, default=4, help="Number of workers (default: 4)")
    parser.add_argument("--batch-size", type=int, default=50, help="Symbols per batch (default: 50)")
    parser.add_argument("--checkpoint-interval", type=int, default=1, help="Checkpoint every N batches (default: 1)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--start-date", help="Optional YYYY-MM-DD")
    parser.add_argument("--end-date", help="Optional YYYY-MM-DD")
    args = parser.parse_args()

    symbols_file = Path(args.symbols_file)
    if not symbols_file.exists():
        print(f"ERROR: Symbols file not found: {symbols_file}")
        return 1

    # Determine today's run_id and checkpoint path
    run_id = f"events_intraday_{datetime.now().strftime('%Y%m%d')}"
    checkpoint_file = PROJECT_ROOT / "logs" / "checkpoints" / f"{run_id}_completed.json"

    # Load all symbols & completed
    all_symbols = load_all_symbols(symbols_file)
    print(f"Total symbols: {len(all_symbols)}")

    completed = read_checkpoint_completed(run_id, checkpoint_file)
    print(f"Completed symbols (checkpoint): {len(completed)}")

    # Remaining symbols for this run
    remaining = [s for s in all_symbols if s not in completed]
    print(f"Remaining symbols: {len(remaining)}")

    if not remaining:
        print("All symbols already processed for the current run_id.")
        return 0

    # Partition remaining into disjoint chunks (no overlaps)
    num_workers = max(1, args.workers)
    chunks: list[list[str]] = [[] for _ in range(num_workers)]
    for idx, sym in enumerate(remaining):
        chunks[idx % num_workers].append(sym)

    # Display plan
    print("\n" + "=" * 80)
    print("PARALLEL PROCESSING PLAN")
    print("=" * 80)
    for wid, syms in enumerate(chunks, start=1):
        if syms:
            print(f"Worker {wid}: {len(syms)} symbols ({syms[0]} ... {syms[-1]})")
        else:
            print(f"Worker {wid}: 0 symbols")
    print("=" * 80)

    if not args.yes:
        response = input("\nStart parallel processing? (yes/no): ").strip().lower()
        if response not in {"y", "yes", "s", "si"}:
            print("Aborted.")
            return 0

    # Create symbol list files and output dirs, then launch workers
    processes = []
    worker_files = []
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    for wid, syms in enumerate(chunks, start=1):
        # Worker symbols file
        worker_file = PROJECT_ROOT / f"worker_{wid}_symbols.txt"
        worker_file.write_text("\n".join(syms), encoding="utf-8")
        worker_files.append(worker_file)

        # Output dir per worker
        out_dir = PROJECT_ROOT / "processed" / "events" / "shards" / f"worker_{wid}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Log per worker
        log_file = logs_dir / f"worker_{wid}_detection.log"
        log_fh = open(log_file, "w", encoding="utf-8")

        cmd = [
            sys.executable, "-u",
            str(PROJECT_ROOT / "scripts" / "processing" / "detect_events_intraday.py"),
            "--from-file", str(worker_file),
            "--batch-size", str(args.batch_size),
            "--checkpoint-interval", str(args.checkpoint_interval),
            "--resume",
            "--output-dir", str(out_dir),
        ]
        if args.start_date:
            cmd += ["--start-date", args.start_date]
        if args.end_date:
            cmd += ["--end-date", args.end_date]

        print(f"\nWorker {wid}: Starting...")
        print(f"  PID/log: {log_file}")
        proc = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT, cwd=PROJECT_ROOT)
        processes.append({"wid": wid, "proc": proc, "log_handle": log_fh, "log_file": log_file})

    print("\n" + "=" * 80)
    print(f"All {num_workers} workers launched successfully!")
    print("=" * 80)
    print("\nMonitoring tips:")
    print(f"  - Heartbeat: tail -f logs/detect_events/heartbeat_{datetime.now().strftime('%Y%m%d')}.log")
    print("  - Worker logs: tail -f logs/worker_N_detection.log")
    print("Press Ctrl+C to stop all workers...")

    try:
        # Wait for all processes to complete
        for p in processes:
            p["proc"].wait()
            p["log_handle"].close()
            print(f"Worker {p['wid']} finished with exit code {p['proc'].returncode}")
    except KeyboardInterrupt:
        print("\nStopping all workers...")
        for p in processes:
            try:
                p["proc"].terminate()
                p["proc"].wait(timeout=5)
            except Exception:
                p["proc"].kill()
            p["log_handle"].close()
        print("All workers stopped.")
        return 1

    # Cleanup worker files
    for wfile in worker_files:
        try:
            wfile.unlink()
        except Exception:
            pass

    print("\n" + "=" * 80)
    print("ALL WORKERS COMPLETED")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
