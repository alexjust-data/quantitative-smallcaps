#!/usr/bin/env python3
"""
Event Enrichment Script - Add Daily Liquidity Metrics
======================================================

Enriches intraday events with daily liquidity metrics required for CORE filtering:
- dollar_volume_day: Daily dollar volume (v × vw from RAW daily bars)
- rvol_day: Relative volume vs 20-day mean (excluding current day)
- Recalculated session labels (PM/RTH/AH) in ET timezone
- vwap_min: Real VWAP from 1m bars (or typical price fallback)

Input:  processed/events/events_intraday_*.parquet
Output: processed/events/events_intraday_enriched_YYYYMMDD.parquet

Author: Generated for FASE 3.2 preparation
Date: 2025-10-13
"""

import polars as pl
from pathlib import Path
from datetime import datetime, time
from zoneinfo import ZoneInfo
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================================
# CONFIGURATION
# ============================================================================

ET_TZ = ZoneInfo("America/New_York")

# Session definitions (ET timezone)
PM_START = time(4, 0)
PM_END = time(9, 30)
RTH_START = time(9, 30)
RTH_END = time(16, 0)
AH_START = time(16, 0)
AH_END = time(20, 0)

ROLLING_WINDOW_DAYS = 20  # For rvol_day calculation

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def determine_session_et(hour: int, minute: int) -> str:
    """
    Determine session based on ET time.

    Args:
        hour: Hour in ET (0-23)
        minute: Minute (0-59)

    Returns:
        Session label: 'PM', 'RTH', or 'AH'
    """
    t = time(hour, minute)

    if PM_START <= t < PM_END:
        return 'PM'
    elif RTH_START <= t < RTH_END:
        return 'RTH'
    elif AH_START <= t < AH_END:
        return 'AH'
    else:
        # Outside regular hours (20:00-04:00 ET)
        return 'CLOSED'

def load_events_shards(shards_dir: Path) -> pl.DataFrame:
    """Load all event shards."""
    print(f"\n[1/6] Loading event shards...")

    shard_files = sorted(list(shards_dir.glob("events_intraday_*_shard*.parquet")))
    if not shard_files:
        raise FileNotFoundError(f"No event shards found in {shards_dir}")

    print(f"  Found {len(shard_files)} shard files")

    dfs = []
    for shard_file in shard_files:
        try:
            df = pl.read_parquet(shard_file)
            dfs.append(df)
        except Exception as e:
            print(f"  [WARNING] Failed to load {shard_file.name}: {e}")
            continue

    if not dfs:
        raise ValueError("No valid shards could be loaded")

    df = pl.concat(dfs)
    print(f"  Loaded: {len(df):,} events from {df['symbol'].n_unique()} symbols")

    return df

def normalize_timestamps(df: pl.DataFrame) -> pl.DataFrame:
    """Convert timestamps to ET timezone and extract date_et."""
    print(f"\n[2/6] Normalizing timestamps to ET timezone...")

    # Ensure timestamp is datetime
    if df['timestamp'].dtype == pl.Utf8:
        df = df.with_columns(
            pl.col('timestamp').str.strptime(pl.Datetime('us', 'UTC'), strict=False)
        )

    # Convert to ET timezone
    df = df.with_columns([
        pl.col('timestamp').dt.convert_time_zone('America/New_York').alias('timestamp_et')
    ])

    # Extract date in ET
    df = df.with_columns([
        pl.col('timestamp_et').dt.date().alias('date_et'),
        pl.col('timestamp_et').dt.hour().alias('hour_et'),
        pl.col('timestamp_et').dt.minute().alias('minute_et')
    ])

    print(f"  Converted {len(df):,} events to ET timezone")
    print(f"  Date range: {df['date_et'].min()} to {df['date_et'].max()}")

    return df

def recalculate_sessions(df: pl.DataFrame) -> pl.DataFrame:
    """Recalculate session labels using ET time."""
    print(f"\n[3/6] Recalculating session labels (PM/RTH/AH)...")

    # Determine session based on ET time
    df = df.with_columns([
        pl.when((pl.col('hour_et') >= 4) &
                ((pl.col('hour_et') < 9) |
                 ((pl.col('hour_et') == 9) & (pl.col('minute_et') < 30))))
        .then(pl.lit('PM'))
        .when((pl.col('hour_et') >= 9) &
              ((pl.col('hour_et') < 16) |
               ((pl.col('hour_et') == 16) & (pl.col('minute_et') == 0))))
        .then(pl.lit('RTH'))
        .when((pl.col('hour_et') >= 16) & (pl.col('hour_et') < 20))
        .then(pl.lit('AH'))
        .otherwise(pl.lit('CLOSED'))
        .alias('session_recalc')
    ])

    # Count session distribution
    session_counts = df.group_by('session_recalc').agg(pl.len().alias('count'))
    print(f"\n  Session distribution (recalculated):")
    for row in session_counts.to_dicts():
        pct = row['count'] / len(df) * 100
        print(f"    {row['session_recalc']:8s}: {row['count']:>8,} ({pct:>5.1f}%)")

    # Replace old session with recalculated
    df = df.drop('session').rename({'session_recalc': 'session'})

    # Filter out CLOSED hours
    before_filter = len(df)
    df = df.filter(pl.col('session') != 'CLOSED')
    filtered = before_filter - len(df)
    if filtered > 0:
        print(f"  [INFO] Filtered {filtered:,} events in CLOSED hours")

    return df

