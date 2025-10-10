import sys
import io
import polars as pl

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

df = pl.read_parquet('processed/events/events_daily_20251009.parquet')

# Check QUBT on 2024-11-13
qubt_nov13 = df.filter(
    (pl.col('symbol') == 'QUBT') &
    (pl.col('date') == pl.date(2024, 11, 13))
)

if qubt_nov13.height == 0:
    print('❌ NO event detected for QUBT on 2024-11-13')
else:
    row = qubt_nov13.row(0, named=True)
    print(f'✅ Event detected: {row["is_event"]}')
    print(f'   Gap: {row["gap_pct"]:.2f}%')
    print(f'   RVOL: {row["rvol"]:.2f}x')
    print(f'   Dollar Volume: ${row["dollar_volume"]/1e6:.2f}M')

# Show all QUBT events
print('\n' + '='*60)
print('ALL QUBT EVENTS:')
print('='*60)

all_qubt = df.filter((pl.col('symbol') == 'QUBT') & (pl.col('is_event') == True))
print(f'Total QUBT events: {all_qubt.height}')
print()

for i, row in enumerate(all_qubt.iter_rows(named=True), 1):
    date_str = row['date'].strftime('%Y-%m-%d')
    print(f'{i:2d}. {date_str} | Gap:{row["gap_pct"]:6.2f}% RVOL:{row["rvol"]:5.2f}x DV:${row["dollar_volume"]/1e6:7.2f}M')
