#!/usr/bin/env python3
"""
Robust parallel orchestrator for intraday event detection - V2
Key improvements:
- Worker-specific shard directories (no file conflicts)
- File locking for safe checkpoint updates
- Isolated symbol processing (no overlap)
- Enhanced crash recovery with detailed logging
"""
import json
import subprocess
import sys
import time
import signal
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import psutil
import polars as pl
from threading import Thread, Lock

PROJECT_ROOT = Path(__file__).resolve().parent

class FileLock:
    """Simple file-based lock for Windows/Unix compatibility"""
    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.fp = None

    def acquire(self, timeout=10):
        """Acquire lock with timeout"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.fp = open(self.lock_file, 'w')
                # Windows-compatible locking only
                import msvcrt
                msvcrt.locking(self.fp.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except (IOError, OSError):
                if self.fp:
                    self.fp.close()
                    self.fp = None
                time.sleep(0.1)
        return False

    def release(self):
        """Release lock"""
        if self.fp:
            try:
                import msvcrt
                msvcrt.locking(self.fp.fileno(), msvcrt.LK_UNLCK, 1)
            except:
                pass
            self.fp.close()
            self.fp = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class WorkerManager:
    """Manages a single worker process with isolated shard directory"""

    def __init__(self, worker_id: int, symbols: List[str], log_dir: Path):
        self.worker_id = worker_id
        self.symbols = symbols
        self.log_dir = log_dir
        self.process: Optional[subprocess.Popen] = None
        self.restarts = 0
        self.max_restarts = 10
        self.last_restart_time = None

        # Worker-specific directories
        self.checkpoint_file = PROJECT_ROOT / "logs" / "checkpoints" / f"worker_{worker_id}_checkpoint.json"
        self.log_file = log_dir / f"worker_{worker_id}.log"
        self.status = "stopped"  # stopped, running, completed, failed

        # Worker-specific shard directory (KEY CHANGE!)
        self.worker_shard_dir = PROJECT_ROOT / "processed" / "events" / "shards" / f"worker_{worker_id}"
        self.worker_shard_dir.mkdir(parents=True, exist_ok=True)

        # File lock for checkpoint
        self.checkpoint_lock = FileLock(self.checkpoint_file.with_suffix('.lock'))

        # Load or create checkpoint
        self.completed_symbols = self._load_checkpoint()

    def _load_checkpoint(self) -> set:
        """Load completed symbols from checkpoint with locking"""
        if not self.checkpoint_file.exists():
            return set()

        try:
            with self.checkpoint_lock:
                with open(self.checkpoint_file) as f:
                    data = json.load(f)
                return set(data.get("completed_symbols", []))
        except Exception as e:
            print(f"[Worker {self.worker_id}] Error loading checkpoint: {e}")
            return set()

    def _save_checkpoint(self, completed: set):
        """Save checkpoint with file locking"""
        try:
            with self.checkpoint_lock:
                self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.checkpoint_file, 'w') as f:
                    json.dump({
                        "worker_id": self.worker_id,
                        "completed_symbols": sorted(list(completed)),
                        "total_assigned": len(self.symbols),
                        "total_completed": len(completed),
                        "last_updated": datetime.now().isoformat(),
                        "restarts": self.restarts
                    }, f, indent=2)
        except Exception as e:
            print(f"[Worker {self.worker_id}] Error saving checkpoint: {e}")

    def get_remaining_symbols(self) -> List[str]:
        """Get symbols not yet completed"""
        return [s for s in self.symbols if s not in self.completed_symbols]

    def get_progress(self) -> Dict:
        """Get current progress stats"""
        remaining = self.get_remaining_symbols()
        return {
            "worker_id": self.worker_id,
            "status": self.status,
            "total": len(self.symbols),
            "completed": len(self.completed_symbols),
            "remaining": len(remaining),
            "progress_pct": len(self.completed_symbols) / len(self.symbols) * 100 if self.symbols else 0,
            "restarts": self.restarts,
            "pid": self.process.pid if self.process else None
        }

    def start(self):
        """Start the worker process with isolated shard directory"""
        remaining = self.get_remaining_symbols()

        if not remaining:
            print(f"[Worker {self.worker_id}] All symbols completed!")
            self.status = "completed"
            return False

        # Build command with worker-specific output directory
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "processing" / "detect_events_intraday.py"),
            "--symbols"
        ] + remaining + [
            "--batch-size", "50",
            "--checkpoint-interval", "1",
            "--worker-id", str(self.worker_id),  # Pass worker ID to script
            "--output-dir", str(self.worker_shard_dir)  # Worker-specific shard dir
        ]

        log_f = open(self.log_file, 'a', encoding='utf-8')
        log_f.write(f"\n{'='*80}\n")
        log_f.write(f"Worker {self.worker_id} starting at {datetime.now()}\n")
        log_f.write(f"Restart #{self.restarts}, Processing {len(remaining)} symbols\n")
        log_f.write(f"Shard directory: {self.worker_shard_dir}\n")
        log_f.write(f"{'='*80}\n\n")
        log_f.flush()

        self.process = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=PROJECT_ROOT
        )

        self.status = "running"
        self.last_restart_time = time.time()

        print(f"[Worker {self.worker_id}] Started PID {self.process.pid} ({len(remaining)} symbols)")
        return True

    def check_and_restart(self) -> bool:
        """Check if process is alive, restart if needed. Returns True if restart occurred."""
        if self.status == "completed":
            return False

        if self.process is None:
            return False

        # Check if process is still running
        returncode = self.process.poll()

        if returncode is None:
            # Still running
            return False

        # Process died
        if returncode == 0:
            # Completed successfully
            print(f"[Worker {self.worker_id}] Completed successfully")
            self.status = "completed"
            return False

        # Crashed
        print(f"[Worker {self.worker_id}] Crashed with exit code {returncode}")

        # Update checkpoint from worker's own shards
        self._update_checkpoint_from_shards()

        # Check if we can restart
        if self.restarts >= self.max_restarts:
            print(f"[Worker {self.worker_id}] Max restarts reached, marking as failed")
            self.status = "failed"
            return False

        # Restart
        self.restarts += 1
        time.sleep(2)  # Brief cooldown
        self.start()
        return True

    def _update_checkpoint_from_shards(self):
        """Update checkpoint by reading ONLY this worker's shard directory"""
        newly_completed = set()

        try:
            # Read all shards from THIS worker's directory only
            today = datetime.now().strftime('%Y%m%d')
            shard_pattern = f"events_intraday_{today}_shard*.parquet"

            for shard_file in self.worker_shard_dir.glob(shard_pattern):
                try:
                    # Read just the symbol column
                    df = pl.read_parquet(shard_file, columns=["symbol"])
                    symbols_in_shard = set(df["symbol"].unique().to_list())

                    # Check which of our assigned symbols are in this shard
                    for symbol in symbols_in_shard:
                        if symbol in self.symbols and symbol not in self.completed_symbols:
                            newly_completed.add(symbol)
                except Exception as e:
                    print(f"[Worker {self.worker_id}] Error reading shard {shard_file.name}: {e}")

        except Exception as e:
            print(f"[Worker {self.worker_id}] Error scanning shards: {e}")

        # Update checkpoint if we found new completions
        if newly_completed:
            self.completed_symbols.update(newly_completed)
            self._save_checkpoint(self.completed_symbols)
            print(f"[Worker {self.worker_id}] Checkpoint updated: +{len(newly_completed)} symbols (Total: {len(self.completed_symbols)}/{len(self.symbols)})")

    def stop(self):
        """Stop the worker process"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except:
                self.process.kill()
            self.status = "stopped"


class ParallelOrchestrator:
    """Orchestrates multiple workers with isolated shard directories"""

    def __init__(self, num_workers: int = 4):
        self.num_workers = num_workers
        self.workers: List[WorkerManager] = []
        self.log_dir = PROJECT_ROOT / "logs" / "parallel_workers"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running = False
        self.lock = Lock()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\n[Orchestrator] Shutdown signal received, stopping all workers...")
        self.running = False

    def initialize_workers(self):
        """Load symbols and create workers with non-overlapping assignments"""
        # Load all symbols
        symbols_file = PROJECT_ROOT / "processed" / "reference" / "symbols_with_1m.parquet"
        all_symbols = pl.read_parquet(symbols_file)["symbol"].to_list()
        print(f"[Orchestrator] Total symbols: {len(all_symbols)}")

        # Read global checkpoint to see what's been completed by ANY worker
        checkpoint_file = PROJECT_ROOT / "logs" / "checkpoints" / "events_intraday_20251013_completed.json"

        if checkpoint_file.exists():
            with open(checkpoint_file) as f:
                checkpoint = json.load(f)
            global_completed = set(checkpoint.get("completed_symbols", []))
            print(f"[Orchestrator] Already completed (global): {len(global_completed)}")
        else:
            global_completed = set()

        # Calculate remaining
        remaining = [s for s in all_symbols if s not in global_completed]
        print(f"[Orchestrator] Remaining: {len(remaining)}")

        if not remaining:
            print("[Orchestrator] All symbols already processed!")
            return False

        # Divide remaining symbols into NON-OVERLAPPING chunks
        chunk_size = len(remaining) // self.num_workers

        for i in range(self.num_workers):
            start_idx = i * chunk_size
            if i == self.num_workers - 1:
                end_idx = len(remaining)
            else:
                end_idx = (i + 1) * chunk_size

            worker_symbols = remaining[start_idx:end_idx]
            worker = WorkerManager(i + 1, worker_symbols, self.log_dir)
            self.workers.append(worker)

        return True

    def display_plan(self):
        """Display the execution plan"""
        print("\n" + "="*80)
        print("PARALLEL PROCESSING PLAN (V2 - Isolated Shards)")
        print("="*80)
        for w in self.workers:
            prog = w.get_progress()
            print(f"Worker {prog['worker_id']}: {prog['total']} symbols "
                  f"(completed: {prog['completed']}, remaining: {prog['remaining']})")
        print("="*80)

    def start_all_workers(self):
        """Start all workers"""
        print("\n[Orchestrator] Starting all workers...")
        for worker in self.workers:
            worker.start()
            time.sleep(1)  # Stagger starts slightly

    def monitor_loop(self):
        """Main monitoring loop"""
        self.running = True
        last_status_time = time.time()
        status_interval = 30  # Print status every 30 seconds

        while self.running:
            # Check each worker
            for worker in self.workers:
                worker.check_and_restart()

            # Check if all completed
            all_completed = all(w.status in ["completed", "failed"] for w in self.workers)
            if all_completed:
                print("\n[Orchestrator] All workers finished")
                break

            # Print status periodically
            if time.time() - last_status_time > status_interval:
                self.print_status()
                last_status_time = time.time()

            time.sleep(5)  # Check every 5 seconds

        self.running = False

    def print_status(self):
        """Print current status of all workers"""
        print("\n" + "="*80)
        print(f"STATUS UPDATE - {datetime.now().strftime('%H:%M:%S')}")
        print("="*80)

        total_completed = 0
        total_remaining = 0
        total_assigned = 0

        for worker in self.workers:
            prog = worker.get_progress()
            total_completed += prog['completed']
            total_remaining += prog['remaining']
            total_assigned += prog['total']

            status_icon = {
                "running": "[RUN]",
                "completed": "[OK]",
                "failed": "[FAIL]",
                "stopped": "[STOP]"
            }.get(prog['status'], "[?]")

            print(f"Worker {prog['worker_id']} {status_icon}: "
                  f"{prog['completed']}/{prog['total']} ({prog['progress_pct']:.1f}%) "
                  f"[PID: {prog['pid']}, Restarts: {prog['restarts']}]")

        overall_pct = (total_completed / total_assigned * 100) if total_assigned > 0 else 0
        print("-"*80)
        print(f"OVERALL: {total_completed}/{total_assigned} ({overall_pct:.1f}%) "
              f"- {total_remaining} remaining")

        if total_completed > 0:
            print(f"Estimated rate: ~{self.num_workers * 15} symbols/hour (parallel)")

        print("="*80)

    def stop_all_workers(self):
        """Stop all workers"""
        print("\n[Orchestrator] Stopping all workers...")
        for worker in self.workers:
            worker.stop()

    def run(self):
        """Main entry point"""
        print("="*80)
        print("PARALLEL INTRADAY EVENT DETECTION ORCHESTRATOR V2")
        print("="*80)

        # Initialize
        if not self.initialize_workers():
            return 0

        # Display plan
        self.display_plan()

        # Start workers
        self.start_all_workers()

        # Monitor
        try:
            self.monitor_loop()
        except KeyboardInterrupt:
            print("\n[Orchestrator] Interrupted by user")
        finally:
            self.stop_all_workers()
            self.print_status()

        # Final status
        print("\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        for worker in self.workers:
            prog = worker.get_progress()
            print(f"Worker {prog['worker_id']}: {prog['status']} - "
                  f"{prog['completed']}/{prog['total']} completed, "
                  f"{prog['restarts']} restarts")
        print("="*80)

        return 0


def main():
    orchestrator = ParallelOrchestrator(num_workers=4)
    return orchestrator.run()


if __name__ == "__main__":
    sys.exit(main())
