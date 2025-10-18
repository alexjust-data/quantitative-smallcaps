#!/usr/bin/env python3
"""
Launch Polygon ingestion with 0.25s rate-limit (aggressive acceleration)
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

root = Path(__file__).resolve().parents[2]
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
log_file = root / 'logs' / f'polygon_ingest_{ts}.log'
pid_file = root / 'logs' / f'polygon_ingest_{ts}.pid'

cmd = [
    sys.executable,
    str(root / 'scripts' / 'ingestion' / 'download_trades_quotes_intraday_v2.py'),
    '--manifest', str(root / 'processed' / 'events' / 'manifest_smallcaps_5y_20251017.parquet'),
    '--output-dir', str(root / 'raw' / 'market_data' / 'event_windows'),
    '--workers', '12',
    '--rate-limit', '0.25',
    '--quotes-hz', '1',
    '--resume'
]

print('[*] Launching Polygon ingestion with FILTERED smallcap manifest...')
print('    Manifest: manifest_smallcaps_5y_20251017.parquet (1,256 symbols < $2B)')
print('    Workers: 12 (parallel latency overlap)')
print('    Rate-limit: 0.25s')
print('    Quotes-hz: 1 (RTH downsample)')
print('    Resume: YES (mantiene archivos ya descargados)')
print()
with open(log_file, 'w') as log:
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    pid_file.write_text(str(proc.pid))
    print(f'[OK] Process launched with PID: {proc.pid}')
    print(f'     Log: {log_file.name}')
    print(f'     Expected: ~120 eventos/min (2 req/evento, 240 req/min)')
    print()
    print('[!] VIGILAR 429 ERRORS:')
    print('    Si aparecen 429 sostenidos -> SUBIR a 0.33-0.40s')
    print()
    print('Monitor log:')
    print(f'    Get-Content {log_file.name} -Tail 50 -Wait')
