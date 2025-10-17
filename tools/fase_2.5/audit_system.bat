@echo off
REM ================================================================================
REM AUDIT SYSTEM - FASE 2.5 Status Monitor (FIXED)
REM ================================================================================
REM This script now correctly merges multiple checkpoints to show real progress

echo.
echo ================================================================================
echo AUDITORIA DEL SISTEMA FASE 2.5
echo ================================================================================
echo Fecha: %date% %time%
echo.

echo --------------------------------------------------------------------------------
echo [1/5] PROCESOS ACTIVOS
echo --------------------------------------------------------------------------------
powershell -Command "Get-WmiObject Win32_Process | Where-Object {$_.CommandLine -like '*detect_events*' -or $_.CommandLine -like '*watchdog*' -or $_.CommandLine -like '*launch_parallel*'} | Select-Object ProcessId, CommandLine | Format-Table -AutoSize"

echo.
echo --------------------------------------------------------------------------------
echo [2/5] CHECKPOINT - PROGRESO REAL (CORREGIDO)
echo --------------------------------------------------------------------------------
echo Merging all recent checkpoints (last 7 days)...
echo.

python -c "import json; from pathlib import Path; from datetime import datetime, timedelta; checkpoint_dir = Path('logs/checkpoints'); today = datetime.now(); cutoff = today - timedelta(days=7); all_completed = set(); checkpoint_files = []; [all_completed.update(set((data := json.load(open(ckpt_file))).get('completed_symbols', []))) or checkpoint_files.append((datetime.strptime((date_str := ckpt_file.stem.replace('events_intraday_', '').replace('_completed', '')), '%%Y%%m%%d'), ckpt_file.name, len(data.get('completed_symbols', [])))) for ckpt_file in sorted(checkpoint_dir.glob('events_intraday_*_completed.json')) if (file_date := datetime.strptime((date_str := ckpt_file.stem.replace('events_intraday_', '').replace('_completed', '')), '%%Y%%m%%d')) >= cutoff]; total_symbols = 1996; completed = len(all_completed); remaining = total_symbols - completed; progress = (completed / total_symbols) * 100 if total_symbols > 0 else 0; print(f'Checkpoint files found: {len(checkpoint_files)}'); [print(f'  - {name}: {count} symbols ({date.strftime(\"%%Y-%%m-%%d\")})') for date, name, count in checkpoint_files]; print(f'\n{\"=\"*60}'); print(f'PROGRESO REAL (merged from all checkpoints):'); print(f'{\"=\"*60}'); print(f'Total symbols: {total_symbols}'); print(f'Completed: {completed}'); print(f'Remaining: {remaining}'); print(f'Progress: {progress:.1f}%%'); print(f'{\"=\"*60}'); checkpoint_files and print(f'\nLast checkpoint: {checkpoint_files[-1][1]}') or None; checkpoint_files and print(f'Last updated: {checkpoint_files[-1][0].strftime(\"%%Y-%%m-%%d\")}') or None"

echo.
echo --------------------------------------------------------------------------------
echo [3/5] HEARTBEAT - ULTIMAS 30 LINEAS
echo --------------------------------------------------------------------------------
REM Find most recent heartbeat file
for /f "delims=" %%f in ('dir /b /o-d logs\detect_events\heartbeat_*.log 2^>nul') do (
    set HEARTBEAT_FILE=%%f
    goto :foundhb
)
:foundhb
if defined HEARTBEAT_FILE (
    echo File: logs\detect_events\%HEARTBEAT_FILE%
    echo.
    powershell -Command "Get-Content logs\detect_events\%HEARTBEAT_FILE% -Tail 30"
) else (
    echo No heartbeat file found
)

echo.
echo --------------------------------------------------------------------------------
echo [4/5] ESTADISTICAS DE ACTIVIDAD
echo --------------------------------------------------------------------------------
python -c "import json; from pathlib import Path; from datetime import datetime; hb_files = sorted(Path('logs/detect_events').glob('heartbeat_*.log'), reverse=True); hb_file = hb_files[0] if hb_files else None; hb_file and (lines := open(hb_file).readlines()) and print(f'Heartbeat file: {hb_file.name}') or None; hb_file and lines and print(f'Total heartbeat entries: {len(lines)}') or None; hb_file and lines and (last_line := lines[-1]) and print(f'Last activity: {last_line.split(chr(9))[0]}') or None; checkpoint_dir = Path('logs/checkpoints'); all_completed = set(); [all_completed.update(set(data.get('completed_symbols', []))) for ckpt_file in checkpoint_dir.glob('events_intraday_*_completed.json') if (data := json.load(open(ckpt_file)))]; remaining = 1996 - len(all_completed); workers = 4; symbols_per_hour_per_worker = 10; remaining > 0 and (hours_remaining := remaining / (workers * symbols_per_hour_per_worker)) and print(f'\nEstimated completion:') or print('\n✅ All symbols completed!'); remaining > 0 and print(f'  Remaining symbols: {remaining}') or None; remaining > 0 and print(f'  Active workers: {workers}') or None; remaining > 0 and print(f'  Speed: ~{symbols_per_hour_per_worker} sym/h per worker') or None; remaining > 0 and print(f'  ETA: ~{hours_remaining:.1f} hours') or None" 2>nul

echo.
echo --------------------------------------------------------------------------------
echo [5/5] LOGS DE WORKERS (ultimas 10 lineas c/u)
echo --------------------------------------------------------------------------------

for %%i in (1 2 3 4) do (
    echo.
    echo === WORKER %%i ===
    if exist "logs\worker_%%i_detection.log" (
        powershell -Command "Get-Content logs\worker_%%i_detection.log -Tail 10"
    ) else if exist "logs\detect_events\worker_%%i_detection.log" (
        powershell -Command "Get-Content logs\detect_events\worker_%%i_detection.log -Tail 10"
    ) else (
        REM Find most recent worker log
        for /f "delims=" %%f in ('dir /b /s /o-d logs\*worker_%%i*.log 2^>nul ^| findstr /v "\.zip" ^| more +0') do (
            powershell -Command "Get-Content '%%f' -Tail 10"
            goto :nextworker%%i
        )
        echo No recent log file found
        :nextworker%%i
    )
)

echo.
echo ================================================================================
echo AUDITORIA COMPLETADA
echo ================================================================================
echo.
