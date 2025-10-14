#!/usr/bin/env python3
"""
Freeze CORE Manifest with Complete Metadata

Takes dry-run manifest and freezes it as stable production version with:
- Config hash
- Normalization method
- Profile version
- Timestamps
- Deduplication info
- Reproducibility metadata

Usage:
    python scripts/processing/freeze_manifest_core.py \
      --input analysis/manifest_core_dryrun_YYYYMMDD_HHMMSS.parquet \
      --output processed/events/manifest_core_YYYYMMDD.parquet
"""

import polars as pl
import argparse
from pathlib import Path
from datetime import datetime, timezone
import json
import hashlib


def freeze_manifest(
    input_file: Path,
    output_file: Path,
    config_hash: str,
    normalization_method: str,
    profile_version: str,
    deduplication_applied: bool,
    source_file: Path
) -> dict:
    """
    Freeze manifest with complete metadata.

    Args:
        input_file: Dry-run manifest to freeze
        output_file: Output frozen manifest
        config_hash: Configuration hash from dry-run
        normalization_method: Score normalization method used
        profile_version: Profile version (e.g., 'core_v1')
        deduplication_applied: Whether deduplication was applied
        source_file: Original enriched file used

    Returns:
        Dictionary with freeze metadata
    """

    print(f"Freezing manifest: {input_file}")
    print()

    # Load dry-run manifest
    df = pl.read_parquet(input_file)

    original_count = len(df)
    unique_symbols = df['symbol'].n_unique()

    print(f"  Events: {original_count:,}")
    print(f"  Symbols: {unique_symbols:,}")
    print()

    # Build metadata
    freeze_timestamp = datetime.now(timezone.utc)

    metadata = {
        # Core identification
        "manifest_id": f"core_{freeze_timestamp.strftime('%Y%m%d_%H%M%S')}",
        "profile": profile_version,
        "config_hash": config_hash,

        # Timestamps
        "created_at": freeze_timestamp.isoformat(),
        "frozen_at": freeze_timestamp.isoformat(),

        # Source data
        "source_file": str(source_file.name),
        "source_file_path": str(source_file),
        "dryrun_file": str(input_file.name),

        # Processing info
        "deduplication_applied": deduplication_applied,
        "normalization_method": normalization_method,

        # Stats
        "total_events": original_count,
        "unique_symbols": unique_symbols,
        "date_range": {
            "start": str(df['date_et'].min()),
            "end": str(df['date_et'].max())
        },

        # Session distribution
        "session_distribution": {},

        # Quality metrics
        "quality_metrics": {
            "score_median": float(df['score'].median()),
            "rvol_median": float(df['rvol_day'].drop_nulls().median()),
            "top20_concentration": 0.0  # Will compute below
        }
    }

    # Session distribution
    session_counts = df.group_by('session').agg(pl.len().alias('count'))
    for row in session_counts.iter_rows(named=True):
        session = row['session']
        count = row['count']
        pct = count / original_count
        metadata["session_distribution"][session] = {
            "count": count,
            "percentage": round(pct * 100, 2)
        }

    # Top 20 concentration
    top20_count = df.group_by('symbol').agg(pl.len().alias('count'))\
                    .sort('count', descending=True).head(20)['count'].sum()
    top20_pct = top20_count / original_count
    metadata["quality_metrics"]["top20_concentration"] = round(top20_pct * 100, 2)

    # Storage/time estimates (from dry-run)
    STORAGE_TRADES_P90_MB = 24.4  # MB per event
    STORAGE_QUOTES_P90_MB = 11.7
    TIME_P90_SEC = 18.0  # seconds per event

    storage_p90_gb = original_count * (STORAGE_TRADES_P90_MB + STORAGE_QUOTES_P90_MB) / 1024
    time_p90_hours = original_count * TIME_P90_SEC / 3600
    time_p90_days = time_p90_hours / 24

    metadata["estimates_fase32"] = {
        "storage_p50_gb": round(original_count * 11.4 / 1024, 1),
        "storage_p90_gb": round(storage_p90_gb, 1),
        "time_p50_hours": round(original_count * 12.0 / 3600, 1),
        "time_p90_hours": round(time_p90_hours, 1),
        "time_p90_days": round(time_p90_days, 2)
    }

    # Write manifest with metadata as custom attributes
    # (Parquet doesn't natively support complex metadata, so we'll also write JSON)
    print("Writing frozen manifest...")
    df.write_parquet(output_file)
    print(f"  Saved: {output_file}")
    print(f"  Size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
    print()

    # Write metadata JSON
    metadata_file = output_file.with_suffix('.json')
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  Metadata: {metadata_file}")
    print()

    # Print summary
    print("="*80)
    print("MANIFEST FROZEN")
    print("="*80)
    print(f"Manifest ID:     {metadata['manifest_id']}")
    print(f"Profile:         {metadata['profile']}")
    print(f"Events:          {metadata['total_events']:,}")
    print(f"Symbols:         {metadata['unique_symbols']:,}")
    print(f"Config hash:     {metadata['config_hash']}")
    print(f"Normalization:   {metadata['normalization_method']}")
    print(f"Deduplication:   {metadata['deduplication_applied']}")
    print()
    print("Session Distribution:")
    for session, data in metadata['session_distribution'].items():
        print(f"  {session:6s}: {data['count']:>6,} ({data['percentage']:>5.1f}%)")
    print()
    print("Quality Metrics:")
    print(f"  Score median:          {metadata['quality_metrics']['score_median']:.3f}")
    print(f"  RVol median:           {metadata['quality_metrics']['rvol_median']:.2f}x")
    print(f"  Top20 concentration:   {metadata['quality_metrics']['top20_concentration']:.1f}%")
    print()
    print("FASE 3.2 Estimates:")
    print(f"  Storage p90:  {metadata['estimates_fase32']['storage_p90_gb']} GB")
    print(f"  Time p90:     {metadata['estimates_fase32']['time_p90_days']} days")
    print("="*80)

    return metadata


def main():
    parser = argparse.ArgumentParser(
        description="Freeze CORE manifest with complete metadata"
    )
    parser.add_argument(
        '--input',
        type=Path,
        help='Input dry-run manifest (if not specified, uses latest)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output frozen manifest path'
    )
    parser.add_argument(
        '--config-hash',
        type=str,
        default='14382c2d3db97410',
        help='Config hash from dry-run (default: 14382c2d3db97410)'
    )
    parser.add_argument(
        '--normalization-method',
        type=str,
        default='percentile_rank_v1',
        help='Normalization method (default: percentile_rank_v1)'
    )
    parser.add_argument(
        '--profile',
        type=str,
        default='core_v1',
        help='Profile version (default: core_v1)'
    )
    parser.add_argument(
        '--source-file',
        type=Path,
        help='Source enriched file (if not specified, auto-detects dedup file)'
    )

    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[2]

    # Determine input file
    if args.input:
        input_file = args.input
    else:
        # Find latest dry-run manifest
        analysis_dir = base_dir / "analysis"
        dryrun_files = sorted(analysis_dir.glob("manifest_core_dryrun_*.parquet"))

        if not dryrun_files:
            print("ERROR: No dry-run manifests found")
            print(f"Searched in: {analysis_dir}")
            return

        input_file = dryrun_files[-1]
        print(f"Using latest dry-run: {input_file.name}")
        print()

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d")
        output_file = base_dir / "processed" / "events" / f"manifest_core_{timestamp}.parquet"

    # Determine source file
    if args.source_file:
        source_file = args.source_file
    else:
        # Auto-detect latest deduplicated file
        events_dir = base_dir / "processed" / "events"
        dedup_files = sorted(events_dir.glob("events_intraday_enriched_dedup_*.parquet"))

        if dedup_files:
            source_file = dedup_files[-1]
            deduplication_applied = True
        else:
            # Fallback to any enriched file
            enriched_files = sorted(events_dir.glob("events_intraday_enriched_*.parquet"))
            if enriched_files:
                source_file = enriched_files[-1]
                deduplication_applied = False
            else:
                print("ERROR: No source files found")
                return

    # Check if dedup in name
    deduplication_applied = 'dedup' in source_file.name

    # Freeze manifest
    metadata = freeze_manifest(
        input_file=input_file,
        output_file=output_file,
        config_hash=args.config_hash,
        normalization_method=args.normalization_method,
        profile_version=args.profile,
        deduplication_applied=deduplication_applied,
        source_file=source_file
    )

    print()
    print("="*80)
    print("NEXT STEPS")
    print("="*80)
    print("1. Verify manifest quality:")
    print(f"   python -c \"import polars as pl; df=pl.read_parquet('{output_file}'); print(df.head())\"")
    print()
    print("2. Launch FASE 3.2 download:")
    print(f"   python scripts/ingestion/download_trades_quotes_intraday.py \\")
    print(f"     --manifest {output_file} \\")
    print("     --workers 2 \\")
    print("     --rate-limit 12 \\")
    print("     --resume")
    print()


if __name__ == "__main__":
    main()
