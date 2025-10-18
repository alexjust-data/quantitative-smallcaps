#!/usr/bin/env python3
"""
Verify that all symbols in manifest are microcaps
"""
import polars as pl
from pathlib import Path

root = Path(__file__).resolve().parents[2]

# Read manifest
manifest_path = root / "processed" / "events" / "manifest_core_5y_20251017.parquet"
print("Leyendo manifest...")
manifest_df = pl.read_parquet(manifest_path)
manifest_symbols = manifest_df['symbol'].unique().sort()
print(f"Símbolos en manifest: {len(manifest_symbols):,}")
print()

# Find fundamentals file
fundamentals_files = list((root / "raw" / "fundamentals").glob("*.parquet"))
if not fundamentals_files:
    print("ERROR: No se encontró archivo de fundamentals")
    exit(1)

fundamentals_path = fundamentals_files[0]
print(f"Leyendo fundamentals: {fundamentals_path.name}")
fundamentals_df = pl.read_parquet(fundamentals_path)
print(f"Símbolos en fundamentals: {len(fundamentals_df):,}")
print()

# Check if market_cap column exists
print("Columnas disponibles:")
for col in fundamentals_df.columns:
    print(f"  - {col}")
print()

# Filter to manifest symbols
manifest_fundamentals = fundamentals_df.filter(
    pl.col('symbol').is_in(manifest_symbols)
)

print("=" * 70)
print("ANÁLISIS DE MARKET CAP")
print("=" * 70)
print()

# Check if we have market_cap column
if 'market_cap' in manifest_fundamentals.columns:
    # Define microcap threshold (typically < $300M)
    MICROCAP_THRESHOLD = 300_000_000  # $300M

    # Analyze market cap distribution
    stats = manifest_fundamentals.select([
        pl.col('market_cap').min().alias('min_mcap'),
        pl.col('market_cap').max().alias('max_mcap'),
        pl.col('market_cap').mean().alias('mean_mcap'),
        pl.col('market_cap').median().alias('median_mcap'),
        (pl.col('market_cap') < MICROCAP_THRESHOLD).sum().alias('microcaps_count'),
        pl.col('market_cap').count().alias('total_count')
    ])

    stat_row = stats.row(0, named=True)

    print(f"Market Cap mínimo:       ${stat_row['min_mcap']:,.0f}")
    print(f"Market Cap máximo:       ${stat_row['max_mcap']:,.0f}")
    print(f"Market Cap promedio:     ${stat_row['mean_mcap']:,.0f}")
    print(f"Market Cap mediano:      ${stat_row['median_mcap']:,.0f}")
    print()
    print(f"Símbolos con market cap: {stat_row['total_count']:,}")
    print(f"Microcaps (< $300M):     {stat_row['microcaps_count']:,} ({stat_row['microcaps_count']/stat_row['total_count']*100:.1f}%)")
    print()

    # Show non-microcaps if any
    non_microcaps = manifest_fundamentals.filter(
        pl.col('market_cap') >= MICROCAP_THRESHOLD
    ).select(['symbol', 'market_cap']).sort('market_cap', descending=True)

    if len(non_microcaps) > 0:
        print("=" * 70)
        print(f"SÍMBOLOS SOBRE THRESHOLD DE $300M ({len(non_microcaps)})")
        print("=" * 70)
        print()
        for row in non_microcaps.head(50).iter_rows(named=True):
            print(f"  {row['symbol']:6} - ${row['market_cap']:>15,.0f}")
    else:
        print("✅ TODOS los símbolos son microcaps (< $300M)")

    # Distribution by brackets
    print()
    print("=" * 70)
    print("DISTRIBUCIÓN POR RANGOS")
    print("=" * 70)
    print()

    brackets = [
        (0, 50_000_000, "Nano-cap (< $50M)"),
        (50_000_000, 100_000_000, "Micro-cap bajo ($50M - $100M)"),
        (100_000_000, 300_000_000, "Micro-cap alto ($100M - $300M)"),
        (300_000_000, 2_000_000_000, "Small-cap ($300M - $2B)"),
        (2_000_000_000, float('inf'), "Mid/Large-cap (> $2B)")
    ]

    for min_cap, max_cap, label in brackets:
        count = manifest_fundamentals.filter(
            (pl.col('market_cap') >= min_cap) & (pl.col('market_cap') < max_cap)
        ).shape[0]
        pct = count / len(manifest_fundamentals) * 100
        print(f"{label:35} {count:4} ({pct:5.1f}%)")

else:
    print("⚠️  Columna 'market_cap' no encontrada en fundamentals")
    print("Intentando buscar columnas alternativas...")

# Check symbols not in fundamentals
print()
print("=" * 70)
print("COBERTURA DE FUNDAMENTALS")
print("=" * 70)
print()

fundamentals_symbols = set(fundamentals_df['symbol'].to_list())
manifest_symbols_set = set(manifest_symbols.to_list())

in_manifest_not_fundamentals = manifest_symbols_set - fundamentals_symbols
in_fundamentals_not_manifest = fundamentals_symbols - manifest_symbols_set

print(f"Símbolos en manifest:                 {len(manifest_symbols_set):,}")
print(f"Símbolos en fundamentals:             {len(fundamentals_symbols):,}")
print(f"Símbolos en ambos:                    {len(manifest_symbols_set & fundamentals_symbols):,}")
print(f"En manifest pero NO en fundamentals:  {len(in_manifest_not_fundamentals):,}")
print(f"En fundamentals pero NO en manifest:  {len(in_fundamentals_not_manifest):,}")

if len(in_manifest_not_fundamentals) > 0:
    print()
    print(f"Símbolos sin fundamentals (primeros 50):")
    for i, sym in enumerate(sorted(in_manifest_not_fundamentals)[:50], 1):
        print(f"  {i:3}. {sym}")
