"""
Time Utilities

Funciones para manejo correcto de timestamps y conversiones de zona horaria.

Polygon.io devuelve timestamps en **Unix milliseconds (UTC)**. Los guardamos como:
- pl.Datetime con time_zone="UTC" en Polars
- ISO-8601 con 'Z' suffix en Parquet

Al comparar con sesiones de mercado (09:30-16:00 ET), SIEMPRE convertir a ET.

Referencias:
- NYSE/NASDAQ operating hours: 09:30-16:00 ET (14:30-21:00 UTC en horario estándar)
- Extended hours: 04:00-09:30 (premarket), 16:00-20:00 (postmarket) ET
- DST changes: Second Sunday March (EDT starts), First Sunday November (EST starts)
"""

from datetime import datetime, timezone
from typing import Union
import polars as pl
from zoneinfo import ZoneInfo

# US Eastern timezone (handles DST automatically)
ET = ZoneInfo("America/New_York")
UTC = timezone.utc


def to_market_time(ts: Union[datetime, pl.Expr]) -> Union[datetime, pl.Expr]:
    """
    Convert UTC timestamp to US Eastern Time (ET).

    Handles DST automatically:
    - EST (UTC-5): First Sunday November to Second Sunday March
    - EDT (UTC-4): Second Sunday March to First Sunday November

    Args:
        ts: UTC timestamp (datetime object or Polars expression)

    Returns:
        Timestamp in ET (same type as input)

    Examples:
        >>> # Python datetime
        >>> utc_time = datetime(2025, 1, 10, 14, 30, tzinfo=UTC)  # 14:30 UTC
        >>> et_time = to_market_time(utc_time)
        >>> print(et_time)  # 09:30 ET (EST, UTC-5)

        >>> # Polars expression
        >>> df = df.with_columns([
        >>>     to_market_time(pl.col("timestamp")).alias("timestamp_et")
        >>> ])
    """
    if isinstance(ts, pl.Expr):
        # Polars expression: convert time zone
        return ts.dt.convert_time_zone("America/New_York")
    elif isinstance(ts, datetime):
        # Python datetime: convert to ET
        if ts.tzinfo is None:
            # Assume UTC if naive
            ts = ts.replace(tzinfo=UTC)
        return ts.astimezone(ET)
    else:
        raise TypeError(f"Expected datetime or pl.Expr, got {type(ts)}")


def is_market_hours(ts_et: datetime, include_extended: bool = False) -> bool:
    """
    Check if timestamp falls within market hours (ET).

    Args:
        ts_et: Timestamp in ET timezone
        include_extended: If True, include premarket (04:00-09:30) and postmarket (16:00-20:00)

    Returns:
        True if within market hours

    Examples:
        >>> from datetime import datetime
        >>> ts = datetime(2025, 1, 10, 10, 30, tzinfo=ET)  # 10:30 ET
        >>> is_market_hours(ts)  # True (RTH)
        >>> is_market_hours(ts, include_extended=True)  # True
    """
    hour = ts_et.hour
    minute = ts_et.minute
    time_decimal = hour + minute / 60.0

    if include_extended:
        # Extended hours: 04:00-20:00 ET
        return 4.0 <= time_decimal < 20.0
    else:
        # Regular hours: 09:30-16:00 ET
        return 9.5 <= time_decimal < 16.0


def get_session(ts_et: datetime) -> str:
    """
    Get market session for timestamp in ET.

    Args:
        ts_et: Timestamp in ET timezone

    Returns:
        Session string: "premarket", "rth", "postmarket", or "closed"

    Examples:
        >>> ts = datetime(2025, 1, 10, 8, 0, tzinfo=ET)  # 08:00 ET
        >>> get_session(ts)  # "premarket"
    """
    hour = ts_et.hour
    minute = ts_et.minute
    time_decimal = hour + minute / 60.0

    if 4.0 <= time_decimal < 9.5:
        return "premarket"
    elif 9.5 <= time_decimal < 16.0:
        return "rth"
    elif 16.0 <= time_decimal < 20.0:
        return "postmarket"
    else:
        return "closed"


