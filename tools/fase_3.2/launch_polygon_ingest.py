#!/usr/bin/env python3
"""
Launch Polygon ingestion in background with logging.
Calls download_trades_quotes_intraday_v2.py with --resume capability.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime

def main():
    ap = argparse.ArgumentParser(description="Launch Polygon ingestion with resume")
    ap.add_argument("--manifest", default="processed/events/manifest_core_FULL.parquet",
                    help="Manifest parquet with symbols and time windows")
    ap.add_argument("--workers", type=int, default=1,
                    help="Number of parallel workers")
    ap.add_argument("--rate-limit", type=int, default=10,
                    help="Rate limit in seconds between API calls")
    ap.add_argument("--quotes-hz", type=int, default=1,
                    help="Quotes frequency in Hz")
    ap.add_argument("--extra-args", default="",
                    help="Extra args for ingestor (e.g. '--start-date 2022-01-01')")
    args = ap.parse_args()

    # Project root (from tools/fase_3.2/ go up 2 levels)
    root = Path(__file__).resolve().parents[2]

    # Validate manifest
    manifest_path = root / args.manifest
    if not manifest_path.exists():
        print(f"ERROR: Manifest not found: {manifest_path}")
        print(f"\nTip: Generate manifest first:")
        print(f"  python tools/make_manifest.py")
        return 1

    # Create timestamped log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = root / "logs" / f"polygon_ingest_{timestamp}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Build command
    cmd = [
        sys.executable,
        str(root / "scripts/ingestion/download_trades_quotes_intraday_v2.py"),
        "--manifest", str(manifest_path),
        "--workers", str(args.workers),
        "--rate-limit", str(args.rate_limit),
        "--quotes-hz", str(args.quotes_hz),
        "--resume"
    ]

    # Add extra args if provided
    if args.extra_args:
        cmd.extend(args.extra_args.split())

    print("=" * 60)
    print("LAUNCHING POLYGON INGESTION")
    print("=" * 60)
    print()
    print(f"Manifest: {manifest_path}")
    print(f"Workers: {args.workers}")
    print(f"Rate limit: {args.rate_limit}s")
    print(f"Quotes Hz: {args.quotes_hz}")
    print(f"Resume: enabled")
    print()
    print(f"Command: {' '.join(cmd)}")
    print(f"Log file: {log_file}")
    print()
    print("=" * 60)
    print()

    # Launch in background
    with open(log_file, 'w', encoding='utf-8') as lf:
        process = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=lf,
            stderr=subprocess.STDOUT
        )

    print(f"[OK] Process launched with PID: {process.pid}")
    print()
    print("To monitor progress:")
    print(f"  # Windows:")
    print(f"  Get-Content {log_file} -Wait -Tail 50")
    print(f"  # Linux/Mac:")
    print(f"  tail -f {log_file}")
    print()
    print("To verify progress:")
    print(f"  python tools/verify_ingest.py")
    print()
    print("To check if running:")
    print(f"  # Windows:")
    print(f"  tasklist /FI \"PID eq {process.pid}\"")
    print(f"  # Linux/Mac:")
    print(f"  ps -p {process.pid}")
    print()

    # Save PID
    pid_file = log_file.parent / f"polygon_ingest_{timestamp}.pid"
    pid_file.write_text(str(process.pid), encoding='utf-8')
    print(f"PID saved to: {pid_file}")
    print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
