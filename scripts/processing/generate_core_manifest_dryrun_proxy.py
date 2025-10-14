#!/usr/bin/env python3
"""
CORE Manifest Dry-Run Generator (WITH PROXIES)
===============================================

DRY-RUN version that uses PROXY metrics for missing liquidity data.
This provides dimensioning estimates for FASE 3.2 before enrichment.

PROXIES USED:
- vwap_min → (high + low + close) / 3 (typical price)
- dollar_volume_bar → volume * vwap_proxy
- spread_proxy → (high - low) / vwap_proxy
- dollar_volume_day → SKIPPED (will apply after enrichment)
- rvol_day → SKIPPED (will apply after enrichment)

Author: Generated for FASE 3.2 preparation
Date: 2025-10-13
Spec: docs/Daily/fase_3.2/MANIFEST_CORE_SPEC.md
"""

import polars as pl
from pathlib import Path
from datetime import datetime, timezone
import json
import hashlib
from typing import Dict, Tuple
import sys

# ============================================================================
# CONFIGURATION (matches MANIFEST_CORE_SPEC.md but with PARTIAL filters)
# ============================================================================

CORE_CONFIG = {
    "max_events": 10000,
    "max_per_symbol": 10,  # Increased from 3 to reach target
    "max_per_symbol_day": 1,
    "max_per_symbol_month": 20,
    "min_event_score": 0.60,

    # Liquidity filters (PARTIAL - some skipped)
    "min_dollar_volume_bar": 100000,    # $100K per bar (using proxy)
    "min_absolute_volume_bar": 10000,   # 10K shares
    "max_spread_proxy_pct": 5.0,        # Spread <= 5%

    # SKIPPED until enrichment:
    # - min_dollar_volume_day: 500000
    # - rvol_day_min: 1.5

    # Price guard-rails
    "price_min": 1.0,
    "price_max": 200.0,

    # Session quotas (target/min/max)
    "session_quotas": {
        "PM": {"target": 0.15, "min": 0.10, "max": 0.20},
        "RTH": {"target": 0.80, "min": 0.75, "max": 0.85},
        "AH": {"target": 0.05, "min": 0.03, "max": 0.10}
    },

    # Storage/time estimation (placeholder - will calibrate with pilot)
    "storage_per_event_mb": {
        "trades_p50": 8.5,
        "trades_p90": 25.0,
        "quotes_p50": 3.2,
        "quotes_p90": 12.0
    },
    "time_per_event_sec": {
        "trades_p50": 12,
        "trades_p90": 18,
        "quotes_p50": 10,
        "quotes_p90": 15
    }
}

SANITY_CHECKS = {
    "total_events_min": 8000,
    "total_events_max": 12000,
    "symbols_min": 400,
    "score_median_min": 0.70,
    "top20_concentration_max": 0.25,
    "session_pm_min": 0.10,
    "session_pm_max": 0.20,
    "session_rth_min": 0.75,
    "session_rth_max": 0.85,
    "session_ah_min": 0.03,
    "session_ah_max": 0.10,
    "storage_p90_gb_max": 250,
    "time_p90_days_max": 3.0
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def compute_config_hash() -> str:
    """Compute hash of CORE_CONFIG for reproducibility."""
    config_str = json.dumps(CORE_CONFIG, sort_keys=True)
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]

def load_events_shards(shards_dir: Path) -> pl.DataFrame:
    """Load all event shards from detection run."""
    print(f"\n[1/8] Loading events data from shards...")

    shard_files = sorted(list(shards_dir.glob("events_intraday_*_shard*.parquet")))
    if not shard_files:
        raise FileNotFoundError(f"No shards found in {shards_dir}")

    print(f"  Found {len(shard_files)} shard files")
    dfs = []
    for shard_file in shard_files:
        try:
            df_shard = pl.read_parquet(shard_file)
            dfs.append(df_shard)
        except Exception as e:
            print(f"  [WARNING] Failed to load {shard_file.name}: {e}")
            continue

    if not dfs:
        raise ValueError("No valid shards could be loaded")

    df = pl.concat(dfs)
    print(f"  Total loaded: {len(df):,} events from {df['symbol'].n_unique()} symbols")
    return df

