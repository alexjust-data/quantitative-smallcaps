"""
Quick download status checker

Shows current progress of all download stages.

Usage:
    python scripts/ingestion/check_download_status.py
    python scripts/ingestion/check_download_status.py --verbose
"""

import sys
import argparse
import io
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def human_size(bytes_size: float) -> str:
    """Convert bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def check_stage(stage_name: str, path: Path, pattern: str = "*.parquet",
                expected: int = None, recursive: bool = False) -> dict:
    """Check completion status of a download stage"""
    if not path.exists():
        return {
            "exists": False,
            "count": 0,
            "size": 0,
            "latest": None,
            "rate": 0.0
        }

    # Count files
    if recursive:
        files = list(path.rglob(pattern))
    else:
        files = list(path.glob(pattern))

    count = len(files)

    # Calculate size
    total_size = sum(f.stat().st_size for f in files if f.is_file())

    # Find latest file
    latest_file = None
    latest_time = None
    if files:
        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        latest_time = datetime.fromtimestamp(latest_file.stat().st_mtime)

    # Calculate completion rate
    rate = (count / expected * 100) if expected else 0.0

    return {
        "exists": True,
        "count": count,
        "size": total_size,
        "size_human": human_size(total_size),
        "latest": latest_file.name if latest_file else None,
        "latest_time": latest_time,
        "rate": rate,
        "expected": expected
    }


def main():
    parser = argparse.ArgumentParser(description="Check download progress")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed information")
    parser.add_argument("--expected-tickers", type=int, default=5005, help="Expected small caps count")
    args = parser.parse_args()

    print("=" * 70)
    print("DOWNLOAD STATUS REPORT")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Week 1: Reference data
    print("📊 WEEK 1: Foundation Data")
    print("-" * 70)

    # Tickers
    ref_dir = PROJECT_ROOT / "raw" / "reference"
    active_tickers = check_stage("Active Tickers", ref_dir, "tickers_active_*.parquet")
    delisted_tickers = check_stage("Delisted Tickers", ref_dir, "tickers_delisted_*.parquet")

    print(f"  Tickers (Active):    {active_tickers['count']} files, {active_tickers['size_human']}")
    print(f"  Tickers (Delisted):  {delisted_tickers['count']} files, {delisted_tickers['size_human']}")

    # Corporate actions
    splits = check_stage("Splits", ref_dir, "splits_*.parquet")
    dividends = check_stage("Dividends", ref_dir, "dividends_*.parquet")

    print(f"  Splits:              {splits['count']} files, {splits['size_human']}")
    print(f"  Dividends:           {dividends['count']} files, {dividends['size_human']}")

    # Daily bars
    bars_1d_dir = PROJECT_ROOT / "raw" / "market_data" / "bars" / "1d"
    daily = check_stage("Daily Bars", bars_1d_dir, "*.parquet", expected=args.expected_tickers)

    status_1d = "✅" if daily['rate'] >= 95 else "🔄"
    print(f"\n  {status_1d} Daily bars (1d):     {daily['count']:,} / {args.expected_tickers:,} ({daily['rate']:.1f}%)")
    print(f"     Size: {daily['size_human']}")
    if daily['latest']:
        print(f"     Latest: {daily['latest']} ({daily['latest_time'].strftime('%Y-%m-%d %H:%M:%S')})")

    # Hourly bars
    bars_1h_dir = PROJECT_ROOT / "raw" / "market_data" / "bars" / "1h"
    hourly = check_stage("Hourly Bars", bars_1h_dir, "*.parquet", expected=args.expected_tickers)

    status_1h = "✅" if hourly['rate'] >= 95 else "🔄"
    print(f"\n  {status_1h} Hourly bars (1h):    {hourly['count']:,} / {args.expected_tickers:,} ({hourly['rate']:.1f}%)")
    print(f"     Size: {hourly['size_human']}")
    if hourly['latest']:
        print(f"     Latest: {hourly['latest']} ({hourly['latest_time'].strftime('%Y-%m-%d %H:%M:%S')})")

    # Week 1 status
    week1_complete = daily['rate'] >= 95 and hourly['rate'] >= 95
    print(f"\n  Week 1 Status: {'✅ COMPLETE' if week1_complete else '🔄 IN PROGRESS'}")

    # Processing: Events
    print("\n📈 PROCESSING: Event Detection")
    print("-" * 70)

    events_dir = PROJECT_ROOT / "processed" / "events"
    events = check_stage("Events", events_dir, "events_daily_*.parquet")

    if events['count'] > 0:
        print(f"  ✅ Events detected:  {events['count']} files, {events['size_human']}")
        if events['latest']:
            print(f"     Latest: {events['latest']}")
    else:
        print(f"  ⏳ Not started (run after Week 1 completes)")

    # Processing: Rankings
    rankings_dir = PROJECT_ROOT / "processed" / "rankings"
    rankings = check_stage("Rankings", rankings_dir, "top_*_by_events_*.parquet")

    if rankings['count'] > 0:
        print(f"  ✅ Rankings:         {rankings['count']} files, {rankings['size_human']}")
        if rankings['latest']:
            print(f"     Latest: {rankings['latest']}")
    else:
        print(f"  ⏳ Not started (run after event detection)")

    # Week 2-3: Minute bars (Top-N)
    print("\n⚡ WEEK 2-3: Minute Bars (Top-N)")
    print("-" * 70)

    bars_1m_dir = PROJECT_ROOT / "raw" / "market_data" / "bars" / "1m"
    if bars_1m_dir.exists():
        # Count symbols (directories)
        symbols_1m = [d for d in bars_1m_dir.iterdir() if d.is_dir()]
        files_1m = list(bars_1m_dir.rglob("*.parquet"))
        size_1m = sum(f.stat().st_size for f in files_1m)

        print(f"  📁 Symbols:          {len(symbols_1m):,}")
        print(f"  📄 Files:            {len(files_1m):,}")
        print(f"  💾 Size:             {human_size(size_1m)}")

        if files_1m:
            latest_1m = max(files_1m, key=lambda f: f.stat().st_mtime)
            latest_time_1m = datetime.fromtimestamp(latest_1m.stat().st_mtime)
            print(f"  🕐 Latest:           {latest_1m.parent.name}/{latest_1m.name}")
            print(f"                       ({latest_time_1m.strftime('%Y-%m-%d %H:%M:%S')})")
    else:
        print(f"  ⏳ Not started")

    # Week 2-3: Event windows
    print("\n🪟 WEEK 2-3: Event Windows (Rest)")
    print("-" * 70)

    events_bars_dir = PROJECT_ROOT / "raw" / "market_data" / "events"
    if events_bars_dir.exists():
        # Count symbols
        symbols_events = [d for d in events_bars_dir.iterdir() if d.is_dir()]
        # Count event directories
        event_dirs = [d for sym_dir in symbols_events for d in sym_dir.iterdir() if d.is_dir()]
        # Count window files
        window_files = list(events_bars_dir.rglob("minute_*.parquet"))
        size_events = sum(f.stat().st_size for f in window_files)

        print(f"  📁 Symbols:          {len(symbols_events):,}")
        print(f"  📅 Events:           {len(event_dirs):,}")
        print(f"  🪟 Windows:          {len(window_files):,}")
        print(f"  💾 Size:             {human_size(size_events)}")

        if window_files:
            latest_event = max(window_files, key=lambda f: f.stat().st_mtime)
            latest_time_event = datetime.fromtimestamp(latest_event.stat().st_mtime)
            print(f"  🕐 Latest:           {latest_event.parent.parent.name}/{latest_event.parent.name}/{latest_event.name}")
            print(f"                       ({latest_time_event.strftime('%Y-%m-%d %H:%M:%S')})")
    else:
        print(f"  ⏳ Not started")

    # Week 4: Complementary
    print("\n📚 WEEK 4: Complementary Data")
    print("-" * 70)

    comp_dir = PROJECT_ROOT / "raw" / "market_data" / "complementary"
    short_interest = check_stage("Short Interest", comp_dir, "short_interest_*.parquet")
    short_volume = check_stage("Short Volume", comp_dir, "short_volume_*.parquet")

    if short_interest['count'] > 0:
        print(f"  ✅ Short Interest:   {short_interest['count']} files, {short_interest['size_human']}")
    else:
        print(f"  ⏳ Short Interest:   Not started")

    if short_volume['count'] > 0:
        print(f"  ✅ Short Volume:     {short_volume['count']} files, {short_volume['size_human']}")
    else:
        print(f"  ⏳ Short Volume:     Not started")

    # Total storage
    print("\n💾 TOTAL STORAGE")
    print("-" * 70)

    raw_dir = PROJECT_ROOT / "raw"
    processed_dir = PROJECT_ROOT / "processed"

    if raw_dir.exists():
        raw_files = list(raw_dir.rglob("*.parquet"))
        raw_size = sum(f.stat().st_size for f in raw_files)
        print(f"  Raw data:            {len(raw_files):,} files, {human_size(raw_size)}")

    if processed_dir.exists():
        processed_files = list(processed_dir.rglob("*.parquet"))
        processed_size = sum(f.stat().st_size for f in processed_files)
        print(f"  Processed data:      {len(processed_files):,} files, {human_size(processed_size)}")

    # Recommendations
    print("\n🎯 NEXT STEPS")
    print("-" * 70)

    if not week1_complete:
        remaining_1h = args.expected_tickers - hourly['count']
        print(f"  ⏳ Wait for Week 1 to complete ({remaining_1h:,} hourly files remaining)")
        print(f"     Estimated: ~{remaining_1h / 100:.1f} hours at current rate")
    elif events['count'] == 0:
        print(f"  ▶️  Run event detection:")
        print(f"     python scripts/ingestion/auto_continue_after_week1.py --check-once")
        print(f"     (or)")
        print(f"     python scripts/processing/detect_events.py --use-percentiles")
    elif rankings['count'] == 0:
        print(f"  ▶️  Run ranking:")
        print(f"     python scripts/processing/rank_by_event_count.py --top-n 2000")
    else:
        print(f"  ▶️  Start Week 2-3 downloads:")
        print(f"     python scripts/ingestion/download_all.py --weeks 2 3 --top-n 2000 --events-preset compact")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
