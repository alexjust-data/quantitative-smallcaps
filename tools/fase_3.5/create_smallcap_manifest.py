#!/usr/bin/env python3
"""
Create filtered manifest with only small-caps (market_cap < $2B)
Filters existing manifest to include only symbols meeting market cap threshold
"""
import polars as pl
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]

print("=" * 70)
print("CREACIÓN DE MANIFEST FILTRADO POR MARKET CAP")
print("=" * 70)
print()

# Threshold
MARKET_CAP_THRESHOLD = 2_000_000_000  # $2B

# Read original manifest
manifest_path = root / "processed" / "events" / "manifest_core_5y_20251017.parquet"
print(f"Leyendo manifest original: {manifest_path.name}")
df_manifest = pl.read_parquet(manifest_path)
print(f"  Total eventos: {len(df_manifest):,}")
print(f"  Total símbolos únicos: {df_manifest['symbol'].n_unique():,}")
print()

# Read ticker details (has market_cap)
ticker_details_path = root / "raw" / "reference" / "ticker_details_all.parquet"
print(f"Leyendo ticker details: {ticker_details_path.name}")
df_tickers = pl.read_parquet(ticker_details_path)
print(f"  Total tickers: {len(df_tickers):,}")
print()

# Get unique symbols from manifest
manifest_symbols = df_manifest.select("symbol").unique()

# Join to get market caps
symbols_with_mcap = manifest_symbols.join(
    df_tickers.select(["ticker", "market_cap"]),
    left_on="symbol",
    right_on="ticker",
    how="left"
)

print("=" * 70)
print("ANÁLISIS MARKET CAP")
print("=" * 70)
print()

# Count symbols by category
total_symbols = len(symbols_with_mcap)
symbols_with_data = symbols_with_mcap.filter(pl.col("market_cap").is_not_null()).height
symbols_missing_data = symbols_with_mcap.filter(pl.col("market_cap").is_null()).height
symbols_within_threshold = symbols_with_mcap.filter(
    (pl.col("market_cap").is_not_null()) & (pl.col("market_cap") < MARKET_CAP_THRESHOLD)
).height
symbols_above_threshold = symbols_with_mcap.filter(
    pl.col("market_cap") >= MARKET_CAP_THRESHOLD
).height

print(f"Total símbolos en manifest:           {total_symbols:,}")
print(f"Símbolos con market cap data:         {symbols_with_data:,} ({symbols_with_data/total_symbols*100:.1f}%)")
print(f"Símbolos sin market cap data:         {symbols_missing_data:,} ({symbols_missing_data/total_symbols*100:.1f}%)")
print()
print(f"Simbolos < $2B (dentro del target):   {symbols_within_threshold:,} ({symbols_within_threshold/total_symbols*100:.1f}%)")
print(f"Simbolos >= $2B (fuera del target):   {symbols_above_threshold:,} ({symbols_above_threshold/total_symbols*100:.1f}%)")
print()

# Get list of symbols to keep (< $2B or missing data)
# We keep symbols with missing data to be conservative (might be delisted small-caps)
symbols_to_keep = symbols_with_mcap.filter(
    pl.col("market_cap").is_null() | (pl.col("market_cap") < MARKET_CAP_THRESHOLD)
)["symbol"].to_list()

symbols_to_exclude = symbols_with_mcap.filter(
    pl.col("market_cap") >= MARKET_CAP_THRESHOLD
)["symbol"].to_list()

print(f"Símbolos a MANTENER: {len(symbols_to_keep):,}")
print(f"Símbolos a EXCLUIR:  {len(symbols_to_exclude):,}")
print()

# Show symbols being excluded
if len(symbols_to_exclude) > 0:
    symbols_excluded_with_mcap = symbols_with_mcap.filter(
        pl.col("market_cap") >= MARKET_CAP_THRESHOLD
    ).sort("market_cap", descending=True)

    print("=" * 70)
    print(f"SIMBOLOS EXCLUIDOS (>= $2B) - Top 30")
    print("=" * 70)
    print()

    for i, row in enumerate(symbols_excluded_with_mcap.head(30).iter_rows(named=True), 1):
        sym = row["symbol"]
        mcap = row["market_cap"]
        if mcap >= 1_000_000_000_000:
            mcap_str = f"${mcap/1_000_000_000_000:.2f}T"
        elif mcap >= 1_000_000_000:
            mcap_str = f"${mcap/1_000_000_000:.2f}B"
        else:
            mcap_str = f"${mcap/1_000_000:.0f}M"
        print(f"  {i:2}. {sym:6} - {mcap_str}")

    if len(symbols_excluded_with_mcap) > 30:
        print(f"  ... y {len(symbols_excluded_with_mcap) - 30} más")
    print()

# Filter manifest
print("=" * 70)
print("FILTRANDO MANIFEST")
print("=" * 70)
print()

df_filtered = df_manifest.filter(pl.col("symbol").is_in(symbols_to_keep))

events_original = len(df_manifest)
events_filtered = len(df_filtered)
events_removed = events_original - events_filtered

print(f"Eventos originales:  {events_original:,}")
print(f"Eventos filtrados:   {events_filtered:,} ({events_filtered/events_original*100:.1f}%)")
print(f"Eventos removidos:   {events_removed:,} ({events_removed/events_original*100:.1f}%)")
print()

# Save filtered manifest
output_path = root / "processed" / "events" / "manifest_smallcaps_5y_20251017.parquet"
df_filtered.write_parquet(output_path)
print(f"✅ Manifest filtrado guardado: {output_path.name}")
print()

# Final summary
print("=" * 70)
print("RESUMEN FINAL")
print("=" * 70)
print()
print(f"Manifest original:     {manifest_path.name}")
print(f"  - Eventos:           {events_original:,}")
print(f"  - Símbolos:          {total_symbols:,}")
print()
print(f"Manifest filtrado:     {output_path.name}")
print(f"  - Eventos:           {events_filtered:,}")
print(f"  - Símbolos:          {len(symbols_to_keep):,}")
print(f"  - Threshold:         < $2B market cap")
print()
print(f"Reducción:             {events_removed:,} eventos ({events_removed/events_original*100:.1f}%)")
print(f"Ahorro tiempo estimado: ~{events_removed/119/60:.1f} horas")
print()
print("=" * 70)
