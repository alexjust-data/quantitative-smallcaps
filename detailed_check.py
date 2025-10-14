#!/usr/bin/env python3
"""Detailed check of all Python processes"""
import psutil
from datetime import datetime

print("="*80)
print("WATCHDOG PROCESSES")
print("="*80)
for proc in psutil.process_iter(['pid', 'cmdline', 'create_time']):
    try:
        cmdline = proc.cmdline()
        if cmdline and 'run_watchdog' in ' '.join(cmdline):
            start_time = datetime.fromtimestamp(proc.create_time()).strftime('%H:%M:%S')
            print(f"PID {proc.pid:6d} | Started: {start_time}")
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

print("\n" + "="*80)
print("DETECTION PROCESSES")
print("="*80)
for proc in psutil.process_iter(['pid', 'cmdline', 'create_time']):
    try:
        cmdline = proc.cmdline()
        if cmdline and 'detect_events_intraday' in ' '.join(cmdline):
            start_time = datetime.fromtimestamp(proc.create_time()).strftime('%H:%M:%S')
            print(f"PID {proc.pid:6d} | Started: {start_time}")
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
