"""
Download Trading Halt Data from FINRA/NASDAQ Trader

Source: http://www.nasdaqtrader.com/dynamic/symdir/tradinghalt.txt
Format: Pipe-delimited text file

Columns:
- Halt Date: Date of halt (MM/DD/YYYY)
- Halt Time: Time of halt (HH:MM:SS)
- Symbol: Ticker symbol
- Name: Company name
- Market: Exchange (NASDAQ, NYSE, etc.)
- Reason Code: Halt reason (LUDP, T1, etc.)
- Pause Threshold Price: Price trigger for halt
- Resumption Date: Date of resumption (MM/DD/YYYY)
- Resumption Quote Time: Time quotes resumed (HH:MM:SS)
- Resumption Trade Time: Time trades resumed (HH:MM:SS)

Reason Codes:
- LUDP: Volatility Trading Pause
- T1: News Pending
- T2: News Released
- T5: Single Stock Trading Pause (SEC Rule 201)
- T6: Extraordinary Market Activity
- T12: Additional Information Requested
"""

from pathlib import Path
from datetime import datetime, timedelta
import polars as pl
import requests
import yaml
import logging
from typing import Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d | %(message)s")
logger = logging.getLogger(__name__)


class HaltDataDownloader:
    """Downloads trading halt data from FINRA/NASDAQ Trader"""

    def __init__(self, base_dir: Path = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parents[2]

        self.base_dir = base_dir
        self.raw_dir = base_dir / "raw" / "reference"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        # FINRA/NASDAQ Trader URLs
        self.halt_url = "http://www.nasdaqtrader.com/dynamic/symdir/tradinghalt.txt"

        # Reason code mapping
        self.reason_codes = {
            "LUDP": "Volatility Trading Pause",
            "T1": "News Pending",
            "T2": "News Released",
            "T5": "Single Stock Trading Pause (SSR)",
            "T6": "Extraordinary Market Activity",
            "T12": "Additional Information Requested",
            "M1": "Market Wide Circuit Breaker Level 1",
            "M2": "Market Wide Circuit Breaker Level 2",
            "M3": "Market Wide Circuit Breaker Level 3",
            "IPO1": "IPO Not Yet Trading",
            "IPOD": "IPO Deferred",
            "MCB3": "Market Wide Circuit Breaker Level 3",
            "R9": "Corporate Action",
            "D": "News Dissemination",
            "H10": "SEC Trading Suspension",
            "O1": "Operations Halt",
        }

    def download_current_halts(self) -> Optional[pl.DataFrame]:
        """
        Download current day's trading halts from NASDAQ Trader.

        Returns:
            DataFrame with halt information or None if failed
        """
        logger.info(f"Downloading trading halts from {self.halt_url}")

        try:
            response = requests.get(self.halt_url, timeout=30)
            response.raise_for_status()

            # Content is pipe-delimited
            # First line is header, last line is footer (usually "Copyright...")
            lines = response.text.strip().split('\n')

            # Remove footer if exists (lines starting with copyright, blank, etc)
            data_lines = [line for line in lines if line and not line.lower().startswith(('copyright', 'data'))]

            if len(data_lines) < 2:
                logger.warning("No halt data found (empty file)")
                return None

            # Parse as CSV with pipe delimiter
            from io import StringIO
            csv_content = '\n'.join(data_lines)

            df = pl.read_csv(
                StringIO(csv_content),
                separator="|",
                truncate_ragged_lines=True,
                ignore_errors=True
            )

            logger.info(f"Downloaded {len(df)} halt records")

            # Clean and parse
            df = self._parse_halt_data(df)

            return df

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download halt data: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse halt data: {e}")
            return None

    def _parse_halt_data(self, df: pl.DataFrame) -> pl.DataFrame:
        """Parse and clean halt data"""

        # Expected columns (may vary slightly)
        # Halt Date|Halt Time|Symbol|Name|Market|Reason Code|Pause Threshold Price|Resumption Date|Resumption Quote Time|Resumption Trade Time

        # Rename columns to standard format
        expected_cols = [
            "Halt Date", "Halt Time", "Symbol", "Name", "Market",
            "Reason Code", "Pause Threshold Price", "Resumption Date",
            "Resumption Quote Time", "Resumption Trade Time"
        ]

        # Check if we have the expected columns
        if len(df.columns) >= 10:
            df.columns = expected_cols[:len(df.columns)]

        logger.info(f"Columns: {df.columns}")

        # Parse timestamps
        df = df.with_columns([
            # Halt timestamp
            pl.when(pl.col("Halt Date").is_not_null() & pl.col("Halt Time").is_not_null())
            .then(
                (pl.col("Halt Date").cast(pl.Utf8) + " " + pl.col("Halt Time").cast(pl.Utf8))
                .str.strptime(pl.Datetime, "%m/%d/%Y %H:%M:%S", strict=False)
            )
            .otherwise(None)
            .alias("halt_timestamp"),

            # Resumption timestamp (trade time)
            pl.when(pl.col("Resumption Date").is_not_null() & pl.col("Resumption Trade Time").is_not_null())
            .then(
                (pl.col("Resumption Date").cast(pl.Utf8) + " " + pl.col("Resumption Trade Time").cast(pl.Utf8))
                .str.strptime(pl.Datetime, "%m/%d/%Y %H:%M:%S", strict=False)
            )
            .otherwise(None)
            .alias("resume_timestamp"),

            # Clean symbol
            pl.col("Symbol").str.strip_chars().str.to_uppercase().alias("symbol"),

            # Reason description
            pl.col("Reason Code").str.strip_chars().alias("reason_code")
        ])

        # Calculate halt duration in minutes
        df = df.with_columns([
            pl.when(pl.col("halt_timestamp").is_not_null() & pl.col("resume_timestamp").is_not_null())
            .then(
                (pl.col("resume_timestamp") - pl.col("halt_timestamp")).dt.total_minutes()
            )
            .otherwise(None)
            .alias("halt_duration_minutes")
        ])

        # Select final columns
        df = df.select([
            "symbol",
            "halt_timestamp",
            "resume_timestamp",
            "halt_duration_minutes",
            "reason_code",
            pl.col("Market").str.strip_chars().alias("market"),
            pl.col("Name").str.strip_chars().alias("company_name"),
            pl.col("Pause Threshold Price").alias("pause_threshold_price")
        ])

        # Filter out invalid rows
        df = df.filter(
            pl.col("symbol").is_not_null() &
            pl.col("halt_timestamp").is_not_null()
        )

        return df

    def save_halt_data(self, df: pl.DataFrame, date: str = None) -> Path:
        """
        Save halt data to parquet.

        Args:
            df: DataFrame with halt data
            date: Date string (YYYYMMDD), defaults to today

        Returns:
            Path to saved file
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        out_path = self.raw_dir / f"trading_halts_{date}.parquet"
        df.write_parquet(out_path, compression="zstd")

        logger.info(f"Saved {len(df)} halt records to {out_path}")
        return out_path

    def download_and_save(self) -> Optional[Path]:
        """Download current halts and save to parquet"""
        df = self.download_current_halts()

        if df is None or len(df) == 0:
            logger.warning("No halt data to save")
            return None

        return self.save_halt_data(df)


def main():
    """Main entry point"""
    downloader = HaltDataDownloader()

    logger.info("=== Trading Halt Data Download ===")
    result = downloader.download_and_save()

    if result:
        logger.info(f"[OK] Halt data saved to: {result}")

        # Show sample
        df = pl.read_parquet(result)
        logger.info(f"\nSample ({min(5, len(df))} rows):")
        print(df.head(5))

        # Summary by reason code
        summary = df.group_by("reason_code").agg([
            pl.count().alias("count"),
            pl.col("halt_duration_minutes").mean().alias("avg_duration_min")
        ]).sort("count", descending=True)

        logger.info("\nHalts by reason code:")
        print(summary)
    else:
        logger.error("[ERROR] Failed to download halt data")


if __name__ == "__main__":
    main()
