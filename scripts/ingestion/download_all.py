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
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

# Add parent directory to path to import ingest_polygon
sys.path.insert(0, str(Path(__file__).parent))
from ingest_polygon import PolygonIngester

import polars as pl


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

        # Find latest active tickers file
        import glob
        files = glob.glob(str(active_tickers_path))
        if not files or force_refresh:
            logger.info("Downloading fresh ticker universe")
            df = self.ingester.download_tickers(active=True)
        else:
            latest = max(files, key=lambda x: Path(x).stat().st_mtime)
            logger.info(f"Loading tickers from {latest}")
            df = pl.read_parquet(latest)

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
        """Week 1: Reference data + daily bars + corporate actions"""
        logger.info("=== WEEK 1: Foundation Data ===")

        # 1. Universe
        logger.info("Step 1/4: Downloading ticker universe")
        self.ingester.download_tickers(active=True)
        self.ingester.download_tickers(active=False)

        # 2. Corporate actions
        logger.info("Step 2/4: Downloading corporate actions")
        self.ingester.download_corporate_actions("splits")
        self.ingester.download_corporate_actions("dividends")

        # 3. Get small caps
        logger.info("Step 3/4: Filtering small caps universe")
        small_caps = self.get_small_caps_universe(letters=getattr(self, "_letters", None))

        # 4. Download 5 years daily for all small caps
        logger.info(f"Step 4/4: Downloading 5 years daily bars for {len(small_caps)} tickers")
        years = self.config["ingestion"]["daily_bars_years"]
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        from_date = (datetime.utcnow() - timedelta(days=years*365)).strftime("%Y-%m-%d")

        failed = []
        skipped = 0
        for i, row in enumerate(small_caps.iter_rows(named=True)):
            ticker = row["ticker"]
            if (i + 1) % 100 == 0:
                logger.info(f"Progress: {i+1}/{len(small_caps)} tickers (skipped: {skipped}, failed: {len(failed)})")

            # Check if already downloaded (resume capability)
            out = self.ingester.raw_dir / "market_data" / "bars" / "1d" / f"{ticker}.parquet"
            if out.exists():
                skipped += 1
                continue

            try:
                # Use windowing for long ranges (365 day windows for daily data)
                for f_date, t_date in self._date_windows(from_date, to_date, window_days=365):
                    logger.debug(f"{ticker}: {f_date} -> {t_date}")
                    df = self.ingester.download_aggregates(ticker, 1, "day", f_date, t_date)
                    if df is not None and df.height > 0:
                        self.ingester.save_aggregates(df, "1d", partition_by_date=False)
            except Exception as e:
                logger.error(f"Failed {ticker}: {e}")
                failed.append(ticker)

            # Rate limiting breather
            time.sleep(0.2)

        if failed:
            failed_file = self.ingester.base_dir / "logs" / f"failed_week1_{datetime.utcnow().strftime('%Y%m%d')}.txt"
            failed_file.parent.mkdir(exist_ok=True)
            failed_file.write_text("\n".join(failed))
            logger.warning(f"Failed tickers ({len(failed)}): saved to {failed_file}")

        logger.info(f"=== Week 1 complete: {len(small_caps) - skipped - len(failed)} downloaded, {skipped} skipped, {len(failed)} failed ===")

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
                # Use 30-day windows for minute data (large volume)
                for f_date, t_date in self._date_windows(from_date, to_date, window_days=30):
                    logger.debug(f"{ticker}: {f_date} -> {t_date}")
                    df = self.ingester.download_aggregates(ticker, 1, "minute", f_date, t_date)
                    if df is not None and df.height > 0:
                        self.ingester.save_aggregates(df, "1m", partition_by_date=True)
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
        """Week 4: Fundamentals, news (optional: trades/quotes)"""
        logger.info("=== WEEK 4: Complementary Data ===")

        logger.info("Week 4 requires additional endpoint implementations")
        logger.info("- Fundamentals: /vX/reference/financials (income, balance, cashflow)")
        logger.info("- News: /v2/reference/news")
        logger.info("- Trades/Quotes: For top 50 tickers only")

        # TODO: Implement these endpoints in ingest_polygon.py
        # For now, Week 4 is a placeholder

        logger.info("=== Week 4 skipped (not yet implemented) ===")

    def run_full_plan(self, weeks: list = [1, 2, 3, 4]):
        """Execute complete month 1 plan"""
        logger.info("===== STARTING FULL HISTORICAL DOWNLOAD =====")
        logger.info(f"Weeks to execute: {weeks}")
        start_time = time.time()

        if 1 in weeks:
            self.download_week1_foundation()

        if 2 in weeks or 3 in weeks:
            top_volatile = self._override_top_volatile or self.config["ingestion"]["top_volatile_count"]
            self.download_week2_3_intraday(top_n=top_volatile)

        if 4 in weeks:
            self.download_week4_complementary()

        elapsed = time.time() - start_time
        logger.info(f"===== DOWNLOAD COMPLETE in {elapsed/3600:.2f} hours =====")


def main():
    parser = argparse.ArgumentParser(description="Historical data download orchestrator")
    parser.add_argument("--weeks", nargs="+", type=int, choices=[1,2,3,4], default=[1,2,3,4],
                        help="Which weeks to execute (default: all)")
    parser.add_argument("--top-volatile", type=int, help="Override top N volatile tickers for week 2-3")
    parser.add_argument("--letters", nargs="+", help="Limit tickers by first letter(s), e.g. A B C")
    parser.add_argument("--retry-failed", action="store_true", help="Retry failed tickers from previous runs")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")

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

        if args.letters:
            logger.info(f"Filter: Tickers starting with {args.letters}")

        if 1 in args.weeks:
            small_caps = downloader.get_small_caps_universe(letters=args.letters)
            years = downloader.config["ingestion"]["daily_bars_years"]
            logger.info(f"Week 1: {len(small_caps)} tickers, {years} years daily bars")

        if 2 in args.weeks or 3 in args.weeks:
            top_n = args.top_volatile or downloader.config["ingestion"]["top_volatile_count"]
            years = downloader.config["ingestion"]["minute_bars_years"]
            logger.info(f"Week 2-3: Top {top_n} tickers, {years} years 1-min bars")

        if 4 in args.weeks:
            logger.info("Week 4: Complementary data (fundamentals, news) - not yet implemented")

        logger.info("Remove --dry-run to execute this plan.")
        return

    # Apply overrides
    if args.top_volatile:
        downloader._override_top_volatile = args.top_volatile

    if args.letters:
        downloader._letters = args.letters

    downloader.run_full_plan(weeks=args.weeks)


if __name__ == "__main__":
    main()
