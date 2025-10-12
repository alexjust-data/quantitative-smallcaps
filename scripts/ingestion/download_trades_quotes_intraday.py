"""
Download trades and quotes for intraday event windows (FASE 3.2)

For each detected intraday event (FASE 2.5), downloads:
- Trades: /v3/trades/{ticker} in [-5min, +10min] window around event timestamp
- Quotes: /v3/quotes/{ticker} in [-5min, +10min] window around event timestamp

This enables tape reading analysis: bid-ask spread, trade imbalance, liquidity depletion.

Critical fixes implemented:
1. Timezone handling: naive → NY → UTC ns for Polygon API
2. Retry logic with exponential backoff for 429/5xx
3. requests.Session() for connection reuse
4. next_url pagination with apiKey handling
5. Resume validation (skip empty parquets)
6. Log summary per event (n_trades, n_quotes, timestamp range)
7. Support for distinct symbols sampling

Usage:
    # Test with 5 events (dry-run)
    python scripts/ingestion/download_trades_quotes_intraday.py --limit 5 --dry-run

    # Download trades only for 38 events (recommended first)
    python scripts/ingestion/download_trades_quotes_intraday.py \
        --events processed/events/events_intraday_20251008.parquet \
        --limit 38 --trades-only --resume

    # Resume interrupted download
    python scripts/ingestion/download_trades_quotes_intraday.py --resume

    # Sample 1 event per symbol (38 unique symbols)
    python scripts/ingestion/download_trades_quotes_intraday.py \
        --events processed/events/events_intraday_20251008.parquet \
        --one-per-symbol --trades-only
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import time
import random
from typing import Optional, Dict
from zoneinfo import ZoneInfo

import polars as pl
import yaml
from loguru import logger
import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


class PolygonTradesQuotesDownloader:
    """Download trades and quotes from Polygon.io for intraday event windows"""

    def __init__(self, config_path: Optional[Path] = None, dry_run: bool = False):
        """Initialize downloader with config"""
        if config_path is None:
            config_path = PROJECT_ROOT / "config" / "config.yaml"

        with open(config_path, "r") as f:
            self.cfg = yaml.safe_load(f)

        # API key from config or environment variable
        self.api_key = self.cfg["polygon"]["api_key"] or os.getenv("POLYGON_API_KEY")
        if not self.api_key:
            raise ValueError("Polygon API key not found. Set POLYGON_API_KEY env var or add to config.yaml")

        self.base_url = "https://api.polygon.io"
        self.dry_run = dry_run

        # Rate limiting config
        self.rate_limit_delay = self.cfg["polygon"].get("rate_limit_delay_seconds", 12)
        self.retry_max_attempts = self.cfg["polygon"].get("retry_max_attempts", 3)
        self.retry_delay_base = self.cfg["polygon"].get("retry_delay_seconds", 5)

        # Event window config
        event_cfg = self.cfg["processing"].get("intraday_events", {})
        self.window_before_minutes = event_cfg.get("event_tape_window_before_minutes", 5)
        self.window_after_minutes = event_cfg.get("event_tape_window_after_minutes", 10)

        # Timezone
        self.ny_tz = ZoneInfo("America/New_York")
        self.utc_tz = ZoneInfo("UTC")

        # HTTP session for connection pooling
        self.session = requests.Session() if not dry_run else None

        logger.info(f"Initialized PolygonTradesQuotesDownloader")
        logger.info(f"  Window: [{-self.window_before_minutes}min, +{self.window_after_minutes}min]")
        logger.info(f"  Rate limit: {self.rate_limit_delay}s between requests")
        logger.info(f"  Retry: {self.retry_max_attempts} attempts, {self.retry_delay_base}s base delay")
        logger.info(f"  Dry run: {self.dry_run}")

    def _ensure_utc_timestamp_ns(self, dt: datetime) -> int:
        """
        Convert datetime to UTC nanoseconds for Polygon API

        Critical: Handles naive timestamps (assumes NY timezone)

        Args:
            dt: datetime object (naive or aware)

        Returns:
            UTC timestamp in nanoseconds
        """
        # If naive, localize to NY timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.ny_tz)

        # Convert to UTC
        dt_utc = dt.astimezone(self.utc_tz)

        # Return nanoseconds
        return int(dt_utc.timestamp() * 1e9)

    def _make_request_with_retry(
        self,
        url: str,
        params: Optional[Dict] = None,
        attempt: int = 1
    ) -> Optional[requests.Response]:
        """
        Make HTTP request with exponential backoff retry

        Args:
            url: Request URL
            params: Query parameters
            attempt: Current attempt number

        Returns:
            Response object or None if all attempts failed
        """
        try:
            response = self.session.get(url, params=params, timeout=30)

            # Handle rate limiting (429)
            if response.status_code == 429:
                if attempt < self.retry_max_attempts:
                    # Exponential backoff with jitter
                    delay = self.retry_delay_base * (2 ** (attempt - 1)) + random.uniform(0, 2)
                    logger.warning(f"Rate limited (429), retrying in {delay:.1f}s (attempt {attempt}/{self.retry_max_attempts})")
                    time.sleep(delay)
                    return self._make_request_with_retry(url, params, attempt + 1)
                else:
                    logger.error(f"Rate limited (429) after {self.retry_max_attempts} attempts, giving up")
                    return None

            # Handle server errors (5xx)
            if response.status_code >= 500:
                if attempt < self.retry_max_attempts:
                    delay = self.retry_delay_base * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    logger.warning(f"Server error ({response.status_code}), retrying in {delay:.1f}s (attempt {attempt}/{self.retry_max_attempts})")
                    time.sleep(delay)
                    return self._make_request_with_retry(url, params, attempt + 1)
                else:
                    logger.error(f"Server error ({response.status_code}) after {self.retry_max_attempts} attempts, giving up")
                    return None

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            if attempt < self.retry_max_attempts:
                delay = self.retry_delay_base * (2 ** (attempt - 1)) + random.uniform(0, 1)
                logger.warning(f"Request failed: {e}, retrying in {delay:.1f}s (attempt {attempt}/{self.retry_max_attempts})")
                time.sleep(delay)
                return self._make_request_with_retry(url, params, attempt + 1)
            else:
                logger.error(f"Request failed after {self.retry_max_attempts} attempts: {e}")
                return None

    def _ensure_api_key_in_url(self, url: str) -> str:
        """
        Ensure next_url contains apiKey parameter

        Args:
            url: Potentially incomplete next_url

        Returns:
            URL with apiKey guaranteed
        """
        if "apiKey=" in url:
            return url

        separator = "&" if "?" in url else "?"
        return f"{url}{separator}apiKey={self.api_key}"

    def download_trades(
        self,
        ticker: str,
        timestamp_gte: int,
        timestamp_lte: int,
        limit: int = 50000
    ) -> Optional[pl.DataFrame]:
        """
        Download trades from Polygon.io with retry logic

        Args:
            ticker: Stock symbol
            timestamp_gte: Start timestamp (nanoseconds UTC)
            timestamp_lte: End timestamp (nanoseconds UTC)
            limit: Max results per page

        Returns:
            DataFrame with trades or None if failed
        """
        if self.dry_run:
            logger.debug(f"{ticker}: DRY RUN - would download trades {timestamp_gte} to {timestamp_lte}")
            return pl.DataFrame()

        url = f"{self.base_url}/v3/trades/{ticker}"
        params = {
            "timestamp.gte": timestamp_gte,
            "timestamp.lte": timestamp_lte,
            "limit": limit,
            "apiKey": self.api_key,
            "order": "asc",
            "sort": "timestamp"
        }

        all_results = []
        next_url = None
        page = 0

        while True:
            page += 1

            # Make request
            if next_url:
                next_url = self._ensure_api_key_in_url(next_url)
                response = self._make_request_with_retry(next_url, params=None)
            else:
                response = self._make_request_with_retry(url, params=params)

            if response is None:
                logger.error(f"{ticker}: Failed to download trades after retries")
                return None if not all_results else pl.DataFrame(all_results)

            try:
                data = response.json()
            except Exception as e:
                logger.error(f"{ticker}: Failed to parse JSON: {e}")
                return None if not all_results else pl.DataFrame(all_results)

            results = data.get("results", [])
            if results:
                all_results.extend(results)
                logger.debug(f"{ticker}: Page {page}: {len(results)} trades (total: {len(all_results)})")

            # Check for pagination
            next_url = data.get("next_url")
            if not next_url:
                break

            # Rate limit between pages
            time.sleep(0.5)

        if not all_results:
            logger.debug(f"{ticker}: No trades found in window")
            return pl.DataFrame()

        # Convert to DataFrame
        df = pl.DataFrame(all_results)

        # Rename columns to standard format
        column_map = {
            "sip_timestamp": "timestamp_ns",
            "participant_timestamp": "exchange_timestamp_ns",
            "price": "price",
            "size": "size",
            "exchange": "exchange",
            "conditions": "conditions",
            "id": "trade_id",
            "sequence_number": "sequence_number",
            "trf_id": "trf_id",
            "trf_timestamp": "trf_timestamp"
        }

        # Rename only columns that exist
        existing_cols = {k: v for k, v in column_map.items() if k in df.columns}
        if existing_cols:
            df = df.rename(existing_cols)

        # Convert timestamp from ns to datetime (UTC)
        if "timestamp_ns" in df.columns:
            df = df.with_columns([
                pl.from_epoch(pl.col("timestamp_ns"), time_unit="ns").alias("timestamp")
            ])

        logger.info(f"{ticker}: Downloaded {len(all_results)} trades")
        return df

    def download_quotes(
        self,
        ticker: str,
        timestamp_gte: int,
        timestamp_lte: int,
        limit: int = 50000
    ) -> Optional[pl.DataFrame]:
        """
        Download quotes (NBBO) from Polygon.io with retry logic

        Args:
            ticker: Stock symbol
            timestamp_gte: Start timestamp (nanoseconds UTC)
            timestamp_lte: End timestamp (nanoseconds UTC)
            limit: Max results per page

        Returns:
            DataFrame with quotes or None if failed
        """
        if self.dry_run:
            logger.debug(f"{ticker}: DRY RUN - would download quotes {timestamp_gte} to {timestamp_lte}")
            return pl.DataFrame()

        url = f"{self.base_url}/v3/quotes/{ticker}"
        params = {
            "timestamp.gte": timestamp_gte,
            "timestamp.lte": timestamp_lte,
            "limit": limit,
            "apiKey": self.api_key,
            "order": "asc",
            "sort": "timestamp"
        }

        all_results = []
        next_url = None
        page = 0

        while True:
            page += 1

            if next_url:
                next_url = self._ensure_api_key_in_url(next_url)
                response = self._make_request_with_retry(next_url, params=None)
            else:
                response = self._make_request_with_retry(url, params=params)

            if response is None:
                logger.error(f"{ticker}: Failed to download quotes after retries")
                return None if not all_results else pl.DataFrame(all_results)

            try:
                data = response.json()
            except Exception as e:
                logger.error(f"{ticker}: Failed to parse JSON: {e}")
                return None if not all_results else pl.DataFrame(all_results)

            results = data.get("results", [])
            if results:
                all_results.extend(results)
                logger.debug(f"{ticker}: Page {page}: {len(results)} quotes (total: {len(all_results)})")

            next_url = data.get("next_url")
            if not next_url:
                break

            time.sleep(0.5)

        if not all_results:
            logger.debug(f"{ticker}: No quotes found in window")
            return pl.DataFrame()

        # Convert to DataFrame
        df = pl.DataFrame(all_results)

        # Rename columns
        column_map = {
            "sip_timestamp": "timestamp_ns",
            "participant_timestamp": "exchange_timestamp_ns",
            "ask_price": "ask_price",
            "bid_price": "bid_price",
            "ask_size": "ask_size",
            "bid_size": "bid_size",
            "ask_exchange": "ask_exchange",
            "bid_exchange": "bid_exchange",
            "conditions": "conditions",
            "indicators": "indicators",
            "sequence_number": "sequence_number",
            "trf_timestamp": "trf_timestamp"
        }

        existing_cols = {k: v for k, v in column_map.items() if k in df.columns}
        if existing_cols:
            df = df.rename(existing_cols)

        # Convert timestamp
        if "timestamp_ns" in df.columns:
            df = df.with_columns([
                pl.from_epoch(pl.col("timestamp_ns"), time_unit="ns").alias("timestamp")
            ])

        logger.info(f"{ticker}: Downloaded {len(all_results)} quotes")
        return df

    def download_event_window(
        self,
        event_row: dict,
        output_dir: Path,
        download_trades: bool = True,
        download_quotes: bool = True,
        resume: bool = False
    ) -> dict:
        """
        Download trades and/or quotes for single event window

        Args:
            event_row: Event row dict with 'symbol', 'timestamp', 'event_type', 'session'
            output_dir: Base output directory
            download_trades: Download trades
            download_quotes: Download quotes
            resume: Skip if files already exist

        Returns:
            Stats dict: {trades_count, quotes_count, success, timestamp_range}
        """
        stats = {
            "trades_count": 0,
            "quotes_count": 0,
            "success": False,
            "timestamp_range": None
        }

        symbol = event_row["symbol"]
        event_ts = event_row["timestamp"]
        event_type = event_row["event_type"]
        session = event_row.get("session", "RTH")

        # Create event ID
        event_id = f"{event_ts.strftime('%Y%m%d_%H%M%S')}_{event_type}"

        # Output paths
        event_dir = output_dir / f"symbol={symbol}" / f"event={event_id}"
        trades_file = event_dir / "trades.parquet"
        quotes_file = event_dir / "quotes.parquet"

        # Resume check with empty file validation
        if resume:
            files_to_check = []
            if download_trades:
                files_to_check.append(trades_file)
            if download_quotes:
                files_to_check.append(quotes_file)

            if all(f.exists() for f in files_to_check):
                # Validate files are not empty
                try:
                    all_valid = True
                    if download_trades and trades_file.exists():
                        df_check = pl.read_parquet(trades_file)
                        if df_check.height == 0:
                            logger.warning(f"{symbol} {event_id}: trades.parquet is empty, re-downloading")
                            all_valid = False
                        else:
                            stats["trades_count"] = df_check.height

                    if download_quotes and quotes_file.exists():
                        df_check = pl.read_parquet(quotes_file)
                        if df_check.height == 0:
                            logger.warning(f"{symbol} {event_id}: quotes.parquet is empty, re-downloading")
                            all_valid = False
                        else:
                            stats["quotes_count"] = df_check.height

                    if all_valid:
                        logger.debug(f"{symbol} {event_id}: Already downloaded (trades={stats['trades_count']}, quotes={stats['quotes_count']}), skipping")
                        stats["success"] = True
                        return stats

                except Exception as e:
                    logger.warning(f"{symbol} {event_id}: Error validating existing files: {e}, re-downloading")

        # Calculate window timestamps (UTC nanoseconds for Polygon API)
        window_start = event_ts - timedelta(minutes=self.window_before_minutes)
        window_end = event_ts + timedelta(minutes=self.window_after_minutes)

        timestamp_gte = self._ensure_utc_timestamp_ns(window_start)
        timestamp_lte = self._ensure_utc_timestamp_ns(window_end)

        logger.info(f"{symbol} {event_id} [{session}]: Window [{window_start.strftime('%Y-%m-%d %H:%M:%S')} to {window_end.strftime('%H:%M:%S')}]")

        # Download trades
        if download_trades:
            df_trades = self.download_trades(symbol, timestamp_gte, timestamp_lte)

            if df_trades is not None and not self.dry_run:
                event_dir.mkdir(parents=True, exist_ok=True)
                df_trades.write_parquet(trades_file, compression="zstd")
                stats["trades_count"] = df_trades.height

                # Log timestamp range
                if df_trades.height > 0 and "timestamp" in df_trades.columns:
                    ts_min = df_trades["timestamp"].min()
                    ts_max = df_trades["timestamp"].max()
                    stats["timestamp_range"] = f"[{ts_min} to {ts_max}]"
                    logger.info(f"{symbol} {event_id}: Saved {df_trades.height} trades {stats['timestamp_range']}")
                else:
                    logger.info(f"{symbol} {event_id}: Saved 0 trades (empty window)")

            # Rate limit
            if not self.dry_run:
                time.sleep(self.rate_limit_delay)

        # Download quotes
        if download_quotes:
            df_quotes = self.download_quotes(symbol, timestamp_gte, timestamp_lte)

            if df_quotes is not None and not self.dry_run:
                event_dir.mkdir(parents=True, exist_ok=True)
                df_quotes.write_parquet(quotes_file, compression="zstd")
                stats["quotes_count"] = df_quotes.height

                if df_quotes.height > 0:
                    logger.info(f"{symbol} {event_id}: Saved {df_quotes.height} quotes")
                else:
                    logger.info(f"{symbol} {event_id}: Saved 0 quotes (empty window)")

            # Rate limit
            if not self.dry_run:
                time.sleep(self.rate_limit_delay)

        stats["success"] = True
        return stats

    def close(self):
        """Close HTTP session"""
        if self.session:
            self.session.close()


def main():
    parser = argparse.ArgumentParser(description="Download trades and quotes for intraday event windows (FASE 3.2)")
    parser.add_argument("--events", type=str, help="Path to intraday events parquet (default: latest events_intraday_*.parquet)")
    parser.add_argument("--limit", type=int, help="Limit number of events to process")
    parser.add_argument("--one-per-symbol", action="store_true", help="Sample 1 event per symbol (distinct symbols)")
    parser.add_argument("--trades-only", action="store_true", help="Download only trades (skip quotes)")
    parser.add_argument("--quotes-only", action="store_true", help="Download only quotes (skip trades)")
    parser.add_argument("--resume", action="store_true", help="Skip already downloaded events (validates non-empty)")
    parser.add_argument("--dry-run", action="store_true", help="Test without downloading")
    parser.add_argument("--output-dir", type=str, help="Output directory (default: raw/market_data/event_windows)")
    args = parser.parse_args()

    # Load config
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    # Find events file
    if args.events:
        events_file = Path(args.events)
    else:
        events_dir = PROJECT_ROOT / cfg["paths"]["processed"] / "events"
        event_files = sorted(events_dir.glob("events_intraday_*.parquet"))
        if not event_files:
            logger.error(f"No intraday events files found in {events_dir}")
            logger.error("Run detect_events_intraday.py first")
            sys.exit(1)
        events_file = event_files[-1]

    if not events_file.exists():
        logger.error(f"Events file not found: {events_file}")
        sys.exit(1)

    # Load events
    logger.info(f"Loading events from {events_file}")
    df_events = pl.read_parquet(events_file)

    logger.info(f"Total events: {df_events.height:,}")
    logger.info(f"Unique symbols: {df_events['symbol'].n_unique():,}")

    # Sample one per symbol if requested
    if args.one_per_symbol:
        df_events = df_events.group_by("symbol").first().sort("symbol")
        logger.info(f"Sampled to 1 event per symbol: {df_events.height:,} events")

    # Apply limit
    if args.limit:
        df_events = df_events.head(args.limit)
        logger.info(f"Limited to first {args.limit} events")

    # Output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = PROJECT_ROOT / cfg["paths"]["raw"] / "market_data" / "event_windows"

    logger.info(f"Output directory: {output_dir}")

    # Initialize downloader
    downloader = PolygonTradesQuotesDownloader(dry_run=args.dry_run)

    # Determine what to download
    download_trades = not args.quotes_only
    download_quotes = not args.trades_only

    logger.info(f"Downloading: trades={download_trades}, quotes={download_quotes}")

    if args.dry_run:
        logger.warning("DRY RUN MODE - No files will be downloaded or saved")

    # Process events
    total_stats = {
        "events_processed": 0,
        "events_skipped": 0,
        "events_failed": 0,
        "total_trades": 0,
        "total_quotes": 0
    }

    start_time = time.time()

    try:
        for i, event_row in enumerate(df_events.iter_rows(named=True)):
            logger.info(f"\n[{i+1}/{df_events.height}] {event_row['symbol']} {event_row['event_type']} @ {event_row['timestamp']} ({event_row.get('session', 'RTH')})")

            try:
                stats = downloader.download_event_window(
                    event_row,
                    output_dir,
                    download_trades=download_trades,
                    download_quotes=download_quotes,
                    resume=args.resume
                )

                if stats["success"]:
                    total_stats["events_processed"] += 1
                    total_stats["total_trades"] += stats["trades_count"]
                    total_stats["total_quotes"] += stats["quotes_count"]

                    if stats.get("timestamp_range"):
                        logger.info(f"  Summary: {stats['trades_count']} trades, {stats['quotes_count']} quotes {stats['timestamp_range']}")
                else:
                    total_stats["events_failed"] += 1

            except Exception as e:
                logger.error(f"Failed to process event: {e}")
                total_stats["events_failed"] += 1

    finally:
        # Close HTTP session
        downloader.close()

    elapsed = time.time() - start_time

    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info(f"DOWNLOAD COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Events processed: {total_stats['events_processed']:,}")
    logger.info(f"Events failed: {total_stats['events_failed']:,}")
    logger.info(f"Total trades downloaded: {total_stats['total_trades']:,}")
    logger.info(f"Total quotes downloaded: {total_stats['total_quotes']:,}")
    logger.info(f"Elapsed time: {elapsed/60:.1f} minutes ({elapsed/3600:.2f} hours)")
    logger.info(f"Avg time per event: {elapsed/max(total_stats['events_processed'], 1):.1f}s")
    logger.info(f"Output directory: {output_dir}")

    # Estimate for full dataset
    if total_stats['events_processed'] > 0:
        avg_time_per_event = elapsed / total_stats['events_processed']
        logger.info(f"\nProjection for larger datasets:")
        for n_events in [100, 500, 1000, 5000]:
            est_hours = (avg_time_per_event * n_events) / 3600
            logger.info(f"  {n_events:,} events → ~{est_hours:.1f} hours")


if __name__ == "__main__":
    main()
