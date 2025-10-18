#!/usr/bin/env python3
"""
Quick market cap audit for symbols in master events
"""
import polars as pl
import requests
import time
from pathlib import Path
import os

root = Path(__file__).resolve().parents[2]

# Get API key
api_key = os.getenv("POLYGON_API_KEY")
if not api_key:
    print("ERROR: POLYGON_API_KEY not set")
    print("Set it with: export POLYGON_API_KEY=your_key")
    exit(1)

print("=" * 70)
print("QUICK MARKET CAP AUDIT")
print("=" * 70)
print()

# Read unique symbols from master
print("[1/4] Reading symbols from master events...")
events_file = root / "processed" / "final" / "events_intraday_MASTER_dedup_v2.parquet"
df_events = pl.read_parquet(events_file)
symbols = sorted(df_events["symbol"].unique().to_list())
print(f"Found {len(symbols)} unique symbols")
print()

# Download market caps from Polygon
print("[2/4] Downloading market caps from Polygon...")
print("(This will take ~3-5 minutes with rate limiting)")
print()

market_caps = []
errors = []

for i, symbol in enumerate(symbols, 1):
    try:
        url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
        params = {"apiKey": api_key}

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if "results" in data:
                results = data["results"]
                mcap = results.get("market_cap")

                market_caps.append({
                    "symbol": symbol,
                    "market_cap": mcap if mcap else None
                })

                if i % 50 == 0:
                    print(f"  Progress: {i}/{len(symbols)} ({i/len(symbols)*100:.1f}%)")
        else:
            errors.append(symbol)

        # Rate limit: ~5 requests per second
        time.sleep(0.21)

    except Exception as e:
        errors.append(symbol)
        if i % 100 == 0:
            print(f"  Errors so far: {len(errors)}")

print(f"Downloaded: {len(market_caps)} symbols")
print(f"Errors: {len(errors)} symbols")
print()

# Create dataframe
print("[3/4] Creating market cap dataframe...")
df_caps = pl.DataFrame(market_caps)

# Save to file
ref_dir = root / "ref"
ref_dir.mkdir(exist_ok=True)
output_file = ref_dir / "symbols_marketcap_latest.parquet"
df_caps.write_parquet(output_file)
print(f"Saved to: {output_file}")
print()

# Analyze distribution
print("[4/4] Analyzing distribution...")
print()
print("=" * 70)
print("MARKET CAP DISTRIBUTION")
print("=" * 70)
print()

bins = [
    ("nano-cap", 0, 50_000_000, "< $50M"),
    ("micro-cap", 50_000_000, 300_000_000, "$50M - $300M"),
    ("small-cap", 300_000_000, 2_000_000_000, "$300M - $2B"),
    ("mid-cap", 2_000_000_000, 10_000_000_000, "$2B - $10B"),
    ("large-cap", 10_000_000_000, 10_000_000_000_000, "> $10B"),
]

results = []
for name, lo, hi, label in bins:
    count = df_caps.filter(
        (pl.col("market_cap") >= lo) & (pl.col("market_cap") < hi)
    ).height
    pct = count / len(symbols) * 100
    results.append((name, label, count, pct))
    print(f"{name:12} {label:20} {count:4} ({pct:5.1f}%)")

# Missing data
missing = df_caps.filter(pl.col("market_cap").is_null()).height
print()
print(f"Sin dato de market cap: {missing} ({missing/len(symbols)*100:.1f}%)")
print()

# Show problematic large caps
print("=" * 70)
print("LARGE-CAPS ENCONTRADOS (> $2B) - FUERA DEL UNIVERSO TARGET")
print("=" * 70)
print()

large_caps = df_caps.filter(pl.col("market_cap") > 2_000_000_000).sort("market_cap", descending=True)

if len(large_caps) > 0:
    print(f"Total large/mid-caps: {len(large_caps)}")
    print()
    print("Top 20 más grandes:")
    print()
    for i, row in enumerate(large_caps.head(20).iter_rows(named=True), 1):
        sym = row["symbol"]
        mcap = row["market_cap"]
        if mcap:
            if mcap >= 1_000_000_000_000:
                mcap_str = f"${mcap/1_000_000_000_000:.2f}T"
            elif mcap >= 1_000_000_000:
                mcap_str = f"${mcap/1_000_000_000:.2f}B"
            else:
                mcap_str = f"${mcap/1_000_000:.0f}M"
            print(f"  {i:2}. {sym:6} - {mcap_str}")
else:
    print("✅ No hay large-caps (todos < $2B)")

print()
print("=" * 70)
print("CONCLUSIÓN")
print("=" * 70)
print()

# Calculate target compliance
small_and_micro = sum([r[2] for r in results if r[0] in ["nano-cap", "micro-cap", "small-cap"]])
total_valid = len(symbols) - missing

print(f"Símbolos en target (< $2B):     {small_and_micro}/{total_valid} ({small_and_micro/total_valid*100:.1f}%)")
print(f"Símbolos fuera de target (≥$2B): {len(large_caps)}/{total_valid} ({len(large_caps)/total_valid*100:.1f}%)")
print()

if len(large_caps) > 0:
    print("⚠️  PROBLEMA: Hay símbolos fuera del universo target de small-caps")
    print("    Recomendación: Filtrar manifest antes de continuar descarga")
else:
    print("✅ OK: Todos los símbolos están dentro del target (< $2B)")
