"""
Rank tickers by event count for Top-K selection

Reads events_daily_*.parquet and ranks symbols by number of historical events.
Outputs ranking to processed/rankings/ for use in Week 2-3 minute bars download.

Usage:
    python scripts/processing/rank_by_event_count.py
    python scripts/processing/rank_by_event_count.py --top-n 2000
    python scripts/processing/rank_by_event_count.py --events-file processed/events/events_daily_20251008.parquet
"""

import sys
from pathlib import Path
from datetime import datetime
import argparse

import polars as pl
import yaml
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def load_config():
    """Load configuration from config.yaml"""
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def rank_by_events(events_file: Path, top_n: int = 2000) -> pl.DataFrame:
    """
    Rank symbols by event count

    Args:
        events_file: Path to events_daily_*.parquet
        top_n: Number of top symbols to return

    Returns:
        DataFrame with rankings
    """
    logger.info(f"Loading events from {events_file}")
    df = pl.read_parquet(events_file)

    # Filter to events only
    df_events = df.filter(pl.col("is_event") == True)

    logger.info(f"Total events: {df_events.height:,}")
    logger.info(f"Total symbols: {df['symbol'].n_unique():,}")

    # Rank by event count
    rank = (df_events
            .group_by("symbol")
            .agg([
                pl.len().alias("n_events"),
                pl.col("is_ssr").sum().alias("n_ssr_events"),
                pl.col("gap_pct").mean().alias("gap_pct_mean"),
                pl.col("gap_pct").max().alias("gap_pct_max"),
                pl.col("rvol").mean().alias("rvol_mean"),
                pl.col("rvol").max().alias("rvol_max"),
                pl.col("atr_pct").mean().alias("atr_pct_mean"),
                pl.col("dollar_volume").mean().alias("dollar_volume_mean"),
            ])
            .sort("n_events", descending=True))

    # Calculate additional metrics
    total_days_per_symbol = (df
                             .group_by("symbol")
                             .agg(pl.len().alias("total_days")))

    rank = rank.join(total_days_per_symbol, on="symbol", how="left")

    # Event rate (%)
    rank = rank.with_columns(
        (pl.col("n_events") / pl.col("total_days") * 100).alias("event_rate_pct")
    )

    # Add rank column
    rank = rank.with_columns(
        pl.int_range(1, pl.len() + 1).alias("rank")
    )

    # Top-N
    top_rank = rank.head(top_n)

    return top_rank


def main():
    parser = argparse.ArgumentParser(description="Rank tickers by event count")
    parser.add_argument("--events-file", type=str, help="Path to events parquet file (default: latest in processed/events/)")
    parser.add_argument("--top-n", type=int, default=2000, help="Number of top symbols to select (default: 2000)")
    parser.add_argument("--output-dir", type=str, help="Output directory (default: processed/rankings)")
    args = parser.parse_args()

    # Load config
    cfg = load_config()

    # Find events file
    if args.events_file:
        events_file = Path(args.events_file)
    else:
        events_dir = PROJECT_ROOT / cfg["paths"]["processed"] / "events"
        event_files = sorted(events_dir.glob("events_daily_*.parquet"))
        if not event_files:
            logger.error(f"No events files found in {events_dir}")
            logger.error("Run detect_events.py first")
            sys.exit(1)
        events_file = event_files[-1]  # Latest

    if not events_file.exists():
        logger.error(f"Events file not found: {events_file}")
        sys.exit(1)

    # Rank
    logger.info(f"Ranking top {args.top_n} symbols by event count")
    top_rank = rank_by_events(events_file, top_n=args.top_n)

    # Output
    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / cfg["paths"]["processed"] / "rankings"
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d")
    output_file = output_dir / f"top_{args.top_n}_by_events_{ts}.parquet"

    top_rank.write_parquet(output_file, compression="zstd")
    logger.info(f"Saved rankings to {output_file}")

    # Summary
    logger.info(f"\n=== Top {args.top_n} Summary ===")
    logger.info(f"Total events: {top_rank['n_events'].sum():,}")
    logger.info(f"Mean events per symbol: {top_rank['n_events'].mean():.1f}")
    logger.info(f"Median events per symbol: {top_rank['n_events'].median():.1f}")
    logger.info(f"Min events (rank {args.top_n}): {top_rank['n_events'].min():,}")
    logger.info(f"Mean event rate: {top_rank['event_rate_pct'].mean():.2f}%")

    # Top 20
    logger.info(f"\n=== Top 20 Symbols ===")
    print(top_rank.select([
        "rank",
        "symbol",
        "n_events",
        "event_rate_pct",
        "gap_pct_mean",
        "rvol_mean",
        "dollar_volume_mean"
    ]).head(20))

    # Distribution stats
    logger.info(f"\n=== Event Count Distribution (Top {args.top_n}) ===")
    quantiles = top_rank["n_events"].quantile([0.25, 0.50, 0.75, 0.90, 0.95, 0.99], interpolation="linear")
    logger.info(f"25th percentile: {quantiles[0]:.0f}")
    logger.info(f"50th percentile (median): {quantiles[1]:.0f}")
    logger.info(f"75th percentile: {quantiles[2]:.0f}")
    logger.info(f"90th percentile: {quantiles[3]:.0f}")
    logger.info(f"95th percentile: {quantiles[4]:.0f}")
    logger.info(f"99th percentile: {quantiles[5]:.0f}")


if __name__ == "__main__":
    main()
