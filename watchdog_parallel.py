#!/usr/bin/env python3
"""
watchdog_parallel.py — Supervisor único para relanzar la FASE 2.5 sin duplicación.
- Relanza launch_parallel_detection.py si no hay procesos activos o si se estanca.
- Usa checkpoint de hoy + --resume (no reprocesa lo ya hecho).
"""

import os, sys, time, json, subprocess, psutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "logs"
HEARTBEATS = LOGS / "detect_events"
CHECKPOINTS = LOGS / "checkpoints"
PID_FILE = LOGS / "watchdog_parallel.pid"

RUN_ID = f"events_intraday_{datetime.now().strftime('%Y%m%d')}"
CHECKPOINT = CHECKPOINTS / f"{RUN_ID}_completed.json"
HEARTBEAT = HEARTBEATS / f"heartbeat_{datetime.now().strftime('%Y%m%d')}.log"

MAX_RESTARTS = 100
STALL_SECONDS = 8 * 60     # 8 min sin heartbeat = estancado
BACKOFF_BASE = 30          # 30s, 60s, 120s...

def already_running() -> bool:
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            return psutil.pid_exists(pid)
        except: pass
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    return False

def last_heartbeat_ts() -> float:
    if not HEARTBEAT.exists(): return 0.0
    try:
        with open(HEARTBEAT, "rb") as f:
            f.seek(0, 2); size = f.tell()
            f.seek(max(0, size-2048))
            lines = f.read().decode("utf-8", "ignore").splitlines()
            if not lines: return 0.0
            ts = lines[-1].split("\t", 1)[0]
            # "YYYY-MM-DD HH:MM:SS.mmm"
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
            return dt.timestamp()
    except: return 0.0

def completed_count() -> int:
    if not CHECKPOINT.exists(): return 0
    try:
        data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        return int(data.get("total_completed", 0))
    except: return 0

def any_detection_running() -> bool:
    for p in psutil.process_iter(['cmdline']):
        try:
            cmd = " ".join(p.info.get('cmdline') or [])
            if "detect_events_intraday.py" in cmd:
                return True
        except: pass
    return False

def launch(workers: int) -> subprocess.Popen:
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts" / "processing" / "launch_parallel_detection.py"),
        "--workers", str(workers),
        "--batch-size", "50",
        "--checkpoint-interval", "1",
        "--yes"
    ]
    return subprocess.Popen(cmd, cwd=str(ROOT))

def main():
    if already_running():
        print("watchdog_parallel: another instance is running, exit.")
        return 0

    restarts = 0
    workers = 4
    prev_completed = completed_count()

    try:
        proc = None
        while restarts < MAX_RESTARTS:
            # Lanzar si no hay procesos detect_events activos
            if not any_detection_running():
                proc = launch(workers)
                restarts += 1
                print(f"[watchdog_parallel] Launched launcher (workers={workers}), restart #{restarts}")

            # Vigilar progreso
            time.sleep(60)
            hb_age = time.time() - last_heartbeat_ts() if last_heartbeat_ts() else 0
            now_completed = completed_count()

            progressed = (now_completed > prev_completed)
            prev_completed = now_completed

            # Caso 1: progreso normal → continuar
            if progressed or hb_age < STALL_SECONDS:
                continue

            # Caso 2: estancado o crash silencioso → matar y relanzar con backoff
            print(f"[watchdog_parallel] Stall/crash detected (hb_age={hb_age:.0f}s, completed={now_completed}). Restarting...")
            # matar cualquier detect_events o launcher para relanzar limpio
            for p in psutil.process_iter(['pid','cmdline']):
                try:
                    cmd = " ".join(p.info.get('cmdline') or [])
                    if any(x in cmd for x in ["detect_events_intraday.py","launch_parallel_detection.py"]):
                        p.kill()
                except: pass

            # backoff exponencial sencillo
            delay = BACKOFF_BASE * (2 ** min(4, restarts//3))
            time.sleep(delay)

            # degradación: si ya reiniciamos más de 2 veces sin progreso, baja a 2 workers
            if restarts >= 3:
                workers = 2

        print("[watchdog_parallel] Max restarts reached; manual intervention required.")
        return 1

    finally:
        try: PID_FILE.unlink()
        except: pass

if __name__ == "__main__":
    sys.exit(main())
