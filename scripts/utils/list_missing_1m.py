"""
List symbols that are missing 1-minute bar data.

This script compares a universe file (e.g., top_2000_by_events) against
available 1m bar data and creates a parquet file with symbols that need
to be downloaded.

Usage:
    python scripts/utils/list_missing_1m.py \
        --universe processed/rankings/top_2000_by_events_20251009.parquet \
        --bars-dir raw/market_data/bars/1m \
        --out processed/reference/symbols_missing_1m.parquet
"""

import argparse
from pathlib import Path
import polars as pl
from typing import Set
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def load_universe_symbols(universe_path: Path) -> Set[str]:
    """
    Load symbols from universe file.

    Args:
        universe_path: Path to parquet file with 'symbol' column

    Returns:
        Set of symbol strings from universe
    """
    df = pl.read_parquet(universe_path)

    if "symbol" not in df.columns:
        raise ValueError(f"Universe file must have 'symbol' column. Found: {df.columns}")

    return set(df["symbol"].to_list())


def scan_1m_directory(bars_dir: Path) -> Set[str]:
    """
    Scan the 1m bars directory and return set of symbols with data.

    Args:
        bars_dir: Path to raw/market_data/bars/1m directory

    Returns:
        Set of symbol strings that have at least one parquet file
    """
    symbols = set()

    if not bars_dir.exists():
        print(f"[WARNING] Directory not found: {bars_dir}")
        return symbols

    # Scan for partitioned directories (format: symbol=SYMBOL/)
    for symbol_dir in bars_dir.iterdir():
        if symbol_dir.is_dir() and symbol_dir.name.startswith("symbol="):
            # Extract symbol name
            symbol = symbol_dir.name.replace("symbol=", "")

            # Verify it has at least one parquet file
            parquet_files = list(symbol_dir.glob("*.parquet"))
            if parquet_files:
                symbols.add(symbol)

    return symbols


def create_missing_symbol_list(missing_symbols: Set[str], output_path: Path) -> None:
    """
    Create parquet file with missing symbol list.

    Args:
        missing_symbols: Set of symbol strings that need downloading
        output_path: Path to output parquet file
    """
    # Create dataframe
    df = pl.DataFrame({
        "symbol": sorted(list(missing_symbols))
    })

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write parquet
    df.write_parquet(output_path)

    print(f"[OK] Created missing symbol list: {output_path}")
    print(f"   Total missing symbols: {len(missing_symbols)}")


def main():
    parser = argparse.ArgumentParser(
        description="List symbols missing 1m bar data"
    )
    parser.add_argument(
        "--universe",
        type=str,
        required=True,
        help="Path to universe parquet file (e.g., processed/rankings/top_2000_by_events.parquet)"
    )
    parser.add_argument(
        "--bars-dir",
        type=str,
        required=True,
        help="Path to bars/1m directory (e.g., raw/market_data/bars/1m)"
    )
    parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output parquet file path (e.g., processed/reference/symbols_missing_1m.parquet)"
    )

    args = parser.parse_args()

    # Convert to absolute paths
    universe_path = PROJECT_ROOT / args.universe
    bars_dir = PROJECT_ROOT / args.bars_dir
    output_path = PROJECT_ROOT / args.out

    print(f"[INFO] Loading universe: {universe_path}")
    universe_symbols = load_universe_symbols(universe_path)
    print(f"   Universe size: {len(universe_symbols)} symbols")

    print(f"\n[INFO] Scanning 1m bars directory: {bars_dir}")
    available_symbols = scan_1m_directory(bars_dir)
    print(f"   Available symbols: {len(available_symbols)}")

    # Calculate missing
    missing_symbols = universe_symbols - available_symbols
    print(f"\n[INFO] Missing symbols: {len(missing_symbols)}")

    if not missing_symbols:
        print("[OK] All symbols in universe have 1m data available!")
        # Create empty file anyway for consistency
        create_missing_symbol_list(set(), output_path)
        return

    # Create output file
    create_missing_symbol_list(missing_symbols, output_path)

    # Print sample
    print("\n[INFO] Sample missing symbols (first 20):")
    for symbol in sorted(list(missing_symbols))[:20]:
        print(f"   - {symbol}")

    if len(missing_symbols) > 20:
        print(f"   ... and {len(missing_symbols) - 20} more")

    # Print coverage stats
    coverage_pct = (len(available_symbols) / len(universe_symbols)) * 100
    print(f"\n[INFO] Coverage: {coverage_pct:.1f}% of universe has 1m data")


if __name__ == "__main__":
    main()
