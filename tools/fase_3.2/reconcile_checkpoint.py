#!/usr/bin/env python3
"""
Reconcile checkpoint with actual progress on disk.
Scans raw data directory and updates checkpoint to reflect reality.
"""
from pathlib import Path
import json
from datetime import datetime

ROOT = Path(r"D:\04_TRADING_SMALLCAPS")
run_date = datetime.now().strftime("%Y%m%d")
run_id = f"events_intraday_{run_date}"
ckpt_path = ROOT / "logs" / "checkpoints" / f"{run_id}_completed.json"
ckpt_path.parent.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("CHECKPOINT RECONCILIATION")
print("=" * 60)

# Scan raw data for completed events
completed_events = set()
raw_root = ROOT / "raw" / "market_data" / "event_windows"

if raw_root.exists():
    for event_dir in raw_root.rglob("event=*"):
        if event_dir.is_dir():
            trades = event_dir / "trades.parquet"
            quotes = event_dir / "quotes.parquet"

            # Only count as complete if BOTH files exist (no .tmp)
            if trades.exists() and quotes.exists():
                event_id = event_dir.name.replace("event=", "")
                completed_events.add(event_id)

print(f"Discovered {len(completed_events)} completed events on disk")

# Also scan for symbol-level completion
completed_symbols = set()
for symbol_dir in raw_root.glob("symbol=*"):
    if symbol_dir.is_dir():
        # Count events with both parquet files
        complete_in_symbol = 0
        for event_dir in symbol_dir.glob("event=*"):
            trades = event_dir / "trades.parquet"
            quotes = event_dir / "quotes.parquet"
            if trades.exists() and quotes.exists():
                complete_in_symbol += 1

        if complete_in_symbol > 0:
            symbol = symbol_dir.name.replace("symbol=", "")
            completed_symbols.add(symbol)

print(f"Symbols with at least 1 completed event: {len(completed_symbols)}")

# Create checkpoint
data = {
    "run_id": run_id,
    "run_date": run_date,
    "completed_events": sorted(completed_events),
    "completed_symbols": sorted(completed_symbols),
    "total_events": len(completed_events),
    "total_symbols": len(completed_symbols),
    "last_updated": datetime.now().isoformat(),
    "reconciled": True
}

ckpt_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

print(f"\n[OK] Checkpoint reconciled: {ckpt_path}")
print(f"     Events: {len(completed_events)}")
print(f"     Symbols: {len(completed_symbols)}")
print("=" * 60)
