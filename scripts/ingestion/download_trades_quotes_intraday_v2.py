#!/usr/bin/env python3
"""
Download trades and quotes for intraday event windows (FASE 3.2)

FASE 3.2 Production version with:
- Manifest CORE support with metadata validation
- Wave-based execution (PM → AH → RTH)
- Checkpoint system (resume from interruptions)
- Heartbeat monitoring (progress tracking)
- Budget cut logic (trim quotes if size exceeds limit)
- Enhanced logging and KPI tracking

Usage:
    # Full manifest CORE download
    python scripts/ingestion/download_trades_quotes_intraday_v2.py \
      --manifest processed/events/manifest_core_20251014.parquet \
      --workers 2 \
      --rate-limit 12 \
      --resume

    # Wave 1: PM events only
    python scripts/ingestion/download_trades_quotes_intraday_v2.py \
      --manifest processed/events/manifest_core_20251014.parquet \
      --wave PM \
      --resume

    # Wave 3: RTH events with optimized quotes
    python scripts/ingestion/download_trades_quotes_intraday_v2.py \
      --manifest processed/events/manifest_core_20251014.parquet \
      --wave RTH \
      --quotes-hz 1 \
      --resume
"""

import sys
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import time
from typing import Optional, Dict, List
from zoneinfo import ZoneInfo

import polars as pl
import yaml
from loguru import logger
import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if exists
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value


class CheckpointManager:
    """Manage download progress checkpoints"""

    def __init__(self, checkpoint_file: Path):
        self.checkpoint_file = checkpoint_file
        self.completed_events = set()
        self._load()

    def _load(self):
        """Load checkpoint from disk"""
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file) as f:
                data = json.load(f)
                self.completed_events = set(data.get("completed_events", []))
            logger.info(f"Loaded checkpoint: {len(self.completed_events)} events completed")
        else:
            logger.info("No checkpoint found, starting fresh")

    def save(self):
        """Save checkpoint to disk"""
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_file, 'w') as f:
            json.dump({
                "completed_events": list(self.completed_events),
                "last_updated": datetime.now().isoformat()
            }, f, indent=2)

    def mark_completed(self, event_id: str):
        """Mark event as completed"""
        self.completed_events.add(event_id)

    def is_completed(self, event_id: str) -> bool:
        """Check if event is already completed"""
        return event_id in self.completed_events


class HeartbeatMonitor:
    """Track and log progress heartbeats"""

    def __init__(self, total_events: int, heartbeat_interval: int = 100):
        self.total_events = total_events
        self.heartbeat_interval = heartbeat_interval
        self.processed = 0
        self.failed = 0
        self.skipped = 0
        self.total_trades = 0
        self.total_quotes = 0
        self.total_size_mb = 0.0
        self.start_time = time.time()

    def update(self, trades_count: int, quotes_count: int, size_mb: float, success: bool, skipped: bool = False):
        """Update stats"""
        if skipped:
            self.skipped += 1
        elif success:
            self.processed += 1
            self.total_trades += trades_count
            self.total_quotes += quotes_count
            self.total_size_mb += size_mb
        else:
            self.failed += 1

        # Heartbeat every N events
        total_done = self.processed + self.failed + self.skipped
        if total_done > 0 and total_done % self.heartbeat_interval == 0:
            self._log_heartbeat()

    def _log_heartbeat(self):
        """Log heartbeat stats"""
        total_done = self.processed + self.failed + self.skipped
        elapsed = time.time() - self.start_time
        pct = (total_done / self.total_events) * 100
        rate = total_done / (elapsed / 3600) if elapsed > 0 else 0
        eta_hours = (self.total_events - total_done) / rate if rate > 0 else 0

        avg_trades = self.total_trades / self.processed if self.processed > 0 else 0
        avg_quotes = self.total_quotes / self.processed if self.processed > 0 else 0
        avg_size_mb = self.total_size_mb / self.processed if self.processed > 0 else 0

        logger.info("="*80)
        logger.info(f"HEARTBEAT: {total_done}/{self.total_events} events ({pct:.1f}%)")
        logger.info(f"  Success: {self.processed} | Failed: {self.failed} | Skipped: {self.skipped}")
        logger.info(f"  Trades: {self.total_trades:,} (avg {avg_trades:.0f}/event)")
        logger.info(f"  Quotes: {self.total_quotes:,} (avg {avg_quotes:.0f}/event)")
        logger.info(f"  Size: {self.total_size_mb:.1f} MB (avg {avg_size_mb:.1f} MB/event)")
        logger.info(f"  Rate: {rate:.1f} events/hour | ETA: {eta_hours:.1f} hours ({eta_hours/24:.1f} days)")
        logger.info("="*80)

    def final_summary(self):
        """Log final summary"""
        elapsed = time.time() - self.start_time
        total_done = self.processed + self.failed + self.skipped

        logger.info("\n" + "="*80)
        logger.info("FINAL SUMMARY")
        logger.info("="*80)
        logger.info(f"Total events: {total_done}/{self.total_events}")
        logger.info(f"  Success: {self.processed} ({self.processed/self.total_events*100:.1f}%)")
        logger.info(f"  Failed: {self.failed} ({self.failed/self.total_events*100:.1f}%)")
        logger.info(f"  Skipped: {self.skipped} ({self.skipped/self.total_events*100:.1f}%)")
        logger.info(f"")
        logger.info(f"Trades: {self.total_trades:,}")
        logger.info(f"Quotes: {self.total_quotes:,}")
        logger.info(f"Total size: {self.total_size_mb:.1f} MB ({self.total_size_mb/1024:.2f} GB)")
        logger.info(f"")
        logger.info(f"Time elapsed: {elapsed/3600:.2f} hours ({elapsed/3600/24:.2f} days)")
        logger.info(f"Rate: {total_done/(elapsed/3600):.1f} events/hour")
        logger.info("="*80)


