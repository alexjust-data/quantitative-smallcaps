#!/usr/bin/env python3
"""
Robust watchdog for intraday event detection with:
- No I/O redirection (all logging to files)
- Heartbeat monitoring
- Automatic restart on stall/crash
- Granular checkpointing
"""

import json
import os
import psutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


class DetectionWatchdog:
    def __init__(
        self,
        script_path: str,
        max_restarts: int = 200,
        heartbeat_timeout_sec: int = 300,  # 5 minutes
        check_interval_sec: int = 30,
    ):
        self.script_path = Path(script_path)
        self.max_restarts = max_restarts
        self.heartbeat_timeout = heartbeat_timeout_sec
        self.check_interval = check_interval_sec

        self.base_dir = Path("D:/04_TRADING_SMALLCAPS")
        self.checkpoint_dir = self.base_dir / "logs" / "checkpoints"
        self.heartbeat_dir = self.base_dir / "logs" / "heartbeats"
        self.log_dir = self.base_dir / "logs" / "detect_events"

        # Ensure directories exist
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.heartbeat_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.run_id = f"events_intraday_{datetime.now().strftime('%Y%m%d')}"
        self.checkpoint_file = self.checkpoint_dir / f"{self.run_id}_completed.json"
        self.heartbeat_file = self.heartbeat_dir / f"heartbeat_{datetime.now().strftime('%Y%m%d')}.log"
        self.watchdog_log = self.log_dir / f"watchdog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        self.process = None
        self.restart_count = 0
        self.total_symbols_processed = 0
        self.start_time = datetime.now()

        # PID files for process tracking
        self.watchdog_pid_file = self.log_dir / "watchdog.pid"
        self.detection_pid_file = self.log_dir / "detection_process.pid"

    def log(self, message: str, level: str = "INFO"):
        """Write to watchdog log file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level:5s}] {message}\n"
        print(log_line.strip())  # Also print to console

        with open(self.watchdog_log, "a", encoding="utf-8") as f:
            f.write(log_line)

    def get_checkpoint_progress(self) -> int:
        """Read current checkpoint to see how many symbols completed"""
        if not self.checkpoint_file.exists():
            return 0

        try:
            with open(self.checkpoint_file, "r") as f:
                data = json.load(f)
                return data.get("total_completed", 0)
        except Exception as e:
            self.log(f"Error reading checkpoint: {e}", "WARN")
            return 0

    def get_last_heartbeat_time(self) -> float:
        """Get the timestamp of the last heartbeat"""
        if not self.heartbeat_file.exists():
            return 0

        try:
            # Read last line of heartbeat file
            with open(self.heartbeat_file, "rb") as f:
                # Seek to end and read backwards to find last line
                f.seek(0, 2)  # Go to end
                file_size = f.tell()

                if file_size == 0:
                    return 0

                # Read last 1KB (should contain several heartbeats)
                seek_pos = max(0, file_size - 1024)
                f.seek(seek_pos)
                lines = f.read().decode("utf-8", errors="ignore").splitlines()

                if not lines:
                    return 0

                # Parse last line: "2025-10-12 20:27:52.620\tSBH\t1\t40\t0\t0.11"
                last_line = lines[-1].strip()
                if not last_line:
                    return 0

                parts = last_line.split("\t")
                if len(parts) < 2:
                    return 0

                timestamp_str = parts[0]
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
                return dt.timestamp()
        except Exception as e:
            self.log(f"Error reading heartbeat: {e}", "WARN")
            return 0

    def is_process_stalled(self) -> bool:
        """Check if process has stalled based on heartbeat"""
        last_heartbeat = self.get_last_heartbeat_time()

        if last_heartbeat == 0:
            # No heartbeat yet - process just started
            return False

        time_since_heartbeat = time.time() - last_heartbeat

        if time_since_heartbeat > self.heartbeat_timeout:
            self.log(f"Process stalled: {time_since_heartbeat:.0f}s since last heartbeat", "WARN")
            return True

        return False

    def check_existing_detection_process(self) -> int:
        """Check if detection script is already running"""
        # Check PID file first
        if self.detection_pid_file.exists():
            try:
                pid = int(self.detection_pid_file.read_text().strip())
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    cmdline = ' '.join(proc.cmdline())
                    if 'detect_events_intraday.py' in cmdline:
                        self.log(f"Found existing process via PID file: {pid}", "INFO")
                        return pid
            except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Scan all processes as backup
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.cmdline()
                if cmdline and 'detect_events_intraday.py' in ' '.join(cmdline):
                    self.log(f"Found existing detection process: PID {proc.pid}", "WARN")
                    return proc.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return None

    def start_process(self):
        """Start the detection process without I/O redirection"""
        self.log("="*80)
        self.log(f"Starting process (restart #{self.restart_count + 1}/{self.max_restarts})")
        self.log("="*80)

        # Check if detection process already running
        existing_pid = self.check_existing_detection_process()
        if existing_pid:
            self.log(f"Detection process already running with PID {existing_pid}, skipping start", "WARN")
            self.log("This prevents duplicate processes. If this is an error, kill the process manually.", "WARN")
            return False

        # Check progress before starting
        completed_before = self.get_checkpoint_progress()
        self.log(f"Checkpoint: {completed_before} symbols already completed")

        # Launch without I/O redirection - let Loguru handle all logging
        cmd = [
            sys.executable,
            "-u",
            str(self.script_path),
            "--from-file", "processed/reference/symbols_with_1m.parquet",
            "--batch-size", "50",
            "--checkpoint-interval", "1",
            "--resume"
        ]

        try:
            # Use Popen without stdout/stderr redirection
            # All output goes to Loguru log files
            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.base_dir),
                # No stdout/stderr redirection - let Python handle it
                # This prevents Windows from killing the process
            )

            self.log(f"Process started with PID: {self.process.pid}")

            # Save PID to file
            self.detection_pid_file.write_text(str(self.process.pid))
            self.log(f"Saved PID to {self.detection_pid_file}")

            self.restart_count += 1
            return True

        except Exception as e:
            self.log(f"Failed to start process: {e}", "ERROR")
            return False

    def stop_process(self):
        """Stop the current process"""
        if self.process and self.process.poll() is None:
            self.log(f"Stopping process PID {self.process.pid}")
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.log("Process didn't terminate, killing it", "WARN")
                self.process.kill()
            except Exception as e:
                self.log(f"Error stopping process: {e}", "ERROR")

        # Clean up PID file
        if self.detection_pid_file.exists():
            try:
                self.detection_pid_file.unlink()
                self.log("Cleaned up detection PID file")
            except Exception as e:
                self.log(f"Error removing PID file: {e}", "WARN")

        self.process = None

    def check_completion(self) -> bool:
        """Check if all symbols are completed"""
        completed = self.get_checkpoint_progress()

        if completed >= 1996:
            self.log("="*80)
            self.log(f"ALL SYMBOLS COMPLETED! ({completed}/1996)")
            self.log("="*80)
            return True

        return False

    def run(self):
        """Main watchdog loop"""
        self.log("="*80)
        self.log("ROBUST WATCHDOG - INTRADAY EVENT DETECTION")
        self.log("="*80)
        self.log(f"Script: {self.script_path}")
        self.log(f"Max restarts: {self.max_restarts}")
        self.log(f"Heartbeat timeout: {self.heartbeat_timeout}s")
        self.log(f"Check interval: {self.check_interval}s")
        self.log("="*80)

        # Register this watchdog
        if self.watchdog_pid_file.exists():
            try:
                old_pid = int(self.watchdog_pid_file.read_text().strip())
                if psutil.pid_exists(old_pid):
                    self.log("="*80)
                    self.log(f"ERROR: Another watchdog is already running with PID {old_pid}", "ERROR")
                    self.log("To start a new watchdog, first kill the old one:", "ERROR")
                    self.log(f"  taskkill /PID {old_pid} /F", "ERROR")
                    self.log("="*80)
                    return 1
                else:
                    self.log(f"Found stale watchdog PID file (PID {old_pid} not running), cleaning up", "WARN")
            except (ValueError, psutil.NoSuchProcess):
                self.log("Found invalid watchdog PID file, cleaning up", "WARN")

        # Write our PID
        self.watchdog_pid_file.write_text(str(os.getpid()))
        self.log(f"Registered watchdog with PID: {os.getpid()}")
        self.log("="*80)

        try:
            while self.restart_count < self.max_restarts:
                # Check if already completed
                if self.check_completion():
                    return 0

                # Start process if not running
                if self.process is None or self.process.poll() is not None:
                    if self.process is not None:
                        exit_code = self.process.poll()
                        self.log(f"Process exited with code: {exit_code}")

                        # Check progress
                        completed_now = self.get_checkpoint_progress()
                        symbols_this_run = completed_now - self.total_symbols_processed
                        self.total_symbols_processed = completed_now

                        self.log(f"Progress: {symbols_this_run} symbols this run, {completed_now}/1996 total")

                        if exit_code == 0:
                            self.log("Process completed successfully!")
                            return 0

                    # Wait a bit before restarting
                    if self.restart_count > 0:
                        self.log("Waiting 5 seconds before restart...")
                        time.sleep(5)

                    if not self.start_process():
                        self.log("Failed to start process, aborting", "ERROR")
                        return 1

                # Monitor process
                time.sleep(self.check_interval)

                # Check if process is stalled
                if self.is_process_stalled():
                    self.log("Process appears stalled, restarting...")
                    self.stop_process()
                    continue

                # Check if process crashed
                if self.process.poll() is not None:
                    self.log("Process terminated, will restart")
                    continue

            # Max restarts reached
            self.log("="*80)
            self.log(f"MAX RESTARTS REACHED ({self.max_restarts})")
            completed = self.get_checkpoint_progress()
            self.log(f"Final progress: {completed}/1996 symbols")
            runtime = (datetime.now() - self.start_time).total_seconds() / 60
            self.log(f"Total runtime: {runtime:.1f} minutes")
            self.log("="*80)
            return 1

        except KeyboardInterrupt:
            self.log("\nInterrupted by user (Ctrl+C)", "WARN")
            self.stop_process()
            # Clean up watchdog PID file
            if self.watchdog_pid_file.exists():
                self.watchdog_pid_file.unlink()
            return 130
        except Exception as e:
            self.log(f"Unexpected error: {e}", "ERROR")
            self.stop_process()
            # Clean up watchdog PID file
            if self.watchdog_pid_file.exists():
                self.watchdog_pid_file.unlink()
            return 1
        finally:
            # Always clean up PID files
            if self.watchdog_pid_file.exists():
                try:
                    self.watchdog_pid_file.unlink()
                    self.log("Cleaned up watchdog PID file")
                except:
                    pass


if __name__ == "__main__":
    script_path = "scripts/processing/detect_events_intraday.py"

    watchdog = DetectionWatchdog(
        script_path=script_path,
        max_restarts=200,
        heartbeat_timeout_sec=300,  # 5 minutes
        check_interval_sec=30,
    )

    sys.exit(watchdog.run())
