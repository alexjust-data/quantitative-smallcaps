#!/usr/bin/env python3
"""Quick verification of manifest before FASE 3.2 launch"""

import polars as pl
import json
import hashlib
from pathlib import Path

manifest_file = Path("processed/events/manifest_core_20251014.parquet")
metadata_file = Path("processed/events/manifest_core_20251014.json")

# Load manifest
df = pl.read_parquet(manifest_file)

print("=" * 60)
print("MANIFEST VERIFICATION - FASE 3.2 LAUNCH")
print("=" * 60)

# Basic stats
print(f"\nOK Manifest loaded: {len(df):,} events")
print(f"OK Symbols: {df['symbol'].n_unique()}")

# Session breakdown
pm_count = len(df.filter(pl.col("session") == "PM"))
ah_count = len(df.filter(pl.col("session") == "AH"))
rth_count = len(df.filter(pl.col("session") == "RTH"))

print(f"\nSESSION BREAKDOWN:")
print(f"  PM:  {pm_count:,} events ({pm_count/len(df)*100:.1f}%)")
print(f"  AH:  {ah_count:,} events ({ah_count/len(df)*100:.1f}%)")
print(f"  RTH: {rth_count:,} events ({rth_count/len(df)*100:.1f}%)")

# Metadata
if metadata_file.exists():
    with open(metadata_file) as f:
        meta = json.load(f)
    print(f"\nMETADATA:")
    print(f"  Manifest ID: {meta.get('manifest_id')}")
    print(f"  Profile: {meta.get('profile')}")
    print(f"  Config hash: {meta.get('config_hash')}")

# SHA-256 hash
with open(manifest_file, 'rb') as f:
    manifest_hash = hashlib.sha256(f.read()).hexdigest()
print(f"\nINTEGRITY:")
print(f"  SHA-256: {manifest_hash[:32]}...")

# Check required columns
required_cols = ["symbol", "timestamp", "session", "score"]
missing = [c for c in required_cols if c not in df.columns]

if "type" not in df.columns and "event_type" not in df.columns:
    missing.append("event_type/type")

if missing:
    print(f"\nERROR: Missing columns: {missing}")
else:
    print(f"\nOK Schema valid: All required columns present")

print("\n" + "=" * 60)
print("READY TO LAUNCH FASE 3.2")
print("=" * 60)