def load_daily_bars(symbols: list[str], base_dir: Path) -> pl.DataFrame:
    """Load daily bars (RAW) for all symbols."""
    print(f"\n[4/6] Loading daily bars (RAW) for {len(symbols)} symbols...")

    daily_dir = base_dir / "raw" / "market_data" / "bars" / "1d_raw"

    all_daily = []
    symbols_found = 0
    symbols_missing = 0

    for symbol in symbols:
        symbol_file = daily_dir / f"{symbol}.parquet"
        if not symbol_file.exists():
            symbols_missing += 1
            continue

        try:
            df = pl.read_parquet(symbol_file)
            if 'symbol' not in df.columns:
                df = df.with_columns(pl.lit(symbol).alias('symbol'))
            all_daily.append(df)
            symbols_found += 1
        except Exception as e:
            print(f"  [WARNING] Failed to load {symbol}.parquet: {e}")
            symbols_missing += 1
            continue

    if not all_daily:
        raise ValueError("No daily bars could be loaded")

    df_daily = pl.concat(all_daily)

    # Ensure we have required columns
    required_cols = ['symbol', 'timestamp', 'volume', 'vwap']
    missing_cols = [c for c in required_cols if c not in df_daily.columns]

    if 'vwap' in missing_cols:
        print(f"  [WARNING] 'vwap' column missing, using typical price (H+L+C)/3")
        df_daily = df_daily.with_columns([
            ((pl.col('high') + pl.col('low') + pl.col('close')) / 3).alias('vwap')
        ])

    # Convert timestamp to date
    df_daily = df_daily.with_columns([
        pl.col('timestamp').dt.date().alias('date')
    ])

    # Calculate dollar_volume_day
    df_daily = df_daily.with_columns([
        (pl.col('volume') * pl.col('vwap')).alias('dollar_volume_day')
    ])

    print(f"  Loaded daily bars: {len(df_daily):,} bars")
    print(f"  Symbols found: {symbols_found}, missing: {symbols_missing}")

    return df_daily.select(['symbol', 'date', 'volume', 'vwap', 'dollar_volume_day'])

def calculate_rvol_day(df_daily: pl.DataFrame) -> pl.DataFrame:
    """Calculate rvol_day (relative volume vs 20-day mean, excluding current day)."""
    print(f"\n[5/6] Calculating rvol_day (20-day rolling mean, left-closed)...")

    # Sort by symbol and date
    df_daily = df_daily.sort(['symbol', 'date'])

    # Calculate rolling mean of dollar_volume_day (20 days, excluding current)
    df_daily = df_daily.with_columns([
        pl.col('dollar_volume_day')
        .rolling_mean(window_size=ROLLING_WINDOW_DAYS, min_periods=ROLLING_WINDOW_DAYS, center=False)
        .shift(1)  # Shift by 1 to exclude current day
        .over('symbol')
        .alias('dv_mean_20d')
    ])

    # Calculate rvol_day
    df_daily = df_daily.with_columns([
        (pl.col('dollar_volume_day') / pl.col('dv_mean_20d')).alias('rvol_day'),
        pl.col('dv_mean_20d').is_null().alias('rvol_day_missing')
    ])

    # Stats
    total_rows = len(df_daily)
    missing_count = df_daily['rvol_day_missing'].sum()
    valid_count = total_rows - missing_count

    print(f"  Total bars: {total_rows:,}")
    print(f"  Valid rvol_day: {valid_count:,} ({valid_count/total_rows:.1%})")
    print(f"  Missing rvol_day: {missing_count:,} ({missing_count/total_rows:.1%})")

    if valid_count > 0:
        rvol_stats = df_daily.filter(~pl.col('rvol_day_missing'))['rvol_day']
        print(f"  RVol stats: p50={rvol_stats.median():.2f}x, p90={rvol_stats.quantile(0.9):.2f}x, max={rvol_stats.max():.2f}x")

    return df_daily

