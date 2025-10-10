"""
Direct launcher for Week 2-3 using existing ranking (skip event detection validation)
"""
import sys
from pathlib import Path

# Add scripts to path
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "scripts"))

from ingestion.download_all import HistoricalDownloader

def main():
    downloader = HistoricalDownloader()

    # Use existing ranking file
    ranking = BASE / "processed" / "rankings" / "top_2000_by_events_20251009.parquet"

    if not ranking.exists():
        print(f"[ERROR] Ranking not found: {ranking}")
        return

    print(f"[OK] Using ranking: {ranking}")
    print("[OK] Launching Week 2-3 Top-2000 1-min bar download...")

    # Launch Week 2-3 directly
    downloader.download_minute_for_topN(ranking)

    print("[OK] Week 2-3 download complete!")

if __name__ == "__main__":
    main()
