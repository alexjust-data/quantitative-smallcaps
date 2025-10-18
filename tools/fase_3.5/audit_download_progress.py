#!/usr/bin/env python3
"""
Audit download progress for filtered smallcap manifest
"""
import re
from pathlib import Path
from datetime import datetime

root = Path(__file__).resolve().parents[2]
log_file = root / "logs" / "polygon_ingest_20251017_225148.log"

print("=" * 70)
print("AUDITORIA DESCARGA - MANIFEST FILTRADO")
print("=" * 70)
print()

# Read log file
with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print(f"Total lineas en log: {len(lines):,}")
print()

# Find progress lines
progress_pattern = re.compile(r'\[(\d+)/(\d+)\]')
progress_lines = []
for line in lines:
    match = progress_pattern.search(line)
    if match:
        current = int(match.group(1))
        total = int(match.group(2))
        progress_lines.append((current, total))

if len(progress_lines) == 0:
    print("ERROR: No se encontraron lineas de progreso")
    exit(1)

first_progress = progress_lines[0]
last_progress = progress_lines[-1]

print("=" * 70)
print("PROGRESO")
print("=" * 70)
print()
print(f"Primer evento:  [{first_progress[0]}/{first_progress[1]}]")
print(f"Ultimo evento:  [{last_progress[0]}/{last_progress[1]}]")
print(f"Eventos procesados: {last_progress[0]:,}")
print(f"Total eventos (segun log): {last_progress[1]:,}")
print(f"Progreso: {last_progress[0]/last_progress[1]*100:.2f}%")
print()

# Check manifest
manifest_path = root / "processed" / "events" / "manifest_smallcaps_5y_20251017.parquet"
if manifest_path.exists():
    import polars as pl
    df = pl.read_parquet(manifest_path)
    total_in_manifest = len(df)
    print(f"Total eventos en manifest filtrado: {total_in_manifest:,}")
    print()
    if total_in_manifest != last_progress[1]:
        print(f"ADVERTENCIA: El log muestra {last_progress[1]:,} eventos")
        print(f"             pero el manifest tiene {total_in_manifest:,} eventos")
        print()

# Find timestamp lines to calculate speed
timestamp_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
timestamps = []
for line in lines:
    match = timestamp_pattern.search(line)
    if match and '[' in line and ']' in line:
        prog_match = progress_pattern.search(line)
        if prog_match:
            ts_str = match.group(1)
            ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
            current = int(prog_match.group(1))
            timestamps.append((ts, current))

if len(timestamps) > 1:
    # Calculate speed from first to last
    first_ts, first_evt = timestamps[0]
    last_ts, last_evt = timestamps[-1]

    elapsed = (last_ts - first_ts).total_seconds() / 60  # minutes
    events_processed = last_evt - first_evt

    if elapsed > 0:
        speed = events_processed / elapsed

        print("=" * 70)
        print("VELOCIDAD")
        print("=" * 70)
        print()
        print(f"Inicio:  {first_ts} (evento {first_evt:,})")
        print(f"Actual:  {last_ts} (evento {last_evt:,})")
        print(f"Tiempo transcurrido: {elapsed:.1f} minutos ({elapsed/60:.1f} horas)")
        print(f"Eventos procesados:  {events_processed:,}")
        print(f"Velocidad promedio:  {speed:.1f} evt/min")
        print()

        # Calculate ETA
        remaining = last_progress[1] - last_progress[0]
        eta_minutes = remaining / speed
        eta_hours = eta_minutes / 60
        eta_days = eta_hours / 24

        print("=" * 70)
        print("ESTIMACION TIEMPO RESTANTE")
        print("=" * 70)
        print()
        print(f"Eventos restantes: {remaining:,}")
        print(f"ETA: {eta_minutes:.0f} minutos ({eta_hours:.1f} horas / {eta_days:.2f} dias)")
        print()

# Check for errors (exclude DEBUG and retrying)
print("=" * 70)
print("ERRORES")
print("=" * 70)
print()

error_lines = [line for line in lines if 'ERROR' in line and 'DEBUG' not in line and 'retrying' not in line.lower()]
error_429 = [line for line in lines if '429' in line]

print(f"Lineas con ERROR (no DEBUG/retrying): {len(error_lines):,}")
print(f"Lineas con 429: {len(error_429):,}")
print()

if len(error_lines) > 0:
    print("Primeros 5 errores:")
    for line in error_lines[:5]:
        print(f"  {line.strip()}")
    print()

if len(error_429) > 0:
    print("Primeros 5 errores 429:")
    for line in error_429[:5]:
        print(f"  {line.strip()}")
    print()

# Summary
print("=" * 70)
print("RESUMEN")
print("=" * 70)
print()
print(f"PID: 7476")
print(f"Manifest: manifest_smallcaps_5y_20251017.parquet")
print(f"Progreso: {last_progress[0]:,} / {last_progress[1]:,} ({last_progress[0]/last_progress[1]*100:.2f}%)")
if len(timestamps) > 1:
    print(f"Velocidad: {speed:.1f} evt/min")
    print(f"ETA: {eta_days:.2f} dias")
print(f"Errores reales: {len(error_lines):,}")
print(f"Rate-limit 429: {len(error_429):,}")
print()
print("=" * 70)
