#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FASE 2.5 - Duplicate Events Analysis Tool

Analiza duplicados en eventos de FASE 2.5 a múltiples niveles:
1. Heartbeat log (símbolos procesados en tiempo real)
2. Checkpoint actual (progreso persistido)
3. Shards individuales
4. Archivo merged final
5. Comparación entre checkpoints y shards

Uso:
    python tools/analyze_duplicates.py
    python tools/analyze_duplicates.py --detailed
    python tools/analyze_duplicates.py --heartbeat-only
    python tools/analyze_duplicates.py --export-csv
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json
import argparse
import re
from collections import Counter

# Fix Windows console encoding
if sys.platform == "win32":
    os.system("")  # Enable ANSI escape codes
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import polars as pl
except ImportError:
    print("ERROR: polars not installed. Run: pip install polars")
    sys.exit(1)


class DuplicateAnalyzer:
    """Analizador de duplicados para FASE 2.5"""

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or PROJECT_ROOT
        self.shards_dir = self.project_root / "processed" / "events" / "shards"
        self.events_dir = self.project_root / "processed" / "events"
        self.checkpoint_dir = self.project_root / "logs" / "checkpoints"
        self.heartbeat_dir = self.project_root / "logs" / "detect_events"

    def analyze_heartbeat_log(self, tail_lines: int = 500) -> dict:
        """Analyze heartbeat log for duplicate symbol processing"""
        print(f"\n{'='*80}")
        print(f"ANALYZING HEARTBEAT LOG (Real-time Processing)")
        print(f"{'='*80}\n")

        # Find most recent heartbeat log
        today = datetime.now().strftime("%Y%m%d")
        heartbeat_file = self.heartbeat_dir / f"heartbeat_{today}.log"

        if not heartbeat_file.exists():
            # Try to find any recent heartbeat file
            candidates = sorted(self.heartbeat_dir.glob("heartbeat_*.log"), reverse=True)
            if candidates:
                heartbeat_file = candidates[0]
            else:
                print(f"ERROR: No heartbeat log found in {self.heartbeat_dir}")
                return {}

        print(f"Heartbeat file: {heartbeat_file.name}")
        print(f"Analyzing last {tail_lines} entries...\n")

        try:
            # Read last N lines efficiently
            with open(heartbeat_file, 'r', encoding='utf-8') as f:
                # Seek to end and read backwards
                f.seek(0, 2)  # End of file
                file_size = f.tell()

                # Read in chunks from the end
                block_size = 8192
                blocks = []
                lines_found = 0

                while file_size > 0 and lines_found < tail_lines:
                    read_size = min(block_size, file_size)
                    f.seek(file_size - read_size)
                    block = f.read(read_size)
                    blocks.append(block)
                    lines_found += block.count('\n')
                    file_size -= read_size

                # Reconstruct and parse
                content = ''.join(reversed(blocks))
                lines = content.splitlines()[-tail_lines:]

            # Parse symbols (format: YYYY-MM-DD HH:MM:SS.mmm    SYMBOL    ...)
            symbols = []
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    # Third column is the symbol
                    symbol = parts[2]
                    symbols.append(symbol)

            # Count duplicates
            symbol_counts = Counter(symbols)
            total_symbols = len(symbols)
            unique_symbols = len(symbol_counts)
            duplicated_symbols = {sym: count for sym, count in symbol_counts.items() if count > 1}
            total_duplications = sum(count - 1 for count in duplicated_symbols.values())

            # Calculate duplication rate
            dup_rate = (total_duplications / total_symbols * 100) if total_symbols > 0 else 0

            print(f"{'='*80}")
            print(f"HEARTBEAT ANALYSIS RESULTS")
            print(f"{'='*80}")
            print(f"Total entries analyzed: {total_symbols:,}")
            print(f"Unique symbols: {unique_symbols:,}")
            print(f"Symbols with duplicates: {len(duplicated_symbols):,}")
            print(f"Total duplicate entries: {total_duplications:,}")
            print(f"Duplication rate: {dup_rate:.2f}%")
            print()

            # Status
            if dup_rate < 5:
                status = "✓ EXCELLENT"
            elif dup_rate < 10:
                status = "✓ GOOD"
            elif dup_rate < 20:
                status = "⚠ WARNING"
            else:
                status = "✗ CRITICAL"

            print(f"Status: {status}")
            print()

            # Show top duplicated symbols
            if duplicated_symbols:
                top_dups = sorted(duplicated_symbols.items(), key=lambda x: x[1], reverse=True)[:20]
                print(f"Top 20 symbols with most duplications:")
                for symbol, count in top_dups:
                    print(f"  {symbol:8s}: {count:2d} times (duplicated {count-1} times)")
                print()

            return {
                "heartbeat_file": heartbeat_file.name,
                "total_entries": total_symbols,
                "unique_symbols": unique_symbols,
                "duplicated_symbols": len(duplicated_symbols),
                "total_duplications": total_duplications,
                "dup_rate_pct": dup_rate,
                "status": status,
                "top_duplicates": top_dups[:10] if duplicated_symbols else []
            }

        except Exception as e:
            print(f"ERROR analyzing heartbeat: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def analyze_current_checkpoint(self) -> dict:
        """Analyze current checkpoint progress"""
        print(f"\n{'='*80}")
        print(f"ANALYZING CURRENT CHECKPOINT")
        print(f"{'='*80}\n")

        # Find today's checkpoint
        today = datetime.now().strftime("%Y%m%d")
        checkpoint_file = self.checkpoint_dir / f"events_intraday_{today}_completed.json"

        if not checkpoint_file.exists():
            # Try to find most recent checkpoint
            candidates = sorted(self.checkpoint_dir.glob("events_intraday_*_completed.json"), reverse=True)
            if candidates:
                checkpoint_file = candidates[0]
            else:
                print(f"ERROR: No checkpoint found in {self.checkpoint_dir}")
                return {}

        print(f"Checkpoint file: {checkpoint_file.name}")

        try:
            data = json.load(open(checkpoint_file, encoding='utf-8'))

            total_completed = data.get("total_completed", 0)
            run_id = data.get("run_id", "unknown")
            last_updated = data.get("last_updated", "unknown")
            completed_symbols = data.get("completed_symbols", [])

            print(f"Run ID: {run_id}")
            print(f"Last updated: {last_updated}")
            print(f"Total completed: {total_completed:,}")
            print(f"Symbols in checkpoint: {len(completed_symbols):,}")
            print()

            # Calculate progress (assuming 1,996 total symbols from FASE 2.5)
            total_symbols = 1996
            progress_pct = (total_completed / total_symbols * 100) if total_symbols > 0 else 0
            remaining = total_symbols - total_completed

            print(f"{'='*80}")
            print(f"PROGRESS SUMMARY")
            print(f"{'='*80}")
            print(f"Total symbols in universe: {total_symbols:,}")
            print(f"Completed: {total_completed:,} ({progress_pct:.1f}%)")
            print(f"Remaining: {remaining:,}")
            print()

            # Progress bar
            bar_width = 50
            filled = int(bar_width * progress_pct / 100)
            bar = '█' * filled + '░' * (bar_width - filled)
            print(f"Progress: [{bar}] {progress_pct:.1f}%")
            print()

            return {
                "checkpoint_file": checkpoint_file.name,
                "run_id": run_id,
                "last_updated": last_updated,
                "total_completed": total_completed,
                "total_symbols": total_symbols,
                "progress_pct": progress_pct,
                "remaining": remaining
            }

        except Exception as e:
            print(f"ERROR analyzing checkpoint: {e}")
            return {"error": str(e)}

    def find_recent_shards(self, days: int = 7) -> list[Path]:
        """Find all shards from last N days"""
        cutoff = datetime.now() - timedelta(days=days)
        shards = []

        for shard in self.shards_dir.rglob("events_intraday_*.parquet"):
            try:
                # Extract date from filename
                parts = shard.stem.split("_")
                date_str = parts[2]  # events_intraday_YYYYMMDD_shardXXXX
                shard_date = datetime.strptime(date_str, "%Y%m%d")

                if shard_date >= cutoff:
                    shards.append(shard)
            except (IndexError, ValueError):
                continue

        return sorted(shards)

    def analyze_single_shard(self, shard_path: Path) -> dict:
        """Analyze duplicates in a single shard"""
        try:
            df = pl.read_parquet(shard_path)

            # Define unique key columns
            key_cols = ["symbol", "timestamp", "event_type"]

            # Count total and unique
            total = len(df)
            unique = df.select(key_cols).n_unique()

            duplicates = total - unique
            dup_rate = (duplicates / total * 100) if total > 0 else 0

            return {
                "file": shard_path.name,
                "total_events": total,
                "unique_events": unique,
                "duplicates": duplicates,
                "dup_rate_pct": dup_rate,
                "status": "OK" if dup_rate < 5 else "WARNING" if dup_rate < 10 else "CRITICAL"
            }
        except Exception as e:
            return {
                "file": shard_path.name,
                "error": str(e),
                "status": "ERROR"
            }

    def analyze_all_shards(self, days: int = 7) -> pl.DataFrame:
        """Analyze all recent shards"""
        print(f"\n{'='*80}")
        print(f"ANALYZING SHARDS (last {days} days)")
        print(f"{'='*80}\n")

        shards = self.find_recent_shards(days)
        print(f"Found {len(shards)} shards to analyze...")

        results = []
        for i, shard in enumerate(shards, 1):
            if i % 50 == 0:
                print(f"  Processed {i}/{len(shards)} shards...")

            result = self.analyze_single_shard(shard)
            results.append(result)

        print(f"✓ Analyzed {len(shards)} shards\n")

        # Convert to DataFrame
        df = pl.DataFrame(results)

        # Filter out errors
        df_ok = df.filter(pl.col("status") != "ERROR")

        if len(df_ok) == 0:
            print("WARNING: No valid shards found!")
            return df

        # Summary stats
        total_events = df_ok["total_events"].sum()
        total_unique = df_ok["unique_events"].sum()
        total_dups = df_ok["duplicates"].sum()
        avg_dup_rate = df_ok["dup_rate_pct"].mean()

        print(f"{'='*80}")
        print(f"SHARD-LEVEL SUMMARY")
        print(f"{'='*80}")
        print(f"Total shards analyzed: {len(df_ok)}")
        print(f"Total events: {total_events:,}")
        print(f"Unique events: {total_unique:,}")
        print(f"Duplicates: {total_dups:,}")
        print(f"Average dup rate: {avg_dup_rate:.2f}%")
        print()

        # Breakdown by status
        status_counts = df.group_by("status").len().sort("len", descending=True)
        print("Breakdown by status:")
        for row in status_counts.iter_rows(named=True):
            print(f"  {row['status']:10s}: {row['len']:5d} shards")
        print()

        # Worst offenders
        worst = df_ok.filter(pl.col("dup_rate_pct") > 0).sort("dup_rate_pct", descending=True).head(10)
        if len(worst) > 0:
            print("Top 10 shards with highest duplication:")
            for row in worst.iter_rows(named=True):
                print(f"  {row['file']:50s} {row['dup_rate_pct']:6.2f}% ({row['duplicates']:,} dups)")
        else:
            print("✓ No duplicates found in any shard!")
        print()

        return df

    def analyze_merged_file(self, file_path: Path = None) -> dict:
        """Analyze duplicates in merged events file"""
        print(f"\n{'='*80}")
        print(f"ANALYZING MERGED FILE")
        print(f"{'='*80}\n")

        # Auto-detect most recent merged file if not provided
        if file_path is None:
            candidates = sorted(self.events_dir.glob("events_intraday_*.parquet"), reverse=True)
            # Exclude enriched/dedup versions
            for candidate in candidates:
                if "enriched" not in candidate.name and "dedup" not in candidate.name and "shard" not in candidate.name:
                    file_path = candidate
                    break

        if file_path is None or not file_path.exists():
            print(f"ERROR: No merged file found in {self.events_dir}")
            return {}

        print(f"File: {file_path.name}")
        print(f"Size: {file_path.stat().st_size / 1024**2:.1f} MB\n")

        try:
            df = pl.read_parquet(file_path)
            key_cols = ["symbol", "timestamp", "event_type"]

            total = len(df)
            unique = df.select(key_cols).n_unique()
            duplicates = total - unique
            dup_rate = (duplicates / total * 100) if total > 0 else 0

            print(f"Total events: {total:,}")
            print(f"Unique events: {unique:,}")
            print(f"Duplicates: {duplicates:,}")
            print(f"Duplication rate: {dup_rate:.2f}%")
            print()

            # Status
            if dup_rate < 5:
                status = "✓ GOOD"
                color = "green"
            elif dup_rate < 10:
                status = "⚠ WARNING"
                color = "yellow"
            else:
                status = "✗ CRITICAL"
                color = "red"

            print(f"Status: {status}")
            print()

            # Find which symbols have duplicates
            if duplicates > 0:
                print("Analyzing symbols with duplicates...")
                dup_groups = df.group_by(key_cols).len().filter(pl.col("len") > 1)
                symbols_with_dups = dup_groups.select("symbol").unique().to_series().to_list()

                print(f"Symbols with duplicates: {len(symbols_with_dups)}")
                print(f"Top 10 symbols by duplicate count:")

                symbol_dup_counts = (
                    dup_groups.group_by("symbol")
                    .agg(pl.col("len").sum().alias("total_dups"))
                    .sort("total_dups", descending=True)
                    .head(10)
                )

                for row in symbol_dup_counts.iter_rows(named=True):
                    print(f"  {row['symbol']:6s}: {row['total_dups']:,} duplicate events")
                print()

            return {
                "file": file_path.name,
                "total_events": total,
                "unique_events": unique,
                "duplicates": duplicates,
                "dup_rate_pct": dup_rate,
                "status": status
            }

        except Exception as e:
            print(f"ERROR: {e}")
            return {"error": str(e)}

    def merge_all_shards(self, output_file: Path = None) -> Path:
        """Merge all recent shards into a single file"""
        print(f"\n{'='*80}")
        print(f"MERGING ALL SHARDS")
        print(f"{'='*80}\n")

        shards = self.find_recent_shards(days=14)
        print(f"Found {len(shards)} shards to merge...")

        if len(shards) == 0:
            print("ERROR: No shards found!")
            return None

        all_dfs = []
        for i, shard in enumerate(shards, 1):
            if i % 50 == 0:
                print(f"  Loading {i}/{len(shards)} shards...")

            try:
                df = pl.read_parquet(shard)
                all_dfs.append(df)
            except Exception as e:
                print(f"  WARNING: Failed to load {shard.name}: {e}")
                continue

        print(f"✓ Loaded {len(all_dfs)} shards")
        print("Merging...")

        merged = pl.concat(all_dfs, how="diagonal")
        merged = merged.sort(["symbol", "timestamp"])

        if output_file is None:
            today = datetime.now().strftime("%Y%m%d")
            output_file = self.events_dir / f"events_intraday_merged_{today}.parquet"

        merged.write_parquet(output_file, compression="zstd")

        print(f"✓ Merged file saved: {output_file}")
        print(f"  Total events: {len(merged):,}")
        print(f"  Size: {output_file.stat().st_size / 1024**2:.1f} MB")
        print()

        return output_file

    def compare_checkpoints_vs_shards(self) -> dict:
        """Compare symbols in checkpoints vs symbols in shards"""
        print(f"\n{'='*80}")
        print(f"COMPARING CHECKPOINTS VS SHARDS")
        print(f"{'='*80}\n")

        # Load all checkpoints
        all_completed = set()
        checkpoint_files = []

        for ckpt_file in sorted(self.checkpoint_dir.glob("events_intraday_*_completed.json")):
            try:
                data = json.load(open(ckpt_file))
                symbols = set(data.get("completed_symbols", []))
                all_completed.update(symbols)
                checkpoint_files.append((ckpt_file.name, len(symbols)))
            except Exception as e:
                print(f"WARNING: Failed to load {ckpt_file.name}: {e}")
                continue

        print(f"Checkpoints loaded: {len(checkpoint_files)}")
        print(f"Unique symbols in checkpoints: {len(all_completed)}")
        print()

        # Find symbols in shards
        shards = self.find_recent_shards(days=14)
        symbols_in_shards = set()

        print(f"Scanning {len(shards)} shards for symbols...")
        for i, shard in enumerate(shards, 1):
            if i % 50 == 0:
                print(f"  Scanned {i}/{len(shards)} shards...")

            try:
                df = pl.read_parquet(shard)
                symbols = df.select("symbol").unique().to_series().to_list()
                symbols_in_shards.update(symbols)
            except:
                continue

        print(f"✓ Unique symbols in shards: {len(symbols_in_shards)}")
        print()

        # Compare
        in_checkpoint_not_shard = all_completed - symbols_in_shards
        in_shard_not_checkpoint = symbols_in_shards - all_completed
        in_both = all_completed & symbols_in_shards

        print(f"{'='*80}")
        print(f"COMPARISON RESULTS")
        print(f"{'='*80}")
        print(f"In both checkpoint AND shards: {len(in_both)}")
        print(f"In checkpoint but NOT in shards: {len(in_checkpoint_not_shard)}")
        print(f"In shards but NOT in checkpoint: {len(in_shard_not_checkpoint)}")
        print()

        if len(in_checkpoint_not_shard) > 0:
            print(f"⚠ WARNING: {len(in_checkpoint_not_shard)} symbols marked complete but no shards found!")
            if len(in_checkpoint_not_shard) <= 20:
                print(f"  Symbols: {sorted(in_checkpoint_not_shard)}")
            print()

        if len(in_shard_not_checkpoint) > 0:
            print(f"⚠ WARNING: {len(in_shard_not_checkpoint)} symbols have shards but not in checkpoint!")
            if len(in_shard_not_checkpoint) <= 20:
                print(f"  Symbols: {sorted(in_shard_not_checkpoint)}")
            print()

        return {
            "checkpoint_symbols": len(all_completed),
            "shard_symbols": len(symbols_in_shards),
            "in_both": len(in_both),
            "checkpoint_only": len(in_checkpoint_not_shard),
            "shard_only": len(in_shard_not_checkpoint)
        }

    def run_full_analysis(self, detailed: bool = False, export_csv: bool = False, heartbeat_only: bool = False):
        """Run complete duplicate analysis"""
        print(f"\n{'='*80}")
        print(f"FASE 2.5 - DUPLICATE EVENTS ANALYSIS")
        print(f"{'='*80}")
        print(f"Project root: {self.project_root}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

        results = {}

        # 0. Analyze heartbeat log (real-time processing)
        heartbeat_analysis = self.analyze_heartbeat_log(tail_lines=500)
        results["heartbeat_analysis"] = heartbeat_analysis

        # 0.5. Analyze current checkpoint
        checkpoint_analysis = self.analyze_current_checkpoint()
        results["checkpoint_analysis"] = checkpoint_analysis

        if heartbeat_only:
            print(f"\n{'='*80}")
            print(f"HEARTBEAT-ONLY ANALYSIS COMPLETE")
            print(f"{'='*80}\n")
            return results

        # 1. Analyze shards
        shard_analysis = self.analyze_all_shards(days=7)
        results["shard_analysis"] = shard_analysis

        if export_csv and len(shard_analysis) > 0:
            csv_path = self.project_root / f"analysis_shards_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            shard_analysis.write_csv(csv_path)
            print(f"✓ Shard analysis exported to: {csv_path}\n")

        # 2. Analyze merged file (or merge if needed)
        merged_files = list(self.events_dir.glob("events_intraday_2025*.parquet"))
        merged_files = [f for f in merged_files if "enriched" not in f.name and "dedup" not in f.name and "shard" not in f.name]

        if len(merged_files) > 0:
            latest_merged = sorted(merged_files, reverse=True)[0]
            merged_analysis = self.analyze_merged_file(latest_merged)
            results["merged_analysis"] = merged_analysis
        else:
            print("No merged file found. Skipping merged analysis...")

        # 3. Compare checkpoints vs shards
        comparison = self.compare_checkpoints_vs_shards()
        results["comparison"] = comparison

        # Final summary
        print(f"\n{'='*80}")
        print(f"FINAL SUMMARY")
        print(f"{'='*80}")

        # Heartbeat summary
        if heartbeat_analysis and "error" not in heartbeat_analysis:
            print(f"\n📊 Real-time Processing (Heartbeat):")
            print(f"  Total entries analyzed: {heartbeat_analysis.get('total_entries', 0):,}")
            print(f"  Unique symbols: {heartbeat_analysis.get('unique_symbols', 0):,}")
            print(f"  Duplicated symbols: {heartbeat_analysis.get('duplicated_symbols', 0):,}")
            print(f"  Duplication rate: {heartbeat_analysis.get('dup_rate_pct', 0):.2f}%")
            print(f"  Status: {heartbeat_analysis.get('status', 'UNKNOWN')}")

        # Checkpoint summary
        if checkpoint_analysis and "error" not in checkpoint_analysis:
            print(f"\n💾 Checkpoint Progress:")
            print(f"  Completed: {checkpoint_analysis.get('total_completed', 0):,} / {checkpoint_analysis.get('total_symbols', 0):,}")
            print(f"  Progress: {checkpoint_analysis.get('progress_pct', 0):.1f}%")
            print(f"  Remaining: {checkpoint_analysis.get('remaining', 0):,} symbols")

        # Merged file summary
        if "merged_analysis" in results and results["merged_analysis"]:
            ma = results["merged_analysis"]
            print(f"\n📁 Merged File Analysis:")
            print(f"  File: {ma.get('file', 'N/A')}")
            print(f"  Total events: {ma.get('total_events', 0):,}")
            print(f"  Duplicates: {ma.get('duplicates', 0):,}")
            print(f"  Duplication rate: {ma.get('dup_rate_pct', 0):.2f}%")
            print(f"  Status: {ma.get('status', 'UNKNOWN')}")

        # Checkpoint vs shards
        if comparison:
            print(f"\n🔍 Checkpoint vs Shards:")
            print(f"  Checkpoint symbols: {comparison.get('checkpoint_symbols', 0):,}")
            print(f"  Shard symbols: {comparison.get('shard_symbols', 0):,}")
            print(f"  Discrepancy: {abs(comparison.get('checkpoint_symbols', 0) - comparison.get('shard_symbols', 0)):,}")

        print(f"\n{'='*80}")
        print(f"ANALYSIS COMPLETE")
        print(f"{'='*80}\n")

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Analyze duplicate events in FASE 2.5"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed analysis per shard"
    )
    parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Export shard analysis to CSV"
    )
    parser.add_argument(
        "--heartbeat-only",
        action="store_true",
        help="Only analyze heartbeat log (fast check)"
    )
    parser.add_argument(
        "--merge-only",
        action="store_true",
        help="Only merge shards, don't analyze"
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=500,
        help="Number of heartbeat lines to analyze (default: 500)"
    )

    args = parser.parse_args()

    analyzer = DuplicateAnalyzer()

    if args.merge_only:
        analyzer.merge_all_shards()
    else:
        analyzer.run_full_analysis(
            detailed=args.detailed,
            export_csv=args.export_csv,
            heartbeat_only=args.heartbeat_only
        )


if __name__ == "__main__":
    main()
