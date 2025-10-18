#!/usr/bin/env python3
"""Quick progress check for Polygon ingestion"""
from pathlib import Path
from collections import defaultdict

root = Path(r"D:\04_TRADING_SMALLCAPS")
raw = root / "raw" / "market_data" / "event_windows"

symbols = set()
events_complete = 0
events_partial = 0

for symbol_dir in raw.glob("symbol=*"):
    sym = symbol_dir.name.replace("symbol=", "")
    symbols.add(sym)

    for event_dir in symbol_dir.glob("event=*"):
        trades = event_dir / "trades.parquet"
        quotes = event_dir / "quotes.parquet"

        if trades.exists() and quotes.exists():
            events_complete += 1
        elif trades.exists() or quotes.exists():
            events_partial += 1

print(f"Unique symbols: {len(symbols)}")
print(f"Complete events (both files): {events_complete}")
print(f"Partial events (one file): {events_partial}")
print(f"First 10 symbols: {sorted(symbols)[:10]}")
