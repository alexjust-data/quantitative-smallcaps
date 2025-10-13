"""
List symbols that have 1-minute bar data available.

This script scans the bars/1m directory and creates a parquet file with
symbols that have at least one file with 1m bar data.

Usage:
    python scripts/utils/list_symbols_with_1m_data.py \
        --bars-dir raw/market_data/bars/1m \
        --out processed/reference/symbols_with_1m.parquet
"""

import argparse
from pathlib import Path
import polars as pl
from typing import Set
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


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
        print(f"[ERROR] Directory not found: {bars_dir}")
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


def create_symbol_list(symbols: Set[str], output_path: Path) -> None:
    """
    Create parquet file with symbol list.

    Args:
        symbols: Set of symbol strings
        output_path: Path to output parquet file
    """
    # Create dataframe
    df = pl.DataFrame({
        "symbol": sorted(list(symbols))
    })

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write parquet
    df.write_parquet(output_path)

    print(f"[OK] Created symbol list: {output_path}")
    print(f"   Total symbols: {len(symbols)}")


def main():
    parser = argparse.ArgumentParser(
        description="List symbols with 1m bar data available"
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
        help="Output parquet file path (e.g., processed/reference/symbols_with_1m.parquet)"
    )

    args = parser.parse_args()

    # Convert to absolute paths
    bars_dir = PROJECT_ROOT / args.bars_dir
    output_path = PROJECT_ROOT / args.out

    print(f"[INFO] Scanning 1m bars directory: {bars_dir}")

    # Scan directory
    symbols = scan_1m_directory(bars_dir)

    if not symbols:
        print("[ERROR] No symbols with 1m data found")
        sys.exit(1)

    # Create output file
    create_symbol_list(symbols, output_path)

    # Print sample
    print("\n[INFO] Sample symbols (first 10):")
    for symbol in sorted(list(symbols))[:10]:
        print(f"   - {symbol}")

    if len(symbols) > 10:
        print(f"   ... and {len(symbols) - 10} more")


if __name__ == "__main__":
    main()
