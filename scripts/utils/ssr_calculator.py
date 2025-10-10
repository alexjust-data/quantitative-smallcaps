"""
SSR (Short Sale Restriction) Calculator

Implementa Reg SHO Rule 201: detección de SSR triggers y propagación.

SSR se activa cuando:
- El precio cae ≥10% vs cierre previo oficial durante RTH
- Permanece activo el resto del día + el siguiente día bursátil completo

Referencias:
- SEC Reg SHO: https://www.sec.gov/divisions/marketreg/rule201faq.htm
"""

from datetime import datetime, timedelta
from pathlib import Path
import polars as pl
import yaml


class SSRCalculator:
    """Calcula SSR triggers según Reg SHO Rule 201"""

    def __init__(self, config_path: Path = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parents[2] / "config" / "liquidity_filters.yaml"

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.ssr_config = config["event_detection"]["ssr"]
        self.sessions = config["general"]["sessions"]

        self.trigger_drop_pct = self.ssr_config["trigger_drop_pct"] / 100.0  # -10% → -0.10
        self.apply_next_day = self.ssr_config["apply_next_day"]
        self.only_rth_trigger = self.ssr_config["only_rth_trigger"]

    def is_rth(self, timestamp: datetime) -> bool:
        """Check if timestamp is during Regular Trading Hours"""
        time_str = timestamp.strftime("%H:%M")
        return self.sessions["rth_start"] <= time_str < self.sessions["rth_end"]

    def detect_ssr_triggers(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Detecta triggers de SSR en DataFrame de barras intradía.

        Args:
            df: DataFrame con columnas: symbol, timestamp, close, date, previous_close

        Returns:
            DataFrame con columnas adicionales:
                - ssr_triggered: bool (si se disparó SSR en este minuto)
                - ssr_active: bool (si SSR está activo en este minuto)
                - ssr_trigger_time: datetime (cuándo se disparó)
                - drop_vs_prev_close_pct: float (% caída vs cierre previo)
        """
        # Asegurar que hay columna previous_close
        if "previous_close" not in df.columns:
            # Asumir que viene de daily data y hacemos self-join
            daily = df.group_by(["symbol", "date"]).agg([
                pl.col("close").last().alias("close_of_day")
            ]).sort(["symbol", "date"])

            daily = daily.with_columns([
                pl.col("close_of_day").shift(1).over("symbol").alias("previous_close")
            ])

            df = df.join(daily.select(["symbol", "date", "previous_close"]), on=["symbol", "date"], how="left")

        # Calcular % drop vs previous_close
        df = df.with_columns([
            ((pl.col("close") - pl.col("previous_close")) / pl.col("previous_close")).alias("drop_vs_prev_close_pct")
        ])

        # Detectar triggers
        if self.only_rth_trigger:
            # Solo triggers en RTH
            df = df.with_columns([
                pl.when(
                    (pl.col("drop_vs_prev_close_pct") <= -self.trigger_drop_pct) &
                    (pl.col("timestamp").dt.hour() >= 9) &
                    (pl.col("timestamp").dt.hour() < 16) &
                    ~((pl.col("timestamp").dt.hour() == 9) & (pl.col("timestamp").dt.minute() < 30))
                ).then(True).otherwise(False).alias("ssr_triggered")
            ])
        else:
            # Triggers en cualquier sesión
            df = df.with_columns([
                (pl.col("drop_vs_prev_close_pct") <= -self.trigger_drop_pct).alias("ssr_triggered")
            ])

        # Propagar SSR: activo desde trigger hasta final del día + día siguiente
        df = df.sort(["symbol", "timestamp"])

        # Identificar primer trigger por símbolo/día
        df = df.with_columns([
            pl.when(pl.col("ssr_triggered"))
            .then(pl.col("timestamp"))
            .otherwise(None)
            .forward_fill()
            .over("symbol")
            .alias("ssr_trigger_time")
        ])

        # SSR activo si:
        # 1. Hay trigger_time definido
        # 2. timestamp >= trigger_time
        # 3. timestamp <= trigger_time + 1 día bursátil (si apply_next_day)
        if self.apply_next_day:
            # SSR vigente resto del día + día siguiente
            df = df.with_columns([
                pl.when(pl.col("ssr_trigger_time").is_not_null())
                .then(
                    (pl.col("timestamp") >= pl.col("ssr_trigger_time")) &
                    (pl.col("timestamp") <= pl.col("ssr_trigger_time") + pl.duration(days=2))
                )
                .otherwise(False)
                .alias("ssr_active")
            ])
        else:
            # SSR solo resto del día
            df = df.with_columns([
                pl.when(pl.col("ssr_trigger_time").is_not_null())
                .then(
                    (pl.col("timestamp") >= pl.col("ssr_trigger_time")) &
                    (pl.col("date") == pl.col("ssr_trigger_time").dt.date())
                )
                .otherwise(False)
                .alias("ssr_active")
            ])

        return df

    def add_ssr_to_daily(self, daily_df: pl.DataFrame) -> pl.DataFrame:
        """
        Añade flag SSR a DataFrame de barras diarias.

        Args:
            daily_df: DataFrame con columnas: symbol, date, close, low

        Returns:
            DataFrame con columnas adicionales: ssr_triggered, ssr_active_next_day
        """
        # Calcular previous_close
        daily_df = daily_df.sort(["symbol", "date"]).with_columns([
            pl.col("close").shift(1).over("symbol").alias("previous_close")
        ])

        # Detectar si low del día tocó -10% vs previous_close
        daily_df = daily_df.with_columns([
            ((pl.col("low") - pl.col("previous_close")) / pl.col("previous_close")).alias("low_vs_prev_pct"),
            (pl.col("low") <= pl.col("previous_close") * (1 - self.trigger_drop_pct)).alias("ssr_triggered")
        ])

        # SSR activo al día siguiente
        if self.apply_next_day:
            daily_df = daily_df.with_columns([
                pl.col("ssr_triggered").shift(-1).over("symbol").fill_null(False).alias("ssr_active_next_day")
            ])

        return daily_df


def example_usage():
    """Ejemplo de uso con datos sintéticos"""
    import polars as pl
    from datetime import datetime, timedelta

    # Datos sintéticos: AAPL con caída de -12% el 2025-10-10 a las 10:15
    data = []
    base_date = datetime(2025, 10, 10, 9, 30)
    prev_close = 150.0

    for i in range(120):  # 2 horas de datos
        ts = base_date + timedelta(minutes=i)

        # Simular caída a las 10:15 (45 minutos después)
        if i < 45:
            price = prev_close - (i * 0.5)  # Caída gradual
        elif i == 45:
            price = prev_close * 0.88  # -12% trigger
        else:
            price = prev_close * 0.89  # Recupera ligeramente

        data.append({
            "symbol": "AAPL",
            "timestamp": ts,
            "date": ts.date(),
            "close": price,
            "previous_close": prev_close
        })

    df = pl.DataFrame(data)

    # Calcular SSR
    calc = SSRCalculator()
    df_ssr = calc.detect_ssr_triggers(df)

    print("\n=== SSR Detection Example ===")
    print(df_ssr.filter(pl.col("ssr_triggered") | pl.col("ssr_active")).select([
        "timestamp", "close", "drop_vs_prev_close_pct", "ssr_triggered", "ssr_active"
    ]))


if __name__ == "__main__":
    example_usage()
