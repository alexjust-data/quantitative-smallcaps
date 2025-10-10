"""
Generate stratified sample of events for manual validation in TradingView
"""
import sys
import io
from pathlib import Path
import polars as pl
import random

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def main():
    # Load events
    events_file = PROJECT_ROOT / "processed" / "events" / "events_daily_20251009.parquet"
    df = pl.read_parquet(events_file)
    events = df.filter(pl.col('is_event') == True)

    print(f'Total events: {events.height:,}')
    print()

    # Load ranking
    ranking_file = PROJECT_ROOT / "processed" / "rankings" / "top_2000_by_events_20251009.parquet"
    ranking = pl.read_parquet(ranking_file)

    # Get symbols by tier
    top_100 = set(ranking.head(100)['symbol'].to_list())
    mid_tier = set(ranking.slice(500, 500)['symbol'].to_list())
    cold_tier = set(ranking.slice(1500, 500)['symbol'].to_list())

    # Sample from each tier
    events_top = events.filter(pl.col('symbol').is_in(top_100))
    events_mid = events.filter(pl.col('symbol').is_in(mid_tier))
    events_cold = events.filter(pl.col('symbol').is_in(cold_tier))

    # Random sample 10 from each
    random.seed(42)
    n_per_tier = 10
    sample_top = events_top.sample(n=min(n_per_tier, events_top.height))
    sample_mid = events_mid.sample(n=min(n_per_tier, events_mid.height))
    sample_cold = events_cold.sample(n=min(n_per_tier, events_cold.height))

    # Combine
    sample = pl.concat([sample_top, sample_mid, sample_cold])

    print('='*80)
    print('SAMPLING FOR MANUAL VALIDATION')
    print('='*80)
    print(f'Sample size: {sample.height} events')
    print()
    print('Strategy:')
    print(f'  - {sample_top.height} from Top-100 (hot tickers)')
    print(f'  - {sample_mid.height} from Rank 500-1000 (mid-tier)')
    print(f'  - {sample_cold.height} from Rank 1500-2000 (cold-tier)')
    print()
    print('='*80)
    print('CHECK THESE EVENTS IN TRADINGVIEW:')
    print('='*80)
    print()

    for i, row in enumerate(sample.iter_rows(named=True), 1):
        date_obj = row['date']
        # Handle different date types
        if hasattr(date_obj, 'strftime'):
            date_str = date_obj.strftime('%Y-%m-%d')
        else:
            date_str = str(date_obj)

        gap = row['gap_pct']
        rvol = row['rvol']
        dv = row['dollar_volume']

        print(f'{i:2d}. {row["symbol"]:8s} | {date_str} | '
              f'Gap:{gap:6.2f}% RVOL:{rvol:5.2f}x DV:${dv/1e6:7.2f}M')

    print()
    print('='*80)
    print('VALIDATION CHECKLIST')
    print('='*80)
    print()
    print('For each event, check in TradingView:')
    print('  1. Is gap visible in daily chart?')
    print('  2. Is volume notably higher than previous days?')
    print('  3. Is it tradable (liquid, not 1 giant print)?')
    print('  4. Does it look like a real trading opportunity?')
    print()
    print('TARGET: ≥70% plausible = ≥21/30 events')
    print()
    print('If <21/30 → Adjust thresholds')
    print('If ≥21/30 → GO for Week 2-3 download')
    print('='*80)


if __name__ == "__main__":
    main()
