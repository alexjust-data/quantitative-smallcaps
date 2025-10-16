#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FASE 2.5 - Duplicate Events Analysis Tool

Analiza duplicados en eventos de FASE 2.5 a múltiples niveles:
1. Shards individuales
2. Archivo merged final
3. Comparación entre checkpoints y shards
4. Identificación de símbolos con duplicados

Uso:
    python tools/analyze_duplicates.py
    python tools/analyze_duplicates.py --detailed
    python tools/analyze_duplicates.py --export-csv
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json
import argparse

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

    def run_full_analysis(self, detailed: bool = False, export_csv: bool = False):
        """Run complete duplicate analysis"""
        print(f"\n{'='*80}")
        print(f"FASE 2.5 - DUPLICATE EVENTS ANALYSIS")
        print(f"{'='*80}")
        print(f"Project root: {self.project_root}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

        results = {}

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
            print("No merged file found. Merging shards...")
            merged_file = self.merge_all_shards()
            if merged_file:
                merged_analysis = self.analyze_merged_file(merged_file)
                results["merged_analysis"] = merged_analysis

        # 3. Compare checkpoints vs shards
        comparison = self.compare_checkpoints_vs_shards()
        results["comparison"] = comparison

        # Final summary
        print(f"\n{'='*80}")
        print(f"FINAL SUMMARY")
        print(f"{'='*80}")

        if "merged_analysis" in results and results["merged_analysis"]:
            ma = results["merged_analysis"]
            print(f"\nMerged File Analysis:")
            print(f"  File: {ma.get('file', 'N/A')}")
            print(f"  Total events: {ma.get('total_events', 0):,}")
            print(f"  Duplicates: {ma.get('duplicates', 0):,}")
            print(f"  Duplication rate: {ma.get('dup_rate_pct', 0):.2f}%")
            print(f"  Status: {ma.get('status', 'UNKNOWN')}")

        print(f"\nCheckpoint vs Shards:")
        print(f"  Checkpoint symbols: {comparison['checkpoint_symbols']}")
        print(f"  Shard symbols: {comparison['shard_symbols']}")
        print(f"  Discrepancy: {abs(comparison['checkpoint_symbols'] - comparison['shard_symbols'])}")

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
        "--merge-only",
        action="store_true",
        help="Only merge shards, don't analyze"
    )

    args = parser.parse_args()

    analyzer = DuplicateAnalyzer()

    if args.merge_only:
        analyzer.merge_all_shards()
    else:
        analyzer.run_full_analysis(
            detailed=args.detailed,
            export_csv=args.export_csv
        )


if __name__ == "__main__":
    main()