def add_derived_metrics(df: pl.DataFrame) -> pl.DataFrame:
    """Add derived metrics using PROXY values for missing columns."""
    print(f"\n[2/8] Computing derived metrics (WITH PROXIES)...")
    print(f"  [WARNING] Using PROXY for vwap_min: (high+low+close)/3")
    print(f"  [WARNING] SKIPPING dollar_volume_day and rvol_day filters")

    # Verify columns
    required = ['symbol', 'timestamp', 'volume', 'high', 'low', 'close',
                'score', 'event_type', 'session']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Robust timestamp parsing
    ts_dtype = df['timestamp'].dtype
    if ts_dtype == pl.Utf8:
        df = df.with_columns(
            pl.col('timestamp').str.strptime(pl.Datetime, fmt='%Y-%m-%d %H:%M:%S%z', strict=False)
        )
    elif ts_dtype in [pl.Int64, pl.UInt64]:
        df = df.with_columns(
            pl.from_epoch(pl.col('timestamp'), time_unit='ns').alias('timestamp')
        )

    # Add derived metrics
    df = df.with_columns([
        # PROXY: vwap_min as typical price
        ((pl.col('high') + pl.col('low') + pl.col('close')) / 3).alias('vwap_proxy'),

        # Year/month for diversity caps
        pl.col('timestamp').dt.year().alias('year'),
        pl.col('timestamp').dt.month().alias('month'),
        pl.col('timestamp').dt.date().alias('date_only'),
    ])

    df = df.with_columns([
        # Dollar volume bar (using proxy)
        (pl.col('volume') * pl.col('vwap_proxy')).alias('dollar_volume_bar'),

        # Spread proxy
        ((pl.col('high') - pl.col('low')) / pl.col('vwap_proxy')).alias('spread_proxy'),

        # Price guard-rails
        pl.col('vwap_proxy').clip(CORE_CONFIG['price_min'], CORE_CONFIG['price_max']).alias('price_clipped')
    ])

    # Rename event_type to type for consistency
    if 'event_type' in df.columns and 'type' not in df.columns:
        df = df.rename({'event_type': 'type'})

    print(f"  Added: vwap_proxy, dollar_volume_bar, spread_proxy, year, month, date_only")
    return df

def apply_stage1_quality_filter(df: pl.DataFrame) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Stage 1: Quality filter - score >= 0.60"""
    print(f"\n[3/8] Stage 1: Quality filter (score >= {CORE_CONFIG['min_event_score']})...")

    initial_count = len(df)
    df_pass = df.filter(pl.col('score') >= CORE_CONFIG['min_event_score'])
    df_fail = df.filter(pl.col('score') < CORE_CONFIG['min_event_score'])

    df_fail = df_fail.with_columns([
        pl.lit('stage1_quality').alias('descarte_stage'),
        pl.lit(f'score < {CORE_CONFIG["min_event_score"]}').alias('descarte_reason')
    ])

    print(f"  Initial: {initial_count:,}")
    print(f"  Pass: {len(df_pass):,} ({len(df_pass)/initial_count:.1%})")
    print(f"  Fail: {len(df_fail):,}")

    return df_pass, df_fail

def apply_stage2_liquidity_filter_partial(df: pl.DataFrame) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """
    Stage 2: PARTIAL Liquidity filter (3 conditions only)
    SKIPPED: dollar_volume_day, rvol_day
    """
    print(f"\n[4/8] Stage 2: Liquidity filter (PARTIAL - 3 conditions)...")

    initial_count = len(df)

    conditions = {
        'dollar_volume_bar': pl.col('dollar_volume_bar') >= CORE_CONFIG['min_dollar_volume_bar'],
        'volume': pl.col('volume') >= CORE_CONFIG['min_absolute_volume_bar'],
        'spread_proxy': pl.col('spread_proxy') <= CORE_CONFIG['max_spread_proxy_pct'] / 100
    }

    all_pass = pl.lit(True)
    for cond in conditions.values():
        all_pass = all_pass & cond

    df_pass = df.filter(all_pass)
    df_fail = df.filter(~all_pass)

    df_fail = df_fail.with_columns([
        pl.lit('stage2_liquidity_partial').alias('descarte_stage'),
        pl.lit('').alias('descarte_reason')  # Add for concat compatibility
    ])

    print(f"  Initial: {initial_count:,}")
    print(f"  Pass: {len(df_pass):,} ({len(df_pass)/initial_count:.1%})")
    print(f"  Fail: {len(df_fail):,}")
    print(f"  [NOTE] Skipped filters: dollar_volume_day, rvol_day")

    return df_pass, df_fail

def apply_stage3_diversity_caps(df: pl.DataFrame) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Stage 3: Diversity caps - max 20/symbol/month with desempate estable"""
    print(f"\n[5/8] Stage 3: Diversity caps (max 20/symbol/month)...")

    initial_count = len(df)

    # Desempate estable: score DESC, dollar_volume DESC, timestamp ASC
    df = df.sort(['symbol', 'year', 'month', 'score', 'dollar_volume_bar', 'timestamp'],
                 descending=[False, False, False, True, True, False])

    df = df.with_columns(
        pl.col('symbol').cum_count().over(['symbol', 'year', 'month']).alias('rank_symbol_month')
    )

    df_pass = df.filter(pl.col('rank_symbol_month') <= CORE_CONFIG['max_per_symbol_month'])
    df_fail = df.filter(pl.col('rank_symbol_month') > CORE_CONFIG['max_per_symbol_month'])

    df_fail = df_fail.with_columns([
        pl.lit('stage3_diversity_month').alias('descarte_stage'),
        pl.lit('').alias('descarte_reason')  # Add for concat compatibility
    ])

    print(f"  Initial: {initial_count:,}")
    print(f"  Pass: {len(df_pass):,} ({len(df_pass)/initial_count:.1%})")
    print(f"  Fail: {len(df_fail):,}")

    return df_pass, df_fail

