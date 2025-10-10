"""
Event Detection with Multi-Branch Logic for Small-Caps

Detects trading events using 5 branches:
- Branch 1: Gap Play (Gap ≥ threshold AND RVOL ≥ threshold)
- Branch 2: Intraday Range Explosion (IRE% ≥ 30% AND RVOL ≥ 2x)
- Branch 3: Volume Spike Without Gap (RVOL ≥ 5x AND Gap ≥ 2%)
- Branch 4: ATR Breakout (ATR% ≥ percentile AND RVOL ≥ threshold_alt)
- Branch 5: Flush Reversal (Close > Open after -20% flush AND RVOL ≥ 2.5x)

Global filters:
- Bullish only (Close > Open)
- Dollar Volume ≥ threshold
- Optional: Multi-day confirmation

Usage:
    python scripts/processing/detect_events.py --use-percentiles
    python scripts/processing/detect_events.py --symbols AAPL TSLA --use-percentiles
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import argparse

import polars as pl
import numpy as np
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


def compute_daily_metrics(df: pl.DataFrame, atr_window: int = 60) -> pl.DataFrame:
    """
    Compute daily metrics: gap_pct, RVOL, ATR%, dollar_volume, IRE%

    Args:
        df: DataFrame with OHLCV data (must have: timestamp, open, high, low, close, volume)
        atr_window: Window for ATR calculation

    Returns:
        DataFrame with additional columns: gap_pct, rvol, atr_pct, dollar_volume, ire_pct
    """
    df = df.sort("timestamp")

    # Previous close
    prev_close = pl.col("close").shift(1)

    # Gap % (preserve sign for direction detection)
    gap_pct = ((pl.col("open") - prev_close) / prev_close * 100)

    # Intraday Range Explosion % (IRE)
    ire_pct = ((pl.col("high") - pl.col("low")) / pl.col("open") * 100)

    # Dollar volume (using close price)
    dollar_volume = pl.col("close") * pl.col("volume")

    # Average volume (20-day rolling)
    avg_volume = pl.col("volume").rolling_mean(window_size=20, min_periods=5)

    # RVOL (Relative Volume)
    rvol = pl.col("volume") / avg_volume

    # True Range
    tr = pl.max_horizontal([
        pl.col("high") - pl.col("low"),
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs()
    ])

    # ATR
    atr = tr.rolling_mean(window_size=atr_window, min_periods=atr_window // 2)

    # ATR%
    atr_pct = (atr / pl.col("close") * 100)

    # Flush detection: Low of last 5 days
    low_5d = pl.col("low").rolling_min(window_size=5, min_periods=1)

    # Drawdown from 5d low
    drawdown_from_5d_low = ((low_5d - pl.col("close")) / low_5d * 100)

    return df.with_columns([
        gap_pct.alias("gap_pct"),
        rvol.alias("rvol"),
        atr_pct.alias("atr_pct"),
        ire_pct.alias("ire_pct"),
        dollar_volume.alias("dollar_volume"),
        avg_volume.alias("avg_volume_20d"),
        atr.alias("atr"),
        drawdown_from_5d_low.alias("drawdown_5d")
    ])


def compute_ssr_flag(df: pl.DataFrame) -> pl.DataFrame:
    """
    Compute SSR (Short Sale Restriction) flag

    SSR activates when low <= 0.90 * prev_close (approximation)
    """
    prev_close = pl.col("close").shift(1)
    ssr_active = (pl.col("low") <= prev_close * 0.90)

    return df.with_columns(ssr_active.alias("is_ssr"))


def compute_premarket_volume(sym: str, bars_1h_dir: Path, event_ts: datetime, cfg: dict) -> float:
    """
    Compute premarket dollar volume from 1h bars using vwap * volume

    Returns:
        Premarket dollar volume, or 0 if data not available
    """
    file_1h = bars_1h_dir / f"{sym}.parquet"
    if not file_1h.exists():
        return 0.0

    try:
        df_1h = pl.read_parquet(file_1h)

        # Convert to NY timezone
        df_1h = df_1h.with_columns(
            pl.col("timestamp").dt.convert_time_zone("America/New_York").alias("ts_ny")
        )

        # Filter to target date and PM hours (7-8 AM NY)
        pm_hours = cfg["processing"]["events"]["premarket_hours_ny"]
        event_date = event_ts.date()

        df_pm = df_1h.filter(
            (pl.col("ts_ny").dt.date() == event_date) &
            (pl.col("ts_ny").dt.hour().is_in(pm_hours))
        )

        if df_pm.height == 0:
            return 0.0

        # Dollar volume using vwap
        if "vwap" in df_pm.columns:
            pm_dvol = (df_pm["vwap"] * df_pm["volume"]).sum()
        else:
            pm_dvol = (df_pm["close"] * df_pm["volume"]).sum()

        return float(pm_dvol) if pm_dvol else 0.0

    except Exception as e:
        logger.warning(f"Failed to compute PM volume for {sym} on {event_ts}: {e}")
        return 0.0


def detect_events_for_symbol(
    symbol: str,
    bars_1d_dir: Path,
    bars_1h_dir: Path,
    cfg: dict,
    use_percentiles: bool = True
) -> pl.DataFrame:
    """
    Detect events for a single symbol using 5-branch logic

    Args:
        symbol: Ticker symbol
        bars_1d_dir: Directory with daily bars
        bars_1h_dir: Directory with hourly bars (for PM volume)
        cfg: Configuration dict
        use_percentiles: Use percentile thresholds for ATR

    Returns:
        DataFrame with event flags including 'date' and 'event_id' columns
    """
    file_1d = bars_1d_dir / f"{symbol}.parquet"

    if not file_1d.exists():
        logger.warning(f"No daily bars found for {symbol}")
        return None

    # Load daily bars
    df = pl.read_parquet(file_1d)

    if df.height < cfg["processing"]["events"]["min_trading_days"]:
        logger.debug(f"Skipping {symbol}: insufficient trading days ({df.height})")
        return None

    # Compute metrics
    atr_window = cfg["processing"]["events"]["atr_pct_window_days"]
    df = compute_daily_metrics(df, atr_window=atr_window)
    df = compute_ssr_flag(df)

    # Event config
    evt_cfg = cfg["processing"]["events"]
    gap_th = float(evt_cfg["gap_pct_threshold"])
    rvol_th = float(evt_cfg["rvol_threshold"])
    rvol_alt = float(evt_cfg["rvol_threshold_alt"])
    min_dvol = float(evt_cfg["min_dollar_volume_event"])

    # New thresholds
    ire_th = float(evt_cfg.get("ire_pct_threshold", 30.0))
    rvol_vswg = float(evt_cfg.get("rvol_vswg_threshold", 5.0))
    gap_vswg_min = float(evt_cfg.get("gap_vswg_min", 2.0))
    rvol_flush = float(evt_cfg.get("rvol_flush_threshold", 2.5))
    drawdown_flush = float(evt_cfg.get("drawdown_flush_threshold", 20.0))

    # ATR threshold (percentile-based with fallback)
    if use_percentiles:
        atr_pct_p = evt_cfg["atr_pct_percentile"]
        atr_valid = df["atr_pct"].drop_nulls()
        if atr_valid.len() >= 30:
            atr_th = np.nanpercentile(atr_valid.to_numpy(), atr_pct_p)
        else:
            # Fallback for insufficient data
            atr_th = 5.0
            logger.debug(f"{symbol}: Using fallback ATR threshold (insufficient data)")
    else:
        atr_th = 5.0  # fallback fixed threshold

    # Branch gates
    df = df.with_columns([
        # Branch 1: Gap Play (only POSITIVE gaps - bullish)
        (pl.col("gap_pct") >= gap_th).alias("gate_gap"),
        (pl.col("rvol") >= rvol_th).alias("gate_rvol"),

        # Branch 2: Intraday Range Explosion
        (pl.col("ire_pct") >= ire_th).alias("gate_ire"),

        # Branch 3: Volume Spike Without Gap (only POSITIVE gaps - bullish)
        (pl.col("rvol") >= rvol_vswg).alias("gate_rvol_vswg"),
        (pl.col("gap_pct") >= gap_vswg_min).alias("gate_gap_vswg"),

        # Branch 4: ATR Breakout
        (pl.col("rvol") >= rvol_alt).alias("gate_rvol_alt"),
        (pl.col("atr_pct") >= atr_th).alias("gate_atr"),

        # Branch 5: Flush Reversal
        (pl.col("close") > pl.col("open")).alias("gate_bullish"),
        (pl.col("rvol") >= rvol_flush).alias("gate_rvol_flush"),
        (pl.col("drawdown_5d") >= drawdown_flush).alias("gate_flush"),

        # Global filters
        (pl.col("dollar_volume") >= min_dvol).alias("gate_dv")
    ])

    # 5-Branch Event Detection
    branch1 = pl.col("gate_gap") & pl.col("gate_rvol")
    branch2 = pl.col("gate_ire") & pl.col("gate_rvol")
    branch3 = pl.col("gate_rvol_vswg") & pl.col("gate_gap_vswg")
    branch4 = pl.col("gate_atr") & pl.col("gate_rvol_alt")
    branch5 = pl.col("gate_bullish") & pl.col("gate_rvol_flush") & pl.col("gate_flush")

    # Combined: Any branch triggers event
    is_event_any_branch = (branch1 | branch2 | branch3 | branch4 | branch5)

    # Apply global filters
    is_event = is_event_any_branch & pl.col("gate_dv")

    # Apply bullish-only filter (optional, configurable)
    # Requires BOTH: Close > Open AND Gap >= 0 (no gap-down reversals)
    if evt_cfg.get("bullish_only", True):
        gap_bullish = (pl.col("gap_pct") >= 0)
        is_event = is_event & pl.col("gate_bullish") & gap_bullish

    df = df.with_columns([
        branch1.alias("branch_gap_play"),
        branch2.alias("branch_ire"),
        branch3.alias("branch_vswg"),
        branch4.alias("branch_atr"),
        branch5.alias("branch_flush"),
        is_event.alias("is_event")
    ])

    # Premarket filter (optional)
    if evt_cfg.get("use_hourly_premarket_filter", False):
        pm_min = float(evt_cfg.get("premarket_min_dollar_volume", 0))

        # Get events with timestamps
        ev = df.filter(pl.col("is_event")).select(["timestamp"])

        if ev.height > 0:
            # Compute pm_ok for each event
            pm_ok_list = []
            for ts in ev["timestamp"]:
                pm_vol = compute_premarket_volume(symbol, bars_1h_dir, ts, cfg)
                pm_ok_list.append(pm_vol >= pm_min)

            # Add pm_ok column to events
            ev = ev.with_columns(pl.Series("pm_ok", pm_ok_list))

            # Join back to main df (default True for non-events)
            df = df.join(ev, on="timestamp", how="left").with_columns(
                pl.col("pm_ok").fill_null(True)
            )

            # Update is_event
            df = df.with_columns(
                (pl.col("is_event") & pl.col("pm_ok")).alias("is_event")
            )

    # Add date column for easy filtering
    df = df.with_columns(
        pl.col("timestamp").dt.date().alias("date")
    )

    # Add event_id for traceability (YYYYMMDD for event days, null otherwise)
    df = df.with_columns(
        pl.when(pl.col("is_event"))
        .then(pl.col("timestamp").dt.strftime("%Y%m%d"))
        .otherwise(None)
        .alias("event_id")
    )

    # Add symbol column
    df = df.with_columns(pl.lit(symbol).alias("symbol"))

    # Select relevant columns
    df = df.select([
        "symbol",
        "date",
        "timestamp",
        "event_id",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "gap_pct",
        "rvol",
        "atr_pct",
        "ire_pct",
        "dollar_volume",
        "is_ssr",
        "gate_gap",
        "gate_rvol",
        "gate_ire",
        "gate_rvol_vswg",
        "gate_gap_vswg",
        "gate_rvol_alt",
        "gate_atr",
        "gate_bullish",
        "gate_rvol_flush",
        "gate_flush",
        "gate_dv",
        "branch_gap_play",
        "branch_ire",
        "branch_vswg",
        "branch_atr",
        "branch_flush",
        "is_event"
    ])

    return df


def main():
    parser = argparse.ArgumentParser(description="Detect trading events with multi-branch logic")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to process (default: all)")
    parser.add_argument("--use-percentiles", action="store_true", help="Use percentile thresholds for ATR")
    parser.add_argument("--output-dir", type=str, help="Output directory (default: processed/events)")
    args = parser.parse_args()

    # Load config
    cfg = load_config()

    # Paths
    bars_1d_dir = PROJECT_ROOT / cfg["paths"]["raw"] / "market_data" / "bars" / "1d"
    bars_1h_dir = PROJECT_ROOT / cfg["paths"]["raw"] / "market_data" / "bars" / "1h"

    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / cfg["paths"]["processed"] / "events"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get symbols
    if args.symbols:
        symbols = args.symbols
    else:
        # All symbols with daily bars
        symbols = sorted([f.stem for f in bars_1d_dir.glob("*.parquet")])

    logger.info(f"Processing {len(symbols)} symbols for event detection")
    logger.info(f"Using percentiles: {args.use_percentiles}")

    # Process each symbol
    results = []
    for i, symbol in enumerate(symbols):
        if (i + 1) % 100 == 0:
            logger.info(f"Progress: {i+1}/{len(symbols)} symbols")

        df_events = detect_events_for_symbol(
            symbol,
            bars_1d_dir,
            bars_1h_dir,
            cfg,
            use_percentiles=args.use_percentiles
        )

        if df_events is not None:
            results.append(df_events)

    # Combine results
    if results:
        df_all = pl.concat(results)

        # Save
        ts = datetime.now(timezone.utc).strftime("%Y%m%d")
        output_file = output_dir / f"events_daily_{ts}.parquet"
        df_all.write_parquet(output_file, compression="zstd")

        logger.info(f"Saved events to {output_file}")

        # Summary stats
        total_events = df_all.filter(pl.col("is_event")).height
        total_days = df_all.height
        event_rate = total_events / total_days * 100 if total_days > 0 else 0

        logger.info(f"Total events detected: {total_events:,}")
        logger.info(f"Total days: {total_days:,}")
        logger.info(f"Event rate: {event_rate:.2f}%")

        # Branch breakdown
        logger.info(f"\nBranch breakdown:")
        for branch in ["branch_gap_play", "branch_ire", "branch_vswg", "branch_atr", "branch_flush"]:
            count = df_all.filter(pl.col(branch) & pl.col("is_event")).height
            pct = count / total_events * 100 if total_events > 0 else 0
            logger.info(f"  {branch:20s}: {count:6,} ({pct:5.1f}%)")

        # Monthly event density summary
        monthly_summary = (df_all.filter(pl.col("is_event"))
                          .with_columns(pl.col("date").dt.strftime("%Y-%m").alias("month"))
                          .group_by("month")
                          .agg(pl.len().alias("n_events"))
                          .sort("month"))

        logger.info(f"\nMonthly event density:")
        print(monthly_summary)

        # Top symbols by event count
        top_symbols = (df_all.filter(pl.col("is_event"))
                       .group_by("symbol")
                       .agg(pl.len().alias("n_events"))
                       .sort("n_events", descending=True)
                       .head(20))

        logger.info(f"\nTop 20 symbols by event count:")
        print(top_symbols)
    else:
        logger.warning("No events detected")


if __name__ == "__main__":
    main()
