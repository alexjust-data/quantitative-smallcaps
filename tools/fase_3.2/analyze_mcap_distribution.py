#!/usr/bin/env python3
"""
Analyze market cap distribution of symbols in manifest
Uses existing ticker_details_all.parquet from raw/reference
"""
import polars as pl
from pathlib import Path

root = Path(__file__).resolve().parents[2]

print("=" * 70)
print("ANÁLISIS DE MARKET CAP - UNIVERSO ACTUAL")
print("=" * 70)
print()

# Read manifest
manifest_path = root / "processed" / "events" / "manifest_core_5y_20251017.parquet"
print(f"Leyendo manifest: {manifest_path.name}")
df_manifest = pl.read_parquet(manifest_path)
manifest_symbols = df_manifest['symbol'].unique().sort()
print(f"Símbolos en manifest: {len(manifest_symbols):,}")
print()

# Read ticker details (has market_cap)
ticker_details_path = root / "raw" / "reference" / "ticker_details_all.parquet"
print(f"Leyendo ticker details: {ticker_details_path.name}")
df_tickers = pl.read_parquet(ticker_details_path)
print(f"Símbolos en ticker details: {len(df_tickers):,}")
print()

# Join to get market caps for our symbols
df_analysis = manifest_symbols.to_frame("symbol").join(
    df_tickers.select(["ticker", "market_cap"]),
    left_on="symbol",
    right_on="ticker",
    how="left"
)

# Count nulls
missing_mcap = df_analysis.filter(pl.col("market_cap").is_null()).height
symbols_with_mcap = df_analysis.filter(pl.col("market_cap").is_not_null())

print("=" * 70)
print("COBERTURA DE MARKET CAP")
print("=" * 70)
print()
print(f"Símbolos con market cap:    {len(symbols_with_mcap):,} ({len(symbols_with_mcap)/len(manifest_symbols)*100:.1f}%)")
print(f"Símbolos SIN market cap:    {missing_mcap:,} ({missing_mcap/len(manifest_symbols)*100:.1f}%)")
print()

if len(symbols_with_mcap) == 0:
    print("ERROR: No hay símbolos con market cap data")
    exit(1)

# Define brackets
print("=" * 70)
print("DISTRIBUCIÓN POR MARKET CAP")
print("=" * 70)
print()

brackets = [
    ("Nano-cap", 0, 50_000_000, "< $50M"),
    ("Micro-cap", 50_000_000, 300_000_000, "$50M - $300M"),
    ("Small-cap", 300_000_000, 2_000_000_000, "$300M - $2B"),
    ("Mid-cap", 2_000_000_000, 10_000_000_000, "$2B - $10B"),
    ("Large-cap", 10_000_000_000, float('inf'), "> $10B")
]

results = []
for name, lo, hi, label in brackets:
    count = symbols_with_mcap.filter(
        (pl.col("market_cap") >= lo) & (pl.col("market_cap") < hi)
    ).height
    pct = count / len(symbols_with_mcap) * 100
    results.append((name, label, count, pct))
    print(f"{name:12} {label:20} {count:4} ({pct:5.1f}%)")

print()

# Summary
target_count = sum([r[2] for r in results if r[0] in ["Nano-cap", "Micro-cap", "Small-cap"]])
out_of_target = sum([r[2] for r in results if r[0] in ["Mid-cap", "Large-cap"]])

print("=" * 70)
print("RESUMEN vs TARGET DEL README (market_cap < $2B)")
print("=" * 70)
print()
print(f"Dentro del target (< $2B):  {target_count:,} ({target_count/len(symbols_with_mcap)*100:.1f}%)")
print(f"Fuera del target (≥ $2B):   {out_of_target:,} ({out_of_target/len(symbols_with_mcap)*100:.1f}%)")
print()

# Show largest out-of-target symbols
if out_of_target > 0:
    print("=" * 70)
    print("SÍMBOLOS FUERA DEL TARGET (≥ $2B) - Top 30")
    print("=" * 70)
    print()

    large_symbols = symbols_with_mcap.filter(
        pl.col("market_cap") >= 2_000_000_000
    ).sort("market_cap", descending=True)

    for i, row in enumerate(large_symbols.head(30).iter_rows(named=True), 1):
        sym = row["symbol"]
        mcap = row["market_cap"]
        if mcap >= 1_000_000_000_000:
            mcap_str = f"${mcap/1_000_000_000_000:.2f}T"
        elif mcap >= 1_000_000_000:
            mcap_str = f"${mcap/1_000_000_000:.2f}B"
        else:
            mcap_str = f"${mcap/1_000_000:.0f}M"
        print(f"  {i:2}. {sym:6} - {mcap_str}")

    print()
    print(f"⚠️  PROBLEMA: Hay {out_of_target} símbolos fuera del target de small-caps")
    print(f"    Esto representa {out_of_target/len(symbols_with_mcap)*100:.1f}% del universo")
else:
    print("✅ OK: Todos los símbolos están dentro del target (< $2B)")

print()
print("=" * 70)
