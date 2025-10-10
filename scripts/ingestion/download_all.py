"""
Complete Historical Download Script
Executes the full Month 1 data ingestion plan for Polygon.io Stocks Advanced

Production improvements:
- Date windowing to avoid timeouts
- Resume capability (skip already downloaded)
- Robust universe filtering (OTC/ADR/ETF)
- UTC timestamps
- Progress tracking and failed ticker logging
"""

import sys
import argparse
import time
import glob
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

# Add parent directory to path to import ingest_polygon
sys.path.insert(0, str(Path(__file__).parent))
from ingest_polygon import PolygonIngester

import polars as pl


def _latest_file(pattern: str) -> Path | None:
    """Get most recent file matching pattern"""
    files = sorted(glob.glob(pattern), key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return Path(files[0]) if files else None


def _read_symbols_from_parquet(parquet_path: Path, col: str = "symbol") -> list[str]:
    """Read symbols from parquet file"""
    df = pl.read_parquet(str(parquet_path))
    # Support both 'ticker' and 'symbol' columns
    if col not in df.columns and "ticker" in df.columns:
        col = "ticker"
    return sorted(set(df[col].drop_nulls().to_list()))


class HistoricalDownloader:
    """Orchestrate historical data download following Month 1 plan"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.ingester = PolygonIngester(config_path)
        self.config = self.ingester.config
        self._override_top_volatile = None
        logger.info("Historical Downloader initialized")

    def _date_windows(self, from_date: str, to_date: str, window_days: int):
        """Yield (from,to) date strings in windows to reduce timeout risk."""
        start = datetime.strptime(from_date, "%Y-%m-%d")
        end = datetime.strptime(to_date, "%Y-%m-%d")
        cur = start
        while cur < end:
            nxt = min(cur + timedelta(days=window_days), end)
            yield cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d")
            cur = nxt

    def get_small_caps_universe(self, force_refresh: bool = False, letters: list = None):
        """Get or filter small caps universe from downloaded tickers

        Args:
            force_refresh: Re-download tickers instead of using cached
            letters: Filter tickers starting with these letters (e.g. ['A', 'B'])
        """
        active_tickers_path = self.ingester.raw_dir / "reference" / "tickers_active_*.parquet"
        delisted_tickers_path = self.ingester.raw_dir / "reference" / "tickers_delisted_*.parquet"

        # Find latest ticker files
        import glob
        active_files = glob.glob(str(active_tickers_path))
        delisted_files = glob.glob(str(delisted_tickers_path))

        if not active_files or not delisted_files or force_refresh:
            logger.info("Downloading fresh ticker universe (active + delisted)")
            df_active = self.ingester.download_tickers(active=True)
            df_delisted = self.ingester.download_tickers(active=False)
            # Align schemas: add delisted_utc to active with nulls
            df_active = df_active.with_columns(pl.lit(None).cast(pl.Utf8).alias("delisted_utc"))
            df = pl.concat([df_active, df_delisted])
            logger.info(f"Combined universe: {len(df_active)} active + {len(df_delisted)} delisted = {len(df)} total")
        else:
            latest_active = max(active_files, key=lambda x: Path(x).stat().st_mtime)
            latest_delisted = max(delisted_files, key=lambda x: Path(x).stat().st_mtime)
            logger.info(f"Loading tickers from {latest_active} and {latest_delisted}")
            df_active = pl.read_parquet(latest_active)
            df_delisted = pl.read_parquet(latest_delisted)
            # Align schemas: add delisted_utc to active with nulls
            if "delisted_utc" not in df_active.columns and "delisted_utc" in df_delisted.columns:
                df_active = df_active.with_columns(pl.lit(None).cast(pl.Utf8).alias("delisted_utc"))
            df = pl.concat([df_active, df_delisted])
            logger.info(f"Loaded universe: {len(df_active)} active + {len(df_delisted)} delisted = {len(df)} total")

        # Filter small caps based on config
        universe_cfg = self.config["universe"]

        logger.info(f"Filtering small caps: price ${universe_cfg['price_min']}-${universe_cfg['price_max']}")

        # Filter by type (Common Stock)
        small_caps = df.filter(pl.col("type") == "CS")

        # Exclude ETFs
        if universe_cfg.get("exclude_etfs", True):
            small_caps = small_caps.filter(pl.col("type") != "ETF")

        # Exclude OTC
        if universe_cfg.get("exclude_otc", True):
            if "market" in small_caps.columns:
                small_caps = small_caps.filter(pl.col("market") != "otc")

        # Exclude ADRs (optional)
        if universe_cfg.get("exclude_adrs", False):
            if "name" in small_caps.columns:
                small_caps = small_caps.filter(~pl.col("name").str.contains("ADR", literal=True))

        # Filter by starting letter (for parallelization/batching)
        if letters:
            letters_upper = [x.upper() for x in letters]
            logger.info(f"Filtering tickers starting with: {letters_upper}")
            small_caps = small_caps.filter(
                pl.col("ticker").str.slice(0, 1).is_in(letters_upper)
            )

        logger.info(f"Small caps universe: {len(small_caps)} tickers")
        return small_caps

    def download_week1_foundation(self):
        """Week 1: Reference data + daily bars + hourly bars + corporate actions"""
        logger.info("=== WEEK 1: Foundation Data ===")

        # 1. Universe
        logger.info("Step 1/5: Downloading ticker universe")
        self.ingester.download_tickers(active=True)
        self.ingester.download_tickers(active=False)

        # 2. Corporate actions
        logger.info("Step 2/5: Downloading corporate actions")
        self.ingester.download_corporate_actions("splits")
        self.ingester.download_corporate_actions("dividends")

        # 3. Get small caps
        logger.info("Step 3/5: Filtering small caps universe")
        small_caps = self.get_small_caps_universe(letters=getattr(self, "_letters", None))

        # 4. Download 5 years daily for all small caps
        logger.info(f"Step 4/5: Downloading 5 years daily bars for {len(small_caps)} tickers")
        years = self.config["ingestion"]["daily_bars_years"]
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        from_date = (datetime.utcnow() - timedelta(days=years*365)).strftime("%Y-%m-%d")

        failed = []
        skipped = 0
        for i, row in enumerate(small_caps.iter_rows(named=True)):
            ticker = row["ticker"]
            if (i + 1) % 100 == 0:
                logger.info(f"Progress: {i+1}/{len(small_caps)} tickers (skipped: {skipped}, failed: {len(failed)})")

            # Check if already downloaded (resume capability) - check BOTH adjusted and raw
            out_adj = self.ingester.raw_dir / "market_data" / "bars" / "1d" / f"{ticker}.parquet"
            out_raw = self.ingester.raw_dir / "market_data" / "bars" / "1d_raw" / f"{ticker}.parquet"
            if out_adj.exists() and out_raw.exists():
                skipped += 1
                continue

            try:
                # Download ADJUSTED prices (for technical analysis)
                for f_date, t_date in self._date_windows(from_date, to_date, window_days=365):
                    logger.debug(f"{ticker} [ADJ]: {f_date} -> {t_date}")
                    df = self.ingester.download_aggregates(ticker, 1, "day", f_date, t_date, adjusted=True)
                    if df is not None and df.height > 0:
                        self.ingester.save_aggregates(df, "1d", partition_by_date=False, adjusted=True)

                # Download RAW prices (for price filters and capitalization)
                for f_date, t_date in self._date_windows(from_date, to_date, window_days=365):
                    logger.debug(f"{ticker} [RAW]: {f_date} -> {t_date}")
                    df = self.ingester.download_aggregates(ticker, 1, "day", f_date, t_date, adjusted=False)
                    if df is not None and df.height > 0:
                        self.ingester.save_aggregates(df, "1d", partition_by_date=False, adjusted=False)
            except Exception as e:
                logger.error(f"Failed {ticker}: {e}")
                failed.append(ticker)

            # Rate limiting breather
            time.sleep(0.2)

        if failed:
            failed_file = self.ingester.base_dir / "logs" / f"failed_week1_daily_{datetime.utcnow().strftime('%Y%m%d')}.txt"
            failed_file.parent.mkdir(exist_ok=True)
            failed_file.write_text("\n".join(failed))
            logger.warning(f"Failed daily tickers ({len(failed)}): saved to {failed_file}")

        logger.info(f"=== Step 4/5 complete: {len(small_caps) - skipped - len(failed)} daily downloaded, {skipped} skipped, {len(failed)} failed ===")

        # 5. Download 5 years hourly for all small caps
        logger.info(f"Step 5/5: Downloading 5 years hourly bars for {len(small_caps)} tickers")
        years = self.config["ingestion"].get("hourly_bars_years", self.config["ingestion"]["daily_bars_years"])
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        from_date = (datetime.utcnow() - timedelta(days=years*365)).strftime("%Y-%m-%d")

        failed_hourly = []
        skipped_hourly = 0
        for i, row in enumerate(small_caps.iter_rows(named=True)):
            ticker = row["ticker"]
            if (i + 1) % 100 == 0:
                logger.info(f"Hourly progress: {i+1}/{len(small_caps)} tickers (skipped: {skipped_hourly}, failed: {len(failed_hourly)})")

            # Check if already downloaded (resume capability) - check BOTH adjusted and raw
            out_adj = self.ingester.raw_dir / "market_data" / "bars" / "1h" / f"{ticker}.parquet"
            out_raw = self.ingester.raw_dir / "market_data" / "bars" / "1h_raw" / f"{ticker}.parquet"
            if out_adj.exists() and out_raw.exists():
                skipped_hourly += 1
                continue

            try:
                # Download ADJUSTED prices (for technical analysis)
                for f_date, t_date in self._date_windows(from_date, to_date, window_days=90):
                    logger.debug(f"{ticker} hourly [ADJ]: {f_date} -> {t_date}")
                    df = self.ingester.download_aggregates(ticker, 1, "hour", f_date, t_date, adjusted=True)
                    if df is not None and df.height > 0:
                        self.ingester.save_aggregates(df, "1h", partition_by_date=False, adjusted=True)

                # Download RAW prices (for price filters and capitalization)
                for f_date, t_date in self._date_windows(from_date, to_date, window_days=90):
                    logger.debug(f"{ticker} hourly [RAW]: {f_date} -> {t_date}")
                    df = self.ingester.download_aggregates(ticker, 1, "hour", f_date, t_date, adjusted=False)
                    if df is not None and df.height > 0:
                        self.ingester.save_aggregates(df, "1h", partition_by_date=False, adjusted=False)
            except Exception as e:
                logger.error(f"Failed hourly {ticker}: {e}")
                failed_hourly.append(ticker)

            # Rate limiting breather
            time.sleep(0.2)

        if failed_hourly:
            failed_file = self.ingester.base_dir / "logs" / f"failed_week1_hourly_{datetime.utcnow().strftime('%Y%m%d')}.txt"
            failed_file.parent.mkdir(exist_ok=True)
            failed_file.write_text("\n".join(failed_hourly))
            logger.warning(f"Failed hourly tickers ({len(failed_hourly)}): saved to {failed_file}")

        logger.info(f"=== Week 1 complete: Daily({len(small_caps) - skipped - len(failed)}) + Hourly({len(small_caps) - skipped_hourly - len(failed_hourly)}) downloaded ===")

    def download_week2_3_intraday(self, top_n: int = 500):
        """Week 2-3: 1-min bars for top volatile tickers"""
        logger.info(f"=== WEEK 2-3: Intraday Data (Top {top_n}) ===")

        # Get small caps and rank by volatility
        small_caps = self.get_small_caps_universe(letters=getattr(self, "_letters", None))

        # Take top N (in production, rank by gap%, rvol, halt_count from processed daily data)
        # For now, use first N
        top_tickers = small_caps.head(top_n)

        logger.info(f"Downloading 3 years of 1-min bars for {len(top_tickers)} tickers")
        years = self.config["ingestion"]["minute_bars_years"]
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        from_date = (datetime.utcnow() - timedelta(days=years*365)).strftime("%Y-%m-%d")

        failed = []
        for i, row in enumerate(top_tickers.iter_rows(named=True)):
            ticker = row["ticker"]
            if (i + 1) % 50 == 0:
                logger.info(f"Progress: {i+1}/{len(top_tickers)} tickers (failed: {len(failed)})")

            try:
                # Download ADJUSTED prices only (1m optimization: reconstruct raw from splits if needed)
                for f_date, t_date in self._date_windows(from_date, to_date, window_days=30):
                    logger.debug(f"{ticker}: {f_date} -> {t_date}")
                    df = self.ingester.download_aggregates(ticker, 1, "minute", f_date, t_date, adjusted=True)
                    if df is not None and df.height > 0:
                        self.ingester.save_aggregates(df, "1m", partition_by_date=True, adjusted=True)
            except Exception as e:
                logger.error(f"Failed {ticker}: {e}")
                failed.append(ticker)

            # Gentle rate limiting for high-volume data
            time.sleep(0.3)

        if failed:
            failed_file = self.ingester.base_dir / "logs" / f"failed_week23_{datetime.utcnow().strftime('%Y%m%d')}.txt"
            failed_file.parent.mkdir(exist_ok=True)
            failed_file.write_text("\n".join(failed))
            logger.warning(f"Failed tickers ({len(failed)}): saved to {failed_file}")

        logger.info(f"=== Week 2-3 complete: {len(top_tickers) - len(failed)} downloaded, {len(failed)} failed ===")

    def download_week4_complementary(self):
        """Week 4: Short Interest & Short Volume"""
        logger.info("=== WEEK 4: Short Interest & Short Volume ===")

        # Short Interest (semi-monthly, 5 years)
        si_years = int(self.config["ingestion"]["short_interest_years"])
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        from_si = (datetime.utcnow() - timedelta(days=si_years * 365)).strftime("%Y-%m-%d")

        logger.info(f"Downloading Short Interest: {from_si} → {to_date}")
        try:
            df_si = self.ingester.download_short_interest(from_si, to_date)
            if df_si is not None:
                logger.info(f"Short Interest downloaded: {len(df_si)} records")
        except Exception as e:
            logger.error(f"Short Interest failed: {e}")

        # Short Volume (daily, 3 years)
        sv_years = int(self.config["ingestion"]["short_volume_years"])
        from_sv = (datetime.utcnow() - timedelta(days=sv_years * 365)).strftime("%Y-%m-%d")

        logger.info(f"Downloading Short Volume: {from_sv} → {to_date}")
        try:
            df_sv = self.ingester.download_short_volume(from_sv, to_date)
            if df_sv is not None:
                logger.info(f"Short Volume downloaded: {len(df_sv)} records")
        except Exception as e:
            logger.error(f"Short Volume failed: {e}")

        logger.info("=== Week 4 complete ===")

    def download_minute_for_topN(self, top_parquet: Path, years: int = None):
        """Download 1-min bars (3y default) for Top-N ranked symbols in batches of 500."""
        if not top_parquet or not top_parquet.exists():
            logger.error(f"Ranking file not found: {top_parquet}")
            return

        symbols = _read_symbols_from_parquet(top_parquet, col="symbol")

        years = years or self.config["ingestion"]["minute_bars_years"]
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        from_date = (datetime.utcnow() - timedelta(days=years*365)).strftime("%Y-%m-%d")

        logger.info(f"=== WEEK 2-3: 1-min for Top-{len(symbols)} ===")
        failed = []
        skipped = 0
        batch = 0

        for i, sym in enumerate(symbols, start=1):
            # Resume check - check BOTH adjusted and raw
            out_dir_adj = self.ingester.raw_dir / "market_data" / "bars" / "1m" / sym
            out_dir_raw = self.ingester.raw_dir / "market_data" / "bars" / "1m_raw" / sym
            if (out_dir_adj.exists() and any(out_dir_adj.glob("*.parquet"))) and \
               (out_dir_raw.exists() and any(out_dir_raw.glob("*.parquet"))):
                skipped += 1
                if i % 100 == 0:
                    logger.info(f"Progress: {i}/{len(symbols)} (skipped: {skipped}, failed: {len(failed)})")
                continue

            try:
                # Download ADJUSTED prices only (1m optimization: reconstruct raw from splits if needed)
                for f_date, t_date in self._date_windows(from_date, to_date, window_days=30):
                    logger.debug(f"{sym}: {f_date} -> {t_date}")
                    df = self.ingester.download_aggregates(sym, 1, "minute", f_date, t_date, adjusted=True)
                    if df is not None and df.height > 0:
                        self.ingester.save_aggregates(df, "1m", partition_by_date=True, adjusted=True)
            except Exception as e:
                logger.error(f"Failed 1m {sym}: {e}")
                failed.append(sym)

            # Rate limiting
            time.sleep(0.25)

            if i % 100 == 0:
                logger.info(f"Progress: {i}/{len(symbols)} (skipped: {skipped}, failed: {len(failed)})")

            if i % 500 == 0:
                batch += 1
                logger.info(f"[TopN] Batch {batch} complete ({i}/{len(symbols)})")

        if failed:
            failed_file = self.ingester.base_dir / "logs" / f"failed_topN_1m_{datetime.utcnow().strftime('%Y%m%d')}.txt"
            failed_file.parent.mkdir(exist_ok=True)
            failed_file.write_text("\n".join(failed))
            logger.warning(f"Failed TopN 1m: {len(failed)}")

        logger.info(f"=== TopN 1-min complete: {len(symbols) - skipped - len(failed)} downloaded, {skipped} skipped, {len(failed)} failed ===")

    def download_event_windows_for_rest(self,
                                        events_parquet: Path = None,
                                        ranking_parquet: Path = None,
                                        preset: str = "compact",
                                        max_symbols: int = None):
        """Download 1-min event windows (D-2 to D+2) for symbols outside Top-N."""
        # 1) Get small caps universe from Week 1
        small_caps = self.get_small_caps_universe(letters=getattr(self, "_letters", None))
        universe = set(small_caps["ticker"].to_list() if "ticker" in small_caps.columns else
                      small_caps["symbol"].to_list())

        # 2) Read Top-N symbols
        top_syms = set()
        if ranking_parquet and ranking_parquet.exists():
            top_syms = set(_read_symbols_from_parquet(ranking_parquet, col="symbol"))

        rest_syms = sorted(universe - top_syms)
        logger.info(f"=== EVENT WINDOWS: Symbols outside Top-N: {len(rest_syms)} ===")

        if not rest_syms:
            logger.warning("No symbols to process for event windows")
            return

        # 3) Get events parquet (use most recent if not specified)
        if not events_parquet:
            events_parquet = _latest_file(str(self.ingester.base_dir / "processed" / "events" / "events_daily_*.parquet"))
        if not events_parquet:
            logger.error("No processed/events/events_daily_*.parquet found. Run detect_events.py first.")
            return

        # 4) Execute event windows download script
        script = self.ingester.base_dir / "scripts" / "ingestion" / "download_event_windows.py"

        if not script.exists():
            logger.error(f"Script not found: {script}")
            return

        # Build command
        cmd = [
            sys.executable, str(script),
            "--events-file", str(events_parquet),
            "--preset", preset,
            "--resume"
        ]

        # Filter to rest symbols (limit for testing if specified)
        if max_symbols:
            rest_syms = rest_syms[:max_symbols]
            logger.info(f"Limiting to first {max_symbols} symbols for testing")

        cmd += ["--symbols"] + rest_syms

        logger.info(f"[REST] Event windows → {len(rest_syms)} symbols with preset '{preset}'")

        try:
            subprocess.run(cmd, check=True)
            logger.info("=== Event windows download complete ===")
        except subprocess.CalledProcessError as e:
            logger.error(f"download_event_windows.py failed: {e}")

    def run_full_plan(self, weeks: list = [1, 2, 3, 4], top_n: int = 2000,
                      events_preset: str = "compact",
                      max_rest_symbols: int = None):
        """Execute complete data ingestion plan with event-based ranking"""
        logger.info("===== STARTING FULL HISTORICAL DOWNLOAD =====")
        logger.info(f"Weeks to execute: {weeks}")
        logger.info(f"Top-N for full minute bars: {top_n}")
        logger.info(f"Event windows preset: {events_preset}")
        start_time = time.time()

        # Week 1: Foundation (1d + 1h bars for all small caps)
        if 1 in weeks:
            self.download_week1_foundation()

        # After Week 1: Detect events and rank by event count
        events_parquet = None
        ranking_parquet = None

        if 2 in weeks or 3 in weeks:
            logger.info("=== Running event detection and ranking ===")

            # 1. Detect events
            detect_script = self.ingester.base_dir / "scripts" / "processing" / "detect_events.py"
            if detect_script.exists():
                try:
                    logger.info("Running detect_events.py --use-percentiles")
                    subprocess.run([sys.executable, str(detect_script), "--use-percentiles"], check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"detect_events.py failed: {e}")
                    logger.error("Skipping Week 2-3 minute bar downloads")
                    return
            else:
                logger.error(f"Script not found: {detect_script}")
                logger.error("Skipping Week 2-3 minute bar downloads")
                return

            # 2. Rank by event count
            rank_script = self.ingester.base_dir / "scripts" / "processing" / "rank_by_event_count.py"
            if rank_script.exists():
                try:
                    logger.info(f"Running rank_by_event_count.py --top-n {top_n}")
                    subprocess.run([sys.executable, str(rank_script), "--top-n", str(top_n)], check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"rank_by_event_count.py failed: {e}")
                    logger.error("Skipping Week 2-3 minute bar downloads")
                    return
            else:
                logger.error(f"Script not found: {rank_script}")
                logger.error("Skipping Week 2-3 minute bar downloads")
                return

            # 3. Find generated files
            events_parquet = _latest_file(str(self.ingester.base_dir / "processed" / "events" / "events_daily_*.parquet"))
            ranking_parquet = _latest_file(str(self.ingester.base_dir / "processed" / "rankings" / f"top_{top_n}_by_events_*.parquet"))

            if not events_parquet or not ranking_parquet:
                logger.error(f"Failed to find events or ranking files")
                logger.error(f"Events: {events_parquet}")
                logger.error(f"Ranking: {ranking_parquet}")
                logger.error("Skipping Week 2-3 minute bar downloads")
                return

            logger.info(f"Using events file: {events_parquet}")
            logger.info(f"Using ranking file: {ranking_parquet}")

            # 4. Download 1-min bars for Top-N
            logger.info(f"=== Downloading 1-min bars for Top-{top_n} ===")
            self.download_minute_for_topN(ranking_parquet)

            # 5. Download event windows for remaining symbols
            logger.info(f"=== Downloading event windows for remaining symbols ===")
            self.download_event_windows_for_rest(
                events_parquet=events_parquet,
                ranking_parquet=ranking_parquet,
                preset=events_preset,
                max_symbols=max_rest_symbols
            )

        # Week 4: Complementary data
        if 4 in weeks:
            self.download_week4_complementary()

        elapsed = time.time() - start_time
        logger.info(f"===== DOWNLOAD COMPLETE in {elapsed/3600:.2f} hours =====")


def main():
    parser = argparse.ArgumentParser(description="Historical data download orchestrator with event-based ranking")
    parser.add_argument("--weeks", nargs="+", type=int, choices=[1,2,3,4], default=[1,2,3,4],
                        help="Which weeks to execute (default: all)")
    parser.add_argument("--top-n", type=int, default=2000, help="Top-N symbols for full minute bars (default: 2000)")
    parser.add_argument("--events-preset", choices=["compact","extended"], default="compact",
                        help="Event window preset (default: compact)")
    parser.add_argument("--max-rest-symbols", type=int, help="Limit number of 'rest' symbols for event windows (testing)")
    parser.add_argument("--letters", nargs="+", help="Limit tickers by first letter(s), e.g. A B C")
    parser.add_argument("--retry-failed", action="store_true", help="Retry failed tickers from previous runs")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")

    # Legacy args (deprecated but kept for backwards compatibility)
    parser.add_argument("--top-volatile", type=int, help="(Deprecated) Use --top-n instead")

    args = parser.parse_args()

    downloader = HistoricalDownloader()

    # Handle retry failed
    if args.retry_failed:
        logger.info("=== RETRY FAILED MODE ===")
        for week_file in ["failed_week1", "failed_week23"]:
            failed_path = downloader.ingester.base_dir / "logs" / f"{week_file}_*.txt"
            import glob
            files = glob.glob(str(failed_path))
            if files:
                latest = max(files, key=lambda x: Path(x).stat().st_mtime)
                failed_tickers = Path(latest).read_text(encoding="utf-8").splitlines()
                failed_tickers = [s.strip() for s in failed_tickers if s.strip()]
                logger.info(f"Found {len(failed_tickers)} failed tickers in {latest}")
                logger.info("Retry logic: manually process these tickers")
                # TODO: Implement retry loop per ticker
        return

    if args.dry_run:
        logger.info("=== DRY RUN MODE ===")
        logger.info(f"Plan: Execute weeks {args.weeks}")
        logger.info(f"Top-N for full minute bars: {args.top_n}")
        logger.info(f"Event windows preset: {args.events_preset}")

        if args.letters:
            logger.info(f"Filter: Tickers starting with {args.letters}")

        if 1 in args.weeks:
            small_caps = downloader.get_small_caps_universe(letters=args.letters)
            years = downloader.config["ingestion"]["daily_bars_years"]
            logger.info(f"Week 1: {len(small_caps)} tickers, {years} years daily + hourly bars")

        if 2 in args.weeks or 3 in args.weeks:
            years = downloader.config["ingestion"]["minute_bars_years"]
            logger.info(f"Week 2-3: Event detection → Rank → Top-{args.top_n} full 1-min ({years}y) + Rest event windows")

        if 4 in args.weeks:
            logger.info("Week 4: Short Interest & Short Volume")

        logger.info("\nRemove --dry-run to execute this plan.")
        return

    # Apply overrides
    if args.letters:
        downloader._letters = args.letters

    # Handle legacy --top-volatile arg
    top_n = args.top_n
    if args.top_volatile:
        logger.warning("--top-volatile is deprecated, use --top-n instead")
        top_n = args.top_volatile

    downloader.run_full_plan(
        weeks=args.weeks,
        top_n=top_n,
        events_preset=args.events_preset,
        max_rest_symbols=args.max_rest_symbols
    )


if __name__ == "__main__":
    main()
