#!/usr/bin/env python3
"""Kill all detection and watchdog processes"""
import psutil
import sys

def kill_all_processes():
    """Kill all Python processes related to detection/watchdog"""
    killed = []
    failed = []

    print("Scanning for Python processes...")
    for proc in psutil.process_iter(['pid', 'cmdline', 'name']):
        try:
            cmdline = ' '.join(proc.cmdline()) if proc.cmdline() else ''

            # Check if it's a relevant Python process
            if 'python' in proc.name().lower():
                if 'detect_events_intraday' in cmdline or 'run_watchdog' in cmdline:
                    print(f"Killing PID {proc.pid}: {proc.name()}")
                    proc.kill()
                    proc.wait(timeout=5)
                    killed.append(proc.pid)

        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            failed.append(proc.pid)
        except psutil.TimeoutExpired:
            print(f"  WARNING: PID {proc.pid} didn't die, force killing...")
            try:
                proc.kill()
                killed.append(proc.pid)
            except:
                failed.append(proc.pid)
        except Exception as e:
            print(f"  ERROR killing PID {proc.pid}: {e}")
            failed.append(proc.pid)

    print(f"\n{'='*80}")
    print(f"RESULTS")
    print(f"{'='*80}")
    print(f"Successfully killed: {len(killed)} processes")
    if killed:
        print(f"  PIDs: {killed}")

    if failed:
        print(f"\nFailed to kill: {len(failed)} processes")
        print(f"  PIDs: {failed}")
        print(f"\nPlease kill these manually:")
        for pid in failed:
            print(f"  taskkill /PID {pid} /F")
        return 1

    print("\nAll processes killed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(kill_all_processes())