def add_market_time_columns(df: pl.DataFrame, timestamp_col: str = "timestamp") -> pl.DataFrame:
    """
    Add market time columns to DataFrame.

    Args:
        df: DataFrame with UTC timestamps
        timestamp_col: Name of timestamp column (default: "timestamp")

    Returns:
        DataFrame with additional columns:
            - timestamp_et: Timestamp in ET
            - hour_et: Hour in ET (0-23)
            - minute_et: Minute in ET (0-59)
            - session: Market session ("premarket", "rth", "postmarket", "closed")
            - is_market_hours: Boolean (True if in RTH)
            - is_extended_hours: Boolean (True if in pre/post market)

    Examples:
        >>> df = add_market_time_columns(df)
        >>> # Filter only RTH events
        >>> rth_events = df.filter(pl.col("session") == "rth")
    """
    # Convert to ET
    df = df.with_columns([
        to_market_time(pl.col(timestamp_col)).alias("timestamp_et")
    ])

    # Extract hour and minute in ET
    df = df.with_columns([
        pl.col("timestamp_et").dt.hour().alias("hour_et"),
        pl.col("timestamp_et").dt.minute().alias("minute_et")
    ])

    # Calculate time_decimal for session detection
    df = df.with_columns([
        (pl.col("hour_et") + pl.col("minute_et") / 60.0).alias("time_decimal_et")
    ])

    # Detect session
    df = df.with_columns([
        pl.when((pl.col("time_decimal_et") >= 4.0) & (pl.col("time_decimal_et") < 9.5))
        .then(pl.lit("premarket"))
        .when((pl.col("time_decimal_et") >= 9.5) & (pl.col("time_decimal_et") < 16.0))
        .then(pl.lit("rth"))
        .when((pl.col("time_decimal_et") >= 16.0) & (pl.col("time_decimal_et") < 20.0))
        .then(pl.lit("postmarket"))
        .otherwise(pl.lit("closed"))
        .alias("session")
    ])

    # Boolean flags
    df = df.with_columns([
        (pl.col("session") == "rth").alias("is_market_hours"),
        (pl.col("session").is_in(["premarket", "postmarket", "rth"])).alias("is_extended_hours")
    ])

    return df


def example_usage():
    """Example usage of time utilities"""
    import polars as pl
    from datetime import datetime, timezone

    # Create sample data with UTC timestamps
    data = {
        "symbol": ["AAPL"] * 5,
        "timestamp": [
            datetime(2025, 1, 10, 13, 0, tzinfo=timezone.utc),  # 08:00 ET (premarket)
            datetime(2025, 1, 10, 14, 30, tzinfo=timezone.utc),  # 09:30 ET (RTH open)
            datetime(2025, 1, 10, 15, 0, tzinfo=timezone.utc),  # 10:00 ET (RTH)
            datetime(2025, 1, 10, 20, 59, tzinfo=timezone.utc),  # 15:59 ET (RTH close)
            datetime(2025, 1, 10, 21, 30, tzinfo=timezone.utc),  # 16:30 ET (postmarket)
        ],
        "price": [150.0, 151.0, 152.0, 153.0, 152.5]
    }

    df = pl.DataFrame(data)

    print("\n=== Original data (UTC) ===")
    print(df)

    # Add market time columns
    df = add_market_time_columns(df)

    print("\n=== With market time columns ===")
    print(df.select([
        "symbol", "timestamp", "timestamp_et", "hour_et", "minute_et", "session", "is_market_hours"
    ]))

    # Filter RTH only
    rth_only = df.filter(pl.col("session") == "rth")
    print("\n=== RTH only ===")
    print(rth_only.select(["symbol", "timestamp_et", "session", "price"]))


if __name__ == "__main__":
    example_usage()
