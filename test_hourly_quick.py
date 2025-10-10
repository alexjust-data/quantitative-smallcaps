"""
Quick test to validate daily (1d) + hourly (1h) bars download
Tests only 3 specific tickers: AAPL, MSFT, GOOG
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent / "scripts" / "ingestion"))
from ingest_polygon import PolygonIngester

def main():
    logger.info("=== QUICK TEST: Daily + Hourly Bars ===")

    ingester = PolygonIngester()
    test_tickers = ["AAPL", "MSFT", "GOOG"]

    # Date range: Last 30 days for speed
    to_date = datetime.utcnow().strftime("%Y-%m-%d")
    from_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")

    logger.info(f"Testing {len(test_tickers)} tickers: {test_tickers}")
    logger.info(f"Date range: {from_date} -> {to_date}")

    # Test 1: Daily bars
    logger.info("\n--- TEST 1/2: Daily bars (1d) ---")
    for ticker in test_tickers:
        try:
            df = ingester.download_aggregates(ticker, 1, "day", from_date, to_date)
            if df is not None and df.height > 0:
                ingester.save_aggregates(df, "1d", partition_by_date=False)
                logger.info(f"✅ {ticker} daily: {df.height} bars")
            else:
                logger.warning(f"⚠️ {ticker} daily: No data")
        except Exception as e:
            logger.error(f"❌ {ticker} daily FAILED: {e}")

    # Test 2: Hourly bars
    logger.info("\n--- TEST 2/2: Hourly bars (1h) ---")
    for ticker in test_tickers:
        try:
            df = ingester.download_aggregates(ticker, 1, "hour", from_date, to_date)
            if df is not None and df.height > 0:
                ingester.save_aggregates(df, "1h", partition_by_date=False)
                logger.info(f"✅ {ticker} hourly: {df.height} bars")
            else:
                logger.warning(f"⚠️ {ticker} hourly: No data")
        except Exception as e:
            logger.error(f"❌ {ticker} hourly FAILED: {e}")

    # Validate results
    logger.info("\n=== VALIDATION ===")
    bars_1d = Path("raw/market_data/bars/1d")
    bars_1h = Path("raw/market_data/bars/1h")

    if bars_1d.exists():
        files_1d = list(bars_1d.glob("*.parquet"))
        logger.info(f"✅ 1d directory: {len(files_1d)} files")
        for f in files_1d:
            logger.info(f"   - {f.name}")
    else:
        logger.error("❌ 1d directory NOT created")

    if bars_1h.exists():
        files_1h = list(bars_1h.glob("*.parquet"))
        logger.info(f"✅ 1h directory: {len(files_1h)} files")
        for f in files_1h:
            logger.info(f"   - {f.name}")
    else:
        logger.error("❌ 1h directory NOT created")

    logger.info("\n=== TEST COMPLETE ===")

if __name__ == "__main__":
    main()
