#!/usr/bin/env python3
"""
ULTRA ROBUST ORCHESTRATOR - Maximum logging and error handling
Logs EVERYTHING to understand why processes die
"""
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime
import psutil

PROJECT_ROOT = Path(__file__).resolve().parent

# Setup logging directory
LOG_DIR = PROJECT_ROOT / "logs" / "ultra_robust"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def log(msg, level="INFO"):
    """Log with timestamp to both console and file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_msg = f"[{timestamp}] [{level}] {msg}"
    print(log_msg, flush=True)

    # Write to master log
    log_file = LOG_DIR / f"orchestrator_{datetime.now().strftime('%Y%m%d')}.log"
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(log_msg + '\n')
        f.flush()

def check_process_alive(pid):
    """Check if process is really alive"""
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False

class WorkerProcess:
    """Manages ONE worker with extreme logging"""

    def __init__(self, worker_id, symbols, max_restarts=20):
        self.worker_id = worker_id
        self.symbols = symbols
        self.max_restarts = max_restarts
        self.restarts = 0
        self.process = None
        self.pid = None
        self.start_time = None
        self.log_file = LOG_DIR / f"worker_{worker_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        log(f"Worker {worker_id} initialized with {len(symbols)} symbols", "INFO")

    def start(self):
        """Start worker process with full logging"""
        if self.process and check_process_alive(self.process.pid):
            log(f"Worker {self.worker_id}: Already running PID {self.process.pid}", "WARN")
            return True

        log(f"Worker {self.worker_id}: Starting (restart #{self.restarts})", "INFO")

        # Aislar salida de shards por worker para evitar colisiones
        worker_out = PROJECT_ROOT / "processed" / "events" / "shards" / f"worker_{self.worker_id}"
        worker_out.mkdir(parents=True, exist_ok=True)

        # Build command
        cmd = [
            sys.executable,
            "-u",  # Unbuffered output
            str(PROJECT_ROOT / "scripts" / "processing" / "detect_events_intraday.py"),
            "--symbols"
        ] + self.symbols + [  # Process ALL assigned symbols
            "--batch-size", "50",
            "--checkpoint-interval", "1",
            "--resume",
            "--output-dir", str(worker_out)
        ]

        log(f"Worker {self.worker_id}: Command: {' '.join(cmd[:20])}...", "DEBUG")

        try:
            # Open log file
            log_f = open(self.log_file, 'a', encoding='utf-8', buffering=1)
            log_f.write(f"\n{'='*80}\n")
            log_f.write(f"Worker {self.worker_id} starting at {datetime.now()}\n")
            log_f.write(f"Restart #{self.restarts}\n")
            log_f.write(f"Command: {' '.join(cmd)}\n")
            log_f.write(f"{'='*80}\n\n")
            log_f.flush()

            # Start process
            self.process = subprocess.Popen(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=PROJECT_ROOT,
                bufsize=1,
                universal_newlines=True
            )

            self.pid = self.process.pid
            self.start_time = time.time()

            log(f"Worker {self.worker_id}: Started successfully PID {self.pid}", "SUCCESS")

            # Wait 2 seconds and verify it's still alive
            time.sleep(2)
            if not check_process_alive(self.pid):
                log(f"Worker {self.worker_id}: DIED IMMEDIATELY after start!", "ERROR")
                return False

            log(f"Worker {self.worker_id}: Still alive after 2s check", "INFO")
            return True

        except Exception as e:
            log(f"Worker {self.worker_id}: Exception during start: {e}", "ERROR")
            log(f"Worker {self.worker_id}: Traceback:\n{traceback.format_exc()}", "ERROR")
            return False

    def check_status(self):
        """Check process status with detailed logging"""
        if not self.process:
            return "NOT_STARTED"

        if not check_process_alive(self.pid):
            log(f"Worker {self.worker_id}: Process PID {self.pid} is DEAD", "ERROR")

            # Get exit code
            returncode = self.process.poll()
            if returncode is not None:
                log(f"Worker {self.worker_id}: Exit code: {returncode} (0x{returncode:08X})", "ERROR")

                # Log memory info from log file
                runtime = time.time() - self.start_time if self.start_time else 0
                log(f"Worker {self.worker_id}: Ran for {runtime:.1f} seconds before death", "INFO")

            return "DEAD"

        # Check if hung (no progress)
        runtime = time.time() - self.start_time if self.start_time else 0
        if runtime > 600:  # 10 minutes
            log(f"Worker {self.worker_id}: Running for {runtime:.0f}s - might be hung", "WARN")

        return "RUNNING"

    def restart_if_needed(self):
        """Restart if dead"""
        status = self.check_status()

        if status == "DEAD":
            if self.restarts >= self.max_restarts:
                log(f"Worker {self.worker_id}: Max restarts ({self.max_restarts}) reached - GIVING UP", "ERROR")
                return False

            log(f"Worker {self.worker_id}: Attempting restart...", "INFO")
            self.restarts += 1
            time.sleep(3)  # Cooldown
            return self.start()

        return status == "RUNNING"

    def kill(self):
        """Kill worker"""
        if self.process and check_process_alive(self.pid):
            log(f"Worker {self.worker_id}: Killing PID {self.pid}", "INFO")
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except:
                try:
                    self.process.kill()
                except:
                    pass


def main():
    log("="*80, "INFO")
    log("ULTRA ROBUST ORCHESTRATOR - STARTING", "INFO")
    log("="*80, "INFO")

    # Load symbols
    symbols_file = PROJECT_ROOT / "processed" / "reference" / "symbols_with_1m.parquet"
    import polars as pl
    all_symbols = pl.read_parquet(symbols_file)["symbol"].to_list()

    log(f"Total symbols loaded: {len(all_symbols)}", "INFO")

    # Determinar run_id del día y checkpoint correspondiente
    run_id = f"events_intraday_{datetime.now().strftime('%Y%m%d')}"
    checkpoint_file = PROJECT_ROOT / "logs" / "checkpoints" / f"{run_id}_completed.json"
    completed = set()
    if checkpoint_file.exists():
        with open(checkpoint_file) as f:
            cp = json.load(f)
        completed = set(cp.get("completed_symbols", []))
        log(f"Checkpoint loaded: {len(completed)} completed symbols", "INFO")

    # Ampliar 'completed' con símbolos observados en manifests (si existen)
    manifests_dir = PROJECT_ROOT / "processed" / "events" / "manifests"
    if manifests_dir.exists():
        observed = set()
        for mf in manifests_dir.glob(f"{run_id}_shard*.json"):
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                for s in data.get("symbols", []):
                    observed.add(s)
            except Exception as e:
                log(f"Manifest read error {mf.name}: {e}", "WARN")
        if observed:
            before = len(completed)
            completed |= observed
            log(f"Reconciled checkpoint with manifests: +{len(completed)-before} symbols", "INFO")

    # Get remaining
    remaining = [s for s in all_symbols if s not in completed]
    log(f"Remaining symbols: {len(remaining)}", "INFO")

    if len(remaining) == 0:
        log("ALL SYMBOLS COMPLETED!", "SUCCESS")
        return 0

    # Create 3 workers (not 4, Worker 4 always fails)
    num_workers = 3
    chunk_size = len(remaining) // num_workers

    workers = []
    for i in range(num_workers):
        start_idx = i * chunk_size
        end_idx = (i + 1) * chunk_size if i < num_workers - 1 else len(remaining)
        worker_symbols = remaining[start_idx:end_idx]

        worker = WorkerProcess(i + 1, worker_symbols, max_restarts=50)
        workers.append(worker)
        log(f"Worker {i+1}: Assigned {len(worker_symbols)} symbols", "INFO")

    # Start all workers
    log("Starting all workers...", "INFO")
    for worker in workers:
        worker.start()
        time.sleep(5)  # Stagger starts

    # Monitor loop
    log("Entering monitor loop...", "INFO")
    iteration = 0

    try:
        while True:
            iteration += 1
            time.sleep(30)  # Check every 30 seconds

            log(f"--- Monitor Loop Iteration {iteration} ---", "INFO")

            all_dead = True
            for worker in workers:
                status = worker.check_status()
                log(f"Worker {worker.worker_id}: Status={status}, PID={worker.pid}, Restarts={worker.restarts}", "INFO")

                if status == "DEAD":
                    worker.restart_if_needed()
                elif status == "RUNNING":
                    all_dead = False

            if all_dead:
                log("ALL WORKERS DEAD - Exiting", "ERROR")
                break

            # Check if we've been running too long
            if iteration > 1000:  # ~8 hours
                log("Maximum runtime reached", "WARN")
                break

    except KeyboardInterrupt:
        log("Keyboard interrupt received", "WARN")
    except Exception as e:
        log(f"Exception in monitor loop: {e}", "ERROR")
        log(f"Traceback:\n{traceback.format_exc()}", "ERROR")
    finally:
        # Cleanup
        log("Cleaning up workers...", "INFO")
        for worker in workers:
            worker.kill()

    log("="*80, "INFO")
    log("ORCHESTRATOR FINISHED", "INFO")
    log("="*80, "INFO")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"FATAL ERROR: {e}", "CRITICAL")
        log(f"Traceback:\n{traceback.format_exc()}", "CRITICAL")
        sys.exit(1)
