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
import json
import gc
import psutil
import signal
from contextlib import contextmanager
import os
import uuid

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


class TimeoutError(Exception):
    """Raised when operation times out"""
    pass


@contextmanager
def timeout(seconds: int):
    """Context manager para timeout de operaciones (solo Unix/Linux)"""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds} seconds")

    # En Windows, signal.SIGALRM no existe, así que simplemente no hacemos nada
    if hasattr(signal, 'SIGALRM'):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # Windows: no timeout, solo yield
        yield


class IntradayEventDetector:
    """Detector de eventos intraday sobre barras 1min (bidireccional)"""

    def __init__(self, config_path: Path = None, output_dir: Path = None):
        if config_path is None:
            config_path = PROJECT_ROOT / "config" / "config.yaml"

        with open(config_path, encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.cfg = self.config["processing"]["intraday_events"]
        self.tz = ZoneInfo("America/New_York")

        # Directorios
        self.raw_bars_dir = PROJECT_ROOT / "raw" / "market_data" / "bars" / "1m"

        # Use custom output_dir if provided (for parallel workers)
        if output_dir:
            self.shards_dir = Path(output_dir)
            self.output_dir = self.shards_dir.parent.parent  # Go up to events dir
        else:
            self.output_dir = PROJECT_ROOT / "processed" / "events"
            self.shards_dir = self.output_dir / "shards"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.shards_dir.mkdir(parents=True, exist_ok=True)

        # Directorios para checkpointing y heartbeat
        self.checkpoint_dir = PROJECT_ROOT / "logs" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.heartbeat_dir = PROJECT_ROOT / "logs" / "heartbeats"
        self.heartbeat_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir = self.output_dir / "manifests"
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

        # Process monitoring
        self.process = psutil.Process()

        # Log file references (set from main())
        self.heartbeat_log_file = None
        self.batch_log_file = None

        logger.info(f"IntradayEventDetector initialized (config: {config_path})")
        logger.info(f"  Checkpoint dir: {self.checkpoint_dir}")
        logger.info(f"  Heartbeat dir: {self.heartbeat_dir}")
        logger.info(f"  Shards dir: {self.shards_dir}")
        logger.info(f"  Manifests dir: {self.manifests_dir}")

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
        events = events.with_columns([pl.col("vol_spike").alias("spike_x").cast(pl.Float64)])
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
            # Intentar leer el archivo parquet con manejo robusto de errores
            df_original = pl.read_parquet(bars_file)
        except TimeoutError:
            logger.error(f"[TIMEOUT] {symbol} {date} - file may be corrupted or too large")
            return pl.DataFrame()
        except (OSError, IOError) as e:
            logger.error(f"[I/O ERROR] {symbol} {date}: {e}")
            return pl.DataFrame()
        except Exception as e:
            logger.error(f"[FAILED] {symbol} {date}: {type(e).__name__}: {e}")
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

    def get_available_dates_for_symbol(self, symbol: str) -> list[str]:
        """
        Escanea directorio del símbolo y retorna lista de fechas disponibles.

        Args:
            symbol: Ticker symbol

        Returns:
            List of date strings (YYYY-MM-DD) with available data
        """
        symbol_dir = self.raw_bars_dir / f"symbol={symbol}"

        if not symbol_dir.exists():
            return []

        dates = []
        for file_path in symbol_dir.glob("date=*.parquet"):
            # Extract date from filename: date=YYYY-MM-DD.parquet
            date_str = file_path.stem.replace("date=", "")
            dates.append(date_str)

        return sorted(dates)

    def load_checkpoint(self, run_id: str) -> set[str]:
        """
        Carga checkpoint con símbolos ya procesados.

        Args:
            run_id: ID único del run (ej: events_intraday_20251012)

        Returns:
            Set de símbolos ya completados
        """
        checkpoint_file = self.checkpoint_dir / f"{run_id}_completed.json"

        if not checkpoint_file.exists():
            logger.info(f"No checkpoint found, starting fresh")
            return set()

        try:
            with open(checkpoint_file, 'r') as f:
                data = json.load(f)
                completed = set(data.get("completed_symbols", []))
                logger.info(f"[CHECKPOINT] Loaded checkpoint: {len(completed)} symbols already completed")
                return completed
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}, starting fresh")
            return set()

    def save_checkpoint(self, run_id: str, completed_symbols: set[str]):
        """
        Guarda checkpoint con símbolos completados.

        Args:
            run_id: ID único del run
            completed_symbols: Set de símbolos completados
        """
        checkpoint_file = self.checkpoint_dir / f"{run_id}_completed.json"

        data = {
            "run_id": run_id,
            "completed_symbols": sorted(list(completed_symbols)),
            "total_completed": len(completed_symbols),
            "last_updated": datetime.now().isoformat()
        }

        try:
            # Lock de checkpoint para escrituras atómicas
            lock_file = self.checkpoint_dir / f"{run_id}.lock"
            with file_lock(lock_file):
                with open(checkpoint_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def update_heartbeat(self, run_id: str, symbol: str, batch_num: int, total_batches: int,
                        events_count: int):
        """
        Actualiza heartbeat con progreso actual.

        Args:
            run_id: ID del run
            symbol: Símbolo actual
            batch_num: Número de batch actual
            total_batches: Total de batches
            events_count: Total de eventos detectados hasta ahora
        """
        heartbeat_file = self.heartbeat_dir / f"{run_id}_heartbeat.json"

        try:
            mem_info = self.process.memory_info()
            mem_gb = mem_info.rss / (1024 ** 3)

            data = {
                "run_id": run_id,
                "last_symbol": symbol,
                "last_timestamp": datetime.now().isoformat(),
                "batch_num": batch_num,
                "total_batches": total_batches,
                "progress_pct": (batch_num / total_batches * 100) if total_batches > 0 else 0,
                "events_detected": events_count,
                "memory_gb": round(mem_gb, 2),
                "status": "running"
            }

            with open(heartbeat_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to update heartbeat: {e}")

    def save_batch_shard(self, batch_df: pl.DataFrame, run_id: str, shard_num: int):
        """
        Guarda un shard (batch) de eventos a disco con numeración atómica.

        Args:
            batch_df: DataFrame con eventos del batch
            run_id: ID del run
            shard_num: Número de shard (ignorado, se calcula automáticamente)
        """
        # 1) Escribe a un tmp único para evitar colisiones entre procesos
        tmp_file = self.shards_dir / f"{run_id}_{uuid.uuid4().hex}.tmp"
        try:
            batch_df.write_parquet(tmp_file, compression="zstd")

            # 2) Sección crítica: asignación de índice bajo lock del run_id
            lock_file = self.shards_dir / f"{run_id}.lock"
            with file_lock(lock_file):
                # Usa búsqueda recursiva para contar todos los shards existentes del run (incluye worker_*)
                existing = sorted(self.shards_dir.rglob(f"**/{run_id}_shard*.parquet"))
                next_idx = len(existing)
                shard_file = self.shards_dir / f"{run_id}_shard{next_idx:04d}.parquet"
                os.replace(tmp_file, shard_file)  # movimiento atómico

            # 3) Manifest por shard (símbolos únicos)
            try:
                symbols = sorted(batch_df.select(pl.col("symbol").unique()).to_series().to_list())
            except Exception:
                symbols = []
            write_shard_manifest(self.manifests_dir, run_id, shard_file.name, symbols, len(batch_df))

            logger.info(f"[SAVED] Shard {next_idx}: {len(batch_df)} events -> {shard_file.name}")
        except Exception as e:
            logger.error(f"Failed to save shard {shard_num}: {e}")
            raise

    def merge_shards(self, run_id: str) -> pl.DataFrame:
        """
        Fusiona todos los shards en un solo archivo final.

        Args:
            run_id: ID del run

        Returns:
            DataFrame con todos los eventos fusionados
        """
        # Búsqueda recursiva: incluye worker_* y cualquier subcarpeta
        shard_pattern = f"{run_id}_shard*.parquet"
        shard_files = sorted(self.shards_dir.rglob(f"**/{shard_pattern}"))

        if not shard_files:
            logger.warning("No shards found to merge")
            return pl.DataFrame()

        logger.info(f"Merging {len(shard_files)} shards...")

        all_shards = []
        for shard_file in shard_files:
            try:
                df = pl.read_parquet(shard_file)
                all_shards.append(df)
                logger.debug(f"  Loaded {shard_file.name}: {len(df)} events")
            except Exception as e:
                logger.error(f"Failed to load shard {shard_file}: {e}")

        if not all_shards:
            return pl.DataFrame()

        final = pl.concat(all_shards, how="diagonal")
        final = final.sort(["symbol", "timestamp"])

        logger.info(f"[MERGED] {len(shard_files)} shards -> {len(final)} total events")
        return final

    def run(self, symbols: list[str], start_date: str = None, end_date: str = None,
            batch_size: int = 50, resume: bool = False, checkpoint_interval: int = 1):
        """
        Ejecuta detección para lista de símbolos con batching, checkpointing y heartbeat.

        Args:
            symbols: Lista de símbolos a procesar
            start_date: Fecha inicio (opcional)
            end_date: Fecha fin (opcional)
            batch_size: Tamaño del batch (símbolos por shard)
            resume: Si True, carga checkpoint y salta símbolos completados
            checkpoint_interval: Guardar checkpoint cada N batches

        Returns:
            DataFrame con todos los eventos detectados
        """
        from datetime import datetime

        # Setup run
        output_date = datetime.now().strftime("%Y%m%d")
        run_id = f"events_intraday_{output_date}"

        # Load checkpoint si resume=True
        completed_symbols = set()
        if resume:
            completed_symbols = self.load_checkpoint(run_id)
            symbols = [s for s in symbols if s not in completed_symbols]
            logger.info(f"Resume mode: {len(symbols)} symbols remaining to process")

        if not symbols:
            logger.info("All symbols already completed!")
            # Merge shards existentes
            final = self.merge_shards(run_id)
            if not final.is_empty():
                output_file = self.output_dir / f"{run_id}.parquet"
                final.write_parquet(output_file, compression="zstd")
                logger.info(f"[FINAL] Final file: {output_file}")
            return final

        total_batches = (len(symbols) + batch_size - 1) // batch_size
        logger.info(f"Processing {len(symbols)} symbols in {total_batches} batches (size={batch_size})")

        total_events = 0
        # Numeración ahora se hace dentro de save_batch_shard() de forma atómica bajo lock
        shard_num = 0

        for batch_idx in range(0, len(symbols), batch_size):
            batch = symbols[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1

            logger.info(f"\n{'='*60}")
            logger.info(f"BATCH {batch_num}/{total_batches} ({len(batch)} symbols)")
            logger.info(f"{'='*60}")

            batch_events = []

            for symbol in batch:
                # Get memory usage
                mem_info = self.process.memory_info()
                mem_gb = mem_info.rss / (1024 ** 3)

                # Update heartbeat (JSON y log separado)
                self.update_heartbeat(run_id, symbol, batch_num, total_batches, total_events)

                # Log heartbeat a archivo separado
                if self.heartbeat_log_file:
                    log_heartbeat(self.heartbeat_log_file, symbol, total_events, batch_num,
                                total_batches, mem_gb)

                # Get available dates for this symbol
                available_dates = self.get_available_dates_for_symbol(symbol)

                if not available_dates:
                    logger.debug(f"{symbol}: No data files found")
                    completed_symbols.add(symbol)
                    continue

                # Filter by date range if provided
                if start_date and end_date:
                    start = datetime.strptime(start_date, "%Y-%m-%d").date()
                    end = datetime.strptime(end_date, "%Y-%m-%d").date()

                    available_dates = [
                        d for d in available_dates
                        if start <= datetime.strptime(d, "%Y-%m-%d").date() <= end
                    ]

                if not available_dates:
                    logger.debug(f"{symbol}: No data in date range")
                    completed_symbols.add(symbol)
                    continue

                # Process all available dates for this symbol
                symbol_events = []
                total_days = len(available_dates)

                logger.info(f"[START] {symbol}: Starting processing of {total_days} days")

                for day_idx, date in enumerate(available_dates, 1):
                    # Log progress every 100 days to detect stalls
                    if day_idx % 100 == 0:
                        logger.info(f"[PROGRESS] {symbol}: Processing day {day_idx}/{total_days} ({date})")

                    try:
                        events = self.process_symbol_date(symbol, date)
                        if not events.is_empty():
                            symbol_events.append(events)
                    except Exception as e:
                        logger.error(f"[ERROR] {symbol} {date}: Unexpected error: {type(e).__name__}: {e}")
                        continue  # Skip this date but continue with others

                if symbol_events:
                    combined = pl.concat(symbol_events, how="diagonal")
                    batch_events.append(combined)
                    total_events += len(combined)
                    logger.info(f"[DONE] {symbol}: {len(combined)} events from {total_days} days ({len(symbol_events)} days with events)")
                else:
                    logger.debug(f"{symbol}: No events detected")

                # Mark symbol as completed
                completed_symbols.add(symbol)

                # Save checkpoint after EVERY symbol for maximum robustness
                # This ensures we never lose more than 1 symbol of work
                self.save_checkpoint(run_id, completed_symbols)

                # Save shard incrementally every 10 symbols to avoid data loss
                # This way if process is killed, we only lose max 10 symbols of events
                if len(batch_events) >= 10:
                    batch_df = pl.concat(batch_events, how="diagonal")
                    batch_df = batch_df.sort(["symbol", "timestamp"])

                    # Guardar shard (asignación de índice atómica interna)
                    self.save_batch_shard(batch_df, run_id, shard_num)

                    # Log
                    mem_info = self.process.memory_info()
                    mem_gb = mem_info.rss / (1024 ** 3)
                    if self.batch_log_file:
                        log_batch_saved(self.batch_log_file, batch_num, batch, len(batch_df),
                                      self.shards_dir / f"{run_id}_shard{shard_num:04d}.parquet", mem_gb)

                    shard_num += 1

                    # Clear batch events from memory
                    batch_events.clear()
                    del batch_df
                    gc.collect()

                # Log checkpoint less frequently to avoid log spam
                if len(completed_symbols) % 10 == 0:
                    logger.info(f"[CHECKPOINT] Progress saved: {len(completed_symbols)} symbols completed")

            # Save batch shard immediately
            if batch_events:
                batch_df = pl.concat(batch_events, how="diagonal")
                batch_df = batch_df.sort(["symbol", "timestamp"])

                # Guardar shard (asignación de índice atómica interna)
                self.save_batch_shard(batch_df, run_id, shard_num)
                total_events += len(batch_df)

                # Log batch guardado a archivo separado
                mem_info = self.process.memory_info()
                mem_gb = mem_info.rss / (1024 ** 3)

                if self.batch_log_file:
                    log_batch_saved(self.batch_log_file, batch_num, batch, len(batch_df),
                                  shard_file, mem_gb)

                # Log uso de recursos
                log_resource_usage()

                shard_num += 1

                # Clear memory
                del batch_events
                del batch_df
                gc.collect()

            # Save checkpoint periódicamente
            if batch_num % checkpoint_interval == 0:
                self.save_checkpoint(run_id, completed_symbols)
                logger.info(f"[CHECKPOINT] Checkpoint saved: {len(completed_symbols)}/{len(symbols) + len(completed_symbols)} symbols")

        # Save final checkpoint
        self.save_checkpoint(run_id, completed_symbols)
        logger.info(f"[COMPLETE] All batches completed: {shard_num} shards saved")

        # Merge all shards into final file
        logger.info(f"\n{'='*60}")
        logger.info("Merging shards into final file...")
        logger.info(f"{'='*60}")

        final = self.merge_shards(run_id)

        if final.is_empty():
            logger.warning("No events detected in any batch")
            return None

        # Save final file
        output_file = self.output_dir / f"{run_id}.parquet"
        final.write_parquet(output_file, compression="zstd")

        logger.info(f"\n{'='*60}")
        logger.info(f"[SUCCESS] DETECTION COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Total events: {len(final):,}")
        logger.info(f"Output file: {output_file}")
        logger.info(f"\nDistribution by type:\n{final.group_by('event_type').len().sort('len', descending=True)}")
        logger.info(f"\nDistribution by direction:\n{final.group_by('direction').len()}")
        logger.info(f"\nDistribution by session:\n{final.group_by('session').len()}")

        # Update final heartbeat
        heartbeat_file = self.heartbeat_dir / f"{run_id}_heartbeat.json"
        try:
            with open(heartbeat_file, 'w') as f:
                json.dump({
                    "run_id": run_id,
                    "status": "completed",
                    "total_events": len(final),
                    "total_symbols": len(completed_symbols),
                    "completed_at": datetime.now().isoformat()
                }, f, indent=2)
        except:
            pass

        return final


def setup_logging():
    """
    Configura logging robusto con separación de logs y sin dependencia de stdout.

    Estructura:
    - logs/detect_events/detect_events_intraday_YYYYMMDD_HHMMSS.log (principal)
    - logs/detect_events/heartbeat_YYYYMMDD.log (progreso incremental)
    - logs/detect_events/batches_YYYYMMDD.log (batches guardados)
    """
    log_dir = PROJECT_ROOT / "logs" / "detect_events"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now()
    date_str = timestamp.strftime("%Y%m%d")
    datetime_str = timestamp.strftime("%Y%m%d_%H%M%S")

    # Archivo principal (todo)
    main_log = log_dir / f"detect_events_intraday_{datetime_str}.log"

    # Archivos auxiliares
    heartbeat_log = log_dir / f"heartbeat_{date_str}.log"
    batch_log = log_dir / f"batches_{date_str}.log"

    # Limpiar handlers existentes
    logger.remove()

    # Handler principal: archivo con rotación
    logger.add(
        main_log,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {process.name}:{thread.name} | {file}:{line} | {message}",
        enqueue=True,        # Multiproceso seguro
        backtrace=True,      # Traceback completo en excepciones
        diagnose=True,       # Contexto adicional en errores
        rotation="50 MB",    # Rota cada 50 MB
        retention="7 days",  # Mantiene logs 7 días
        compression="zip",   # Comprime logs viejos
        mode="a"             # Append si relanzas (resume)
    )

    # Handler consola: solo INFO y superior
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
        colorize=True,
        enqueue=True
    )

    return {
        "main_log": main_log,
        "heartbeat_log": heartbeat_log,
        "batch_log": batch_log
    }

# ----------------------------- LOCK + MANIFEST ------------------------------
def write_shard_manifest(manifests_dir: Path, run_id: str, shard_name: str,
                         symbols: list[str], events_count: int):
    """Manifest simple por shard (≈10 líneas): ayuda a reconciliar checkpoint."""
    try:
        manifests_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": run_id,
            "shard": shard_name,
            "symbols": symbols,
            "events": int(events_count),
            "written_at": datetime.now().isoformat()
        }
        (manifests_dir / shard_name.replace(".parquet", ".json")).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"Failed to write manifest for {shard_name}: {e}")

