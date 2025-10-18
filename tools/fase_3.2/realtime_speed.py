#!/usr/bin/env python3
"""
Measure realtime speed by counting files on disk
"""
import time
from pathlib import Path

root = Path(__file__).resolve().parents[2]
event_windows = root / "raw" / "market_data" / "event_windows"

print("Medición de velocidad en tiempo real (60 segundos)...")
print("Contando archivos parquet en disco...")
print()

# Count initial files
parquet_files = list(event_windows.rglob("*.parquet"))
parquet_files = [f for f in parquet_files if '.tmp' not in f.name]
start_count = len(parquet_files)
start_time = time.time()

print(f"[Inicio] Archivos en disco: {start_count:,}")
print("Esperando 60 segundos...")

# Wait 60 seconds
time.sleep(60)

# Count final files
parquet_files2 = list(event_windows.rglob("*.parquet"))
parquet_files2 = [f for f in parquet_files2 if '.tmp' not in f.name]
end_count = len(parquet_files2)
elapsed = time.time() - start_time

# Calculate speed
files_added = end_count - start_count
events_added = files_added / 2  # trades + quotes = 1 event
speed = events_added / (elapsed / 60)

print()
print(f"[Final] Archivos en disco: {end_count:,}")
print()
print("=" * 70)
print("RESULTADOS")
print("=" * 70)
print()
print(f"Tiempo transcurrido:  {elapsed:.1f} segundos")
print(f"Archivos añadidos:    {files_added}")
print(f"Eventos completados:  {events_added:.0f}")
print(f"Velocidad medida:     {speed:.1f} eventos/min")
print(f"Velocidad archivos:   {files_added / (elapsed / 60):.1f} archivos/min")
