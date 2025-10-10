"""
Auto-continue pipeline after Week 1 completes

Monitors Week 1 download progress and automatically launches:
1. detect_events.py --use-percentiles
2. rank_by_event_count.py --top-n 2000
3. (Optional) Start Week 2-3 downloads

Usage:
    python scripts/ingestion/auto_continue_after_week1.py --top-n 2000 --events-preset compact
    python scripts/ingestion/auto_continue_after_week1.py --top-n 2000 --events-preset compact --auto-start-week23
"""

import sys
import time
import subprocess
import io
from pathlib import Path
from datetime import datetime
import argparse

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SimpleLogger:
    """Simple logger replacement for loguru"""
    @staticmethod
    def info(msg):
        print(f"[INFO] {msg}")

    @staticmethod
    def error(msg):
        print(f"[ERROR] {msg}", file=sys.stderr)

    @staticmethod
    def warning(msg):
        print(f"[WARN] {msg}")

logger = SimpleLogger()


def check_week1_complete(expected_tickers: int = 5005, tolerance: float = 0.95) -> tuple[bool, dict]:
    """
    Check if Week 1 is complete (daily + hourly bars downloaded)

    Args:
        expected_tickers: Expected number of tickers
        tolerance: Minimum completion rate (0.95 = 95%)

    Returns:
        (is_complete, stats_dict)
    """
    bars_1d_dir = PROJECT_ROOT / "raw" / "market_data" / "bars" / "1d"
    bars_1h_dir = PROJECT_ROOT / "raw" / "market_data" / "bars" / "1h"

    # Count files
    count_1d = len(list(bars_1d_dir.glob("*.parquet"))) if bars_1d_dir.exists() else 0
    count_1h = len(list(bars_1h_dir.glob("*.parquet"))) if bars_1h_dir.exists() else 0

    # Calculate completion rates
    rate_1d = count_1d / expected_tickers
    rate_1h = count_1h / expected_tickers

    stats = {
        "count_1d": count_1d,
        "count_1h": count_1h,
        "rate_1d": rate_1d,
        "rate_1h": rate_1h,
        "expected": expected_tickers
    }

    # Both must meet tolerance
    is_complete = rate_1d >= tolerance and rate_1h >= tolerance

    return is_complete, stats


def run_detect_events() -> bool:
    """Run detect_events.py with percentiles"""
    script = PROJECT_ROOT / "scripts" / "processing" / "detect_events.py"

    if not script.exists():
        logger.error(f"Script not found: {script}")
        return False

    logger.info("=" * 60)
    logger.info("STEP 1: Running event detection (triple-gate logic)")
    logger.info("=" * 60)

    # Use venv Python instead of sys.executable
    venv_python = PROJECT_ROOT / ".venv-smallcap" / "Scripts" / "python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    try:
        result = subprocess.run(
            [python_exe, str(script), "--use-percentiles"],
            check=True,
            capture_output=False
        )
        logger.info("✅ Event detection complete")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ detect_events.py failed: {e}")
        return False


def run_rank_by_events(top_n: int = 2000) -> bool:
    """Run rank_by_event_count.py"""
    script = PROJECT_ROOT / "scripts" / "processing" / "rank_by_event_count.py"

    if not script.exists():
        logger.error(f"Script not found: {script}")
        return False

    logger.info("=" * 60)
    logger.info(f"STEP 2: Ranking tickers by event count (Top-{top_n})")
    logger.info("=" * 60)

    # Use venv Python instead of sys.executable
    venv_python = PROJECT_ROOT / ".venv-smallcap" / "Scripts" / "python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    try:
        result = subprocess.run(
            [python_exe, str(script), "--top-n", str(top_n)],
            check=True,
            capture_output=False
        )
        logger.info(f"✅ Ranking complete (Top-{top_n})")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ rank_by_event_count.py failed: {e}")
        return False


