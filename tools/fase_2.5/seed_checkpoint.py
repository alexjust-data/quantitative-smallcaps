#!/usr/bin/env python3
"""
Seed checkpoint from existing shards.

Usage:
    python tools/seed_checkpoint.py events_intraday_20251012

This will scan all shards for the specified run_id and create a checkpoint
file with all symbols found in those shards.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def seed_checkpoint(run_id: str, target_run_id: str = None):
    """
    Scan all shards for run_id and create checkpoint with completed symbols.

    Args:
        run_id: Run ID to scan shards for (e.g., events_intraday_20251012)
        target_run_id: Target run ID for checkpoint (defaults to today's date)
    """
    shards_dir = PROJECT_ROOT / "processed" / "events" / "shards"
    checkpoint_dir = PROJECT_ROOT / "logs" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Find all shards for this run_id (including worker_* subdirs)
    files = sorted(shards_dir.rglob(f"**/{run_id}_shard*.parquet"))

    if not files:
        print(f"ERROR: No shards found for run_id: {run_id}")
        print(f"Searched in: {shards_dir}")
        return 1

    print(f"Found {len(files)} shards for {run_id}")
    print(f"Scanning for symbols...")

    # Collect all unique symbols from all shards
    syms = set()
    for f in files:
        try:
            df = pl.read_parquet(f, columns=["symbol"])
            symbols_in_shard = df["symbol"].unique().to_list()
            syms.update(symbols_in_shard)
            print(f"  {f.name}: {len(symbols_in_shard)} unique symbols")
        except Exception as e:
            print(f"  WARNING: Failed to read {f.name}: {e}")
            continue

    print(f"\nTotal unique symbols found: {len(syms)}")

    # Use target_run_id if provided, otherwise today's date
    if target_run_id is None:
        target_run_id = f"events_intraday_{datetime.now().strftime('%Y%m%d')}"

    # Create checkpoint file
    checkpoint_file = checkpoint_dir / f"{target_run_id}_completed.json"

    checkpoint_data = {
        "run_id": target_run_id,
        "completed_symbols": sorted(list(syms)),
        "total_completed": len(syms),
        "last_updated": datetime.now().isoformat(),
        "seeded_from": run_id,
        "seeded_at": datetime.now().isoformat()
    }

    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, indent=2)

    print(f"\nCheckpoint created: {checkpoint_file}")
    print(f"Run ID: {target_run_id}")
    print(f"Symbols marked as completed: {len(syms)}")

    return 0

def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/seed_checkpoint.py <run_id> [target_run_id]")
        print("\nExample:")
        print("  python tools/seed_checkpoint.py events_intraday_20251012")
        print("  python tools/seed_checkpoint.py events_intraday_20251012 events_intraday_20251014")
        return 1

    run_id = sys.argv[1]
    target_run_id = sys.argv[2] if len(sys.argv) > 2 else None

    return seed_checkpoint(run_id, target_run_id)

if __name__ == "__main__":
    sys.exit(main())
