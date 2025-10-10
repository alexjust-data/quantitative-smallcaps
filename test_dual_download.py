"""Test dual download (adjusted + raw prices) for a single symbol"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from scripts.ingestion.ingest_polygon import PolygonIngester

def test_dual_download():
    """Test downloading both adjusted and raw prices for AAPL"""
    ingester = PolygonIngester()

    # Use AAPL as test (known to have splits)
    ticker = "AAPL"
    to_date = "2020-09-30"
    from_date = "2020-01-01"

    print(f"[TEST] Downloading {ticker} data: {from_date} to {to_date}")
    print("-" * 60)

    # Download adjusted prices
    print("\n[1/2] Downloading ADJUSTED prices...")
    df_adj = ingester.download_aggregates(ticker, 1, "day", from_date, to_date, adjusted=True)
    if df_adj is not None:
        print(f"  - Rows: {df_adj.height}")
        print(f"  - Date range: {df_adj['date'].min()} to {df_adj['date'].max()}")
        ingester.save_aggregates(df_adj, "1d", partition_by_date=False, adjusted=True)
        print(f"  - Saved to: raw/market_data/bars/1d/{ticker}.parquet")
    else:
        print("  - No data received")

    # Download raw prices
    print("\n[2/2] Downloading RAW prices...")
    df_raw = ingester.download_aggregates(ticker, 1, "day", from_date, to_date, adjusted=False)
    if df_raw is not None:
        print(f"  - Rows: {df_raw.height}")
        print(f"  - Date range: {df_raw['date'].min()} to {df_raw['date'].max()}")
        ingester.save_aggregates(df_raw, "1d", partition_by_date=False, adjusted=False)
        print(f"  - Saved to: raw/market_data/bars/1d_raw/{ticker}.parquet")
    else:
        print("  - No data received")

    # Compare prices on a specific date (before the split)
    if df_adj is not None and df_raw is not None:
        print("\n[COMPARISON] Prices on 2020-01-02 (before 2020-08-31 split 4:1):")
        print("-" * 60)

        date_filter = "2020-01-02"
        adj_row = df_adj.filter(df_adj["date"].cast(str) == date_filter)
        raw_row = df_raw.filter(df_raw["date"].cast(str) == date_filter)

        if adj_row.height > 0 and raw_row.height > 0:
            adj_close = adj_row["close"][0]
            raw_close = raw_row["close"][0]
            ratio = raw_close / adj_close

            print(f"  Adjusted close: ${adj_close:.2f}")
            print(f"  Raw close:      ${raw_close:.2f}")
            print(f"  Ratio:          {ratio:.2f}x (should be ~4.0 due to 4:1 split)")
        else:
            print("  Date not found in data")

    print("\n[OK] Test complete!")

if __name__ == "__main__":
    test_dual_download()
