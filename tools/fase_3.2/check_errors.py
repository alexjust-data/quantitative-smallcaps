#!/usr/bin/env python3
"""
Check for errors in Polygon ingestion log

Usage:
    python tools/fase_3.2/check_errors.py
    python tools/fase_3.2/check_errors.py --log logs/polygon_ingest_20251017_175943.log
"""
from pathlib import Path
import argparse
import re
from datetime import datetime
from collections import Counter

def main():
    ap = argparse.ArgumentParser(description="Check for errors in Polygon ingestion")
    ap.add_argument("--log", help="Path to log file (default: find most recent)")
    ap.add_argument("--tail", type=int, default=100, help="Show last N error lines")
    ap.add_argument("--verbose", action="store_true", help="Show all error details")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]

    # Find log file
    if args.log:
        log_path = Path(args.log)
    else:
        # Find most recent polygon_ingest log
        log_dir = root / "logs"
        log_files = sorted(log_dir.glob("polygon_ingest_*.log"))
        if not log_files:
            print("ERROR: No polygon_ingest log files found")
            return 1
        log_path = log_files[-1]

    if not log_path.exists():
        print(f"ERROR: Log file not found: {log_path}")
        return 1

    print("=" * 70)
    print("POLYGON INGESTION ERROR CHECK")
    print("=" * 70)
    print()
    print(f"Log file: {log_path.name}")
    print(f"Log size: {log_path.stat().st_size / 1024 / 1024:.1f} MB")
    print()

    # Read log
    try:
        log_content = log_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        log_content = log_path.read_text(encoding="latin-1", errors="ignore")

    # Find errors
    error_patterns = [
        (r"ERROR", "ERROR"),
        (r"FAILED", "FAILED"),
        (r"Exception", "Exception"),
        (r"Traceback", "Traceback"),
        (r"429.*Too Many", "HTTP 429 Rate Limit"),
        (r"WinError", "WinError"),
        (r"FileNotFoundError", "FileNotFoundError"),
    ]

    error_lines = []
    error_types = Counter()

    for line in log_content.split("\n"):
        for pattern, error_type in error_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                # Exclude false positives
                if "Skipping" in line:
                    continue
                if re.search(r"\[\d+/\d+\]", line):  # Event counter like [429/572850]
                    continue
                if "Failed: 0" in line or "Failed: 0|" in line:  # Heartbeat with 0 failures
                    continue
                if "_log_heartbeat" in line:  # Heartbeat messages
                    continue
                # Exclude DEBUG messages (they are informational, not errors)
                if "DEBUG" in line:
                    continue
                # Exclude retry messages (they are part of recovery logic, not errors)
                if "retrying" in line.lower():
                    continue

                error_lines.append(line)
                error_types[error_type] += 1
                break

    # Extract progress info
    progress_matches = re.findall(r"\[(\d+)/572850\]", log_content)
    if progress_matches:
        latest_event = int(progress_matches[-1])
        progress_pct = (latest_event / 572850) * 100
    else:
        latest_event = 0
        progress_pct = 0

    # Count downloads
    saved_trades = log_content.count("Saved") and log_content.count("trades")
    saved_quotes = log_content.count("Saved") and log_content.count("quotes")

    # Results
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print(f"Total errors found: {len(error_lines)}")
    if error_types:
        print()
        print("Error breakdown:")
        for error_type, count in error_types.most_common():
            print(f"  - {error_type}: {count}")
    print()
    print(f"Latest event processed: {latest_event:,}/572,850 ({progress_pct:.2f}%)")
    print()

    # Status
    if len(error_lines) == 0:
        print("[OK] STATUS: NO ERRORS DETECTED")
        print()
        print("The ingestion is running cleanly with no errors.")
    else:
        print(f"[WARNING] STATUS: {len(error_lines)} ERRORS DETECTED")
        print()

        if args.verbose or len(error_lines) <= 10:
            print("=" * 70)
            print("ERROR DETAILS")
            print("=" * 70)
            print()
            for line in error_lines[-args.tail:]:
                # Clean ANSI codes
                clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line)
                print(clean_line)
        else:
            print(f"(Use --verbose to see all errors, or --tail N to show last N lines)")
            print()
            print("Last 5 errors:")
            for line in error_lines[-5:]:
                clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line)
                print(f"  {clean_line[:100]}...")

    print()
    print("=" * 70)

    return 0 if len(error_lines) == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
