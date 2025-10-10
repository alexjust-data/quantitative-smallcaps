# scripts/processing/annotate_events_flatbase.py
"""
Añade flags de "base plana" y el label de "+100% run en 5 días" sobre eventos ya detectados.
No toca la lógica de detección ni la descarga en curso.
"""
import polars as pl
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
EVENTS_IN = BASE / "processed" / "events" / "events_daily_20251009.parquet"  # ajusta si cambia el nombre
DAILY_DIR = BASE / "raw" / "market_data" / "bars" / "1d"
OUT = BASE / "processed" / "events" / f"events_annotated_{datetime.utcnow().strftime('%Y%m%d')}.parquet"

# --- helpers -------------------------------------------------
def load_daily(symbol: str) -> pl.DataFrame:
    p = DAILY_DIR / f"{symbol}.parquet"
    if not p.exists():
        return None
    df = pl.read_parquet(p)
    # columnas esperadas: timestamp, open, high, low, close, volume, dollar_volume
    # Cast to datetime[ms, UTC] to match events file
    return (df
            .with_columns(pl.col("timestamp").cast(pl.Datetime("ms", "UTC")))
            .sort("timestamp")
            .with_columns([
                ((pl.col("high") - pl.col("low")) / pl.col("open") * 100).alias("range_pct"),
            ]))

def pct_change(s: pl.Series, n: int) -> pl.Series:
    return (s.shift(-n) / s - 1.0) * 100

# --- parámetros (también puedes ponerlos en config.yaml) -----
LOOKBACK_D = 20            # ventana para "quietness"
QUIET_ATR_PCT = 25         # percentil para ATR% "bajo"
QUIET_RVOL_MAX = 0.8       # RVOL máximo para días "silenciosos"
QUIET_MIN_DAYS = 15        # #días silenciosos necesarios en 20
RUN_FWD_D = 5              # horizonte para medir el "run" posterior
RUN_X2_THRESHOLD = 100.0   # +100%

# -------------------------------------------------------------
print(f"• Cargando eventos: {EVENTS_IN}")
events = pl.read_parquet(EVENTS_IN)
symbols = events.select("symbol").unique().to_series().to_list()
print(f"• Símbolos en eventos: {len(symbols)}")

annots = []
for i, sym in enumerate(symbols):
    if (i + 1) % 100 == 0:
        print(f"  Procesando: {i+1}/{len(symbols)}")

    d = load_daily(sym)
    if d is None or d.height == 0:
        continue

    # ATR% (Wilder 14 por defecto; simple y suficiente aquí)
    d = d.with_columns([
        (pl.max_horizontal(pl.col("high") - pl.col("low"),
                           (pl.col("high") - pl.col("close").shift(1)).abs(),
                           (pl.col("low") - pl.col("close").shift(1)).abs()
                          ).rolling_mean(window_size=14, min_samples=7)
         / pl.col("close") * 100).alias("atr_pct"),
    ])

    # RVOL simple: volumen / media 30d
    d = d.with_columns([
        (pl.col("volume") / pl.col("volume").rolling_mean(30, min_samples=15)).alias("rvol_30"),
    ])

    # percentil 25 de ATR% en ventana móvil 20d para marcar "quiet"
    d = d.with_columns([
        pl.col("atr_pct").rolling_quantile(quantile=0.25, window_size=LOOKBACK_D, min_samples=10).alias("atr_pct_p25_20d")
    ])
    d = d.with_columns([
        ((pl.col("atr_pct") <= pl.col("atr_pct_p25_20d")) & (pl.col("rvol_30") <= QUIET_RVOL_MAX)).alias("is_quiet_day")
    ])
    d = d.with_columns([
        pl.col("is_quiet_day").cast(pl.Int8).rolling_sum(LOOKBACK_D, min_samples=10).alias("quiet_days_20d")
    ])
    d = d.with_columns([
        (pl.col("quiet_days_20d") >= QUIET_MIN_DAYS).alias("had_flat_base_20d")
    ])

    # max run 5d
    d = d.with_columns([
        ((pl.col("close").shift(-RUN_FWD_D) / pl.col("close") - 1.0) * 100.0).alias("ret_fwd_5d")
    ])

    # Calculate max run (highest high in next 5 days vs current close)
    # Use a simpler approach: shift high values and compare
    max_high_5d = pl.max_horizontal([
        pl.col("high").shift(-i) for i in range(1, RUN_FWD_D + 1)
    ])

    d = d.with_columns([
        ((max_high_5d / pl.col("close") - 1.0) * 100.0).alias("max_run_5d")
    ])

    # merge con eventos del símbolo
    ev_sym = events.filter(pl.col("symbol") == sym)
    ev = ev_sym.join(
        d.select(["timestamp","had_flat_base_20d","max_run_5d"]),
        on="timestamp", how="left"
    ).with_columns([
        (pl.col("max_run_5d") >= RUN_X2_THRESHOLD).alias("x2_run_flag"),
        # "flat-base breakout" si venía plano y el branch IRE (o VSWG) se activó
        ((pl.col("had_flat_base_20d") == True) & ((pl.col("branch_ire") == True) | (pl.col("branch_vswg") == True))).alias("is_flat_base_breakout")
    ])

    annots.append(ev)

out = pl.concat(annots) if annots else events
out.write_parquet(OUT)
print(f"[OK] Guardado: {OUT}")
print(f"\nEstadisticas:")
print(f"  Eventos con flat_base: {out.filter(pl.col('had_flat_base_20d')).height}")
print(f"  Eventos con x2_run: {out.filter(pl.col('x2_run_flag')).height}")
print(f"  Eventos flat_base_breakout: {out.filter(pl.col('is_flat_base_breakout')).height}")