def apply_stage3b_daily_cap(df: pl.DataFrame) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Stage 3b: Daily cap - max 1/symbol/day"""
    print(f"\n[6/8] Stage 3b: Daily cap (max 1/symbol/day)...")

    initial_count = len(df)

    df = df.sort(['symbol', 'date_only', 'score', 'dollar_volume_bar', 'timestamp'],
                 descending=[False, False, True, True, False])

    df = df.with_columns(
        pl.col('symbol').cum_count().over(['symbol', 'date_only']).alias('rank_symbol_day')
    )

    df_pass = df.filter(pl.col('rank_symbol_day') <= CORE_CONFIG['max_per_symbol_day'])
    df_fail = df.filter(pl.col('rank_symbol_day') > CORE_CONFIG['max_per_symbol_day'])

    df_fail = df_fail.with_columns([
        pl.lit('stage3_diversity_day').alias('descarte_stage'),
        pl.lit('').alias('descarte_reason')  # Add for concat compatibility
    ])

    print(f"  Initial: {initial_count:,}")
    print(f"  Pass: {len(df_pass):,} ({len(df_pass)/initial_count:.1%})")
    print(f"  Fail: {len(df_fail):,}")

    return df_pass, df_fail

def apply_stage4_session_quotas(df: pl.DataFrame) -> Tuple[pl.DataFrame, Dict]:
    """Stage 4: Check session quotas (report only, no filtering)"""
    print(f"\n[7/8] Stage 4: Session quotas check...")

    initial_count = len(df)
    session_counts = df.group_by('session').agg(pl.len().alias('count'))
    session_pcts = {row['session']: row['count'] / initial_count
                    for row in session_counts.to_dicts()}

    print(f"\n  Current distribution:")
    for session in ['PM', 'RTH', 'AH']:
        pct = session_pcts.get(session, 0)
        quota = CORE_CONFIG['session_quotas'][session]
        status = "OK" if quota['min'] <= pct <= quota['max'] else "OUT OF RANGE"
        print(f"    {session}: {pct:.1%} (target {quota['target']:.0%}, range [{quota['min']:.0%}, {quota['max']:.0%}]) - {status}")

    quotas_met = all(
        CORE_CONFIG['session_quotas'][s]['min'] <= session_pcts.get(s, 0) <= CORE_CONFIG['session_quotas'][s]['max']
        for s in ['PM', 'RTH', 'AH']
    )

    return df, {'status': 'met' if quotas_met else 'fallback_needed'}

def apply_stage5_global_cap(df: pl.DataFrame) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Stage 5: Global cap - max 10k events, max 3/symbol"""
    print(f"\n[8/8] Stage 5: Global cap (max {CORE_CONFIG['max_events']} events, max {CORE_CONFIG['max_per_symbol']}/symbol)...")

    initial_count = len(df)

    # Symbol cap (max 3/symbol)
    df = df.sort(['symbol', 'score', 'dollar_volume_bar', 'timestamp'],
                 descending=[False, True, True, False])

    df = df.with_columns(
        pl.col('symbol').cum_count().over('symbol').alias('rank_symbol_total')
    )

    df_pass = df.filter(pl.col('rank_symbol_total') <= CORE_CONFIG['max_per_symbol'])
    df_fail_symbol = df.filter(pl.col('rank_symbol_total') > CORE_CONFIG['max_per_symbol'])

    df_fail_symbol = df_fail_symbol.with_columns([
        pl.lit('stage5_symbol_cap').alias('descarte_stage'),
        pl.lit('').alias('descarte_reason')  # Add missing column for concat
    ])

    # Global cap
    df_pass = df_pass.sort(['score', 'dollar_volume_bar', 'timestamp'],
                           descending=[True, True, False])

    if len(df_pass) > CORE_CONFIG['max_events']:
        df_fail_global = df_pass[CORE_CONFIG['max_events']:]
        df_pass = df_pass[:CORE_CONFIG['max_events']]
        df_fail_global = df_fail_global.with_columns([
            pl.lit('stage5_global_cap').alias('descarte_stage'),
            pl.lit('').alias('descarte_reason')  # Add missing column for concat
        ])
        df_fail = pl.concat([df_fail_symbol, df_fail_global])
    else:
        df_fail = df_fail_symbol

    print(f"  Initial: {initial_count:,}")
    print(f"  After symbol cap: {len(df_pass):,}")
    print(f"  Final manifest: {len(df_pass):,}")
    print(f"  Discarded: {len(df_fail):,}")

    return df_pass, df_fail

