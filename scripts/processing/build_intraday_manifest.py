#!/usr/bin/env python
"""
Manifest Builder for Intraday Event Download (Profile-Aware)

Reads detected events from processed/events/events_intraday_*.parquet and generates
an optimized manifest for downloading trades/quotes based on the active profile
(CORE/PLUS/PREMIUM).

Features:
- Profile-aware selection (max_events, max_per_symbol, max_per_symbol_day)
- Diversity enforcement across symbols and time
- Time bucket coverage (opening, mid-day, power hour, PM, AH)
- Liquidity filtering (bar/day volume, spread, rvol)
- Event score thresholds
- Session filtering (RTH/PM/AH)

Output: processed/events/events_intraday_manifest.parquet
"""

import sys
from pathlib import Path
from datetime import datetime, time
from typing import Dict, List
import yaml
import polars as pl
import numpy as np
from loguru import logger
from zoneinfo import ZoneInfo

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


class IntradayManifestBuilder:
    """Build optimized manifest for intraday event download"""

    def __init__(self, config_path: Path = None):
        if config_path is None:
            config_path = PROJECT_ROOT / "config" / "config.yaml"

        with open(config_path, encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # Get active profile
        self.active_profile = self.config["processing"]["profiles"]["active_profile"]
        logger.info(f"Active profile: {self.active_profile.upper()}")

        # Merge profile overrides into base config
        self._merge_profile_config()

        # Access merged configuration
        self.manifest_cfg = self.config["processing"]["intraday_manifest"]
        self.liquidity_cfg = self.config["processing"]["liquidity_filters"]

        self.tz = ZoneInfo("America/New_York")

        # Directories
        self.events_dir = PROJECT_ROOT / "processed" / "events"
        self.output_dir = PROJECT_ROOT / "processed" / "events"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Manifest Builder initialized (profile: {self.active_profile})")

    def _merge_profile_config(self):
        """Merge active profile overrides into base config"""
        profile_overrides = self.config["processing"]["profiles"].get(self.active_profile, {})

        # Deep merge profile overrides
        for key, value in profile_overrides.items():
            if key in self.config["processing"]:
                if isinstance(value, dict) and isinstance(self.config["processing"][key], dict):
                    # Merge nested dicts
                    self.config["processing"][key].update(value)
                else:
                    # Replace value
                    self.config["processing"][key] = value

        logger.info(f"Profile '{self.active_profile}' config merged")

    def load_all_events(self) -> pl.DataFrame:
        """Load all detected events from processed/events/events_intraday_*.parquet"""
        events_glob = self.manifest_cfg.get("events_glob", "events_intraday_*.parquet")

        # If events_glob contains path, use it directly; otherwise append to events_dir
        if "/" in events_glob or "\\" in events_glob:
            events_pattern = str(PROJECT_ROOT / events_glob)
        else:
            events_pattern = str(self.events_dir / events_glob)

        logger.info(f"Loading events from: {events_pattern}")

        try:
            df = pl.read_parquet(events_pattern)
            logger.info(f"Loaded {len(df):,} events from {events_pattern}")
            return df
        except Exception as e:
            logger.error(f"Failed to load events: {e}")
            return pl.DataFrame()

    def apply_session_filter(self, df: pl.DataFrame) -> pl.DataFrame:
        """Filter by allowed sessions (RTH/PM/AH)"""
        allow_sessions = self.manifest_cfg.get("allow_sessions", {})
        allowed = []
        if allow_sessions.get("premarket", True):
            allowed.append("PM")
        if allow_sessions.get("rth", True):
            allowed.append("RTH")
        if allow_sessions.get("afterhours", True):
            allowed.append("AH")

        if not allowed:
            logger.warning("No sessions enabled - returning empty DataFrame")
            return df.filter(pl.lit(False))

        df = df.filter(pl.col("session").is_in(allowed))
        logger.info(f"After session filter ({allowed}): {len(df):,} events")
        return df

    def apply_score_filter(self, df: pl.DataFrame) -> pl.DataFrame:
        """Filter by minimum event score"""
        min_score = self.manifest_cfg.get("min_event_score", 0.0)
        df = df.filter(pl.col("score") >= min_score)
        logger.info(f"After score filter (>= {min_score}): {len(df):,} events")
        return df

    def apply_liquidity_filters(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply liquidity filters (bar/day volume, spread proxy, rvol)"""
        # Bar-level filters
        min_dollar_bar = self.liquidity_cfg.get("min_dollar_volume_bar", 0)
        min_volume_bar = self.liquidity_cfg.get("min_absolute_volume_bar", 0)
        max_spread_pct = self.liquidity_cfg.get("max_spread_proxy_pct", 100.0)

        if min_dollar_bar > 0:
            df = df.filter(pl.col("dollar_volume") >= min_dollar_bar)
            logger.info(f"After dollar_volume >= ${min_dollar_bar:,.0f}: {len(df):,} events")

        if min_volume_bar > 0:
            df = df.filter(pl.col("volume") >= min_volume_bar)
            logger.info(f"After volume >= {min_volume_bar:,}: {len(df):,} events")

        if max_spread_pct < 100.0:
            # Spread proxy: (high - low) / vwap (approximate)
            # We'll use (high - low) / close as proxy since we don't have VWAP in events
            df = df.with_columns([
                ((pl.col("high") - pl.col("low")) / pl.col("close") * 100).alias("spread_proxy_pct")
            ])
            df = df.filter(pl.col("spread_proxy_pct") <= max_spread_pct)
            logger.info(f"After spread_proxy <= {max_spread_pct}%: {len(df):,} events")
            df = df.drop("spread_proxy_pct")

        # Day-level filters (would require daily data - skip for now)
        # TODO: Load daily bars and apply min_dollar_volume_day, rvol_day_min

        return df

    def apply_diversity_caps(self, df: pl.DataFrame) -> pl.DataFrame:
        """Enforce max events per symbol and per symbol-day"""
        max_per_symbol = self.manifest_cfg.get("max_per_symbol", 999999)
        max_per_symbol_day = self.manifest_cfg.get("max_per_symbol_day", 999999)

        # Add date column if not exists
        if "date" not in df.columns:
            df = df.with_columns([
                pl.col("timestamp").dt.date().alias("date")
            ])

        # Apply max_per_symbol_day first (more restrictive)
        if max_per_symbol_day < 999999:
            df = df.with_columns([
                pl.col("score").rank(method="ordinal", descending=True)
                .over(["symbol", "date"])
                .alias("rank_symbol_day")
            ])
            df = df.filter(pl.col("rank_symbol_day") <= max_per_symbol_day)
            df = df.drop("rank_symbol_day")
            logger.info(f"After max {max_per_symbol_day} per symbol-day: {len(df):,} events")

        # Apply max_per_symbol
        if max_per_symbol < 999999:
            df = df.with_columns([
                pl.col("score").rank(method="ordinal", descending=True)
                .over("symbol")
                .alias("rank_symbol")
            ])
            df = df.filter(pl.col("rank_symbol") <= max_per_symbol)
            df = df.drop("rank_symbol")
            logger.info(f"After max {max_per_symbol} per symbol: {len(df):,} events")

        return df

    def ensure_time_buckets(self, df: pl.DataFrame) -> pl.DataFrame:
        """Ensure minimum coverage across time buckets (opening, mid-day, power hour, PM, AH)"""
        ensure_buckets = self.manifest_cfg.get("ensure_time_buckets", {})
        if not ensure_buckets:
            return df

        max_events = self.manifest_cfg.get("max_events", len(df))

        # Assign time bucket
        df = df.with_columns([
            pl.col("timestamp").dt.time().alias("time_only")
        ])

        def get_bucket(t: time) -> str:
            """Classify time into bucket"""
            if t < time(9, 30):
                return "0400-0930"  # Premarket
            elif t < time(10, 15):
                return "0930-1015"  # Opening
            elif t < time(14, 0):
                return "1015-1400"  # Mid-day
            elif t < time(16, 0):
                return "1400-1600"  # Power hour
            else:
                return "1600-2000"  # Afterhours

        df = df.with_columns([
            pl.col("time_only").map_elements(get_bucket, return_dtype=pl.Utf8).alias("time_bucket")
        ])

        # Calculate target counts per bucket
        bucket_targets = {}
        for bucket, pct in ensure_buckets.items():
            bucket_targets[bucket] = int(max_events * pct)

        # Sample from each bucket
        sampled_dfs = []
        for bucket, target_count in bucket_targets.items():
            bucket_df = df.filter(pl.col("time_bucket") == bucket)
            if len(bucket_df) > 0:
                # Take top N by score, up to target
                bucket_df = bucket_df.sort("score", descending=True).head(target_count)
                sampled_dfs.append(bucket_df)
                logger.info(f"  Bucket {bucket}: {len(bucket_df):,} events (target: {target_count:,})")

        if sampled_dfs:
            df = pl.concat(sampled_dfs)
            df = df.drop(["time_only", "time_bucket"])
            logger.info(f"After time bucket enforcement: {len(df):,} events")

        return df

    def apply_priority_ranking(self, df: pl.DataFrame) -> pl.DataFrame:
        """Rank events by priority (event type, score)"""
        priority_types = self.manifest_cfg.get("priority_event_types", [])

        if priority_types:
            # Create priority rank (lower = higher priority)
            type_rank_map = {et: i for i, et in enumerate(priority_types)}
            # Events not in priority list get rank = 999
            df = df.with_columns([
                pl.col("event_type")
                .map_elements(lambda x: type_rank_map.get(x, 999), return_dtype=pl.Int32)
                .alias("priority_rank")
            ])

            # Sort by priority rank, then score
            df = df.sort(["priority_rank", "score"], descending=[False, True])
            df = df.drop("priority_rank")
            logger.info(f"Applied priority ranking (types: {priority_types})")

        else:
            # Just sort by score
            df = df.sort("score", descending=True)

        return df

    def select_top_events(self, df: pl.DataFrame) -> pl.DataFrame:
        """Select top N events according to max_events"""
        max_events = self.manifest_cfg.get("max_events", len(df))

        if len(df) > max_events:
            df = df.head(max_events)
            logger.info(f"Selected top {max_events:,} events")
        else:
            logger.info(f"Kept all {len(df):,} events (< max_events: {max_events:,})")

        return df

    def build_manifest(self) -> pl.DataFrame:
        """Build complete manifest with all filters and diversity enforcement"""
        logger.info("=" * 80)
        logger.info(f"Building Intraday Manifest (Profile: {self.active_profile.upper()})")
        logger.info("=" * 80)

        # Load all events
        df = self.load_all_events()
        if df.is_empty():
            logger.error("No events loaded - cannot build manifest")
            return df

        logger.info(f"Initial events loaded: {len(df):,}")

        # Apply filters in sequence
        df = self.apply_session_filter(df)
        df = self.apply_score_filter(df)
        df = self.apply_liquidity_filters(df)
        df = self.apply_diversity_caps(df)
        df = self.apply_priority_ranking(df)

        # Time bucket enforcement (if configured)
        if self.manifest_cfg.get("ensure_time_buckets"):
            df = self.ensure_time_buckets(df)
        else:
            # Just select top N
            df = self.select_top_events(df)

        # Final summary
        logger.info("=" * 80)
        logger.info("MANIFEST SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total events: {len(df):,}")

        if not df.is_empty():
            logger.info(f"Symbols: {df['symbol'].n_unique():,}")
            logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

            # Event type distribution
            logger.info("\nEvent types:")
            type_dist = df.group_by("event_type").agg(pl.len().alias("count")).sort("count", descending=True)
            for row in type_dist.iter_rows(named=True):
                logger.info(f"  {row['event_type']:<25} {row['count']:>6,}")

            # Session distribution
            logger.info("\nSessions:")
            session_dist = df.group_by("session").agg(pl.len().alias("count")).sort("count", descending=True)
            for row in session_dist.iter_rows(named=True):
                logger.info(f"  {row['session']:<10} {row['count']:>6,}")

            # Direction distribution
            logger.info("\nDirection:")
            dir_dist = df.group_by("direction").agg(pl.len().alias("count")).sort("count", descending=True)
            for row in dir_dist.iter_rows(named=True):
                logger.info(f"  {row['direction']:<10} {row['count']:>6,}")

            # Top symbols by event count
            logger.info("\nTop 10 symbols:")
            symbol_dist = df.group_by("symbol").agg(pl.len().alias("count")).sort("count", descending=True).head(10)
            for row in symbol_dist.iter_rows(named=True):
                logger.info(f"  {row['symbol']:<10} {row['count']:>6,}")

        return df

    def save_manifest(self, df: pl.DataFrame, output_path: Path = None):
        """Save manifest to parquet"""
        if output_path is None:
            output_path = self.output_dir / "events_intraday_manifest.parquet"

        if df.is_empty():
            logger.warning("Empty manifest - nothing to save")
            return

        df.write_parquet(output_path, compression="zstd")
        logger.info(f"Manifest saved: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build optimized manifest for intraday event download"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "config.yaml",
        help="Path to config.yaml"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "processed" / "events" / "events_intraday_manifest.parquet",
        help="Output manifest path"
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Just show what would be selected, don't save"
    )

    args = parser.parse_args()

    # Configure logger
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )

    # Build manifest
    builder = IntradayManifestBuilder(config_path=args.config)
    manifest = builder.build_manifest()

    # Save unless summary-only
    if not args.summary_only and not manifest.is_empty():
        builder.save_manifest(manifest, output_path=args.out)

    logger.success("Manifest build complete!")


if __name__ == "__main__":
    main()