@contextmanager
def file_lock(path: Path, timeout: int = 30, poll: float = 0.2):
    """File lock portable con busy-wait corto."""
    import time
    start = time.time()
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            if time.time() - start > timeout:
                raise TimeoutError(f"Lock timeout: {path}")
            time.sleep(poll)
    try:
        yield
    finally:
        try:
            os.remove(str(path))
        except Exception:
            pass

def log_heartbeat(heartbeat_file: Path, symbol: str, events_count: int, batch_num: int,
                  total_batches: int, mem_gb: float):
    """
    Registra heartbeat (progreso) en archivo separado.

    Esto permite saber exactamente dónde se detuvo el proceso si falla.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    progress_pct = (batch_num / total_batches * 100) if total_batches > 0 else 0

    # Log principal
    logger.info(f"[HEARTBEAT] {symbol} | batch={batch_num}/{total_batches} ({progress_pct:.1f}%) | events={events_count:,} | RAM={mem_gb:.2f}GB")

    # Archivo heartbeat separado (append, sin buffer)
    with open(heartbeat_file, "a", encoding="utf-8", buffering=1) as f:
        f.write(f"{timestamp}\t{symbol}\t{batch_num}\t{total_batches}\t{events_count}\t{mem_gb:.2f}\n")

def log_batch_saved(batch_file: Path, batch_num: int, symbols: list[str], total_events: int,
                    shard_file: Path, mem_gb: float):
    """
    Registra confirmación de batch guardado.

    Permite verificar qué batches están completos si el proceso se interrumpe.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # Log principal con nivel SUCCESS
    logger.success(f"[BATCH SAVED] #{batch_num:03d} | symbols={len(symbols)} | events={total_events:,} | file={shard_file.name} | RAM={mem_gb:.2f}GB")

    # Archivo batch separado
    with open(batch_file, "a", encoding="utf-8", buffering=1) as f:
        f.write(f"{timestamp}\t{batch_num}\t{len(symbols)}\t{total_events}\t{shard_file.name}\t{mem_gb:.2f}\n")

