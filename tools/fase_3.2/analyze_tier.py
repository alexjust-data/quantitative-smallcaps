#!/usr/bin/env python3
"""
Analyze tier column to verify microcaps
"""
import polars as pl
from pathlib import Path

root = Path(__file__).resolve().parents[2]

# Read events file
events_file = root / "processed" / "final" / "events_intraday_MASTER_dedup_v2.parquet"
print("Leyendo eventos...")
df = pl.read_parquet(events_file)

print(f"Total eventos: {len(df):,}")
print(f"Total símbolos únicos: {df['symbol'].n_unique():,}")
print()

# Analyze tier column
print("=" * 70)
print("ANÁLISIS DE COLUMNA 'TIER'")
print("=" * 70)
print()

tier_counts = df.group_by('tier').agg([
    pl.count().alias('eventos'),
    pl.col('symbol').n_unique().alias('simbolos_unicos')
]).sort('tier')

print("Distribución por TIER:")
print()
for row in tier_counts.iter_rows(named=True):
    tier = row['tier']
    eventos = row['eventos']
    simbolos = row['simbolos_unicos']
    print(f"  Tier {tier}: {eventos:>7,} eventos | {simbolos:>5,} símbolos únicos")

# Get unique symbols per tier
print()
print("=" * 70)
print("SÍMBOLOS POR TIER")
print("=" * 70)
print()

# Get one row per symbol with its tier (take most frequent tier for each symbol)
symbol_tiers = df.group_by('symbol').agg([
    pl.col('tier').mode().first().alias('tier')
]).sort('symbol')

print(f"Total símbolos únicos: {len(symbol_tiers):,}")
print()

# Count symbols per tier
symbols_per_tier = symbol_tiers.group_by('tier').agg([
    pl.count().alias('count')
]).sort('tier')

print("Símbolos únicos por tier:")
print()
for row in symbols_per_tier.iter_rows(named=True):
    tier = row['tier']
    count = row['count']
    pct = count / len(symbol_tiers) * 100
    print(f"  Tier {tier}: {count:>5,} símbolos ({pct:>5.1f}%)")

# Show sample symbols from each tier
print()
print("=" * 70)
print("MUESTRA DE SÍMBOLOS POR TIER (10 por tier)")
print("=" * 70)

for tier_val in sorted(symbol_tiers['tier'].unique().to_list()):
    tier_symbols = symbol_tiers.filter(pl.col('tier') == tier_val)
    print(f"\nTier {tier_val} (primeros 10 símbolos):")
    for sym in tier_symbols['symbol'].head(10).to_list():
        print(f"  - {sym}")

# Check manifest symbols vs events symbols
print()
print("=" * 70)
print("VERIFICACIÓN CON MANIFEST")
print("=" * 70)
print()

manifest_file = root / "processed" / "events" / "manifest_core_5y_20251017.parquet"
manifest_df = pl.read_parquet(manifest_file)
manifest_symbols = set(manifest_df['symbol'].unique().to_list())

events_symbols = set(symbol_tiers['symbol'].to_list())

print(f"Símbolos en manifest:  {len(manifest_symbols):,}")
print(f"Símbolos en events:    {len(events_symbols):,}")
print(f"Símbolos en ambos:     {len(manifest_symbols & events_symbols):,}")
print(f"Solo en manifest:      {len(manifest_symbols - events_symbols):,}")
print(f"Solo en events:        {len(events_symbols - manifest_symbols):,}")

# Interpret tiers
print()
print("=" * 70)
print("INTERPRETACIÓN DE TIERS")
print("=" * 70)
print()
print("Basado en la estructura típica de clasificación:")
print()
print("  Tier 1: Probablemente Nano-cap  (< $50M)")
print("  Tier 2: Probablemente Micro-cap ($50M - $300M)")
print("  Tier 3: Probablemente Small-cap ($300M - $2B)")
print()
print("VERIFICACIÓN NECESARIA:")
print("  - Consultar documentación de FASE 2.5 para confirmar definición de tiers")
print("  - Verificar que Tier 1 y 2 son microcaps")
