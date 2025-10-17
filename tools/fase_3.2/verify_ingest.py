#!/usr/bin/env python3
"""
Verify ingestion progress by comparing checkpoint vs actual raw data on disk.
Shows symbols completed, symbols with raw data, and symbols in progress.
"""
from pathlib import Path
import json
import argparse
from datetime import datetime
from collections import defaultdict

def main():
    ap = argparse.ArgumentParser(description="Verify ingestion progress")
    ap.add_argument("--run-date", default=datetime.now().strftime("%Y%m%d"),
                    help="Run date for checkpoint file (YYYYMMDD)")
    ap.add_argument("--raw-root", default="raw",
                    help="Root directory for raw data")
    ap.add_argument("--checkpoint-dir", default="logs/checkpoints",
                    help="Checkpoint directory")
    ap.add_argument("--sample", type=int, default=10,
                    help="Number of in-progress symbols to show")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]

    # Read checkpoint
    ckpt_path = root / args.checkpoint_dir / f"events_intraday_{args.run_date}_completed.json"
    if not ckpt_path.exists():
        print(f"WARNING: Checkpoint not found: {ckpt_path}")
        print("Trying most recent checkpoint...")
        ckpt_files = sorted((root / args.checkpoint_dir).glob("events_intraday_*.json"))
        if not ckpt_files:
            print("ERROR: No checkpoint files found")
            return 1
        ckpt_path = ckpt_files[-1]
        print(f"Using: {ckpt_path}")

    data = json.loads(ckpt_path.read_text(encoding="utf-8"))
    done = set(data.get("completed_symbols", []))
    total_completed = data.get("total_completed", len(done))
    last_update = data.get("last_updated", "unknown")

    print("=" * 60)
    print("INGESTION PROGRESS VERIFICATION")
    print("=" * 60)
    print()
    print(f"Checkpoint: {ckpt_path.name}")
    print(f"Last updated: {last_update}")
    print(f"Symbols completed: {total_completed}")
    print()

    # Scan raw data on disk
    raw_root = root / args.raw_root
    if not raw_root.exists():
        print(f"WARNING: Raw data directory not found: {raw_root}")
        return 0

    print(f"Scanning raw data in: {raw_root}")
    print()

    # Count files per symbol
    symbol_files = defaultdict(int)

    # Scan trades
    trades_dir = raw_root / "trades"
    if trades_dir.exists():
        for sym_dir in trades_dir.iterdir():
            if sym_dir.is_dir():
                symbol = sym_dir.name
                file_count = len(list(sym_dir.glob("*.parquet")))
                symbol_files[symbol] += file_count

    # Scan quotes
    quotes_dir = raw_root / "quotes"
    if quotes_dir.exists():
        for sym_dir in quotes_dir.iterdir():
            if sym_dir.is_dir():
                symbol = sym_dir.name
                file_count = len(list(sym_dir.glob("*.parquet")))
                symbol_files[symbol] += file_count

    have = set(symbol_files.keys())

    print(f"Symbols with raw data on disk: {len(have)}")
    print()

    # Analysis
    in_progress = sorted(have - done)
    not_started = done - have  # Marked complete but no files (edge case)

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()
    print(f"Checkpoint completed: {len(done)}")
    print(f"Raw data on disk: {len(have)}")
    print(f"In progress: {len(in_progress)}")
    if not_started:
        print(f"Marked complete but no raw files: {len(not_started)}")
    print()

    # Show in-progress symbols
    if in_progress:
        print("=" * 60)
        print(f"IN-PROGRESS SYMBOLS (showing {min(args.sample, len(in_progress))} of {len(in_progress)})")
        print("=" * 60)
        print()
        for i, sym in enumerate(in_progress[:args.sample], 1):
            files = symbol_files.get(sym, 0)
            print(f"  {i:3d}. {sym:8s} ({files:3d} files)")
        if len(in_progress) > args.sample:
            print(f"  ... and {len(in_progress) - args.sample} more")
        print()

    # File count distribution
    if have:
        print("=" * 60)
        print("FILE COUNT DISTRIBUTION")
        print("=" * 60)
        print()
        file_counts = sorted(symbol_files.values())
        min_files = min(file_counts)
        max_files = max(file_counts)
        avg_files = sum(file_counts) / len(file_counts)
        print(f"  Min files per symbol: {min_files}")
        print(f"  Max files per symbol: {max_files}")
        print(f"  Avg files per symbol: {avg_files:.1f}")
        print()

    # Progress percentage
    # Estimate: if we know total symbols from manifest
    manifest_path = root / "processed/events/manifest_core_FULL.parquet"
    if manifest_path.exists():
        try:
            import polars as pl
            man = pl.read_parquet(manifest_path)
            total_symbols = man.height
            pct_complete = (len(done) / total_symbols) * 100
            print("=" * 60)
            print("PROGRESS ESTIMATE")
            print("=" * 60)
            print()
            print(f"  Total symbols in manifest: {total_symbols}")
            print(f"  Completed: {len(done)} ({pct_complete:.1f}%)")
            print(f"  Remaining: {total_symbols - len(done)}")
            print()
        except ImportError:
            pass

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