class PolygonTradesQuotesDownloader:
    """Download trades and quotes from Polygon.io for FASE 3.2"""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        dry_run: bool = False,
        quotes_hz: Optional[float] = None
    ):
        """
        Initialize downloader

        Args:
            config_path: Path to config.yaml
            dry_run: If True, don't actually download
            quotes_hz: Target quote frequency (Hz) for downsampling (None = all quotes)
        """
        if config_path is None:
            config_path = PROJECT_ROOT / "config" / "config.yaml"

        # Try to load config, fall back to defaults if it fails
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f)
        except (UnicodeDecodeError, FileNotFoundError) as e:
            logger.warning(f"Could not load config.yaml ({e}), using defaults")
            self.cfg = {"polygon": {"api_key": None, "rate_limit_delay_seconds": 12}}

        # API key - prioritize environment variable
        self.api_key = os.getenv("POLYGON_API_KEY") or self.cfg.get("polygon", {}).get("api_key")
        if not self.api_key:
            raise ValueError("Polygon API key not found in POLYGON_API_KEY env var or config.yaml")

        self.base_url = "https://api.polygon.io"
        self.dry_run = dry_run
        self.quotes_hz = quotes_hz

        # Rate limiting
        self.rate_limit_delay = self.cfg.get("polygon", {}).get("rate_limit_delay_seconds", 12)
        self.retry_max_attempts = 5  # Increased from 3 for better resilience
        self.retry_delay_base = 5

        # Event window config (from manifest or default)
        self.window_before_minutes = 3
        self.window_after_minutes = 7

        # Timezone
        self.ny_tz = ZoneInfo("America/New_York")
        self.utc_tz = ZoneInfo("UTC")

        # HTTP session with gzip compression
        self.session = requests.Session() if not dry_run else None
        if self.session:
            self.session.headers["Accept-Encoding"] = "gzip, deflate, br"

        logger.info("Initialized PolygonTradesQuotesDownloader (FASE 3.2)")
        logger.info(f"  Window: [-{self.window_before_minutes}min, +{self.window_after_minutes}min]")
        logger.info(f"  Rate limit: {self.rate_limit_delay}s")
        logger.info(f"  Quotes Hz: {quotes_hz if quotes_hz else 'all'}")
        logger.info(f"  Dry run: {dry_run}")

    def _ensure_utc_timestamp_ns(self, dt: datetime) -> int:
        """Convert datetime to UTC nanoseconds for Polygon API"""
        if dt.tzinfo is None:
            # Assume NY timezone if naive
            dt = dt.replace(tzinfo=self.ny_tz)

        # Convert to UTC
        dt_utc = dt.astimezone(self.utc_tz)

        # Convert to nanoseconds
        return int(dt_utc.timestamp() * 1_000_000_000)

    def _make_request_with_retry(self, url: str, params: Optional[Dict] = None) -> Optional[requests.Response]:
        """Make HTTP request with exponential backoff retry"""
        if self.dry_run:
            return None

        for attempt in range(self.retry_max_attempts):
            try:
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 200:
                    return response

                if response.status_code == 429:
                    delay = self.retry_delay_base * (2 ** attempt)
                    logger.warning(f"429 Rate limit, retrying in {delay}s (attempt {attempt+1}/{self.retry_max_attempts})")
                    time.sleep(delay)
                    continue

                if response.status_code >= 500:
                    delay = self.retry_delay_base * (2 ** attempt)
                    logger.warning(f"5xx error {response.status_code}, retrying in {delay}s")
                    time.sleep(delay)
                    continue

                logger.error(f"HTTP {response.status_code}: {response.text[:200]}")
                return None

            except Exception as e:
                logger.error(f"Request failed: {e}")
                if attempt < self.retry_max_attempts - 1:
                    time.sleep(self.retry_delay_base)

        return None

    def _ensure_api_key_in_url(self, url: str) -> str:
        """Ensure apiKey is in URL for pagination"""
        if "apiKey=" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}apiKey={self.api_key}"
        return url

    def download_trades(
        self,
        ticker: str,
        timestamp_gte: int,
        timestamp_lte: int,
        limit: int = 50000
    ) -> Optional[pl.DataFrame]:
        """Download trades from Polygon API"""
        if self.dry_run:
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

            if next_url:
                next_url = self._ensure_api_key_in_url(next_url)
                response = self._make_request_with_retry(next_url, params=None)
            else:
                response = self._make_request_with_retry(url, params=params)

            if response is None:
                logger.error(f"{ticker}: Failed to download trades")
                return None if not all_results else pl.DataFrame(all_results)

            try:
                data = response.json()
            except Exception as e:
                logger.error(f"{ticker}: Failed to parse JSON: {e}")
                return None if not all_results else pl.DataFrame(all_results)

            results = data.get("results", [])
            if results:
                all_results.extend(results)

            next_url = data.get("next_url")
            if not next_url:
                break

            time.sleep(0.5)  # Pagination delay

        if not all_results:
            return pl.DataFrame()

        df = pl.DataFrame(all_results)

        # Rename columns
        column_map = {
            "sip_timestamp": "timestamp_ns",
            "participant_timestamp": "exchange_timestamp_ns",
            "price": "price",
            "size": "size",
            "exchange": "exchange",
            "conditions": "conditions",
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

        return df

    def download_quotes(
        self,
        ticker: str,
        timestamp_gte: int,
        timestamp_lte: int,
        limit: int = 50000
    ) -> Optional[pl.DataFrame]:
        """Download quotes (NBBO) from Polygon API"""
        if self.dry_run:
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
                logger.error(f"{ticker}: Failed to download quotes")
                return None if not all_results else pl.DataFrame(all_results)

            try:
                data = response.json()
            except Exception as e:
                logger.error(f"{ticker}: Failed to parse JSON: {e}")
                return None if not all_results else pl.DataFrame(all_results)

            results = data.get("results", [])
            if results:
                all_results.extend(results)

            next_url = data.get("next_url")
            if not next_url:
                break

            time.sleep(0.5)

        if not all_results:
            return pl.DataFrame()

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
            "indicators": "indicators"
        }

        existing_cols = {k: v for k, v in column_map.items() if k in df.columns}
        if existing_cols:
            df = df.rename(existing_cols)

        # Convert timestamp
        if "timestamp_ns" in df.columns:
            df = df.with_columns([
                pl.from_epoch(pl.col("timestamp_ns"), time_unit="ns").alias("timestamp")
            ])

        # Downsample quotes if requested
        if self.quotes_hz and len(df) > 0:
            df = self._downsample_quotes(df, self.quotes_hz)

        return df

    def _downsample_quotes(self, df: pl.DataFrame, target_hz: float) -> pl.DataFrame:
        """Downsample quotes to target frequency"""
        if len(df) == 0:
            return df

        # Calculate window duration in seconds
        window_seconds = (self.window_before_minutes + self.window_after_minutes) * 60

        # Target number of quotes
        target_count = int(window_seconds * target_hz)

        if len(df) <= target_count:
            return df  # Already below target

        # Sample evenly
        step = len(df) / target_count
        indices = [int(i * step) for i in range(target_count)]
        df_sampled = df[indices]

        logger.debug(f"Downsampled quotes: {len(df)} → {len(df_sampled)} ({target_hz} Hz)")
        return df_sampled

    def download_event_window(
        self,
        event_row: Dict,
        output_dir: Path,
        download_trades: bool = True,
        download_quotes: bool = True,
        resume: bool = False,
        budget_mb: Optional[float] = None
    ) -> Dict:
        """
        Download trades+quotes for single event

        Args:
            event_row: Event data (symbol, timestamp, event_type, etc.)
            output_dir: Base output directory
            download_trades: Whether to download trades
            download_quotes: Whether to download quotes
            resume: If True, skip downloading existing valid files
            budget_mb: Max size budget in MB (triggers quote trimming)

        Returns:
            Dict with stats
        """
        symbol = event_row["symbol"]
        raw_timestamp = event_row["timestamp"]
        event_type = event_row["event_type"]
        session = event_row.get("session", "RTH")

        # --- PATCH 1: Stable UTC timestamp for IDs / windows ---
        if isinstance(raw_timestamp, str):
            # Parse ISO8601 with/without timezone
            try:
                event_ts = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            except Exception:
                event_ts = datetime.strptime(raw_timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        else:
            # polars Datetime -> python datetime (usually already in UTC)
            event_ts = raw_timestamp
            if event_ts.tzinfo is None:
                event_ts = event_ts.replace(tzinfo=timezone.utc)

        event_ts_utc = event_ts.astimezone(timezone.utc)

        # --- PATCH 2: Per-row windows from manifest (fallback to defaults) ---
        window_before = int(event_row.get("window_before_min", self.window_before_minutes))
        window_after = int(event_row.get("window_after_min", self.window_after_minutes))

        # --- PATCH 3: Stable event ID with hash ---
        id_seed = f"{symbol}|{event_type}|{event_ts_utc.isoformat()}".encode()
        id_hash = hashlib.sha1(id_seed).hexdigest()[:8]
        event_id = f"{symbol}_{event_type}_{event_ts_utc.strftime('%Y%m%d_%H%M%S')}_{id_hash}"

        # Output paths
        symbol_dir = output_dir / f"symbol={symbol}"
        event_dir = symbol_dir / f"event={event_id}"
        trades_file = event_dir / "trades.parquet"
        quotes_file = event_dir / "quotes.parquet"

        stats = {
            "success": False,
            "skipped": False,
            "trades_count": 0,
            "quotes_count": 0,
            "size_mb": 0.0
        }

        # --- PATCH 4: Partial resume (check each file independently) ---
        if resume:
            if download_trades and trades_file.exists():
                try:
                    df_t = pl.read_parquet(trades_file)
                    stats["trades_count"] = len(df_t)
                    download_trades = False  # Skip trades download
                    logger.debug(f"{symbol} {event_id}: Resume → trades already exist, skipping")
                except Exception:
                    logger.warning(f"{symbol} {event_id}: Existing trades file corrupt, will retry")

            if download_quotes and quotes_file.exists():
                try:
                    df_q = pl.read_parquet(quotes_file)
                    stats["quotes_count"] = len(df_q)
                    download_quotes = False  # Skip quotes download
                    logger.debug(f"{symbol} {event_id}: Resume → quotes already exist, skipping")
                except Exception:
                    logger.warning(f"{symbol} {event_id}: Existing quotes file corrupt, will retry")

            # Both files already exist and valid
            if not download_trades and not download_quotes:
                stats["success"] = True
                stats["skipped"] = True
                return stats

        # Calculate window timestamps (nanoseconds for Polygon API)
        window_start = event_ts_utc - timedelta(minutes=window_before)
        window_end = event_ts_utc + timedelta(minutes=window_after)

        timestamp_gte = self._ensure_utc_timestamp_ns(window_start)
        timestamp_lte = self._ensure_utc_timestamp_ns(window_end)

        # Download trades
        if download_trades:
            df_trades = self.download_trades(symbol, timestamp_gte, timestamp_lte)

            if df_trades is not None and not self.dry_run:
                event_dir.mkdir(parents=True, exist_ok=True)

                # --- PATCH 5: Atomic writes ---
                tmp_trades = trades_file.with_suffix(".parquet.tmp")
                if len(df_trades) > 0:
                    df_trades.write_parquet(tmp_trades, compression="zstd")
                    tmp_trades.replace(trades_file)
                    stats["trades_count"] = len(df_trades)

                    if trades_file.exists():
                        stats["size_mb"] += trades_file.stat().st_size / 1024 / 1024

                    logger.info(f"{symbol} {event_id}: Saved {len(df_trades)} trades")
                else:
                    logger.info(f"{symbol} {event_id}: 0 trades (no file written)")

            if not self.dry_run:
                time.sleep(self.rate_limit_delay)

        # Download quotes
        if download_quotes:
            df_quotes = self.download_quotes(symbol, timestamp_gte, timestamp_lte)

            if df_quotes is not None and not self.dry_run:
                # --- PATCH 6: NBBO by-change-only downsampling ---
                try:
                    nbbo_cols = [c for c in ["bid_price", "ask_price", "bid_size", "ask_size"]
                                if c in df_quotes.columns]

                    if len(nbbo_cols) >= 2 and len(df_quotes) > 0:
                        # Mark rows where any NBBO field changes from previous row
                        changes = None
                        for col in nbbo_cols:
                            cond = pl.col(col) != pl.col(col).shift(1)
                            changes = cond if changes is None else (changes | cond)

                        # Keep first row always
                        changes = changes.fill_null(True)
                        df_quotes_filtered = df_quotes.filter(changes)

                        if len(df_quotes_filtered) < len(df_quotes):
                            logger.debug(f"{symbol} {event_id}: NBBO by-change: {len(df_quotes)} → {len(df_quotes_filtered)} quotes")
                            df_quotes = df_quotes_filtered

                except Exception as e:
                    logger.warning(f"{symbol} {event_id}: NBBO by-change downsampling skipped: {e}")

                event_dir.mkdir(parents=True, exist_ok=True)

                # --- PATCH 5: Atomic writes ---
                tmp_quotes = quotes_file.with_suffix(".parquet.tmp")
                if len(df_quotes) > 0:
                    df_quotes.write_parquet(tmp_quotes, compression="zstd")
                    tmp_quotes.replace(quotes_file)
                    stats["quotes_count"] = len(df_quotes)

                    if quotes_file.exists():
                        stats["size_mb"] += quotes_file.stat().st_size / 1024 / 1024

                    logger.info(f"{symbol} {event_id}: Saved {len(df_quotes)} quotes")
                else:
                    logger.info(f"{symbol} {event_id}: 0 quotes (no file written)")

            if not self.dry_run:
                time.sleep(self.rate_limit_delay)

        # Budget cut logic
        if budget_mb and stats["size_mb"] > budget_mb:
            logger.warning(f"{symbol} {event_id}: Size {stats['size_mb']:.1f} MB exceeds budget {budget_mb} MB")
            # TODO: Implement quote trimming if needed

        stats["success"] = True
        return stats

    def close(self):
        """Close HTTP session"""
        if self.session:
            self.session.close()


def load_manifest_with_validation(manifest_path: Path) -> tuple[pl.DataFrame, dict]:
    """Load manifest and validate metadata"""
    logger.info(f"Loading manifest: {manifest_path}")

    # Load manifest
    df = pl.read_parquet(manifest_path)

    # --- PATCH 7: Validate required schema columns ---
    required_cols = ["symbol", "timestamp", "session", "score"]
    missing_cols = [col for col in required_cols if col not in df.columns]

    # Check for event_type or type (both are valid)
    if "event_type" not in df.columns and "type" not in df.columns:
        missing_cols.append("event_type/type")

    if missing_cols:
        logger.error(f"Manifest missing required columns: {missing_cols}")
        logger.error(f"Available columns: {df.columns}")
        raise ValueError(f"Invalid manifest schema: missing {missing_cols}")

    # Normalize 'type' to 'event_type' if needed
    if "type" in df.columns and "event_type" not in df.columns:
        df = df.rename({"type": "event_type"})
        logger.info("✓ Normalized 'type' column to 'event_type'")

    logger.info(f"✓ Manifest schema validation passed ({len(required_cols) + 1} required columns)")

    # Optional columns for per-row windows
    optional_cols = ["window_before_min", "window_after_min"]
    has_optional = [col for col in optional_cols if col in df.columns]
    if has_optional:
        logger.info(f"✓ Per-row window columns detected: {has_optional}")

    # Load metadata
    metadata_file = manifest_path.with_suffix('.json')
    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)

        logger.info(f"Manifest ID: {metadata.get('manifest_id')}")
        logger.info(f"Profile: {metadata.get('profile')}")
        logger.info(f"Config hash: {metadata.get('config_hash')}")
        logger.info(f"Events: {len(df):,}")
        logger.info(f"Symbols: {df['symbol'].n_unique()}")

        # Session distribution
        for session, data in metadata.get('session_distribution', {}).items():
            logger.info(f"  {session}: {data['count']} events ({data['percentage']:.1f}%)")

    else:
        logger.warning("No metadata file found")
        metadata = {}

    return df, metadata


