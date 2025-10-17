#!/usr/bin/env python3
"""
Deduplicate events in enriched file.

Strategy:
1. Define unique key: (symbol, timestamp, event_type)
2. For duplicates, keep BEST event by:
   - Highest score
   - If tie: most complete data (fewest nulls)
   - If tie: first occurrence

Usage:
    python scripts/processing/deduplicate_events.py
"""

import polars as pl
from pathlib import Path
from datetime import datetime
import argparse


def count_nulls(df: pl.DataFrame, exclude_cols: list[str] = None) -> pl.Expr:
    """Count null values across all columns except excluded ones."""
    exclude_cols = exclude_cols or []
    cols_to_check = [c for c in df.columns if c not in exclude_cols]

    # Sum nulls across columns for each row
    null_counts = pl.lit(0)
    for col in cols_to_check:
        null_counts = null_counts + pl.col(col).is_null().cast(pl.Int32)

    return null_counts


def deduplicate_events(
    input_file: Path,
    output_file: Path,
    dry_run: bool = False
) -> dict:
    """
    Deduplicate events using robust strategy.

    Args:
        input_file: Path to input parquet file
        output_file: Path to output parquet file
        dry_run: If True, only report stats without writing

    Returns:
        Dictionary with deduplication statistics
    """

    print(f"Loading: {input_file}")
    df = pl.read_parquet(input_file)

    original_count = len(df)
    print(f"Original events: {original_count:,}")
    print()

    # Define unique key
    unique_key = ['symbol', 'timestamp', 'event_type']

    # Step 1: Identify duplicates
    print("Step 1: Identifying duplicates...")
    dup_check = df.group_by(unique_key).agg(
        pl.len().alias('count')
    ).filter(pl.col('count') > 1)

    num_dup_groups = len(dup_check)
    total_dup_events = dup_check['count'].sum() - num_dup_groups

    print(f"  Duplicate groups: {num_dup_groups:,}")
    print(f"  Duplicate events: {total_dup_events:,}")
    print(f"  Percentage: {total_dup_events / original_count * 100:.1f}%")
    print()

    if num_dup_groups == 0:
        print("✓ No duplicates found. File is already deduplicated.")
        return {
            "original_count": original_count,
            "deduplicated_count": original_count,
            "duplicates_removed": 0,
            "percentage_removed": 0.0
        }

    # Step 2: Add ranking columns for deduplication
    print("Step 2: Ranking events for deduplication...")

    # Add null count for each row (fewer nulls = better data quality)
    exclude_from_null_check = unique_key + ['score', 'score_raw']

    df_ranked = df.with_columns([
        # Count nulls in each row (excluding key columns and score)
        count_nulls(df, exclude_from_null_check).alias('_null_count')
    ])

    # Add rank within each duplicate group
    # Priority: highest score -> fewest nulls -> first occurrence (by row number)
    df_ranked = df_ranked.with_row_index('_row_num').with_columns([
        pl.col('score').rank(method='ordinal', descending=True)
          .over(unique_key).alias('_rank_score'),
        pl.col('_null_count').rank(method='ordinal', descending=False)
          .over(unique_key).alias('_rank_nulls'),
        pl.col('_row_num').rank(method='ordinal', descending=False)
          .over(unique_key).alias('_rank_row')
    ])

    # Combine rankings (lexicographic order)
    df_ranked = df_ranked.with_columns([
        (pl.col('_rank_score').cast(pl.Utf8) + '_' +
         pl.col('_rank_nulls').cast(pl.Utf8) + '_' +
         pl.col('_rank_row').cast(pl.Utf8)).alias('_combined_rank')
    ])

    # Step 3: Keep only the best event per group
    print("Step 3: Keeping best event per group...")

    # For each group, keep row with minimum combined_rank (which is lexicographically smallest)
    df_dedup = df_ranked.with_columns([
        pl.col('_combined_rank').min().over(unique_key).alias('_best_rank')
    ]).filter(
        pl.col('_combined_rank') == pl.col('_best_rank')
    )

    # Drop temporary columns
    temp_cols = ['_null_count', '_row_num', '_rank_score', '_rank_nulls',
                 '_rank_row', '_combined_rank', '_best_rank']
    df_dedup = df_dedup.drop(temp_cols)

    deduplicated_count = len(df_dedup)
    removed_count = original_count - deduplicated_count
    removed_pct = removed_count / original_count * 100

    print(f"  Deduplicated events: {deduplicated_count:,}")
    print(f"  Removed: {removed_count:,} ({removed_pct:.1f}%)")
    print()

    # Step 4: Verify no duplicates remain
    print("Step 4: Verifying deduplication...")
    verify = df_dedup.group_by(unique_key).agg(
        pl.len().alias('count')
    ).filter(pl.col('count') > 1)

    if len(verify) > 0:
        print(f"  WARNING: {len(verify)} duplicate groups still remain!")
        return None
    else:
        print("  OK Verification passed: No duplicates remain")
        print()

    # Statistics (sin asumir 'date_et')
    stats = {
        "original_count": original_count,
        "deduplicated_count": deduplicated_count,
        "duplicates_removed": removed_count,
        "percentage_removed": removed_pct,
        "unique_symbols": df_dedup['symbol'].n_unique(),
    }

    # Add date range info if available
    if "date_et" in df_dedup.columns:
        stats["date_start"] = str(df_dedup["date_et"].min())
        stats["date_end"] = str(df_dedup["date_et"].max())
    elif "timestamp" in df_dedup.columns:
        stats["timestamp_start"] = str(df_dedup["timestamp"].min())
        stats["timestamp_end"] = str(df_dedup["timestamp"].max())
    else:
        stats["range_info"] = "no date-like columns present"

    # Print summary
    print("="*80)
    print("DEDUPLICATION SUMMARY")
    print("="*80)
    print(f"Original events:      {stats['original_count']:>10,}")
    print(f"Deduplicated events:  {stats['deduplicated_count']:>10,}")
    print(f"Duplicates removed:   {stats['duplicates_removed']:>10,} ({stats['percentage_removed']:.1f}%)")
    print(f"Unique symbols:       {stats['unique_symbols']:>10,}")

    # Print date/timestamp range if available
    if "date_start" in stats and "date_end" in stats:
        print(f"Date range (ET):      {stats['date_start']} to {stats['date_end']}")
    elif "timestamp_start" in stats and "timestamp_end" in stats:
        print(f"Timestamp range:      {stats['timestamp_start']} to {stats['timestamp_end']}")
    elif "range_info" in stats:
        print(f"Range info:           {stats['range_info']}")

    print("="*80)
    print()

    # Write output
    if not dry_run:
        print(f"Writing deduplicated file: {output_file}")
        df_dedup.write_parquet(output_file)
        print(f"OK Saved: {output_file}")
        print(f"  Size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print("DRY RUN: No file written")

    import json, datetime, os
    if not dry_run:
        stats_file = os.path.splitext(output_file)[0] + ".stats.json"
        stats["run_id"] = f"dedup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        stats["input_file"] = str(input_file)
        stats["output_file"] = str(output_file)
        stats["finished_at"] = datetime.datetime.now().isoformat()
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        print(f"\nStats written to: {stats_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate events in enriched file"
    )
    parser.add_argument(
        '--input',
        type=Path,
        help='Input parquet file (if not specified, uses latest enriched file)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output parquet file (if not specified, adds _dedup suffix)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Only report statistics without writing file'
    )

    args = parser.parse_args()

    # Determine input file
    if args.input:
        input_file = args.input
    else:
        # Find latest enriched file
        base_dir = Path(__file__).resolve().parents[2]
        events_dir = base_dir / "processed" / "events"
        enriched_files = sorted(events_dir.glob("events_intraday_enriched_*.parquet"))

        if not enriched_files:
            print("ERROR: No enriched files found")
            print(f"Searched in: {events_dir}")
            return

        input_file = enriched_files[-1]
        print(f"Using latest enriched file: {input_file.name}")
        print()

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        # Add _dedup suffix before timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = input_file.parent / f"events_intraday_enriched_dedup_{timestamp}.parquet"

    # Run deduplication
    stats = deduplicate_events(input_file, output_file, dry_run=args.dry_run)

    if stats and not args.dry_run:
        print()
        print("="*80)
        print("NEXT STEPS")
        print("="*80)
        print("1. Use deduplicated file for all downstream processing")
        print("2. Run normalize_event_scores.py on deduplicated file")
        print("3. Run generate_core_manifest_dryrun.py with deduplicated file")
        print()


if __name__ == "__main__":
    main()
