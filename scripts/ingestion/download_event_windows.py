"""
Download minute bars for event windows only (D-2 to D+2)

For tickers outside Top-2000, download 1-min bars only for specific time windows
around detected events, instead of full 3-year history.

This saves massive storage and download time while capturing all useful signal.

Usage:
    python scripts/ingestion/download_event_windows.py --preset compact --resume
    python scripts/ingestion/download_event_windows.py --symbols AAPL TSLA --preset compact
    python scripts/ingestion/download_event_windows.py --events-file processed/events/events_daily_20251008.parquet
    python scripts/ingestion/download_event_windows.py --dry-run  # Test without downloading
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import time

import polars as pl
import yaml
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "ingestion"))

from ingest_polygon import PolygonIngester


def load_config():
    """Load configuration from config.yaml"""
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def parse_time(time_str: str) -> tuple:
    """Parse HH:MM string to (hour, minute)"""
    h, m = time_str.split(":")
    return int(h), int(m)


def get_event_windows(preset: str, cfg: dict) -> dict:
    """
    Get time windows for event days from config

    Returns dict: {day_offset: [["HH:MM","HH:MM"], ...]}
    Example: {"d_minus_2": [["09:30","16:00"]], "d": [["07:00","16:00"]]}
    """
    windows_cfg = cfg["processing"]["events_windows"]

    if preset not in windows_cfg:
        raise ValueError(f"Preset '{preset}' not found in config. Available: {list(windows_cfg.keys())}")

    preset_cfg = windows_cfg[preset]

    # Map day names to offsets
    day_map = {
        "d_minus_2": -2,
        "d_minus_1": -1,
        "d": 0,
        "d_plus_1": 1,
        "d_plus_2": 2
    }

    windows = {}
    for day_name, time_ranges in preset_cfg.items():
        if day_name in day_map:
            windows[day_map[day_name]] = time_ranges

    return windows


def filter_to_time_window(df: pl.DataFrame, start_time: str, end_time: str, timezone: str = "America/New_York") -> pl.DataFrame:
    """
    Filter DataFrame to specific time window (HH:MM to HH:MM) in target timezone

    CRITICAL: This function ensures exact time slicing in NY timezone.
    Times are inclusive: [start_time, end_time]

    Args:
        df: DataFrame with 'timestamp' column (UTC)
        start_time: "HH:MM" (NY timezone)
        end_time: "HH:MM" (NY timezone)
        timezone: Target timezone

    Returns:
        Filtered DataFrame with bars in time window
    """
    if df.height == 0:
        return df

    # Convert to target timezone
    df = df.with_columns(
        pl.col("timestamp").dt.convert_time_zone(timezone).alias("ts_local")
    )

    start_h, start_m = parse_time(start_time)
    end_h, end_m = parse_time(end_time)

    # Filter by hour and minute (inclusive)
    df_filtered = df.filter(
        (
            (pl.col("ts_local").dt.hour() > start_h) |
            ((pl.col("ts_local").dt.hour() == start_h) & (pl.col("ts_local").dt.minute() >= start_m))
        ) &
        (
            (pl.col("ts_local").dt.hour() < end_h) |
            ((pl.col("ts_local").dt.hour() == end_h) & (pl.col("ts_local").dt.minute() <= end_m))
        )
    )

    # Drop temp column
    df_filtered = df_filtered.drop("ts_local")

    return df_filtered


def download_day_cached(
    ingester: PolygonIngester,
    symbol: str,
    target_date: datetime,
    day_cache: dict
) -> pl.DataFrame:
    """
    Download entire trading day for a symbol with caching

    Args:
        ingester: PolygonIngester instance
        symbol: Ticker symbol
        target_date: Date to download
        day_cache: Cache dict {(symbol, date): DataFrame}

    Returns:
        DataFrame with all minute bars for the day, or None if failed
    """
    cache_key = (symbol, target_date.date())

    # Check cache
    if cache_key in day_cache:
        return day_cache[cache_key]

    # Download
    from_date = target_date.strftime("%Y-%m-%d")
    to_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        df = ingester.download_aggregates(
            ticker=symbol,
            multiplier=1,
            timespan="minute",
            from_date=from_date,
            to_date=to_date
        )

        if df is None or df.height == 0:
            logger.debug(f"{symbol}: No data for {from_date}")
            day_cache[cache_key] = None
            return None

        # Cache and return
        day_cache[cache_key] = df
        return df

    except Exception as e:
        logger.error(f"{symbol}: Failed to download {from_date}: {e}")
        day_cache[cache_key] = None
        return None


def download_windows_for_event(
    ingester: PolygonIngester,
    symbol: str,
    event_date: datetime,
    windows: dict,
    output_dir: Path,
    cfg: dict,
    day_cache: dict,
    dry_run: bool = False
) -> dict:
    """
    Download all windows for a single event using day caching

    Args:
        ingester: PolygonIngester instance
        symbol: Ticker symbol
        event_date: Date of the event (D)
        windows: Event windows dict {day_offset: time_ranges}
        output_dir: Output directory for this symbol/event
        cfg: Config dict
        day_cache: Cache dict for downloaded days
        dry_run: If True, don't actually download or save files

    Returns:
        Dict with stats: {windows_saved, windows_failed}
    """
    stats = {"windows_saved": 0, "windows_failed": 0}
    timezone = cfg["processing"]["timezone"]

    # Download each day once and slice into windows
    for day_offset, time_ranges in windows.items():
        target_date = event_date + timedelta(days=day_offset)
        day_key = f"d{day_offset:+d}"

        # Download entire day (cached)
        df_day = download_day_cached(ingester, symbol, target_date, day_cache)

        if df_day is None:
            # Mark all windows for this day as failed
            stats["windows_failed"] += len(time_ranges)
            continue

        # Slice each time window
        for time_range in time_ranges:
            start_time, end_time = time_range
            df_window = filter_to_time_window(df_day, start_time, end_time, timezone=timezone)

            if df_window.height == 0:
                logger.debug(f"{symbol}: No bars in window {day_key} {start_time}-{end_time}")
                stats["windows_failed"] += 1
                continue

            # Save window
            window_name = f"minute_{day_key}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.parquet"
            output_file = output_dir / window_name

            if not dry_run:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                df_window.write_parquet(output_file, compression="zstd")

            logger.debug(f"{symbol}: Saved {df_window.height} bars to {window_name}")
            stats["windows_saved"] += 1

    return stats


def download_events_for_symbol(
    symbol: str,
    events_df: pl.DataFrame,
    ingester: PolygonIngester,
    windows: dict,
    base_output_dir: Path,
    cfg: dict,
    resume: bool = True,
    dry_run: bool = False
) -> dict:
    """
    Download all event windows for a symbol

    Args:
        symbol: Ticker symbol
        events_df: DataFrame with events for this symbol
        ingester: PolygonIngester instance
        windows: Event windows dict {day_offset: time_ranges}
        base_output_dir: Base output directory
        cfg: Config dict
        resume: Skip already downloaded events
        dry_run: If True, don't actually download or save files

    Returns:
        Dict with stats: {events_processed, events_skipped, windows_saved, windows_failed}
    """
    stats = {"events_processed": 0, "events_skipped": 0, "windows_saved": 0, "windows_failed": 0}

    # Get events for this symbol
    symbol_events = events_df.filter(pl.col("symbol") == symbol)

    if symbol_events.height == 0:
        return stats

    logger.info(f"{symbol}: {symbol_events.height} events found")

    # Day cache for this symbol (reuse across events)
    day_cache = {}

    # Process each event
    for event_row in symbol_events.iter_rows(named=True):
        event_date = event_row["timestamp"]
        event_id = event_row.get("event_id", event_date.strftime("%Y%m%d"))

        # Output directory for this event
        event_output_dir = base_output_dir / symbol / event_id

        # Resume check: if all expected windows exist, skip
        if resume and event_output_dir.exists():
            expected_files = []
            for day_offset, time_ranges in windows.items():
                day_key = f"d{day_offset:+d}"
                for start_time, end_time in time_ranges:
                    window_name = f"minute_{day_key}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.parquet"
                    expected_files.append(event_output_dir / window_name)

            if all(f.exists() for f in expected_files):
                stats["events_skipped"] += 1
                stats["windows_saved"] += len(expected_files)
                continue

        # Download windows for this event
        event_stats = download_windows_for_event(
            ingester,
            symbol,
            event_date,
            windows,
            event_output_dir,
            cfg,
            day_cache,
            dry_run=dry_run
        )

        stats["events_processed"] += 1
        stats["windows_saved"] += event_stats["windows_saved"]
        stats["windows_failed"] += event_stats["windows_failed"]

        # Rate limiting between events
        if not dry_run:
            time.sleep(0.1)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Download minute bars for event windows only")
    parser.add_argument("--events-file", type=str, help="Path to events parquet file (default: latest)")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to process (default: all with events)")
    parser.add_argument("--preset", type=str, default="compact", help="Window preset from config (default: compact)")
    parser.add_argument("--output-dir", type=str, help="Output directory (default: raw/market_data/events)")
    parser.add_argument("--resume", action="store_true", help="Skip already downloaded events")
    parser.add_argument("--max-symbols", type=int, help="Limit number of symbols to process")
    parser.add_argument("--dry-run", action="store_true", help="Test without actually downloading or saving files")
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
        events_file = event_files[-1]

    if not events_file.exists():
        logger.error(f"Events file not found: {events_file}")
        sys.exit(1)

    # Load events
    logger.info(f"Loading events from {events_file}")
    df_events = pl.read_parquet(events_file)
    df_events = df_events.filter(pl.col("is_event") == True)

    logger.info(f"Total events: {df_events.height:,}")
    logger.info(f"Symbols with events: {df_events['symbol'].n_unique():,}")

    # Filter symbols if specified
    if args.symbols:
        df_events = df_events.filter(pl.col("symbol").is_in(args.symbols))
        logger.info(f"Filtered to {len(args.symbols)} specified symbols")

    # Get unique symbols
    symbols = df_events["symbol"].unique().to_list()

    if args.max_symbols:
        symbols = symbols[:args.max_symbols]
        logger.info(f"Limited to first {args.max_symbols} symbols")

    # Get event windows
    windows = get_event_windows(args.preset, cfg)
    logger.info(f"Using preset '{args.preset}' with windows:")
    for offset, time_ranges in windows.items():
        logger.info(f"  D{offset:+d}: {time_ranges}")

    # Output directory
    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / cfg["paths"]["raw"] / "market_data" / "events"

    if args.dry_run:
        logger.warning("DRY RUN MODE - No files will be downloaded or saved")

    # Initialize ingester
    ingester = PolygonIngester() if not args.dry_run else None

    # Process symbols
    total_stats = {"events_processed": 0, "events_skipped": 0, "windows_saved": 0, "windows_failed": 0}

    for i, symbol in enumerate(symbols):
        logger.info(f"\n[{i+1}/{len(symbols)}] Processing {symbol}")

        stats = download_events_for_symbol(
            symbol,
            df_events,
            ingester,
            windows,
            output_dir,
            cfg,
            resume=args.resume,
            dry_run=args.dry_run
        )

        total_stats["events_processed"] += stats["events_processed"]
        total_stats["events_skipped"] += stats["events_skipped"]
        total_stats["windows_saved"] += stats["windows_saved"]
        total_stats["windows_failed"] += stats["windows_failed"]

        logger.info(f"{symbol}: events_processed={stats['events_processed']}, events_skipped={stats['events_skipped']}, "
                   f"windows_saved={stats['windows_saved']}, windows_failed={stats['windows_failed']}")

    # Final summary
    logger.info(f"\n=== COMPLETE ===")
    logger.info(f"Events processed: {total_stats['events_processed']:,}")
    logger.info(f"Events skipped: {total_stats['events_skipped']:,}")
    logger.info(f"Windows saved: {total_stats['windows_saved']:,}")
    logger.info(f"Windows failed: {total_stats['windows_failed']:,}")
    logger.info(f"Output directory: {output_dir}")


if __name__ == "__main__":
    main()
