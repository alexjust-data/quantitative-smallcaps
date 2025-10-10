"""
Liquidity Filters (Nivel 1)

Filtros de liquidez para event detection que validan ejecutabilidad real.

Implementa:
- Dollar volume contextual (RTH vs premarket, penny stocks)
- Spread proxy winsorizado con detección de wicks
- RVOL (daily + intradía con estacionalidad)
- Continuidad temporal (% minutos activos)
- Integración con SSR calculator
- Detección de trading halts (heurística + FINRA)
"""

from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
import polars as pl
import yaml
import numpy as np
from .halt_detector import HaltDetector


class LiquidityFilter:
    """Filtros de liquidez para validar eventos tradeable"""

    def __init__(self, config_path: Path = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parents[2] / "config" / "liquidity_filters.yaml"

        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.event_cfg = self.config["event_detection"]
        self.sessions = self.config["general"]["sessions"]

        # Umbrales
        self.dv_premarket = self.event_cfg["min_dollar_volume"]["premarket"]
        self.dv_postmarket = self.event_cfg["min_dollar_volume"]["postmarket"]
        self.dv_rth = self.event_cfg["min_dollar_volume"]["rth"]
        self.dv_rth_low_price = self.event_cfg["min_dollar_volume"]["rth_low_price"]

        self.spread_window = self.event_cfg["spread_proxy"]["window_minutes"]
        self.spread_percentile = self.event_cfg["spread_proxy"]["percentile_winsor"]
        self.max_spread = self.event_cfg["spread_proxy"]["max_spread_pct"]
        self.zscore_method = self.event_cfg["spread_proxy"]["zscore_method"]

        self.min_body_ratio = self.event_cfg["wick_detection"]["min_body_ratio"]

        self.rvol_daily_lookback = self.event_cfg["rvol"]["daily_lookback_days"]
        self.rvol_intra_lookback = self.event_cfg["rvol"]["intraday_lookback_days"]
        self.min_rvol = self.event_cfg["rvol"]["min_rvol_threshold"]

        self.continuity_window = self.event_cfg["continuity"]["window_minutes"]
        self.min_continuity = self.event_cfg["continuity"]["min_active_ratio"]

        self.min_price = self.event_cfg["price_range"]["min_price"]
        self.max_price = self.event_cfg["price_range"]["max_price"]
        self.low_price_threshold = self.event_cfg["price_range"]["low_price_threshold"]

        # Initialize halt detector
        self.halt_detector = HaltDetector(config_path)

    def get_session(self, timestamp: datetime) -> str:
        """Determina sesión (premarket, rth, postmarket)"""
        time_str = timestamp.strftime("%H:%M")

        if self.sessions["premarket_start"] <= time_str < self.sessions["premarket_end"]:
            return "premarket"
        elif self.sessions["rth_start"] <= time_str < self.sessions["rth_end"]:
            return "rth"
        elif self.sessions["postmarket_start"] <= time_str < self.sessions["postmarket_end"]:
            return "postmarket"
        else:
            return "unknown"

    def compute_dollar_volume_filter(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Añade columna dollar_volume_pass según sesión y precio.

        Requires: symbol, timestamp, volume, vwap, close
        Adds: dollar_volume, session, dollar_volume_pass
        """
        # Calcular dollar_volume
        df = df.with_columns([
            (pl.col("volume") * pl.col("vwap")).alias("dollar_volume")
        ])

        # Detectar sesión (requiere timestamp como datetime)
        df = df.with_columns([
            pl.col("timestamp").map_elements(
                lambda ts: self.get_session(ts),
                return_dtype=pl.Utf8
            ).alias("session")
        ])

        # Umbral dinámico según sesión y precio
        df = df.with_columns([
            pl.when(pl.col("session") == "premarket")
            .then(pl.lit(self.dv_premarket))
            .when(pl.col("session") == "postmarket")
            .then(pl.lit(self.dv_postmarket))
            .when((pl.col("session") == "rth") & (pl.col("close") < self.low_price_threshold))
            .then(pl.lit(self.dv_rth_low_price))
            .otherwise(pl.lit(self.dv_rth))
            .alias("dv_threshold")
        ])

        # Aplicar filtro
        df = df.with_columns([
            (pl.col("dollar_volume") >= pl.col("dv_threshold")).alias("dollar_volume_pass")
        ])

        return df

    def compute_spread_proxy(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calcula spread proxy winsorizado con detección de wicks.

        Requires: symbol, timestamp, high, low, vwap, open, close
        Adds: spread_proxy_raw, spread_proxy_p95, body_ratio, is_wicky, spread_pass
        """
        # Spread raw (full range)
        df = df.with_columns([
            ((pl.col("high") - pl.col("low")) / pl.col("vwap")).alias("spread_proxy_raw")
        ])

        # Body ratio (resistente a wicks)
        df = df.with_columns([
            (abs(pl.col("close") - pl.col("open")) / (pl.col("high") - pl.col("low") + 1e-9)).alias("body_ratio")
        ])

        # Winsorizar p95 sobre ventana de 10 minutos
        df = df.sort(["symbol", "timestamp"]).with_columns([
            pl.col("spread_proxy_raw")
            .rolling_quantile(
                quantile=self.spread_percentile / 100.0,
                window_size=self.spread_window,
                min_periods=1
            )
            .over("symbol")
            .alias("spread_proxy_p95")
        ])

        # Detectar wicks (spread alto pero body pequeño)
        df = df.with_columns([
            ((pl.col("spread_proxy_p95") > self.max_spread) &
             (pl.col("body_ratio") < self.min_body_ratio)).alias("is_wicky")
        ])

        # Filtro: pasar si spread < threshold o no es wicky
        df = df.with_columns([
            ((pl.col("spread_proxy_p95") <= self.max_spread) | ~pl.col("is_wicky")).alias("spread_pass")
        ])

        return df

    def compute_rvol_daily(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calcula RVOL diario (volumen día / avg últimos 20 días).

        Requires: symbol, date, volume (agregado por día)
        Adds: avg_volume_20d, rvol_daily, rvol_daily_pass
        """
        # Asegurar ordenamiento
        df = df.sort(["symbol", "date"])

        # Promedio de volumen 20 días (excluyendo día actual)
        df = df.with_columns([
            pl.col("volume")
            .shift(1)
            .rolling_mean(window_size=self.rvol_daily_lookback, min_periods=5)
            .over("symbol")
            .alias("avg_volume_20d")
        ])

        # RVOL
        df = df.with_columns([
            (pl.col("volume") / (pl.col("avg_volume_20d") + 1e-9)).alias("rvol_daily")
        ])

        # Filtro
        df = df.with_columns([
            (pl.col("rvol_daily") >= self.min_rvol).alias("rvol_daily_pass")
        ])

        return df

    def compute_rvol_intraday(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calcula RVOL intradía con estacionalidad (volumen minuto vs avg del mismo minuto).

        Requires: symbol, timestamp, volume, date
        Adds: hour, minute, avg_volume_same_minute_60d, rvol_intraday, rvol_intraday_pass
        """
        # Extraer hora y minuto
        df = df.with_columns([
            pl.col("timestamp").dt.hour().alias("hour"),
            pl.col("timestamp").dt.minute().alias("minute")
        ])

        # Calcular baseline por (symbol, hour, minute) excluyendo día actual
        # Esto requiere lookback de 60 días
        df = df.sort(["symbol", "date", "timestamp"])

        # NOTA: Esta lógica requiere group_by complejo.
        # Por simplicidad, usamos rolling sobre días previos filtrados.
        # En producción, esto debería ser un join con tabla pre-calculada.

        # Simplificación: promedio móvil de 60 días del mismo (hour, minute)
        # Requiere datos históricos suficientes

        # Para implementación completa, necesitaríamos:
        # 1. Group by (symbol, hour, minute)
        # 2. Rolling mean de 60 observaciones excluyendo fecha actual
        # 3. Join de vuelta al df principal

        # Por ahora, usamos proxy: rolling mean de volumen sobre 60 barras
        df = df.with_columns([
            pl.col("volume")
            .shift(1)
            .rolling_mean(window_size=60, min_periods=10)
            .over("symbol")
            .alias("avg_volume_same_minute_60d")
        ])

        df = df.with_columns([
            (pl.col("volume") / (pl.col("avg_volume_same_minute_60d") + 1e-9)).alias("rvol_intraday")
        ])

        df = df.with_columns([
            (pl.col("rvol_intraday") >= self.min_rvol).alias("rvol_intraday_pass")
        ])

        return df

    def compute_continuity(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calcula continuidad temporal (% minutos con volumen > 0 en última hora).

        Requires: symbol, timestamp, volume
        Adds: active_minutes_ratio, continuity_pass
        """
        # Ventana de 1 hora hacia atrás
        window_seconds = self.continuity_window * 60

        df = df.sort(["symbol", "timestamp"])

        # Contar minutos con volumen > 0 en ventana
        df = df.with_columns([
            (pl.col("volume") > 0).cast(pl.Int32).alias("is_active")
        ])

        # Rolling sum sobre ventana
        df = df.with_columns([
            pl.col("is_active")
            .rolling_sum(window_size=self.continuity_window, min_periods=1)
            .over("symbol")
            .alias("active_minutes_count")
        ])

        # Ratio
        df = df.with_columns([
            (pl.col("active_minutes_count") / self.continuity_window).alias("active_minutes_ratio")
        ])

        # Filtro
        df = df.with_columns([
            (pl.col("active_minutes_ratio") >= self.min_continuity).alias("continuity_pass")
        ])

        return df

    def compute_price_filter(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Filtra por rango de precio.

        Requires: close
        Adds: price_pass
        """
        df = df.with_columns([
            ((pl.col("close") >= self.min_price) & (pl.col("close") <= self.max_price)).alias("price_pass")
        ])

        return df

    def apply_all_filters(
        self,
        df: pl.DataFrame,
        include_rvol_intraday: bool = False,
        include_halt_detection: bool = True,
        official_halts_df: Optional[pl.DataFrame] = None
    ) -> pl.DataFrame:
        """
        Aplica todos los filtros y añade columna liquidity_pass (AND de todos).

        Args:
            df: DataFrame con barras de 1 minuto
            include_rvol_intraday: Si True, incluye RVOL intradía (requiere más histórico)
            include_halt_detection: Si True, detecta trading halts
            official_halts_df: DataFrame opcional con halt data oficial de FINRA

        Returns:
            DataFrame con todas las columnas de filtros y liquidity_pass
        """
        df = self.compute_dollar_volume_filter(df)
        df = self.compute_spread_proxy(df)
        df = self.compute_continuity(df)
        df = self.compute_price_filter(df)

        # Halt detection
        if include_halt_detection:
            df = self.halt_detector.detect_all_halts(
                df,
                official_halts_df=official_halts_df,
                propagate_window=True
            )

            # Rechazar eventos en halt_window
            df = df.with_columns([
                (~pl.col("halt_window")).alias("halt_pass")
            ])
        else:
            df = df.with_columns([
                pl.lit(True).alias("halt_pass")
            ])

        if include_rvol_intraday:
            df = self.compute_rvol_intraday(df)
            df = df.with_columns([
                (
                    pl.col("dollar_volume_pass") &
                    pl.col("spread_pass") &
                    pl.col("continuity_pass") &
                    pl.col("price_pass") &
                    pl.col("rvol_intraday_pass") &
                    pl.col("halt_pass")
                ).alias("liquidity_pass")
            ])
        else:
            df = df.with_columns([
                (
                    pl.col("dollar_volume_pass") &
                    pl.col("spread_pass") &
                    pl.col("continuity_pass") &
                    pl.col("price_pass") &
                    pl.col("halt_pass")
                ).alias("liquidity_pass")
            ])

        return df

    def filter_events(
        self,
        df: pl.DataFrame,
        include_rvol_intraday: bool = False,
        include_halt_detection: bool = True,
        official_halts_df: Optional[pl.DataFrame] = None
    ) -> pl.DataFrame:
        """
        Aplica filtros y devuelve solo eventos que pasan liquidity_pass.

        Args:
            df: DataFrame con eventos candidatos
            include_rvol_intraday: Si True, usa RVOL intradía
            include_halt_detection: Si True, detecta trading halts
            official_halts_df: DataFrame opcional con halt data oficial

        Returns:
            DataFrame filtrado con solo eventos líquidos
        """
        df = self.apply_all_filters(
            df,
            include_rvol_intraday=include_rvol_intraday,
            include_halt_detection=include_halt_detection,
            official_halts_df=official_halts_df
        )

        passed = df.filter(pl.col("liquidity_pass"))
        rejected = df.filter(~pl.col("liquidity_pass"))

        if self.config["general"]["log_rejected_events"]:
            print(f"[LiquidityFilter] Total events: {len(df)}")
            print(f"[LiquidityFilter] Passed: {len(passed)} ({100*len(passed)/len(df):.1f}%)")
            print(f"[LiquidityFilter] Rejected: {len(rejected)} ({100*len(rejected)/len(df):.1f}%)")

            if len(rejected) > 0:
                print("\n[LiquidityFilter] Rejection breakdown:")
                print(f"  - Dollar volume: {(~rejected['dollar_volume_pass']).sum()}")
                print(f"  - Spread proxy: {(~rejected['spread_pass']).sum()}")
                print(f"  - Continuity: {(~rejected['continuity_pass']).sum()}")
                print(f"  - Price range: {(~rejected['price_pass']).sum()}")
                if "halt_pass" in rejected.columns:
                    print(f"  - Halt window: {(~rejected['halt_pass']).sum()}")

        return passed


def example_usage():
    """Ejemplo de uso con datos sintéticos"""
    from datetime import datetime, timedelta
    import polars as pl

    # Generar datos sintéticos
    base_time = datetime(2025, 10, 10, 9, 30)
    data = []

    for i in range(120):  # 2 horas
        ts = base_time + timedelta(minutes=i)

        # Simular evento líquido a las 10:00
        if 25 <= i <= 35:  # 10:00-10:10
            volume = 500000
            vwap = 5.0
        else:
            volume = 50000
            vwap = 5.0

        data.append({
            "symbol": "TEST",
            "timestamp": ts,
            "date": ts.date(),
            "volume": volume,
            "vwap": vwap,
            "open": vwap,
            "close": vwap + np.random.uniform(-0.1, 0.1),
            "high": vwap + abs(np.random.uniform(0, 0.2)),
            "low": vwap - abs(np.random.uniform(0, 0.2))
        })

    df = pl.DataFrame(data)

    # Aplicar filtros
    lf = LiquidityFilter()
    df_filtered = lf.filter_events(df)

    print("\n=== Liquidity Filter Example ===")
    print(df_filtered.select(["timestamp", "dollar_volume", "spread_proxy_p95", "liquidity_pass"]).head(20))


if __name__ == "__main__":
    example_usage()
