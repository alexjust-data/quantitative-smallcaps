#!/usr/bin/env python3
"""Check for watchdog and detection processes with error handling"""
import psutil

watchdogs = []
detections = []

for proc in psutil.process_iter(['pid', 'cmdline', 'name']):
    try:
        cmdline = proc.cmdline()
        if cmdline:
            cmdline_str = ' '.join(cmdline)
            if 'run_watchdog' in cmdline_str:
                watchdogs.append(proc.pid)
            elif 'detect_events_intraday' in cmdline_str:
                detections.append(proc.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        # Skip processes we can't access
        pass

print(f"Watchdogs: {len(watchdogs)}")
if watchdogs:
    print(f"  PIDs: {watchdogs}")

print(f"Detections: {len(detections)}")
if detections:
    print(f"  PIDs: {detections}")

print(f"\nTotal: {len(watchdogs)} watchdogs, {len(detections)} detections")
