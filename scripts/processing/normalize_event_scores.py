#!/usr/bin/env python3
"""
Normalize Event Scores to [0, 1] Range

CRITICAL: Event scores must be normalized for proper desempate estable
and accurate sanity checks. Current scores range from 0.5 to 7195.4,
which is NOT the expected [0, 1] range.

This script:
1. Loads latest enriched events file
2. Normalizes scores using min-max per event_type and session
3. Keeps original scores as 'score_raw' for auditing
4. Saves normalized events with timestamp

Author: FASE 3.2 Pipeline
Date: 2025-10-13
"""

import polars as pl
from pathlib import Path
from datetime import datetime
import sys

def normalize_scores(input_file: Path, output_file: Path):
    """
    Normalize scores using min-max per event_type and session.

    Formula: score_norm = (score - min) / (max - min)
    Applied per: (event_type, session) groups
    """

    print("=" * 80)
    print("EVENT SCORE NORMALIZATION")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Input: {input_file.name}")
    print("=" * 80)

    # Load data
    print("\n[1/5] Loading events...")
    df = pl.read_parquet(input_file)
    print(f"  Loaded: {len(df):,} events from {df['symbol'].n_unique()} symbols")

    # Check if already normalized
    if 'score_raw' in df.columns:
        print("\n  WARNING: File already contains 'score_raw' column")
        print("  This suggests scores were previously normalized")
        response = input("  Continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("  Aborted")
            sys.exit(0)

    # Original score stats
    print("\n[2/5] Original score statistics...")
    print(f"  Min:    {df['score'].min():.2f}")
    print(f"  Max:    {df['score'].max():.2f}")
    print(f"  Median: {df['score'].median():.2f}")
    print(f"  Mean:   {df['score'].mean():.2f}")

    # Check for nulls
    null_count = df['score'].null_count()
    if null_count > 0:
        print(f"\n  WARNING: {null_count} null scores found!")
        print("  Filtering out null scores...")
        df = df.filter(pl.col('score').is_not_null())

    # Normalize per event_type and session using PERCENTILE RANK
    print("\n[3/5] Normalizing scores (percentile rank per event_type + session)...")
    print("  Method: CDF empirical (resolves heavy-tailed distribution)")

    # Calculate percentile rank within each group
    # rank() gives position, we normalize by max position to get [0, 1]
    df = df.with_columns([
        pl.col('score')
        .rank(method='average')  # Average handles ties
        .over(['event_type', 'session'])
        .alias('score_rank')
    ])

    # Get max rank per group for normalization
    df = df.with_columns([
        pl.col('score_rank')
        .max()
        .over(['event_type', 'session'])
        .alias('score_rank_max')
    ])

    # Normalize rank to [0, 1]
    # (rank - 1) / (max_rank - 1) ensures 0.0 for worst and 1.0 for best
    df = df.with_columns([
        pl.when(pl.col('score_rank_max') > 1)
        .then((pl.col('score_rank') - 1) / (pl.col('score_rank_max') - 1))
        .otherwise(pl.lit(0.5))  # If only 1 event in group, set to middle
        .alias('score_normalized')
    ])

    # Replace original score with normalized (keep backup)
    df = df.with_columns([
        pl.col('score').alias('score_raw'),
        pl.col('score_normalized').alias('score')
    ]).drop(['score_normalized', 'score_rank', 'score_rank_max'])

    # Normalized score stats
    print("\n[4/5] Normalized score statistics (percentile rank)...")
    print(f"  Min:    {df['score'].min():.4f}")
    print(f"  Max:    {df['score'].max():.4f}")
    print(f"  Median: {df['score'].median():.4f}")
    print(f"  Mean:   {df['score'].mean():.4f}")
    print(f"  P25:    {df['score'].quantile(0.25):.4f}")
    print(f"  P75:    {df['score'].quantile(0.75):.4f}")

    # Distribution sanity check (percentile rank should be ~uniform)
    pct_above_60 = (df.filter(pl.col('score') >= 0.60).height / len(df)) * 100
    pct_above_70 = (df.filter(pl.col('score') >= 0.70).height / len(df)) * 100
    pct_above_80 = (df.filter(pl.col('score') >= 0.80).height / len(df)) * 100

    print(f"\n  Distribution (expected ~uniform for percentile rank):")
    print(f"    >= 0.60: {pct_above_60:.1f}% (expected ~40%)")
    print(f"    >= 0.70: {pct_above_70:.1f}% (expected ~30%)")
    print(f"    >= 0.80: {pct_above_80:.1f}% (expected ~20%)")

    # Validation
    print("\n[5/5] Validation checks...")

    checks_passed = 0
    checks_total = 6

    # Check 1: Min >= 0
    if df['score'].min() >= 0.0:
        print("  [PASS] Min >= 0.0")
        checks_passed += 1
    else:
        print(f"  [FAIL] Min < 0.0: {df['score'].min()}")

    # Check 2: Max <= 1
    if df['score'].max() <= 1.0:
        print("  [PASS] Max <= 1.0")
        checks_passed += 1
    else:
        print(f"  [FAIL] Max > 1.0: {df['score'].max()}")

    # Check 3: No nulls
    if df['score'].null_count() == 0:
        print("  [PASS] No null scores")
        checks_passed += 1
    else:
        print(f"  [FAIL] {df['score'].null_count()} null scores")

    # Check 4: score_raw preserved
    if 'score_raw' in df.columns:
        print("  [PASS] Original scores preserved as 'score_raw'")
        checks_passed += 1
    else:
        print("  [FAIL] Original scores NOT preserved")

    # Check 5: Median close to 0.5 (expected for percentile rank)
    median = df['score'].median()
    if 0.40 <= median <= 0.60:
        print(f"  [PASS] Median ~0.5 ({median:.4f}) - proper percentile rank")
        checks_passed += 1
    else:
        print(f"  [WARN] Median {median:.4f} not near 0.5 - distribution may be skewed")

    # Check 6: Reasonable fraction above threshold (40% ± 10% for score >= 0.60)
    if 30.0 <= pct_above_60 <= 50.0:
        print(f"  [PASS] {pct_above_60:.1f}% events >= 0.60 (expected ~40%)")
        checks_passed += 1
    else:
        print(f"  [WARN] {pct_above_60:.1f}% events >= 0.60 (expected ~40%)")

    print(f"\n  Validation: {checks_passed}/{checks_total} checks passed")

    if checks_passed < checks_total:
        print("\n  WARNING: Some validation checks failed!")
        response = input("  Save anyway? (y/n): ")
        if response.lower() != 'y':
            print("  Aborted")
            sys.exit(1)

    # Save
    print(f"\n  Saving to: {output_file.name}")
    df.write_parquet(output_file)
    print(f"  Saved: {len(df):,} events")

    # Summary
    print("\n" + "=" * 80)
    print("NORMALIZATION COMPLETE")
    print("=" * 80)
    print(f"\nOutput file: {output_file}")
    print(f"Total events: {len(df):,}")
    print(f"Unique symbols: {df['symbol'].n_unique()}")
    print(f"\nScore range: [{df['score'].min():.4f}, {df['score'].max():.4f}]")
    print(f"Score median: {df['score'].median():.4f}")
    print("\n[NEXT] Run dry-run with normalized scores:")
    print(f"       python scripts/processing/generate_core_manifest_dryrun.py")
    print("=" * 80)


def main():
    base_dir = Path(__file__).resolve().parents[2]

    # Find latest enriched file
    events_dir = base_dir / "processed" / "events"
    enriched_files = sorted(events_dir.glob("events_intraday_enriched_*.parquet"))

    if not enriched_files:
        print("ERROR: No enriched events files found")
        print(f"Expected location: {events_dir}")
        print("Run enrich_events_with_daily_metrics.py first")
        sys.exit(1)

    input_file = enriched_files[-1]
    print(f"\nFound {len(enriched_files)} enriched file(s)")
    print(f"Using latest: {input_file.name}\n")

    # Generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = events_dir / f"events_intraday_enriched_normalized_{timestamp}.parquet"

    # Confirm
    response = input(f"Proceed with normalization? (y/n): ")
    if response.lower() != 'y':
        print("Aborted")
        sys.exit(0)

    # Execute
    normalize_scores(input_file, output_file)


if __name__ == "__main__":
    main()