def start_week23_downloads(top_n: int = 2000, events_preset: str = "compact") -> bool:
    """Start Week 2-3 downloads (Top-N minute bars + event windows)"""
    script = PROJECT_ROOT / "scripts" / "ingestion" / "download_all.py"

    if not script.exists():
        logger.error(f"Script not found: {script}")
        return False

    logger.info("=" * 60)
    logger.info("STEP 3: Starting Week 2-3 downloads")
    logger.info(f"  - Top-{top_n}: Full 3y minute bars")
    logger.info(f"  - Rest: Event windows (preset: {events_preset})")
    logger.info("=" * 60)

    # Use venv Python instead of sys.executable
    venv_python = PROJECT_ROOT / ".venv-smallcap" / "Scripts" / "python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    try:
        # Launch in background (non-blocking)
        subprocess.Popen(
            [python_exe, str(script),
             "--weeks", "2", "3",
             "--top-n", str(top_n),
             "--events-preset", events_preset],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info("✅ Week 2-3 downloads started in background")
        logger.info(f"   Monitor progress: tail -f logs/download_all.log")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to start Week 2-3: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Auto-continue pipeline after Week 1")
    parser.add_argument("--top-n", type=int, default=2000, help="Top-N for ranking and full minute bars")
    parser.add_argument("--events-preset", choices=["compact", "extended"], default="compact",
                        help="Event window preset")
    parser.add_argument("--auto-start-week23", action="store_true",
                        help="Automatically start Week 2-3 downloads after ranking")
    parser.add_argument("--check-interval", type=int, default=300,
                        help="Check interval in seconds (default: 300 = 5 min)")
    parser.add_argument("--expected-tickers", type=int, default=5005,
                        help="Expected number of tickers (default: 5005)")
    parser.add_argument("--tolerance", type=float, default=0.95,
                        help="Completion tolerance (default: 0.95 = 95%%)")
    parser.add_argument("--check-once", action="store_true",
                        help="Check once and exit (no monitoring loop)")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Auto-Continue Pipeline Monitor")
    logger.info("=" * 60)
    logger.info(f"Top-N: {args.top_n}")
    logger.info(f"Events preset: {args.events_preset}")
    logger.info(f"Auto-start Week 2-3: {args.auto_start_week23}")
    logger.info(f"Expected tickers: {args.expected_tickers}")
    logger.info(f"Tolerance: {args.tolerance * 100:.0f}%")

    if args.check_once:
        # Single check
        is_complete, stats = check_week1_complete(args.expected_tickers, args.tolerance)

        logger.info(f"\nWeek 1 Status:")
        logger.info(f"  Daily bars:  {stats['count_1d']:,} / {stats['expected']:,} ({stats['rate_1d']*100:.1f}%)")
        logger.info(f"  Hourly bars: {stats['count_1h']:,} / {stats['expected']:,} ({stats['rate_1h']*100:.1f}%)")

        if is_complete:
            logger.info("\n✅ Week 1 COMPLETE")
        else:
            logger.info("\n🔄 Week 1 still in progress")
            sys.exit(1)
    else:
        # Monitoring loop
        logger.info(f"\nMonitoring Week 1 progress (check every {args.check_interval}s)...")
        logger.info("Press Ctrl+C to stop\n")

        while True:
            is_complete, stats = check_week1_complete(args.expected_tickers, args.tolerance)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[{timestamp}] Daily: {stats['count_1d']:,}/{stats['expected']:,} ({stats['rate_1d']*100:.1f}%) | "
                       f"Hourly: {stats['count_1h']:,}/{stats['expected']:,} ({stats['rate_1h']*100:.1f}%)")

            if is_complete:
                logger.info("\n🎉 Week 1 COMPLETE! Starting next steps...")
                break

            time.sleep(args.check_interval)

    # Week 1 complete - run next steps
    logger.info("\n" + "=" * 60)
    logger.info("Week 1 Complete - Running post-processing")
    logger.info("=" * 60 + "\n")

    # Step 1: Detect events
    if not run_detect_events():
        logger.error("Failed to detect events. Stopping.")
        sys.exit(1)

    time.sleep(2)

    # Step 2: Rank by events
    if not run_rank_by_events(args.top_n):
        logger.error("Failed to rank tickers. Stopping.")
        sys.exit(1)

    time.sleep(2)

    # Step 3: Optionally start Week 2-3
    if args.auto_start_week23:
        if not start_week23_downloads(args.top_n, args.events_preset):
            logger.error("Failed to start Week 2-3 downloads")
            sys.exit(1)
    else:
        logger.info("\n" + "=" * 60)
        logger.info("Next step: Start Week 2-3 downloads manually:")
        logger.info(f"  python scripts/ingestion/download_all.py --weeks 2 3 --top-n {args.top_n} --events-preset {args.events_preset}")
        logger.info("=" * 60)

    logger.info("\n✅ Auto-continue pipeline complete")


if __name__ == "__main__":
    main()
