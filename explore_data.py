"""
Exploración de Datos - Small Caps Trading System
Script Python para explorar los datos descargados de Polygon.io
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import polars as pl
from pathlib import Path
from datetime import datetime, timedelta

print("=" * 80)
print("EXPLORACIÓN DE DATOS - Small Caps Trading System")
print("=" * 80)

# Paths
base = Path(".")
raw = base / "raw"
bars_1d = raw / "market_data" / "bars" / "1d"
bars_1h = raw / "market_data" / "bars" / "1h"
bars_1m = raw / "market_data" / "bars" / "1m"
tickers_dir = raw / "reference"
splits_dir = raw / "corporate_actions" / "splits"
dividends_dir = raw / "corporate_actions" / "dividends"

# 1. Universo de Tickers
print("\n" + "=" * 80)
print("1. UNIVERSO DE TICKERS")
print("=" * 80)

ticker_files = sorted(tickers_dir.glob("tickers_*.parquet"))
if ticker_files:
    df_tickers = pl.read_parquet(ticker_files[-1])
    print(f"\nTickers totales: {len(df_tickers):,}")
    print(f"Archivo: {ticker_files[-1].name}")
    print(f"\nColumnas: {df_tickers.columns}")
    print(f"\nPrimeras 10 filas:")
    print(df_tickers.head(10))

    # Distribución por tipo
    if 'type' in df_tickers.columns:
        print(f"\nDistribución por tipo:")
        type_counts = df_tickers.group_by("type").agg(pl.len().alias("count")).sort("count", descending=True)
        print(type_counts)

    # Distribución por market
    if 'market' in df_tickers.columns:
        print(f"\nDistribución por market:")
        market_counts = df_tickers.group_by("market").agg(pl.len().alias("count")).sort("count", descending=True)
        print(market_counts)
else:
    print("No ticker files found")

# 2. Daily Bars (1d)
print("\n" + "=" * 80)
print("2. DAILY BARS (1d)")
print("=" * 80)

files_1d = sorted(bars_1d.glob("*.parquet")) if bars_1d.exists() else []
print(f"\nArchivos daily bars: {len(files_1d)}")
if files_1d:
    print(f"Primeros 10: {[f.stem for f in files_1d[:10]]}")

    # Cargar AAPL como ejemplo
    ticker = "AAPL"
    file_1d = bars_1d / f"{ticker}.parquet"

    if file_1d.exists():
        df_1d = pl.read_parquet(file_1d)
        print(f"\n--- Ticker: {ticker} ---")
        print(f"Rows: {len(df_1d):,}")
        print(f"Date range: {df_1d['timestamp'].min()} -> {df_1d['timestamp'].max()}")
        print(f"\nColumnas: {df_1d.columns}")
        print(f"\nPrimeras 5 filas:")
        print(df_1d.head(5))
        print(f"\nEstadísticas de precios:")
        print(df_1d.select(["close", "volume", "vwap"]).describe())
    else:
        print(f"File not found: {file_1d}")
else:
    print("No daily bars found")

# 3. Hourly Bars (1h)
print("\n" + "=" * 80)
print("3. HOURLY BARS (1h)")
print("=" * 80)

files_1h = sorted(bars_1h.glob("*.parquet")) if bars_1h.exists() else []
print(f"\nArchivos hourly bars: {len(files_1h)}")
if files_1h:
    print(f"Primeros 10: {[f.stem for f in files_1h[:10]]}")

    # Cargar AAPL como ejemplo
    ticker = "AAPL"
    file_1h = bars_1h / f"{ticker}.parquet"

    if file_1h.exists():
        df_1h = pl.read_parquet(file_1h)
        print(f"\n--- Ticker: {ticker} ---")
        print(f"Rows: {len(df_1h):,}")
        print(f"Date range: {df_1h['timestamp'].min()} -> {df_1h['timestamp'].max()}")
        print(f"\nColumnas: {df_1h.columns}")
        print(f"\nPrimeras 5 filas:")
        print(df_1h.head(5))

        # Últimos 5 días
        from datetime import timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=5)
        df_recent = df_1h.filter(pl.col("timestamp") >= cutoff).sort("timestamp")
        print(f"\nÚltimos 5 días ({len(df_recent)} bars):")
        print(df_recent.tail(10))
    else:
        print(f"File not found: {file_1h}")
else:
    print("No hourly bars found")

# 4. Comparación Daily vs Hourly
if files_1d and files_1h:
    print("\n" + "=" * 80)
    print("4. COMPARACIÓN: DAILY vs HOURLY")
    print("=" * 80)

    ticker = "AAPL"
    file_1d = bars_1d / f"{ticker}.parquet"
    file_1h = bars_1h / f"{ticker}.parquet"

    if file_1d.exists() and file_1h.exists():
        df_1d = pl.read_parquet(file_1d)
        df_1h = pl.read_parquet(file_1h)

        print(f"\nTicker: {ticker}")
        print(f"Daily bars (1d): {len(df_1d):,} rows")
        print(f"Hourly bars (1h): {len(df_1h):,} rows")
        print(f"Ratio: {len(df_1h) / len(df_1d):.1f}x más granular")

        size_1d = file_1d.stat().st_size / 1024
        size_1h = file_1h.stat().st_size / 1024
        print(f"\nTamaño archivo 1d: {size_1d:.1f} KB")
        print(f"Tamaño archivo 1h: {size_1h:.1f} KB")
        print(f"Ratio: {size_1h / size_1d:.1f}x")

# 5. Corporate Actions - Splits
print("\n" + "=" * 80)
print("5. CORPORATE ACTIONS - SPLITS")
print("=" * 80)

split_files = sorted(splits_dir.glob("*.parquet")) if splits_dir.exists() else []
if split_files:
    df_splits = pl.read_parquet(split_files[-1])
    print(f"\nTotal splits: {len(df_splits):,}")
    print(f"Archivo: {split_files[-1].name}")
    print(f"\nColumnas: {df_splits.columns}")
    print(f"\nÚltimos 10 splits:")
    print(df_splits.sort("execution_date", descending=True).head(10))
else:
    print("No splits files found")

# 6. Corporate Actions - Dividends
print("\n" + "=" * 80)
print("6. CORPORATE ACTIONS - DIVIDENDS")
print("=" * 80)

dividend_files = sorted(dividends_dir.glob("*.parquet")) if dividends_dir.exists() else []
if dividend_files:
    df_divs = pl.read_parquet(dividend_files[-1])
    print(f"\nTotal dividends: {len(df_divs):,}")
    print(f"Archivo: {dividend_files[-1].name}")
    print(f"\nColumnas: {df_divs.columns}")
    print(f"\nÚltimos 10 dividends:")
    print(df_divs.sort("ex_dividend_date", descending=True).head(10))

    print(f"\nTop 20 tickers por número de dividendos:")
    top_div = df_divs.group_by("ticker").agg([
        pl.len().alias("num_dividends"),
        pl.col("cash_amount").sum().alias("total_amount")
    ]).sort("num_dividends", descending=True).head(20)
    print(top_div)
else:
    print("No dividend files found")

print("\n" + "=" * 80)
print("EXPLORACIÓN COMPLETA")
print("=" * 80)