def main():
    parser = argparse.ArgumentParser(description="Download trades+quotes for FASE 3.2 manifest")
    parser.add_argument("--manifest", type=str, required=True, help="Path to manifest CORE parquet")
    parser.add_argument("--wave", type=str, choices=['PM', 'AH', 'RTH', 'all'], default='all',
                        help="Download specific wave (default: all)")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers (default: 1)")
    parser.add_argument("--rate-limit", type=float, default=12, help="Seconds between requests (default: 12)")
    parser.add_argument("--quotes-hz", type=float, help="Target quote frequency Hz (e.g., 1 for RTH)")
    parser.add_argument("--trades-only", action="store_true", help="Download only trades")
    parser.add_argument("--quotes-only", action="store_true", help="Download only quotes")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--dry-run", action="store_true", help="Test without downloading")
    parser.add_argument("--output-dir", type=str, help="Output directory")
    parser.add_argument("--limit", type=int, help="Limit number of events (for testing)")

    args = parser.parse_args()

    # Load manifest
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        logger.error(f"Manifest not found: {manifest_path}")
        sys.exit(1)

    df_manifest, metadata = load_manifest_with_validation(manifest_path)

    # Filter by wave
    if args.wave != 'all':
        df_manifest = df_manifest.filter(pl.col('session') == args.wave)
        logger.info(f"Filtered to {args.wave} wave: {len(df_manifest):,} events")

    # Apply limit for testing
    if args.limit:
        df_manifest = df_manifest.head(args.limit)
        logger.info(f"Limited to {args.limit} events")

    # Output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = PROJECT_ROOT / "raw" / "market_data" / "event_windows"

    logger.info(f"Output directory: {output_dir}")

    # Checkpoint
    checkpoint_file = PROJECT_ROOT / "logs" / "checkpoints" / f"fase3.2_{args.wave}_progress.json"
    checkpoint = CheckpointManager(checkpoint_file) if args.resume else None

    # Initialize downloader
    downloader = PolygonTradesQuotesDownloader(
        dry_run=args.dry_run,
        quotes_hz=args.quotes_hz
    )

    # Override rate limit
    if args.rate_limit:
        downloader.rate_limit_delay = args.rate_limit
        logger.info(f"Rate limit set to {args.rate_limit}s")

    # What to download
    download_trades = not args.quotes_only
    download_quotes = not args.trades_only

    logger.info(f"Downloading: trades={download_trades}, quotes={download_quotes}")

    # Heartbeat monitor
    monitor = HeartbeatMonitor(len(df_manifest), heartbeat_interval=100)

    # Process events
    try:
        for i, event_row in enumerate(df_manifest.iter_rows(named=True)):
            event_id = f"{event_row['symbol']}_{event_row['event_type']}_{event_row['timestamp']}"

            # Skip if completed
            if checkpoint and checkpoint.is_completed(event_id):
                logger.debug(f"[{i+1}/{len(df_manifest)}] Skipping {event_id} (already completed)")
                monitor.update(0, 0, 0.0, True, skipped=True)
                continue

            logger.info(f"\n[{i+1}/{len(df_manifest)}] {event_row['symbol']} {event_row['event_type']} @ {event_row['timestamp']} ({event_row.get('session', 'RTH')})")

            try:
                stats = downloader.download_event_window(
                    event_row,
                    output_dir,
                    download_trades=download_trades,
                    download_quotes=download_quotes,
                    resume=args.resume  # Pass resume flag to enable partial resume
                )

                if stats.get("skipped"):
                    monitor.update(stats["trades_count"], stats["quotes_count"], stats["size_mb"], True, skipped=True)
                elif stats["success"]:
                    monitor.update(stats["trades_count"], stats["quotes_count"], stats["size_mb"], True)

                    # Mark as completed in checkpoint
                    if checkpoint:
                        checkpoint.mark_completed(event_id)

                        # Save checkpoint every 100 events
                        if (i + 1) % 100 == 0:
                            checkpoint.save()
                else:
                    monitor.update(0, 0, 0.0, False)

            except Exception as e:
                logger.error(f"Failed to process event: {e}")
                monitor.update(0, 0, 0.0, False)

    finally:
        # Final checkpoint save
        if checkpoint:
            checkpoint.save()
            logger.info(f"Checkpoint saved: {checkpoint_file}")

        # Close downloader
        downloader.close()

        # Final summary
        monitor.final_summary()


if __name__ == "__main__":
    main()
