"""
Trading Halt Detector

Combines FINRA/NASDAQ official halt data with heuristic pattern detection
to identify trading halts and halt-like conditions in 1-minute bar data.

Heuristic patterns for halt detection:
1. Flat candle with zero volume (high == low AND volume == 0)
2. Extreme gap (>20%) + volume explosion (10x next candle)
3. Sequence of 3+ consecutive flat candles
4. Sudden volume drought after high activity

Usage:
    detector = HaltDetector()
    df_with_halts = detector.detect_all_halts(bars_df, official_halts_df)
"""

from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
import polars as pl
import yaml
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d | %(message)s")
logger = logging.getLogger(__name__)


class HaltDetector:
    """Detects trading halts using official data + heuristics"""

    def __init__(self, config_path: Path = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parents[2] / "config" / "liquidity_filters.yaml"

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Halt detection thresholds
        self.halt_window_minutes = config["execution"]["context_slippage"]["halt_window_minutes"]

        # Heuristic thresholds (not in config yet - using hardcoded)
        self.extreme_gap_threshold = 0.20  # 20% gap
        self.volume_explosion_multiplier = 10.0  # 10x volume
        self.flat_candle_sequence_min = 3  # 3+ consecutive flat candles
        self.volume_drought_ratio = 0.1  # Volume drops to 10% of recent avg

    def detect_flat_zero_volume(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Pattern 1: Flat candle with zero volume (high == low AND volume == 0)

        Args:
            df: DataFrame with OHLCV columns

        Returns:
            DataFrame with 'halt_flat_zero' column
        """
        df = df.with_columns([
            ((pl.col("high") == pl.col("low")) & (pl.col("volume") == 0)).alias("halt_flat_zero")
        ])

        return df

    def detect_extreme_gap(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Pattern 2: Extreme gap (>20%) + volume explosion (10x)

        Args:
            df: DataFrame with OHLCV columns, sorted by (symbol, timestamp)

        Returns:
            DataFrame with 'halt_extreme_gap' column
        """
        df = df.sort(["symbol", "timestamp"])

        df = df.with_columns([
            # Gap from previous close
            (abs((pl.col("open") - pl.col("close").shift(1)) / (pl.col("close").shift(1) + 1e-9)))
            .over("symbol")
            .alias("gap_pct"),

            # Volume ratio vs previous
            (pl.col("volume") / (pl.col("volume").shift(1) + 1e-9))
            .over("symbol")
            .alias("volume_ratio")
        ])

        # Mark as halt if gap > threshold AND volume explosion
        df = df.with_columns([
            (
                (pl.col("gap_pct") > self.extreme_gap_threshold) &
                (pl.col("volume_ratio") > self.volume_explosion_multiplier)
            ).alias("halt_extreme_gap")
        ])

        return df

    def detect_flat_sequence(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Pattern 3: Sequence of 3+ consecutive flat candles (high == low)

        Args:
            df: DataFrame with OHLCV columns

        Returns:
            DataFrame with 'halt_flat_sequence' column
        """
        df = df.sort(["symbol", "timestamp"])

        # Mark flat candles
        df = df.with_columns([
            (pl.col("high") == pl.col("low")).alias("is_flat")
        ])

        # Count consecutive flat candles
        df = df.with_columns([
            pl.col("is_flat")
            .cast(pl.Int32)
            .rolling_sum(window_size=self.flat_candle_sequence_min, min_periods=self.flat_candle_sequence_min)
            .over("symbol")
            .alias("flat_count_window")
        ])

        # Mark as halt if 3+ consecutive flats
        df = df.with_columns([
            (pl.col("flat_count_window") >= self.flat_candle_sequence_min).alias("halt_flat_sequence")
        ])

        return df

    def detect_volume_drought(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Pattern 4: Sudden volume drought after high activity

        Args:
            df: DataFrame with volume column

        Returns:
            DataFrame with 'halt_volume_drought' column
        """
        df = df.sort(["symbol", "timestamp"])

        # Recent average volume (last 20 minutes)
        df = df.with_columns([
            pl.col("volume")
            .shift(1)  # Exclude current
            .rolling_mean(window_size=20, min_periods=5)
            .over("symbol")
            .alias("avg_volume_20m")
        ])

        # Drought if current volume < 10% of recent avg
        df = df.with_columns([
            (
                (pl.col("volume") < pl.col("avg_volume_20m") * self.volume_drought_ratio) &
                (pl.col("avg_volume_20m") > 0)  # Only if there was activity before
            ).alias("halt_volume_drought")
        ])

        return df

    def combine_heuristic_patterns(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Combine all heuristic patterns into single 'is_halt_like' flag.

        Args:
            df: DataFrame with all pattern columns

        Returns:
            DataFrame with 'is_halt_like' column
        """
        # Apply all pattern detectors
        df = self.detect_flat_zero_volume(df)
        df = self.detect_extreme_gap(df)
        df = self.detect_flat_sequence(df)
        df = self.detect_volume_drought(df)

        # Combine: any pattern triggers halt-like flag
        df = df.with_columns([
            (
                pl.col("halt_flat_zero") |
                pl.col("halt_extreme_gap") |
                pl.col("halt_flat_sequence") |
                pl.col("halt_volume_drought")
            ).alias("is_halt_like")
        ])

        return df

    def load_official_halts(self, date: str = None) -> Optional[pl.DataFrame]:
        """
        Load official halt data from FINRA/NASDAQ for a specific date.

        Args:
            date: Date string (YYYYMMDD), defaults to today

        Returns:
            DataFrame with halt data or None if not found
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        base_dir = Path(__file__).resolve().parents[2]
        halt_file = base_dir / "raw" / "reference" / f"trading_halts_{date}.parquet"

        if not halt_file.exists():
            logger.warning(f"Official halt data not found: {halt_file}")
            return None

        df = pl.read_parquet(halt_file)
        logger.info(f"Loaded {len(df)} official halts from {halt_file}")

        return df

    def mark_official_halts(self, bars_df: pl.DataFrame, halts_df: pl.DataFrame) -> pl.DataFrame:
        """
        Mark bars that occur during official trading halts.

        Args:
            bars_df: DataFrame with 1-minute bars (symbol, timestamp, ...)
            halts_df: DataFrame with official halts (symbol, halt_timestamp, resume_timestamp)

        Returns:
            DataFrame with 'is_official_halt' column
        """
        if halts_df is None or len(halts_df) == 0:
            bars_df = bars_df.with_columns([
                pl.lit(False).alias("is_official_halt")
            ])
            return bars_df

        # Join bars with halts
        # For each bar, check if timestamp falls within any halt window for that symbol

        # Approach: Cross join + filter (inefficient but clear)
        # Better approach for production: interval tree or rolling join

        bars_with_halts = []

        for symbol in bars_df["symbol"].unique().to_list():
            symbol_bars = bars_df.filter(pl.col("symbol") == symbol)
            symbol_halts = halts_df.filter(pl.col("symbol") == symbol)

            if len(symbol_halts) == 0:
                # No halts for this symbol
                symbol_bars = symbol_bars.with_columns([
                    pl.lit(False).alias("is_official_halt")
                ])
                bars_with_halts.append(symbol_bars)
                continue

            # Check each bar against all halt windows
            def is_in_halt_window(ts, halt_times):
                for halt_start, halt_end in halt_times:
                    if halt_start <= ts <= halt_end:
                        return True
                return False

            halt_windows = [
                (row["halt_timestamp"], row["resume_timestamp"] or row["halt_timestamp"] + timedelta(hours=1))
                for row in symbol_halts.iter_rows(named=True)
            ]

            symbol_bars = symbol_bars.with_columns([
                pl.col("timestamp")
                .map_elements(lambda ts: is_in_halt_window(ts, halt_windows), return_dtype=pl.Boolean)
                .alias("is_official_halt")
            ])

            bars_with_halts.append(symbol_bars)

        result = pl.concat(bars_with_halts)
        logger.info(f"Marked {result['is_official_halt'].sum()} bars as official halts")

        return result

    def propagate_halt_window(self, df: pl.DataFrame, window_minutes: int = None) -> pl.DataFrame:
        """
        Propagate halt flag ±N minutes around halt detection.

        Args:
            df: DataFrame with 'is_halt_like' or 'is_official_halt' column
            window_minutes: Minutes before/after to mark as halt window (default from config)

        Returns:
            DataFrame with 'halt_window' column
        """
        if window_minutes is None:
            window_minutes = self.halt_window_minutes

        df = df.sort(["symbol", "timestamp"])

        # Combine official and heuristic halts
        halt_col = "is_halt_combined"
        if "is_official_halt" in df.columns and "is_halt_like" in df.columns:
            df = df.with_columns([
                (pl.col("is_official_halt") | pl.col("is_halt_like")).alias(halt_col)
            ])
        elif "is_official_halt" in df.columns:
            halt_col = "is_official_halt"
        elif "is_halt_like" in df.columns:
            halt_col = "is_halt_like"
        else:
            raise ValueError("DataFrame must have 'is_official_halt' or 'is_halt_like' column")

        # Propagate forward and backward
        df = df.with_columns([
            pl.col(halt_col)
            .rolling_max(window_size=window_minutes, min_periods=1)
            .over("symbol")
            .alias("halt_window_forward")
        ])

        # Backward propagation (shift negative)
        df = df.with_columns([
            pl.col(halt_col)
            .shift(-window_minutes)
            .rolling_max(window_size=window_minutes, min_periods=1)
            .over("symbol")
            .alias("halt_window_backward")
        ])

        # Combine
        df = df.with_columns([
            (pl.col("halt_window_forward") | pl.col("halt_window_backward")).alias("halt_window")
        ])

        return df

    def detect_all_halts(
        self,
        bars_df: pl.DataFrame,
        official_halts_df: Optional[pl.DataFrame] = None,
        propagate_window: bool = True
    ) -> pl.DataFrame:
        """
        Main method: Detect all halts (official + heuristic) and propagate window.

        Args:
            bars_df: DataFrame with 1-minute bars (symbol, timestamp, OHLCV)
            official_halts_df: Optional DataFrame with official halt data
            propagate_window: If True, create ±15min halt_window

        Returns:
            DataFrame with halt flags:
                - is_halt_like (heuristic detection)
                - is_official_halt (from FINRA data)
                - halt_window (±15min around any halt)
        """
        logger.info(f"Detecting halts in {len(bars_df)} bars across {bars_df['symbol'].n_unique()} symbols")

        # Step 1: Heuristic detection
        bars_df = self.combine_heuristic_patterns(bars_df)

        heuristic_halts = bars_df["is_halt_like"].sum()
        logger.info(f"Heuristic detection: {heuristic_halts} halt-like bars")

        # Step 2: Official halts
        if official_halts_df is not None:
            bars_df = self.mark_official_halts(bars_df, official_halts_df)
            official_halts_count = bars_df["is_official_halt"].sum()
            logger.info(f"Official halts: {official_halts_count} bars")
        else:
            bars_df = bars_df.with_columns([
                pl.lit(False).alias("is_official_halt")
            ])

        # Step 3: Propagate window
        if propagate_window:
            bars_df = self.propagate_halt_window(bars_df)
            halt_window_count = bars_df["halt_window"].sum()
            logger.info(f"Halt window (±{self.halt_window_minutes}min): {halt_window_count} bars")

        return bars_df


def example_usage():
    """Example usage with synthetic data"""
    from datetime import datetime, timedelta
    import polars as pl

    # Generate synthetic bars with simulated halt
    base_time = datetime(2025, 10, 10, 10, 0)
    data = []

    for i in range(60):  # 1 hour of data
        ts = base_time + timedelta(minutes=i)

        # Simulate halt at minute 30-35 (5 minute halt)
        if 30 <= i < 35:
            # Flat candle with zero volume (halt pattern)
            volume = 0
            open_price = close_price = high_price = low_price = 10.0
        else:
            volume = 100000 if i < 30 else 50000
            open_price = 10.0
            close_price = 10.1
            high_price = 10.2
            low_price = 9.9

        data.append({
            "symbol": "TEST",
            "timestamp": ts,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume
        })

    bars_df = pl.DataFrame(data)

    # Detect halts
    detector = HaltDetector()
    result = detector.detect_all_halts(bars_df, official_halts_df=None)

    print("\n=== Halt Detection Example ===")
    print(result.select([
        "timestamp", "volume", "is_halt_like", "halt_window"
    ]).filter(pl.col("halt_window")))


if __name__ == "__main__":
    example_usage()
