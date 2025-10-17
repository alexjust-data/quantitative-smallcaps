#!/usr/bin/env python3
"""
Generate manifest for Polygon ingestion from MASTER dedup dataset.
Manifest contains: symbol, ts_start, ts_end (time window per symbol).
"""
from pathlib import Path
import argparse
import polars as pl

def main():
    ap = argparse.ArgumentParser(description="Generate ingestion manifest from MASTER dedup")
    ap.add_argument("--input", default="processed/final/events_intraday_MASTER_dedup_v2.parquet",
                    help="Parquet deduplicado master")
    ap.add_argument("--output", default="processed/events/manifest_core_FULL.parquet",
                    help="Salida manifest .parquet")
    ap.add_argument("--start-epoch", type=int, default=0,
                    help="Epoch inicial (0 = toda la historia)")
    ap.add_argument("--end-epoch", type=int, default=0,
                    help="Epoch final (0 = sin tope)")
    args = ap.parse_args()

    p_in = Path(args.input)
    if not p_in.exists():
        print(f"ERROR: Input file not found: {p_in}")
        return 1

    print(f"Reading input: {p_in}")
    df = pl.read_parquet(p_in, columns=["symbol","timestamp"])

    print(f"Generating manifest for {df['symbol'].n_unique()} symbols...")
    man = (df.group_by("symbol")
             .agg([pl.col("timestamp").min().alias("ts_start"),
                   pl.col("timestamp").max().alias("ts_end")]))

    # Ajustar ventana si se pide
    if args.start_epoch or args.end_epoch:
        se = args.start_epoch or 0
        ee = args.end_epoch or man["ts_end"].max()
        man = man.with_columns(
            pl.lit(se).alias("ts_start"),
            pl.lit(ee).alias("ts_end")
        )
        print(f"Window override: {se} -> {ee}")
    else:
        # 0 = pedir todo; algunos ingestors interpretan 0 como "full history"
        man = man.with_columns(pl.lit(0).alias("ts_start"))
        print("Using full history (ts_start=0)")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    man.write_parquet(out)

    print(f"\n[OK] Manifest created:")
    print(f"  Output: {out}")
    print(f"  Symbols: {man.height}")
    print(f"  Size: {out.stat().st_size / 1024:.1f} KB")

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
