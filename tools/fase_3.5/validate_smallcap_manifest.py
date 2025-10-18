#!/usr/bin/env python3
"""
Validate the filtered smallcap manifest
Simple validation without Unicode characters
"""
import polars as pl
from pathlib import Path

root = Path(__file__).resolve().parents[2]

print("=" * 70)
print("VALIDACION MANIFEST FILTRADO")
print("=" * 70)
print()

# Read the NEW filtered manifest
manifest_path = root / "processed" / "events" / "manifest_smallcaps_5y_20251017.parquet"
print(f"Leyendo manifest filtrado: {manifest_path.name}")
df_manifest = pl.read_parquet(manifest_path)

total_events = len(df_manifest)
unique_symbols = df_manifest['symbol'].n_unique()
symbols_list = df_manifest['symbol'].unique().sort().to_list()

print(f"  Total eventos:    {total_events:,}")
print(f"  Total simbolos:   {unique_symbols:,}")
print()

# Read ticker details to verify market caps
ticker_details_path = root / "raw" / "reference" / "ticker_details_all.parquet"
print(f"Leyendo ticker details: {ticker_details_path.name}")
df_tickers = pl.read_parquet(ticker_details_path)
print()

# Join to check market caps of symbols in filtered manifest
df_check = df_manifest.select("symbol").unique().join(
    df_tickers.select(["ticker", "market_cap"]),
    left_on="symbol",
    right_on="ticker",
    how="left"
)

# Count by category
with_data = df_check.filter(pl.col("market_cap").is_not_null()).height
missing_data = df_check.filter(pl.col("market_cap").is_null()).height
under_2b = df_check.filter(
    (pl.col("market_cap").is_not_null()) & (pl.col("market_cap") < 2_000_000_000)
).height
over_2b = df_check.filter(pl.col("market_cap") >= 2_000_000_000).height

print("=" * 70)
print("VERIFICACION MARKET CAP")
print("=" * 70)
print()
print(f"Simbolos con market cap data:     {with_data:,}")
print(f"Simbolos sin market cap data:     {missing_data:,}")
print(f"Simbolos < $2B (VALIDOS):         {under_2b:,}")
print(f"Simbolos >= $2B (NO DEBERIAN):    {over_2b:,}")
print()

if over_2b > 0:
    print("ERROR: Hay simbolos >= $2B en el manifest filtrado!")
    large = df_check.filter(pl.col("market_cap") >= 2_000_000_000).sort("market_cap", descending=True)
    for row in large.head(10).iter_rows(named=True):
        print(f"  {row['symbol']}: ${row['market_cap']/1e9:.2f}B")
    print()
else:
    print("OK: Todos los simbolos estan dentro del target (< $2B)")
    print()

print("=" * 70)
print("RESUMEN")
print("=" * 70)
print()
print(f"Manifest:       {manifest_path.name}")
print(f"Eventos:        {total_events:,}")
print(f"Simbolos:       {unique_symbols:,}")
print(f"Validos:        {under_2b + missing_data:,}")
print()
print("=" * 70)