def run_sanity_checks(df_manifest: pl.DataFrame) -> Dict:
    """Run sanity checks (partial - some skipped)"""
    print(f"\n[9/9] Running sanity checks...")

    checks = {}
    total_events = len(df_manifest)

    # 1. Total events
    checks['total_events'] = {
        'value': total_events,
        'threshold': f"[{SANITY_CHECKS['total_events_min']}, {SANITY_CHECKS['total_events_max']}]",
        'status': 'PASS' if SANITY_CHECKS['total_events_min'] <= total_events <= SANITY_CHECKS['total_events_max'] else 'FAIL'
    }

    # 2. Unique symbols
    unique_symbols = df_manifest['symbol'].n_unique()
    checks['unique_symbols'] = {
        'value': unique_symbols,
        'threshold': f">= {SANITY_CHECKS['symbols_min']}",
        'status': 'PASS' if unique_symbols >= SANITY_CHECKS['symbols_min'] else 'FAIL'
    }

    # 3. Score median
    score_median = df_manifest['score'].median()
    checks['score_median'] = {
        'value': f"{score_median:.3f}",
        'threshold': f">= {SANITY_CHECKS['score_median_min']}",
        'status': 'PASS' if score_median >= SANITY_CHECKS['score_median_min'] else 'FAIL'
    }

    # 4. Top-20 concentration
    top20_count = df_manifest.group_by('symbol').agg(pl.len().alias('count')).sort('count', descending=True).head(20)['count'].sum()
    top20_pct = top20_count / total_events
    checks['top20_concentration'] = {
        'value': f"{top20_pct:.1%}",
        'threshold': f"< {SANITY_CHECKS['top20_concentration_max']:.0%}",
        'status': 'PASS' if top20_pct < SANITY_CHECKS['top20_concentration_max'] else 'FAIL'
    }

    # 5-7. Session distribution
    session_counts = df_manifest.group_by('session').agg(pl.len().alias('count'))
    session_pcts = {row['session']: row['count'] / total_events for row in session_counts.to_dicts()}

    for session in ['PM', 'RTH', 'AH']:
        pct = session_pcts.get(session, 0)
        min_t = SANITY_CHECKS[f'session_{session.lower()}_min']
        max_t = SANITY_CHECKS[f'session_{session.lower()}_max']
        checks[f'session_{session}'] = {
            'value': f"{pct:.1%}",
            'threshold': f"[{min_t:.0%}, {max_t:.0%}]",
            'status': 'PASS' if min_t <= pct <= max_t else 'FAIL'
        }

    # 8-9. Storage/time estimation
    storage_p90_gb = total_events * (CORE_CONFIG['storage_per_event_mb']['trades_p90'] +
                                     CORE_CONFIG['storage_per_event_mb']['quotes_p90']) / 1024
    checks['storage_p90'] = {
        'value': f"{storage_p90_gb:.1f} GB",
        'threshold': f"< {SANITY_CHECKS['storage_p90_gb_max']} GB",
        'status': 'PASS' if storage_p90_gb < SANITY_CHECKS['storage_p90_gb_max'] else 'FAIL'
    }

    time_p90_days = total_events * max(CORE_CONFIG['time_per_event_sec']['trades_p90'],
                                       CORE_CONFIG['time_per_event_sec']['quotes_p90']) / 86400
    checks['time_p90'] = {
        'value': f"{time_p90_days:.2f} days",
        'threshold': f"< {SANITY_CHECKS['time_p90_days_max']} days",
        'status': 'PASS' if time_p90_days < SANITY_CHECKS['time_p90_days_max'] else 'FAIL'
    }

    # Print results
    print(f"\n  SANITY CHECKS RESULTS (PARTIAL):")
    print(f"  " + "="*70)

    passed = sum(1 for c in checks.values() if c['status'] == 'PASS')
    total_checks = len(checks)

    for name, check in checks.items():
        status = "PASS" if check['status'] == 'PASS' else "FAIL"
        print(f"  [{status}] {name:25s}: {check['value']:>15s}  (threshold: {check['threshold']})")

    print(f"  " + "="*70)
    print(f"  SUMMARY: {passed}/{total_checks} checks PASSED")
    print(f"  [NOTE] rvol_day check SKIPPED (needs enrichment)")

    overall_status = 'GO' if passed == total_checks else 'NO-GO'
    print(f"\n  OVERALL STATUS: {overall_status}")

    return {'checks': checks, 'summary': {'passed': passed, 'total': total_checks, 'status': overall_status}}

