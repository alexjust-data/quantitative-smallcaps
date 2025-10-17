#!/usr/bin/env python3
"""
watchdog_parallel.py — Supervisor único para relanzar la FASE 2.5 sin duplicación.
- Relanza launch_parallel_detection.py si no hay procesos activos o si se estanca.
- Usa checkpoint de hoy + --resume (no reprocesa lo ya hecho).
"""

import os, sys, time, json, subprocess, psutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent  # Project root, not tools/
LOGS = ROOT / "logs"
HEARTBEATS = LOGS / "detect_events"
CHECKPOINTS = LOGS / "checkpoints"
PID_FILE = LOGS / "watchdog_parallel.pid"
PAUSE_FLAG = ROOT / "RUN_PAUSED.flag"

MAX_RESTARTS = 100
STALL_SECONDS = 8 * 60     # 8 min sin heartbeat = estancado
BACKOFF_BASE = 30          # 30s, 60s, 120s...

def already_running() -> bool:
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                cmd = " ".join(p.cmdline())
                if "watchdog_parallel.py" in cmd:
                    return True
        except: pass
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    return False

def last_heartbeat_ts(hb_path: Path) -> float:
    if not hb_path.exists(): return 0.0
    try:
        with open(hb_path, "rb") as f:
            f.seek(0, 2); size = f.tell()
            f.seek(max(0, size-2048))
            lines = f.read().decode("utf-8", "ignore").splitlines()
            if not lines: return 0.0
            ts = lines[-1].split("\t", 1)[0]
            # "YYYY-MM-DD HH:MM:SS.mmm" with fallback
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return dt.timestamp()
    except: return 0.0

def completed_count(ck_path: Path) -> int:
    if not ck_path.exists(): return 0
    try:
        data = json.loads(ck_path.read_text(encoding="utf-8"))
        return int(data.get("total_completed", 0))
    except: return 0

def any_detection_running() -> bool:
    for p in psutil.process_iter(['cmdline']):
        try:
            cmd = " ".join(p.info.get('cmdline') or [])
            if "detect_events_intraday.py" in cmd or "launch_parallel_detection.py" in cmd:
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
    prev_completed = 0

    try:
        proc = None
        while restarts < MAX_RESTARTS:
            # Modo pausa seguro (no lanza nada)
            if PAUSE_FLAG.exists():
                print("[watchdog_parallel] RUN_PAUSED.flag present → exiting.")
                break

            # Recalcular rutas por si cambia el día
            today_str = datetime.now().strftime('%Y%m%d')
            run_id = f"events_intraday_{today_str}"
            ck_path = CHECKPOINTS / f"{run_id}_completed.json"
            hb_path = HEARTBEATS / f"heartbeat_{today_str}.log"
            if prev_completed == 0:
                prev_completed = completed_count(ck_path)

            # Lanzar si no hay procesos detect_events activos
            if not any_detection_running():
                proc = launch(workers)
                restarts += 1
                print(f"[watchdog_parallel] Launched launcher (workers={workers}), restart #{restarts}")

            # Vigilar progreso
            time.sleep(60)
            last_hb = last_heartbeat_ts(hb_path)
            hb_age = time.time() - last_hb if last_hb else 0
            now_completed = completed_count(ck_path)

            progressed = (now_completed > prev_completed)
            prev_completed = now_completed

            # Si no hay heartbeat pero HAY procesos, trátalo como estancado directo
            if hb_age == 0 and any_detection_running():
                hb_age = STALL_SECONDS + 1

            # Caso 1: progreso normal → continuar (y reset de backoff)
            if progressed or hb_age < STALL_SECONDS:
                if progressed:
                    restarts = 0
                    # si habíamos degradado, intenta recuperar hasta 4
                    if workers < 4: workers = min(4, workers + 1)
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

            # degradación progresiva de workers si persisten los fallos
            if restarts >= 3:
                workers = 2
            if restarts >= 6:
                workers = 1

        print("[watchdog_parallel] Max restarts reached; manual intervention required.")
        return 1

    finally:
        try: PID_FILE.unlink()
        except: pass

if __name__ == "__main__":
    sys.exit(main())
