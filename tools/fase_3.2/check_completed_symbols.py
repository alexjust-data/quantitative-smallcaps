#!/usr/bin/env python3
"""
Check how many symbols are 100% complete
"""
from pathlib import Path
import polars as pl

root = Path(__file__).resolve().parents[2]
manifest_path = root / "processed" / "events" / "manifest_core_5y_20251017.parquet"
event_windows = root / "raw" / "market_data" / "event_windows"

print("=" * 70)
print("ANÁLISIS DE SÍMBOLOS COMPLETADOS")
print("=" * 70)
print()

# Read manifest
print("Leyendo manifest...")
df = pl.read_parquet(manifest_path)
print(f"Total eventos en manifest: {len(df):,}")
print(f"Total símbolos en manifest: {df['symbol'].n_unique()}")
print()

# Count events per symbol in manifest
manifest_events = df.group_by('symbol').agg(
    pl.count().alias('events_in_manifest')
).sort('symbol')

print("Contando eventos completados en disco...")
# Count completed events on disk (both trades and quotes files exist)
completed = []
for symbol_dir in sorted(event_windows.glob("symbol=*")):
    symbol = symbol_dir.name.replace("symbol=", "")

    # Count events with both files
    events_complete = 0
    for event_dir in symbol_dir.glob("event=*"):
        trades_file = event_dir / "trades.parquet"
        quotes_file = event_dir / "quotes.parquet"
        if trades_file.exists() and quotes_file.exists():
            events_complete += 1

    completed.append({
        'symbol': symbol,
        'events_complete': events_complete
    })

disk_events = pl.DataFrame(completed)

# Join to compare
comparison = manifest_events.join(disk_events, on='symbol', how='left').fill_null(0)
comparison = comparison.with_columns([
    ((pl.col('events_complete') / pl.col('events_in_manifest')) * 100).alias('pct_complete'),
    (pl.col('events_complete') == pl.col('events_in_manifest')).alias('is_complete')
])

# Summary
total_symbols_manifest = len(comparison)
symbols_100_complete = comparison.filter(pl.col('is_complete')).shape[0]
symbols_in_progress = comparison.filter((pl.col('events_complete') > 0) & (~pl.col('is_complete'))).shape[0]
symbols_not_started = comparison.filter(pl.col('events_complete') == 0).shape[0]

print()
print("=" * 70)
print("RESUMEN")
print("=" * 70)
print()
print(f"Total símbolos:              {total_symbols_manifest:,}")
print(f"Símbolos 100% completos:     {symbols_100_complete:,} ({symbols_100_complete/total_symbols_manifest*100:.1f}%)")
print(f"Símbolos en progreso:        {symbols_in_progress:,} ({symbols_in_progress/total_symbols_manifest*100:.1f}%)")
print(f"Símbolos no comenzados:      {symbols_not_started:,} ({symbols_not_started/total_symbols_manifest*100:.1f}%)")
print()

# Show 100% complete symbols
complete_symbols = comparison.filter(pl.col('is_complete')).sort('symbol')
print("=" * 70)
print(f"SÍMBOLOS 100% COMPLETOS ({len(complete_symbols)})")
print("=" * 70)
print()
for i, row in enumerate(complete_symbols.iter_rows(named=True), 1):
    print(f"{i:3}. {row['symbol']:6} - {row['events_in_manifest']:,} eventos")

# Show symbols in progress (top 20 by completion %)
print()
print("=" * 70)
print("SÍMBOLOS EN PROGRESO (Top 20 por % completado)")
print("=" * 70)
print()
in_progress = comparison.filter((pl.col('events_complete') > 0) & (~pl.col('is_complete'))).sort('pct_complete', descending=True).head(20)
for i, row in enumerate(in_progress.iter_rows(named=True), 1):
    print(f"{i:3}. {row['symbol']:6} - {row['events_complete']:4}/{row['events_in_manifest']:4} eventos ({row['pct_complete']:5.1f}%)")