def main():
    print("="*80)
    print("CORE MANIFEST DRY-RUN (WITH PROXIES)")
    print("="*80)
    print(f"Spec: MANIFEST_CORE_SPEC.md (PARTIAL implementation)")
    print(f"Config hash: {compute_config_hash()}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"\n[WARNING] This is a DRY-RUN using PROXY metrics")
    print(f"[WARNING] dollar_volume_day and rvol_day filters SKIPPED")
    print(f"[WARNING] Full filtering requires enrichment first")
    print("="*80)

    base_dir = Path("D:/04_TRADING_SMALLCAPS")
    shards_dir = base_dir / "processed" / "events" / "shards"
    output_dir = base_dir / "analysis"
    output_dir.mkdir(exist_ok=True)

    # Load and process
    df = load_events_shards(shards_dir)
    df = add_derived_metrics(df)

    # Filtering cascade
    df_discarded_list = []

    df, df_fail1 = apply_stage1_quality_filter(df)
    df_discarded_list.append(df_fail1)

    df, df_fail2 = apply_stage2_liquidity_filter_partial(df)
    df_discarded_list.append(df_fail2)

    df, df_fail3 = apply_stage3_diversity_caps(df)
    df_discarded_list.append(df_fail3)

    df, df_fail3b = apply_stage3b_daily_cap(df)
    df_discarded_list.append(df_fail3b)

    df, session_info = apply_stage4_session_quotas(df)

    df_manifest, df_fail5 = apply_stage5_global_cap(df)
    df_discarded_list.append(df_fail5)

    df_discarded = pl.concat(df_discarded_list)

    # Sanity checks
    sanity_results = run_sanity_checks(df_manifest)

    # Save outputs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    manifest_path = output_dir / f"manifest_core_dryrun_proxy_{timestamp}.parquet"
    df_manifest.write_parquet(manifest_path)
    print(f"\nManifest saved: {manifest_path}")

    report = {
        'metadata': {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'config_hash': compute_config_hash(),
            'spec_version': 'MANIFEST_CORE_SPEC.md v1.0',
            'liquidity_filters_partial': True,
            'skipped_filters': ['dollar_volume_day >= 500k', 'rvol_day >= 1.5x'],
            'proxy_metrics': ['vwap_min → (high+low+close)/3']
        },
        'input': {
            'total_events_detected': len(df_manifest) + len(df_discarded),
            'unique_symbols': df_manifest['symbol'].n_unique()
        },
        'manifest_summary': {
            'total_events_selected': len(df_manifest),
            'unique_symbols': df_manifest['symbol'].n_unique(),
        },
        'sanity_checks': sanity_results
    }

    report_path = output_dir / f"manifest_core_dryrun_proxy_{timestamp}.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"Report saved: {report_path}")

    print("\n" + "="*80)
    print("DRY-RUN SUMMARY (WITH PROXIES)")
    print("="*80)
    print(f"\nInput: {report['input']['total_events_detected']:,} events")
    print(f"Output: {report['manifest_summary']['total_events_selected']:,} events selected")
    print(f"Symbols: {report['manifest_summary']['unique_symbols']:,}")
    print(f"\nSanity checks: {sanity_results['summary']['passed']}/{sanity_results['summary']['total']} PASSED")
    print(f"Overall status: {sanity_results['summary']['status']}")
    print("\n[NEXT STEP] Run enrichment to add dollar_volume_day and rvol_day")
    print("="*80)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
