#!/usr/bin/env python3
"""
Launch FASE 3.2 PM Wave in a subprocess
This keeps the process running even if the parent terminal closes

Usage:
    python launch_pm_wave.py
    python launch_pm_wave.py --input path/to/events.parquet
"""

import subprocess
import sys
import argparse
from pathlib import Path
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="Launch FASE 3.2 PM Wave Analysis")
    parser.add_argument(
        '--input',
        type=str,
        default='processed/final/events_intraday_MASTER_dedup_v2.parquet',
        help='Input manifest or events file (default: MASTER dedup v2)'
    )
    parser.add_argument(
        '--wave',
        type=str,
        default='PM',
        choices=['AM', 'PM', 'ALL'],
        help='Wave to process (default: PM)'
    )
    parser.add_argument(
        '--rate-limit',
        type=int,
        default=12,
        help='Rate limit in seconds (default: 12)'
    )
    parser.add_argument(
        '--quotes-hz',
        type=int,
        default=1,
        help='Quotes frequency in Hz (default: 1)'
    )
    args = parser.parse_args()

    # Validate input file
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        return 1

    # Get file info
    size_mb = input_file.stat().st_size / (1024 * 1024)

    print("="*60)
    print("LAUNCHING FASE 3.2 - PRICE & MOMENTUM WAVE ANALYSIS")
    print("="*60)
    print()
    print(f"Input file: {input_file}")
    print(f"File size: {size_mb:.1f} MB")
    print(f"Wave: {args.wave}")
    print(f"Rate limit: {args.rate_limit}s between requests")
    print(f"Quotes Hz: {args.quotes_hz}")
    print(f"Resume: enabled")
    print()

    # Generate timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(f"logs/fase3.2_pm_wave_{timestamp}.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Log file: {log_file}")
    print()
    print("="*60)
    print()

    # Prepare command
    cmd = [
        sys.executable,
        "scripts/ingestion/download_trades_quotes_intraday_v2.py",
        "--manifest", str(input_file),
        "--wave", args.wave,
        "--rate-limit", str(args.rate_limit),
        "--quotes-hz", str(args.quotes_hz),
        "--resume"
    ]

    print(f"Launching process...")
    print(f"Command: {' '.join(cmd)}")
    print()

    # Launch subprocess
    with open(log_file, 'w', encoding='utf-8') as f:
        process = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            cwd=Path.cwd()
        )

    print(f"[OK] Process launched with PID: {process.pid}")
    print()
    print("To monitor progress:")
    print(f"  tail -f {log_file}")
    print(f"  # or on Windows:")
    print(f"  Get-Content {log_file} -Wait")
    print()
    print("To check if running (Linux/Mac):")
    print(f"  ps -p {process.pid}")
    print()
    print("To check if running (Windows):")
    print(f"  tasklist /FI \"PID eq {process.pid}\"")
    print()
    print("Process will continue running in background...")
    print(f"PID: {process.pid}")
    print()

    # Save PID to file for easy tracking
    pid_file = Path(f"logs/fase3.2_pm_wave_{timestamp}.pid")
    pid_file.write_text(str(process.pid), encoding='utf-8')
    print(f"PID saved to: {pid_file}")
    print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
