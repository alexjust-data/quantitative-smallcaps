"""
Polygon.io Data Ingestion Script
Production-grade ingestion with rate limiting, retries, pagination and DQ validation
"""

import os
import sys
import time
import random
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

import requests
import polars as pl
import yaml
from loguru import logger
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class PolygonIngester:
    """Ingest data from Polygon.io API with resilience and validation"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = self._load_config(config_path)
        self.api_key = os.getenv("POLYGON_API_KEY") or self.config["polygon"]["api_key"]

        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not found in environment or config")

        self.base_url = self.config["polygon"]["base_url"].rstrip("/")
        self.rate_limit = int(self.config["polygon"]["rate_limit_per_minute"])
        self.timeout = int(self.config["polygon"]["timeout"])

        # paths
        self.base_dir = Path(self.config["paths"]["base_dir"])
        self.raw_dir = self.base_dir / self.config["paths"]["raw"]

        # logging + http session + ratelimit
        self._setup_logging()
        self._init_http_session()
        self._init_rate_limiter()

    # ----------------------------- infra ---------------------------------

    def _load_config(self, path: str) -> Dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _setup_logging(self):
        log_cfg = self.config["logging"]
        log_file = self.base_dir / log_cfg["files"]["ingestion"]
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.remove()
        logger.add(
            log_file,
            format=log_cfg["format"],
            level=log_cfg["level"],
            rotation=log_cfg["rotation"],
            retention=log_cfg["retention"],
            enqueue=True,
        )
        # Console output with UTF-8 encoding
        logger.add(sys.stdout, format=log_cfg["format"], level=log_cfg["level"])

    def _init_http_session(self):
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=50, pool_maxsize=50, max_retries=0
        )
        self.session.mount("https://", adapter)
        self.session.headers.update({"Accept": "application/json"})

    def _init_rate_limiter(self):
        self.tokens = self.rate_limit
        self.last_refill = time.time()
        self.tokens_per_second = max(self.rate_limit / 60.0, 0.1)

    def _acquire_token(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.rate_limit, self.tokens + elapsed * self.tokens_per_second)
        self.last_refill = now
        if self.tokens < 1:
            sleep_time = (1 - self.tokens) / self.tokens_per_second
            logger.debug(f"Rate limit: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
            self.tokens = 1
        self.tokens -= 1

    def _backoff(self, attempt: int) -> float:
        backoff = self.config["polygon"].get("backoff", {"base_seconds": 1, "max_seconds": 60})
        base = backoff["base_seconds"]
        max_delay = backoff["max_seconds"]
        delay = min(base * (2 ** attempt), max_delay)
        jitter = random.uniform(0, delay * 0.1)
        return delay + jitter

    # ----------------------------- http ----------------------------------

    def _make_request(self, endpoint: str, params: Optional[Dict] = None, attempt: int = 0) -> Optional[Dict]:
        """
        endpoint: can be a path like '/v3/reference/tickers' or a full URL
        """
        self._acquire_token()

        if endpoint.startswith("http"):
            # Full URL (pagination next_url) - check if apiKey already in URL
            url = endpoint
            if "apiKey=" in url:
                qparams = None  # Don't add params if apiKey already present
            else:
                qparams = {"apiKey": self.api_key}
        else:
            url = f"{self.base_url}{endpoint}"
            qparams = dict(params or {})
            if "apiKey=" not in endpoint:
                qparams["apiKey"] = self.api_key

        try:
            resp = self.session.get(url, params=qparams, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                max_retries = int(self.config["ingestion"]["max_retries"])
                if attempt < max_retries:
                    sleep_time = self._backoff(attempt)
                    logger.warning(f"429 rate limited. Retry {attempt+1}/{max_retries} in {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    return self._make_request(endpoint, params, attempt + 1)
                logger.error(f"Max retries exceeded (429) for {endpoint}")
                return None

            if resp.status_code >= 500:
                max_retries = int(self.config["ingestion"]["max_retries"])
                if attempt < max_retries:
                    sleep_time = self._backoff(attempt)
                    logger.warning(f"Server {resp.status_code}. Retry {attempt+1}/{max_retries} in {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    return self._make_request(endpoint, params, attempt + 1)
                logger.error(f"Server error persists for {endpoint}")
                return None

            logger.error(f"Request failed {resp.status_code}: {resp.text[:500]}")
            return None

        except requests.exceptions.Timeout:
            max_retries = int(self.config["ingestion"]["max_retries"])
            if attempt < max_retries:
                sleep_time = self._backoff(attempt)
                logger.warning(f"Timeout. Retry {attempt+1}/{max_retries} in {sleep_time:.2f}s")
                time.sleep(sleep_time)
                return self._make_request(endpoint, params, attempt + 1)
            logger.error(f"Timeout persists for {endpoint}")
            return None
        except Exception as e:
            logger.error(f"Request exception: {e}")
            return None

    # --------------------------- reference --------------------------------

    def download_tickers(self, active: bool = True) -> pl.DataFrame:
        """Download all tickers (active or delisted) with pagination."""
        logger.info(f"Downloading {'active' if active else 'delisted'} tickers")
        endpoint = "/v3/reference/tickers"
        params = {"market": "stocks", "active": str(active).lower(), "limit": 1000}

        results: List[Dict[str, Any]] = []
        next_url: Optional[str] = None

        while True:
            if next_url:
                data = self._make_request(next_url)
            else:
                data = self._make_request(endpoint, params)

            if not data or "results" not in data:
                break

            results.extend(data["results"])
            logger.info(f"Downloaded {len(results)} tickers so far")
            next_url = data.get("next_url")
            if not next_url:
                break

        if not results:
            logger.warning("No tickers downloaded")
            return pl.DataFrame()

        df = pl.DataFrame(results)

        ts = datetime.utcnow().strftime("%Y%m%d")
        out = self.raw_dir / "reference" / f"tickers_{'active' if active else 'delisted'}_{ts}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out, compression="zstd")
        logger.info(f"Saved {len(df)} tickers to {out}")
        return df

    def download_corporate_actions(self, action_type: str = "splits") -> pl.DataFrame:
        """Download splits or dividends with pagination."""
        logger.info(f"Downloading {action_type}")
        endpoint = f"/v3/reference/{action_type}"
        params = {"limit": 1000}

        results: List[Dict[str, Any]] = []
        next_url: Optional[str] = None

        while True:
            if next_url:
                data = self._make_request(next_url)
            else:
                data = self._make_request(endpoint, params)

            if not data or "results" not in data:
                break

            results.extend(data["results"])
            logger.info(f"Downloaded {len(results)} {action_type} so far")
            next_url = data.get("next_url")
            if not next_url:
                break

        if not results:
            logger.warning(f"No {action_type} downloaded")
            return pl.DataFrame()

        df = pl.DataFrame(results)
        ts = datetime.utcnow().strftime("%Y%m%d")
        out = self.raw_dir / "corporate_actions" / f"{action_type}_{ts}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out, compression="zstd")
        logger.info(f"Saved {len(df)} {action_type} to {out}")
        return df

    # --------------------------- aggregates --------------------------------

    def download_aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,
        from_date: str,
        to_date: str,
    ) -> Optional[pl.DataFrame]:
        """Download aggregate bars with pagination."""
        endpoint = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params = {"adjusted": "true", "sort": "asc", "limit": self.config["ingestion"]["page_limit"]}

        logger.info(f"Downloading {timespan} bars for {ticker}: {from_date} -> {to_date}")

        all_results: List[Dict[str, Any]] = []
        current_endpoint = endpoint
        current_params = params

        while True:
            data = self._make_request(current_endpoint, current_params)
            if not data:
                break
            if data.get("status") != "OK":
                logger.warning(f"Non-OK status for {ticker}: {data.get('status')}")
                break

            results = data.get("results", [])
            if not results:
                break
            all_results.extend(results)

            next_url = data.get("next_url")
            if not next_url:
                break
            current_endpoint = next_url
            current_params = None
            logger.debug(f"Paginating {ticker}: {len(all_results)} bars so far")

        if not all_results:
            logger.warning(f"No data for {ticker}")
            return None

        df = pl.DataFrame(
            all_results,
            schema={
                "v": pl.Int64,
                "vw": pl.Float64,
                "o": pl.Float64,
                "c": pl.Float64,
                "h": pl.Float64,
                "l": pl.Float64,
                "t": pl.Int64,
                "n": pl.Int32,
            },
        ).rename(
            {"v": "volume", "vw": "vwap", "o": "open", "c": "close",
             "h": "high", "l": "low", "t": "timestamp", "n": "transactions"}
        )

        df = df.with_columns(
            pl.from_epoch(pl.col("timestamp"), time_unit="ms").dt.replace_time_zone("UTC").alias("timestamp")
        )

        df = df.with_columns(
            pl.col(["open", "high", "low", "close", "vwap"]).cast(pl.Float32),
        )

        df = df.with_columns(
            pl.lit(ticker).alias("symbol"),
            pl.col("timestamp").dt.date().alias("date"),
        )

        logger.info(f"Downloaded {len(df)} bars for {ticker}")
        return df

    # --------------------------- DQ & save ---------------------------------

    def _dq_check_aggregates(self, df: pl.DataFrame) -> bool:
        """Basic Data Quality checks."""
        if df.height == 0:
            logger.error("DQ: empty dataframe")
            return False

        dup = df.select([pl.col("symbol"), pl.col("timestamp")]).is_duplicated().any()
        if dup:
            logger.error("DQ: duplicated (symbol,timestamp) found")
            return False

        nulls = df.null_count().to_dicts()[0]
        has_nulls = any(v > 0 for v in nulls.values())
        if has_nulls:
            logger.warning(f"DQ: nulls present {nulls}")

        # (3) Warn if not sorted
        try:
            is_sorted = df["timestamp"].is_sorted()
            if not is_sorted:
                logger.warning("DQ: timestamps not sorted — sorting before save")
        except Exception:
            # Fallback: assume not sorted
            logger.warning("DQ: Unable to check sort order — sorting before save")

        return True

    def save_aggregates(self, df: pl.DataFrame, timespan: str, partition_by_date: bool = True):
        """Save aggregates to partitioned parquet"""
        if df is None or df.height == 0:
            return
        if not self._dq_check_aggregates(df):
            logger.error("Aborting save due to DQ failure")
            return

        base_path = self.raw_dir / "market_data" / "bars" / str(timespan).lower()
        base_path.mkdir(parents=True, exist_ok=True)

        # (3) Ensure sorted before persist
        df = df.sort(["symbol", "timestamp"])

        if partition_by_date:
            for sym in df.get_column("symbol").unique().to_list():
                sdf = df.filter(pl.col("symbol") == sym)
                for d in sdf.get_column("date").unique().to_list():
                    dstr = str(d)
                    out = base_path / f"symbol={sym}" / f"date={dstr}.parquet"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    sdf.filter(pl.col("date") == d).write_parquet(out, compression="zstd")
            logger.info(f"Saved {df.height} bars partitioned by symbol/date into {base_path}")
        else:
            sym = df.get_column("symbol")[0]
            out = base_path / f"{sym}.parquet"
            df.write_parquet(out, compression="zstd")
            logger.info(f"Saved {df.height} bars to {out}")


def main():
    parser = argparse.ArgumentParser(description="Polygon.io data ingestion")
    parser.add_argument(
        "--task",
        required=True,
        choices=["tickers", "corporate_actions", "aggregates"],
        help="Task to perform",
    )
    parser.add_argument("--ticker", help="Ticker symbol (for aggregates)")
    parser.add_argument(
        "--timespan",
        choices=["minute", "hour", "day", "week"],
        default="day",
        help="Timespan for aggregates",
    )
    parser.add_argument("--days", type=int, default=7, help="Days of history to download")

    # (1) Mutually exclusive flags for partition
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--partition", dest="partition", action="store_true", help="Partition by date")
    grp.add_argument("--no-partition", dest="partition", action="store_false", help="Do not partition")
    parser.set_defaults(partition=True)

    args = parser.parse_args()

    try:
        ingester = PolygonIngester()

        if args.task == "tickers":
            logger.info("=== Downloading tickers ===")
            ingester.download_tickers(active=True)
            ingester.download_tickers(active=False)

        elif args.task == "corporate_actions":
            logger.info("=== Downloading corporate actions ===")
            ingester.download_corporate_actions("splits")
            ingester.download_corporate_actions("dividends")

        elif args.task == "aggregates":
            if not args.ticker:
                logger.error("--ticker required for aggregates task")
                sys.exit(1)

            logger.info(f"=== Downloading {args.timespan} aggregates for {args.ticker} ===")
            to_date = datetime.utcnow().strftime("%Y-%m-%d")
            from_date = (datetime.utcnow() - timedelta(days=args.days)).strftime("%Y-%m-%d")

            df = ingester.download_aggregates(
                args.ticker, 1, args.timespan, from_date, to_date
            )
            if df is not None:
                # (2) Consistent label for folder: 1d/1m/1h/1w
                timespan_label_map = {"day": "1d", "minute": "1m", "hour": "1h", "week": "1w"}
                timespan_label = timespan_label_map[args.timespan]
                ingester.save_aggregates(df, timespan_label, partition_by_date=args.partition)

        logger.info("=== Ingestion complete ===")

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
