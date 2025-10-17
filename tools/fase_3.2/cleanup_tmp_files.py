#!/usr/bin/env python3
"""
Clean up orphaned .tmp files from Polygon ingestion.
- If final .parquet exists: remove .tmp (redundant)
- If .tmp is valid and final doesn't exist: rename to final
- If .tmp is corrupt: delete (will be re-downloaded)
"""
from pathlib import Path
import polars as pl
import os

ROOT = Path(r"D:\04_TRADING_SMALLCAPS")
raw_root = ROOT / "raw" / "market_data" / "event_windows"

print("=" * 60)
print("CLEANUP ORPHANED .tmp FILES")
print("=" * 60)

tmp_files = list(raw_root.rglob("*.parquet.tmp"))
print(f"Found {len(tmp_files)} .tmp files")
print()

fixed = 0
removed = 0
skipped = 0

for tmp_path in tmp_files:
    final_path = tmp_path.with_suffix("")  # Remove .tmp extension

    try:
        if final_path.exists():
            # Final file already exists, remove tmp
            tmp_path.unlink(missing_ok=True)
            removed += 1
            print(f"[REMOVED] {tmp_path.name} (final exists)")
            continue

        # Try to validate tmp file
        try:
            df = pl.read_parquet(tmp_path, n_rows=10)
            # Valid parquet, rename to final
            os.replace(str(tmp_path), str(final_path))
            fixed += 1
            print(f"[FIXED] {tmp_path.name} → {final_path.name}")
        except Exception as read_err:
            # Corrupt file, delete it
            tmp_path.unlink(missing_ok=True)
            removed += 1
            print(f"[REMOVED] {tmp_path.name} (corrupt: {read_err})")

    except Exception as e:
        print(f"[SKIPPED] {tmp_path.name}: {e}")
        skipped += 1

print()
print("=" * 60)
print(f"RESULTS:")
print(f"  Fixed (renamed to final): {fixed}")
print(f"  Removed (redundant/corrupt): {removed}")
print(f"  Skipped (errors): {skipped}")
print("=" * 60)
