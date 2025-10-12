#!/usr/bin/env python
"""
Download Reference Static Data from Polygon:
- Exchanges
- Ticker Types
- Market Holidays (upcoming)
- Condition Codes (trades/quotes)
- Ticker Details (active + delisted universe)
"""

import sys
from pathlib import Path
from loguru import logger
import polars as pl

# Import local package
sys.path.insert(0, str(Path(__file__).parent))
from ingest_polygon import PolygonIngester


def load_universe_symbols(ing: PolygonIngester) -> list[str]:
    """Carga símbolo de activos + delisted del directorio raw/reference si existen; si no, los descarga."""
    ref_dir = ing.raw_dir / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)

    import glob
    active_files = sorted(glob.glob(str(ref_dir / "tickers_active_*.parquet")))
    delisted_files = sorted(glob.glob(str(ref_dir / "tickers_delisted_*.parquet")))

    if not active_files:
        logger.info("Active tickers not found locally → downloading...")
        ing.download_tickers(active=True)
        active_files = sorted(glob.glob(str(ref_dir / "tickers_active_*.parquet")))

    if not delisted_files:
        logger.info("Delisted tickers not found locally → downloading...")
        ing.download_tickers(active=False)
        delisted_files = sorted(glob.glob(str(ref_dir / "tickers_delisted_*.parquet")))

    df_a = pl.read_parquet(active_files[-1])
    df_d = pl.read_parquet(delisted_files[-1])
    # ambas tienen campo 'ticker' en Polygon reference
    symbols = pl.concat([df_a.select("ticker"), df_d.select("ticker")]).unique().to_series().to_list()
    logger.info(f"Universe size (active+delisted): {len(symbols)}")
    return symbols


def main():
    ing = PolygonIngester()  # usa config/config.yaml
    cfg_ref = ing.config.get("reference_endpoints", {})

    # 1) Exchanges
    if cfg_ref.get("enable_exchanges", True):
        ing.download_exchanges()

    # 2) Ticker Types
    if cfg_ref.get("enable_ticker_types", True):
        ing.download_ticker_types()

    # 3) Holidays
    if cfg_ref.get("enable_holidays", True):
        ing.download_market_holidays()

    # 4) Condition Codes
    if cfg_ref.get("enable_condition_codes", True):
        if cfg_ref.get("conditions", {}).get("trades", True):
            ing.download_condition_codes("trades")
        if cfg_ref.get("conditions", {}).get("quotes", True):
            ing.download_condition_codes("quotes")

    # 5) Ticker Details (universo completo)
    if cfg_ref.get("enable_ticker_details", True):
        symbols = load_universe_symbols(ing)
        ing.download_ticker_details(symbols)

    logger.info("=== Reference static download complete ===")


if __name__ == "__main__":
    main()