def join_daily_metrics(df_events: pl.DataFrame, df_daily: pl.DataFrame) -> pl.DataFrame:
    """Join daily metrics to events."""
    print(f"\n[6/6] Joining daily metrics to events...")

    initial_count = len(df_events)

    # Join on (symbol, date_et)
    df_enriched = df_events.join(
        df_daily.select(['symbol', 'date', 'dollar_volume_day', 'rvol_day', 'rvol_day_missing']),
        left_on=['symbol', 'date_et'],
        right_on=['symbol', 'date'],
        how='left'
    )

    # Check join success
    null_dv = df_enriched['dollar_volume_day'].null_count()
    null_rvol = df_enriched['rvol_day'].null_count()

    print(f"  Events before join: {initial_count:,}")
    print(f"  Events after join: {len(df_enriched):,}")
    print(f"  Missing dollar_volume_day: {null_dv:,} ({null_dv/len(df_enriched):.1%})")
    print(f"  Missing rvol_day: {null_rvol:,} ({null_rvol/len(df_enriched):.1%})")

    # Add proxy metrics if not exist
    if 'vwap_min' not in df_enriched.columns:
        print(f"  [INFO] Adding vwap_min proxy (H+L+C)/3")
        df_enriched = df_enriched.with_columns([
            ((pl.col('high') + pl.col('low') + pl.col('close')) / 3).alias('vwap_min')
        ])

    if 'dollar_volume_bar' not in df_enriched.columns:
        print(f"  [INFO] Adding dollar_volume_bar (volume × vwap_min)")
        df_enriched = df_enriched.with_columns([
            (pl.col('volume') * pl.col('vwap_min')).alias('dollar_volume_bar')
        ])

    if 'spread_proxy' not in df_enriched.columns:
        print(f"  [INFO] Adding spread_proxy ((H-L)/vwap_min)")
        df_enriched = df_enriched.with_columns([
            ((pl.col('high') - pl.col('low')) / pl.col('vwap_min')).alias('spread_proxy')
        ])

    # Add enrichment metadata
    df_enriched = df_enriched.with_columns([
        pl.lit(True).alias('enriched'),
        pl.lit(datetime.now().isoformat()).alias('enriched_at')
    ])

    return df_enriched

def main():
    print("="*80)
    print("EVENT ENRICHMENT - Daily Liquidity Metrics")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Rolling window: {ROLLING_WINDOW_DAYS} days")
    print("="*80)

    base_dir = Path("D:/04_TRADING_SMALLCAPS")
    shards_dir = base_dir / "processed" / "events" / "shards"
    output_dir = base_dir / "processed" / "events"
    output_dir.mkdir(exist_ok=True)

    # Load events
    df_events = load_events_shards(shards_dir)

    # Normalize timestamps and recalculate sessions
    df_events = normalize_timestamps(df_events)
    df_events = recalculate_sessions(df_events)

    # Get unique symbols
    symbols = df_events['symbol'].unique().to_list()
    print(f"\n  Unique symbols in events: {len(symbols)}")

    # Load daily bars
    df_daily = load_daily_bars(symbols, base_dir)

    # Calculate rvol_day
    df_daily = calculate_rvol_day(df_daily)

    # Join daily metrics to events
    df_enriched = join_daily_metrics(df_events, df_daily)

    # Save enriched events
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"events_intraday_enriched_{timestamp}.parquet"

    df_enriched.write_parquet(output_file, compression="zstd")

    print("\n" + "="*80)
    print("ENRICHMENT COMPLETE")
    print("="*80)
    print(f"\nOutput file: {output_file}")
    print(f"Total events: {len(df_enriched):,}")
    print(f"Unique symbols: {df_enriched['symbol'].n_unique()}")

    # Final session distribution
    session_final = df_enriched.group_by('session').agg(pl.len().alias('count'))
    print(f"\nFinal session distribution:")
    for row in session_final.to_dicts():
        pct = row['count'] / len(df_enriched) * 100
        print(f"  {row['session']:8s}: {row['count']:>8,} ({pct:>5.1f}%)")

    # Liquidity metrics summary
    valid_rvol = df_enriched.filter(~pl.col('rvol_day_missing'))
    if len(valid_rvol) > 0:
        print(f"\nRVol Day summary (valid events):")
        print(f"  Valid: {len(valid_rvol):,} ({len(valid_rvol)/len(df_enriched):.1%})")
        print(f"  Median: {valid_rvol['rvol_day'].median():.2f}x")
        print(f"  P90: {valid_rvol['rvol_day'].quantile(0.9):.2f}x")

    print("\n[NEXT] Run dry-run with enriched events for CORE manifest")
    print("="*80)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
