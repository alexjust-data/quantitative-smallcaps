#!/usr/bin/env python3
"""
Kill all current detection processes and start parallel orchestrator
"""
import psutil
import time
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

def kill_all_detection_processes():
    """Kill all detection and watchdog processes"""
    print("Killing all detection and watchdog processes...")

    killed_watchdogs = []
    killed_detections = []

    for proc in psutil.process_iter(['pid', 'cmdline', 'name']):
        try:
            cmdline = proc.cmdline()
            if cmdline:
                cmdline_str = ' '.join(cmdline)

                if 'run_watchdog' in cmdline_str:
                    print(f"  Killing watchdog PID {proc.pid}")
                    proc.kill()
                    killed_watchdogs.append(proc.pid)
                elif 'detect_events_intraday' in cmdline_str:
                    print(f"  Killing detection PID {proc.pid}")
                    proc.kill()
                    killed_detections.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    print(f"\nKilled {len(killed_watchdogs)} watchdogs, {len(killed_detections)} detection processes")

    # Wait for processes to die
    time.sleep(3)

    # Verify
    remaining_watchdogs = 0
    remaining_detections = 0

    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = proc.cmdline()
            if cmdline:
                cmdline_str = ' '.join(cmdline)
                if 'run_watchdog' in cmdline_str:
                    remaining_watchdogs += 1
                elif 'detect_events_intraday' in cmdline_str:
                    remaining_detections += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    if remaining_watchdogs > 0 or remaining_detections > 0:
        print(f"\nWARNING: Still running - {remaining_watchdogs} watchdogs, {remaining_detections} detections")
        return False

    print("All processes killed successfully!\n")
    return True

def main():
    print("="*80)
    print("RESTART WITH PARALLEL PROCESSING")
    print("="*80)
    print()

    # Kill existing processes
    if not kill_all_detection_processes():
        print("\nFailed to kill all processes. Please kill them manually and try again.")
        return 1

    # Start orchestrator
    print("Starting parallel orchestrator...\n")

    cmd = [sys.executable, str(PROJECT_ROOT / "parallel_orchestrator.py")]

    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        return result.returncode
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130

if __name__ == "__main__":
    sys.exit(main())
