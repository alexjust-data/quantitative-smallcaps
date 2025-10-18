#!/usr/bin/env python3
"""
Find fundamentals files
"""
from pathlib import Path

root = Path(__file__).resolve().parents[2]

print("Buscando archivos con datos fundamentales...")
print()

# Search for parquet files that might contain fundamentals
search_dirs = [
    root / "raw",
    root / "processed",
    root / "processed" / "final",
]

fundamentals_candidates = []

for search_dir in search_dirs:
    if not search_dir.exists():
        continue

    for pq_file in search_dir.rglob("*.parquet"):
        name_lower = pq_file.name.lower()
        if any(keyword in name_lower for keyword in ['fundamental', 'market_cap', 'mcap', 'universe', 'screening', 'filter']):
            size_mb = pq_file.stat().st_size / 1024 / 1024
            fundamentals_candidates.append((pq_file, size_mb))

print(f"Encontrados {len(fundamentals_candidates)} archivos candidatos:")
print()

for fpath, size_mb in sorted(fundamentals_candidates, key=lambda x: x[1], reverse=True):
    rel_path = fpath.relative_to(root)
    print(f"{size_mb:7.1f} MB - {rel_path}")

# Also check the events file - it might have market_cap
print()
print("=" * 70)
print("Revisando archivo de eventos (events_intraday_MASTER_dedup_v2.parquet)")
print("=" * 70)

events_file = root / "processed" / "final" / "events_intraday_MASTER_dedup_v2.parquet"
if events_file.exists():
    import polars as pl

    print(f"Leyendo primeras 1000 filas...")
    df = pl.scan_parquet(events_file).head(1000).collect()

    print(f"\nColumnas en el archivo de eventos ({len(df.columns)}):")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i:2}. {col}")

    # Check if there's market_cap or similar
    cap_columns = [c for c in df.columns if 'cap' in c.lower() or 'market' in c.lower()]
    if cap_columns:
        print(f"\nColumnas relacionadas con market cap:")
        for col in cap_columns:
            print(f"  - {col}")
            print(f"    Sample values: {df[col].head(5).to_list()}")