def log_resource_usage(interval_symbols: int = 10):
    """
    Registra uso de recursos del sistema periódicamente.

    Útil para detectar fugas de memoria o cuellos de botella.
    """
    try:
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        logger.debug(f"[RESOURCE] RAM used: {mem.percent:.1f}% ({mem.used/1e9:.2f}/{mem.total/1e9:.2f} GB) | CPU: {cpu:.1f}%")
    except Exception as e:
        logger.warning(f"Failed to log resource usage: {e}")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Detect intraday events from 1min bars (Production-grade with batching)")
    parser.add_argument("--symbols", nargs="+", help="List of symbols (or use --from-file)")
    parser.add_argument("--from-file", help="Load symbols from parquet (e.g. events_daily)")
    parser.add_argument("--start-date", help="Start date YYYY-MM-DD (optional - if not provided, processes all available dates)")
    parser.add_argument("--end-date", help="End date YYYY-MM-DD (optional - if not provided, processes all available dates)")
    parser.add_argument("--limit", type=int, help="Limit number of symbols (for testing)")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size (symbols per shard, default: 50)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint (skip completed symbols)")
    parser.add_argument("--checkpoint-interval", type=int, default=1, help="Save checkpoint every N batches (default: 1)")
    parser.add_argument("--worker-id", type=int, help="Worker ID for parallel processing (optional)")
    parser.add_argument("--output-dir", help="Custom output directory for shards (optional)")

    args = parser.parse_args()

    # Setup logging robusto
    log_files = setup_logging()

    logger.info("="*80)
    logger.info("INTRADAY EVENT DETECTION - PRODUCTION MODE")
    logger.info("="*80)
    logger.info(f"Main log: {log_files['main_log']}")
    logger.info(f"Heartbeat log: {log_files['heartbeat_log']}")
    logger.info(f"Batch log: {log_files['batch_log']}")
    logger.info(f"Batch size: {args.batch_size} symbols/batch")
    logger.info(f"Checkpoint interval: every {args.checkpoint_interval} batch(es)")
    logger.info(f"Resume mode: {args.resume}")
    if args.worker_id:
        logger.info(f"Worker ID: {args.worker_id}")
    if args.output_dir:
        logger.info(f"Custom output dir: {args.output_dir}")
    logger.info("="*80)

    detector = IntradayEventDetector(output_dir=Path(args.output_dir) if args.output_dir else None)
    detector.heartbeat_log_file = log_files['heartbeat_log']
    detector.batch_log_file = log_files['batch_log']

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

    # Run detection with batching and checkpointing
    try:
        detector.run(
            symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            batch_size=args.batch_size,
            resume=args.resume,
            checkpoint_interval=args.checkpoint_interval
        )
    except KeyboardInterrupt:
        logger.warning("[INTERRUPT] Process interrupted by user (Ctrl+C)")
        logger.info("Progress saved in checkpoint. Use --resume to continue.")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
