#!/usr/bin/env python
"""
FASE 2.5: Intraday Event Detection (Bidirectional - Long + Short setups)

Detecta eventos de microestructura sobre barras 1min:
- Volume Spike (explosión de volumen)
- VWAP Break (reclaim alcista / rejection bajista)
- Price Momentum (movimiento rápido precio)
- Consolidation Break (base plana → ruptura)
- Opening Range Break (solo RTH)
- Flush Detection (capitulation bajista)
- Tape Speed (velocidad trades - disabled hasta tener /trades)

Output: processed/events/events_intraday_YYYYMMDD.parquet
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, time
from typing import Literal
import yaml
import polars as pl
import numpy as np
from loguru import logger
from zoneinfo import ZoneInfo

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


class IntradayEventDetector:
    """Detector de eventos intraday sobre barras 1min (bidireccional)"""

    def __init__(self, config_path: Path = None):
        if config_path is None:
            config_path = PROJECT_ROOT / "config" / "config.yaml"

        with open(config_path, encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.cfg = self.config["processing"]["intraday_events"]
        self.tz = ZoneInfo("America/New_York")

        # Directorios
        self.raw_bars_dir = PROJECT_ROOT / "raw" / "market_data" / "bars" / "1m"
        self.output_dir = PROJECT_ROOT / "processed" / "events"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"IntradayEventDetector initialized (config: {config_path})")

    def classify_session(self, ts: datetime) -> Literal["PM", "RTH", "AH"]:
        """Clasifica timestamp en sesión (PM/RTH/AH)"""
        t = ts.time()
        pm_start = time.fromisoformat(self.cfg["session_bounds"]["premarket"][0])
        rth_start = time.fromisoformat(self.cfg["session_bounds"]["rth"][0])
        rth_end = time.fromisoformat(self.cfg["session_bounds"]["rth"][1])
        ah_end = time.fromisoformat(self.cfg["session_bounds"]["afterhours"][1])

        if pm_start <= t < rth_start:
            return "PM"
        elif rth_start <= t < rth_end:
            return "RTH"
        elif rth_end <= t < ah_end:
            return "AH"
        else:
            return "RTH"  # Default fallback

    def calculate_vwap(self, df: pl.DataFrame, anchor: str = "RTH") -> pl.DataFrame:
        """
        Calcula VWAP (anchored a sesión RTH o full day)

        Args:
            df: DataFrame con barras 1min (OHLCV + timestamp)
            anchor: "RTH" (reset 09:30) o "DAY" (reset 04:00)
        """
        df = df.with_columns([
            ((pl.col("high") + pl.col("low") + pl.col("close")) / 3).alias("typical_price"),
            (pl.col("volume") * ((pl.col("high") + pl.col("low") + pl.col("close")) / 3)).alias("tp_volume")
        ])

        if anchor == "RTH":
            # Anchor a 09:30 (reset VWAP en apertura RTH)
            rth_start_time = time(9, 30)
            df = df.with_columns([
                (pl.col("timestamp").dt.time() >= rth_start_time).alias("is_rth_or_after")
            ])

            # Reset cumsum en el primer bar de RTH
            df = df.with_columns([
                pl.when(pl.col("is_rth_or_after"))
                .then(pl.col("tp_volume").cum_sum().over(pl.col("is_rth_or_after").cum_sum()))
                .otherwise(pl.lit(None))
                .alias("cum_tp_volume"),

                pl.when(pl.col("is_rth_or_after"))
                .then(pl.col("volume").cum_sum().over(pl.col("is_rth_or_after").cum_sum()))
                .otherwise(pl.lit(None))
                .alias("cum_volume")
            ])
        else:
            # Full day VWAP
            df = df.with_columns([
                pl.col("tp_volume").cum_sum().alias("cum_tp_volume"),
                pl.col("volume").cum_sum().alias("cum_volume")
            ])

        df = df.with_columns([
            (pl.col("cum_tp_volume") / pl.col("cum_volume")).alias("vwap")
        ])

        return df.drop(["typical_price", "tp_volume", "cum_tp_volume", "cum_volume"])

    def detect_volume_spike(self, df: pl.DataFrame) -> pl.DataFrame:
        """DETECTOR 1: Volume Spike"""
        cfg = self.cfg["volume_spike"]
        if not cfg["enable"]:
            return pl.DataFrame()

        window = cfg["rolling_window_minutes"]
        method = cfg["rolling_method"]

        # Rolling baseline (median or mean)
        if method == "median":
            df = df.with_columns([
                pl.col("volume").rolling_median(window, min_samples=1).alias("vol_baseline")
            ])
        else:
            df = df.with_columns([
                pl.col("volume").rolling_mean(window, min_samples=1).alias("vol_baseline")
            ])

        df = df.with_columns([
            (pl.col("volume") / pl.col("vol_baseline")).alias("spike_x"),
            ((pl.col("high") - pl.col("low")) / pl.col("open") * 100).alias("range_pct"),
            (pl.col("volume") * pl.col("close")).alias("dollar_volume"),
            pl.col("timestamp").map_elements(lambda x: self.classify_session(x), return_dtype=pl.Utf8).alias("session")
        ])

        # Filtros por sesión
        rth_min_spike = cfg["rth"]["min_spike"]
        rth_min_vol = cfg["rth"]["min_absolute_volume"]
        rth_min_dv = cfg["rth"]["min_dollar_volume"]

        pm_ah_min_spike = cfg["pm_ah"]["min_spike"]
        pm_ah_min_vol = cfg["pm_ah"]["min_absolute_volume"]
        pm_ah_min_dv = cfg["pm_ah"]["min_dollar_volume"]

        events = df.filter(
            (
                ((pl.col("session") == "RTH") & (pl.col("spike_x") >= rth_min_spike) &
                 (pl.col("volume") >= rth_min_vol) & (pl.col("dollar_volume") >= rth_min_dv))
                |
                ((pl.col("session").is_in(["PM", "AH"])) & (pl.col("spike_x") >= pm_ah_min_spike) &
                 (pl.col("volume") >= pm_ah_min_vol) & (pl.col("dollar_volume") >= pm_ah_min_dv))
            )
            & (pl.col("range_pct") >= cfg["min_range_1m_pct"])
        )

        if events.is_empty():
            return pl.DataFrame()

        # Determinar dirección (alcista si close > open, bajista si close < open)
        events = events.with_columns([
            pl.when(pl.col("close") > pl.col("open"))
            .then(pl.lit("up"))
            .otherwise(pl.lit("down"))
            .alias("direction")
        ])

        # Confirmación bajista adicional
        if cfg.get("bearish_confirmation"):
            # TODO: Implementar consecutive red bars check (requiere window context)
            pass

        events = events.with_columns([
            pl.lit("volume_spike").alias("event_type"),
            pl.lit(None, dtype=pl.Float64).alias("score")
        ])

        logger.info(f"Volume spikes detected: {len(events)}")
        return events.select(["symbol", "timestamp", "event_type", "direction", "session", "spike_x",
                               "open", "high", "low", "close", "volume", "dollar_volume", "score"])

    def detect_vwap_break(self, df: pl.DataFrame) -> pl.DataFrame:
        """DETECTOR 2: VWAP Break"""
        cfg = self.cfg["vwap_break"]
        if not cfg["enable"]:
            return pl.DataFrame()

        # Calcular VWAP
        df = self.calculate_vwap(df, anchor=cfg["vwap_reference"])

        if df["vwap"].null_count() == len(df):
            return pl.DataFrame()

        # Rolling volume para confirmación (separado en 2 pasos para scope)
        df = df.with_columns([
            pl.col("volume").rolling_mean(20, min_samples=1).alias("vol_avg_20m"),
            ((pl.col("close") - pl.col("vwap")) / pl.col("vwap") * 100).alias("dist_from_vwap_pct")
        ])

        df = df.with_columns([
            (pl.col("volume") / pl.col("vol_avg_20m")).alias("vol_multiplier")
        ])

        # Bullish: price breaks above VWAP
        bull_cfg = cfg["bullish"]
        bullish_breaks = df.filter(
            (pl.col("dist_from_vwap_pct") >= bull_cfg["min_distance_pct"]) &
            (pl.col("vol_multiplier") >= bull_cfg["min_volume_confirm"]) &
            (pl.col("close") > pl.col("vwap"))
        )

        # Bearish: price breaks below VWAP (rejection)
        bear_cfg = cfg["bearish"]
        bearish_breaks = df.filter(
            (pl.col("dist_from_vwap_pct") <= -bear_cfg["min_distance_pct"]) &
            (pl.col("vol_multiplier") >= bear_cfg["min_volume_confirm"]) &
            (pl.col("close") < pl.col("vwap"))
        )

        # Combinar
        bullish_breaks = bullish_breaks.with_columns([pl.lit("up").alias("direction")])
        bearish_breaks = bearish_breaks.with_columns([pl.lit("down").alias("direction")])

        events = pl.concat([bullish_breaks, bearish_breaks])

        if events.is_empty():
            return pl.DataFrame()

        events = events.with_columns([
            pl.lit("vwap_break").alias("event_type"),
            pl.col("timestamp").map_elements(lambda x: self.classify_session(x), return_dtype=pl.Utf8).alias("session"),
            (pl.col("volume") * pl.col("close")).alias("dollar_volume"),
            pl.lit(None, dtype=pl.Float64).alias("score"),
            pl.col("dist_from_vwap_pct").abs().alias("spike_x")
        ])

        logger.info(f"VWAP breaks detected: {len(events)}")
        # Cast to Float64 for schema consistency
        events = events.with_columns([pl.col("spike_x").cast(pl.Float64)])
        return events.select(["symbol", "timestamp", "event_type", "direction", "session", "spike_x",
                               "open", "high", "low", "close", "volume", "dollar_volume", "score"])

    def detect_price_momentum(self, df: pl.DataFrame) -> pl.DataFrame:
        """DETECTOR 3: Price Momentum"""
        cfg = self.cfg["price_momentum"]
        if not cfg["enable"]:
            return pl.DataFrame()

        window = cfg["window_minutes"]

        # Returns en window_minutes (separado en 2 pasos para scope)
        df = df.with_columns([
            ((pl.col("close") / pl.col("close").shift(window) - 1) * 100).alias("ret_window"),
            pl.col("close").shift(window).alias("close_prev"),
            pl.col("high").rolling_max(20, min_samples=1).alias("high_20m"),
            pl.col("low").rolling_min(20, min_samples=1).alias("low_20m"),
            pl.col("volume").rolling_mean(20, min_samples=1).alias("vol_avg_20m")
        ])

        df = df.with_columns([
            (pl.col("volume") / pl.col("vol_avg_20m")).alias("vol_multiplier")
        ])

        # Bullish momentum
        bull_cfg = cfg["bullish"]
        bullish = df.filter(
            (pl.col("ret_window") >= bull_cfg["min_change_pct"]) &
            (pl.col("vol_multiplier") >= cfg["min_volume_multiplier"]) &
            (pl.col("close") > pl.col("high_20m"))  # Breakout requirement
        )

        # Bearish momentum
        bear_cfg = cfg["bearish"]
        bearish = df.filter(
            (pl.col("ret_window") <= -bear_cfg["min_change_pct"]) &
            (pl.col("vol_multiplier") >= cfg["min_volume_multiplier"]) &
            (pl.col("close") < pl.col("low_20m"))  # Breakdown requirement
        )

        bullish = bullish.with_columns([pl.lit("up").alias("direction")])
        bearish = bearish.with_columns([pl.lit("down").alias("direction")])

        events = pl.concat([bullish, bearish])

        if events.is_empty():
            return pl.DataFrame()

        events = events.with_columns([
            pl.lit("price_momentum").alias("event_type"),
            pl.col("timestamp").map_elements(lambda x: self.classify_session(x), return_dtype=pl.Utf8).alias("session"),
            (pl.col("volume") * pl.col("close")).alias("dollar_volume"),
            pl.col("ret_window").abs().alias("spike_x"),
            pl.lit(None, dtype=pl.Float64).alias("score")
        ])

        logger.info(f"Price momentum events detected: {len(events)}")
        # Cast to Float64 for schema consistency
        events = events.with_columns([pl.col("spike_x").cast(pl.Float64)])
        return events.select(["symbol", "timestamp", "event_type", "direction", "session", "spike_x",
                               "open", "high", "low", "close", "volume", "dollar_volume", "score"])

    def detect_consolidation_break(self, df: pl.DataFrame) -> pl.DataFrame:
        """DETECTOR 4: Consolidation Break"""
        cfg = self.cfg["consolidation_break"]
        if not cfg["enable"]:
            return pl.DataFrame()

        window = cfg["consolidation_window_minutes"]

        # Rango de consolidación (30min rolling) - separado en 2 pasos
        df = df.with_columns([
            pl.col("high").rolling_max(window, min_samples=1).alias("consol_high"),
            pl.col("low").rolling_min(window, min_samples=1).alias("consol_low"),
            pl.col("volume").rolling_mean(20, min_samples=1).alias("vol_avg_20m")
        ])

        df = df.with_columns([
            ((pl.col("consol_high") - pl.col("consol_low")) / pl.col("open") * 100).alias("consol_range_pct"),
            (pl.col("volume") / pl.col("vol_avg_20m")).alias("vol_spike")
        ])

        # ATR normalizado (aproximado con high-low) - separado en 2 pasos
        df = df.with_columns([
            ((pl.col("high") - pl.col("low")) / pl.col("open")).alias("bar_range_pct")
        ])

        df = df.with_columns([
            pl.col("bar_range_pct").rolling_median(30, min_samples=1).alias("atr_30m")
        ])

        max_consol_range = cfg["max_range_atr_multiple"]
        min_breakout = cfg["min_breakout_pct"]
        min_vol_spike = cfg["min_volume_spike"]

        # Consolidación: rango <= 0.5x ATR
        df = df.with_columns([
            (pl.col("consol_range_pct") <= (max_consol_range * pl.col("atr_30m") * 100)).alias("is_consolidating")
        ])

        # Breakouts: romper consol_high con volumen
        bullish = df.filter(
            (pl.col("is_consolidating").shift(1)) &
            (pl.col("close") > pl.col("consol_high").shift(1)) &
            (pl.col("vol_spike") >= min_vol_spike) &
            ((pl.col("close") - pl.col("consol_high").shift(1)) / pl.col("consol_high").shift(1) * 100 >= min_breakout)
        )

        # Breakdowns: romper consol_low con volumen
        bearish = df.filter(
            (pl.col("is_consolidating").shift(1)) &
            (pl.col("close") < pl.col("consol_low").shift(1)) &
            (pl.col("vol_spike") >= min_vol_spike) &
            ((pl.col("consol_low").shift(1) - pl.col("close")) / pl.col("consol_low").shift(1) * 100 >= min_breakout)
        )

        bullish = bullish.with_columns([pl.lit("up").alias("direction")])
        bearish = bearish.with_columns([pl.lit("down").alias("direction")])

        events = pl.concat([bullish, bearish])

        if events.is_empty():
            return pl.DataFrame()

        events = events.with_columns([
            pl.lit("consolidation_break").alias("event_type"),
            pl.col("timestamp").map_elements(lambda x: self.classify_session(x), return_dtype=pl.Utf8).alias("session"),
            (pl.col("volume") * pl.col("close")).alias("dollar_volume"),
            pl.lit(None, dtype=pl.Float64).alias("score")
        ])

        logger.info(f"Consolidation breaks detected: {len(events)}")
        # Cast to Float64 for schema consistency
        events = events.with_columns([pl.col("spike_x").cast(pl.Float64)])
        return events.select(["symbol", "timestamp", "event_type", "direction", "session", "spike_x",
                               "open", "high", "low", "close", "volume", "dollar_volume", "score"])

    def detect_opening_range_break(self, df: pl.DataFrame) -> pl.DataFrame:
        """DETECTOR 5: Opening Range Break (solo RTH)"""
        cfg = self.cfg["opening_range_break"]
        if not cfg["enable"]:
            return pl.DataFrame()

        or_duration = cfg["or_duration_minutes"]
        rth_start = time(9, 30)

        # Identificar barras de Opening Range (primeros 15min de RTH)
        df = df.with_columns([
            pl.col("timestamp").dt.time().alias("time"),
            ((pl.col("timestamp").dt.time() >= rth_start) &
             (pl.col("timestamp").dt.time() < time(9, 30 + or_duration))).alias("is_or_period")
        ])

        # Calcular OR high/low por día
        or_stats = df.filter(pl.col("is_or_period")).group_by(
            pl.col("timestamp").dt.date().alias("date")
        ).agg([
            pl.col("high").max().alias("or_high"),
            pl.col("low").min().alias("or_low")
        ])

        df = df.join(or_stats, left_on=pl.col("timestamp").dt.date(), right_on="date", how="left")

        # ORB alcista: romper or_high después del OR period
        bullish = df.filter(
            (~pl.col("is_or_period")) &
            (pl.col("timestamp").dt.time() < time(16, 0)) &
            (pl.col("close") > pl.col("or_high")) &
            ((pl.col("close") - pl.col("or_high")) / pl.col("or_high") * 100 >= cfg["min_breakout_pct"])
        )

        # ORB bajista: romper or_low
        bearish = df.filter(
            (~pl.col("is_or_period")) &
            (pl.col("timestamp").dt.time() < time(16, 0)) &
            (pl.col("close") < pl.col("or_low")) &
            ((pl.col("or_low") - pl.col("close")) / pl.col("or_low") * 100 >= cfg["min_breakout_pct"])
        )

        bullish = bullish.with_columns([pl.lit("up").alias("direction")])
        bearish = bearish.with_columns([pl.lit("down").alias("direction")])

        events = pl.concat([bullish, bearish])

        if events.is_empty():
            return pl.DataFrame()

        # Calcular métricas en 2 pasos para scope
        events = events.with_columns([
            pl.lit("opening_range_break").alias("event_type"),
            pl.lit("RTH").alias("session"),
            (pl.col("volume") * pl.col("close")).alias("dollar_volume"),
            pl.col("volume").rolling_mean(20, min_samples=1).over(pl.col("symbol")).alias("vol_avg")
        ])

        events = events.with_columns([
            (pl.col("volume") / pl.col("vol_avg")).alias("spike_x"),
            pl.lit(None, dtype=pl.Float64).alias("score")
        ])

        logger.info(f"Opening range breaks detected: {len(events)}")
        # Cast to Float64 for schema consistency
        events = events.with_columns([pl.col("spike_x").cast(pl.Float64)])
        return events.select(["symbol", "timestamp", "event_type", "direction", "session", "spike_x",
                               "open", "high", "low", "close", "volume", "dollar_volume", "score"])

    def detect_flush(self, df: pl.DataFrame) -> pl.DataFrame:
        """DETECTOR 7: Flush Detection"""
        cfg = self.cfg["flush_detection"]
        if not cfg["enable"]:
            return pl.DataFrame()

        window = cfg["window_minutes"]

        # High del día hasta ahora (rolling) - separado en 3 pasos para scope
        df = df.with_columns([
            pl.col("high").cum_max().over(pl.col("timestamp").dt.date()).alias("day_high"),
            pl.col("volume").rolling_mean(20, min_samples=1).alias("vol_avg_20m"),
            (pl.col("close") < pl.col("open")).alias("is_red_bar")
        ])

        df = df.with_columns([
            ((pl.col("day_high") - pl.col("close")) / pl.col("day_high") * 100).alias("drop_from_high_pct"),
            (pl.col("volume") / pl.col("vol_avg_20m")).alias("vol_spike")
        ])

        # Consecutive red bars (aproximación: rolling sum últimos 3 bars)
        df = df.with_columns([
            pl.col("is_red_bar").cast(pl.Int32).rolling_sum(3, min_samples=1).alias("red_bars_last3")
        ])

        events = df.filter(
            (pl.col("drop_from_high_pct") >= cfg["min_drop_pct"]) &
            (pl.col("vol_spike") >= cfg["min_volume_spike"]) &
            (pl.col("red_bars_last3") >= cfg["min_consecutive_red_bars"])
        )

        if events.is_empty():
            return pl.DataFrame()

        events = events.with_columns([
            pl.lit("flush").alias("event_type"),
            pl.lit("down").alias("direction"),
            pl.col("timestamp").map_elements(lambda x: self.classify_session(x), return_dtype=pl.Utf8).alias("session"),
            (pl.col("volume") * pl.col("close")).alias("dollar_volume"),
            pl.col("drop_from_high_pct").alias("spike_x"),
            pl.lit(None, dtype=pl.Float64).alias("score")
        ])

        logger.info(f"Flush events detected: {len(events)}")
        # Cast to Float64 for schema consistency
        events = events.with_columns([pl.col("spike_x").cast(pl.Float64)])
        return events.select(["symbol", "timestamp", "event_type", "direction", "session", "spike_x",
                               "open", "high", "low", "close", "volume", "dollar_volume", "score"])

    def deduplicate_events(self, events: pl.DataFrame) -> pl.DataFrame:
        """Deduplicación de eventos superpuestos"""
        cfg = self.cfg["deduplication"]
        if not cfg["enable"] or events.is_empty():
            return events

        # Calcular score composite
        weights = cfg["score_weights"]
        events = events.with_columns([
            (
                pl.col("spike_x").fill_null(0) * weights["volume_spike_magnitude"] +
                ((pl.col("high") - pl.col("low")) / pl.col("open") * 100).fill_null(0) * weights["price_change_magnitude"] +
                pl.lit(1.0) * weights["volume_confirm"]
            ).alias("score")
        ])

        # Deduplicación simple: keep highest score within 10min window per symbol
        window_sec = cfg["window_minutes"] * 60
        events = events.sort(["symbol", "timestamp", "score"], descending=[False, False, True])

        # Group consecutive events within window and keep highest score
        # (Simplified: keep one event per symbol per 10min bucket)
        events = events.with_columns([
            (pl.col("timestamp").cast(pl.Int64) // (window_sec * 1_000_000_000)).alias("time_bucket")
        ])

        events = events.group_by(["symbol", "time_bucket", "event_type"]).agg([
            pl.all().sort_by("score", descending=True).first()
        ])

        return events.drop("time_bucket")

    def process_symbol_date(self, symbol: str, date: str) -> pl.DataFrame:
        """Procesa un símbolo/fecha y detecta todos los eventos"""
        bars_file = self.raw_bars_dir / f"symbol={symbol}" / f"date={date}.parquet"

        if not bars_file.exists():
            logger.debug(f"No bars file for {symbol} {date}: {bars_file}")
            return pl.DataFrame()

        try:
            df_original = pl.read_parquet(bars_file)
        except Exception as e:
            logger.warning(f"Failed to read {bars_file}: {e}")
            return pl.DataFrame()

        if df_original.is_empty() or len(df_original) < 30:  # At least 30 bars (30min data)
            return pl.DataFrame()

        # Añadir symbol si no existe
        if "symbol" not in df_original.columns:
            df_original = df_original.with_columns([pl.lit(symbol).alias("symbol")])

        # Detectar eventos - cada detector recibe una copia fresca de las columnas base
        all_events = []
        base_cols = ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
        if "transactions" in df_original.columns:
            base_cols.append("transactions")

        try:
            df_clean = df_original.select(base_cols)
            events = self.detect_volume_spike(df_clean)
            if not events.is_empty():
                all_events.append(events)
        except Exception as e:
            logger.warning(f"Volume spike detection failed for {symbol} {date}: {e}")

        try:
            df_clean = df_original.select(base_cols)
            events = self.detect_vwap_break(df_clean)
            if not events.is_empty():
                all_events.append(events)
        except Exception as e:
            logger.warning(f"VWAP break detection failed for {symbol} {date}: {e}")

        try:
            df_clean = df_original.select(base_cols)
            events = self.detect_price_momentum(df_clean)
            if not events.is_empty():
                all_events.append(events)
        except Exception as e:
            logger.warning(f"Price momentum detection failed for {symbol} {date}: {e}")

        try:
            df_clean = df_original.select(base_cols)
            events = self.detect_consolidation_break(df_clean)
            if not events.is_empty():
                all_events.append(events)
        except Exception as e:
            logger.warning(f"Consolidation break detection failed for {symbol} {date}: {e}")

        try:
            df_clean = df_original.select(base_cols)
            events = self.detect_opening_range_break(df_clean)
            if not events.is_empty():
                all_events.append(events)
        except Exception as e:
            logger.warning(f"ORB detection failed for {symbol} {date}: {e}")

        try:
            df_clean = df_original.select(base_cols)
            events = self.detect_flush(df_clean)
            if not events.is_empty():
                all_events.append(events)
        except Exception as e:
            logger.warning(f"Flush detection failed for {symbol} {date}: {e}")

        if not all_events:
            return pl.DataFrame()

        # Concatenar todos los eventos
        combined = pl.concat(all_events, how="diagonal")

        # Deduplicar
        combined = self.deduplicate_events(combined)

        # Añadir metadata adicional
        combined = combined.with_columns([
            pl.col("timestamp").dt.date().alias("date"),
            pl.when(pl.col("direction") == "up")
            .then(pl.lit("bullish"))
            .otherwise(pl.lit("bearish"))
            .alias("event_bias"),

            pl.when(pl.col("close") > pl.col("open"))
            .then(pl.lit("green"))
            .otherwise(pl.lit("red"))
            .alias("close_vs_open"),

            pl.lit(1).alias("tier")  # TODO: Tiering based on intensity
        ])

        return combined

    def run(self, symbols: list[str], start_date: str, end_date: str):
        """Ejecuta detección para lista de símbolos y rango de fechas"""
        from datetime import datetime, timedelta

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        all_events = []
        date_range = []
        current = start
        while current <= end:
            date_range.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        logger.info(f"Processing {len(symbols)} symbols × {len(date_range)} dates = {len(symbols)*len(date_range)} symbol-dates")

        for symbol in symbols:
            symbol_events = []
            for date in date_range:
                events = self.process_symbol_date(symbol, date)
                if not events.is_empty():
                    symbol_events.append(events)

            if symbol_events:
                combined = pl.concat(symbol_events, how="diagonal")
                all_events.append(combined)
                logger.info(f"{symbol}: {len(combined)} events detected")

        if not all_events:
            logger.warning("No events detected")
            return None

        final = pl.concat(all_events, how="diagonal")

        # Sort por timestamp
        final = final.sort(["symbol", "timestamp"])

        # Save
        output_file = self.output_dir / f"events_intraday_{end_date.replace('-', '')}.parquet"
        final.write_parquet(output_file, compression="zstd")

        logger.info(f"✅ Saved {len(final)} intraday events to {output_file}")
        logger.info(f"\nDistribution by type:\n{final.group_by('event_type').len().sort('len', descending=True)}")
        logger.info(f"\nDistribution by direction:\n{final.group_by('direction').len()}")
        logger.info(f"\nDistribution by session:\n{final.group_by('session').len()}")

        return final


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Detect intraday events from 1min bars")
    parser.add_argument("--symbols", nargs="+", help="List of symbols (or use --from-file)")
    parser.add_argument("--from-file", help="Load symbols from parquet (e.g. events_daily)")
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--limit", type=int, help="Limit number of symbols (for testing)")

    args = parser.parse_args()

    detector = IntradayEventDetector()

    # Load symbols
    if args.from_file:
        df = pl.read_parquet(args.from_file)
        symbols = df["symbol"].unique().to_list()
        logger.info(f"Loaded {len(symbols)} unique symbols from {args.from_file}")
    elif args.symbols:
        symbols = args.symbols
    else:
        raise ValueError("Must provide --symbols or --from-file")

    if args.limit:
        symbols = symbols[:args.limit]
        logger.info(f"Limited to {len(symbols)} symbols")

    detector.run(symbols, args.start_date, args.end_date)


if __name__ == "__main__":
    main()
