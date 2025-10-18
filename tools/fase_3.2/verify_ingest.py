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

    # Scan raw data on disk (event_windows structure)
    event_windows_dir = root / "raw" / "market_data" / "event_windows"
    if not event_windows_dir.exists():
        print(f"WARNING: Event windows directory not found: {event_windows_dir}")
        return 0

    print(f"Scanning raw data in: {event_windows_dir}")
    print()

    # Count events per symbol (complete = both trades + quotes)
    symbol_files = defaultdict(int)
    symbol_events_complete = defaultdict(int)
    symbol_events_partial = defaultdict(int)
    completed_events = set()

    # Scan event_windows structure: symbol=XXX/event=YYY/
    for symbol_dir in event_windows_dir.glob("symbol=*"):
        if not symbol_dir.is_dir():
            continue

        # Extract symbol name from "symbol=XXX"
        symbol = symbol_dir.name.replace("symbol=", "")

        for event_dir in symbol_dir.glob("event=*"):
            if not event_dir.is_dir():
                continue

            # Extract event ID from "event=YYY"
            event_id = event_dir.name.replace("event=", "")

            trades = event_dir / "trades.parquet"
            quotes = event_dir / "quotes.parquet"

            if trades.exists() and quotes.exists():
                # Complete event (both files)
                symbol_events_complete[symbol] += 1
                symbol_files[symbol] += 2
                completed_events.add(event_id)
            elif trades.exists() or quotes.exists():
                # Partial event (one file only)
                symbol_events_partial[symbol] += 1
                symbol_files[symbol] += 1

    have = set(symbol_files.keys())
    total_complete_events = sum(symbol_events_complete.values())
    total_partial_events = sum(symbol_events_partial.values())

    print(f"Symbols with raw data on disk: {len(have)}")
    print(f"Complete events (trades + quotes): {total_complete_events}")
    print(f"Partial events (one file only): {total_partial_events}")
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
    print(f"Symbols on disk: {len(have)}")
    print(f"Complete events on disk: {total_complete_events}")
    print(f"Partial events on disk: {total_partial_events}")
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

    # Progress percentage from manifest
    manifest_candidates = [
        root / "processed/events/manifest_core_5y_20251017.parquet",
        root / "processed/events/manifest_core_FULL.parquet",
    ]
    manifest_path = None
    for candidate in manifest_candidates:
        if candidate.exists():
            manifest_path = candidate
            break

    if manifest_path:
        try:
            import polars as pl
            man = pl.read_parquet(manifest_path)
            total_events = man.height
            pct_complete = (total_complete_events / total_events) * 100
            events_remaining = total_events - total_complete_events

            print("=" * 60)
            print("PROGRESS ESTIMATE")
            print("=" * 60)
            print()
            print(f"  Manifest: {manifest_path.name}")
            print(f"  Total events in manifest: {total_events:,}")
            print(f"  Completed events: {total_complete_events:,} ({pct_complete:.2f}%)")
            print(f"  Remaining events: {events_remaining:,}")
            print()

            # Estimate completion time
            if total_complete_events > 0:
                # Rough estimate based on 13.1 events/min from previous session
                events_per_min = 13.1
                minutes_remaining = events_remaining / events_per_min
                hours_remaining = minutes_remaining / 60
                days_remaining = hours_remaining / 24
                print(f"  Estimated time remaining: ~{days_remaining:.1f} days")
                print(f"    (assuming ~{events_per_min} events/min)")
                print()

        except ImportError:
            pass
        except Exception as e:
            print(f"WARNING: Could not read manifest: {e}")
            print()

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
