#!/usr/bin/env python3
"""
Measure current ingestion speed
"""
import time
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
log_file = root / "logs" / "polygon_ingest_20251017_195752.log"

print("Medición de velocidad en curso (60 segundos)...")
print()

# Read initial event count
lines = log_file.read_text(encoding='utf-8', errors='ignore').split('\n')
events = [int(re.search(r'\[(\d+)/', l).group(1))
          for l in lines if 'process_event' in l and re.search(r'\[(\d+)/', l)]
start_event = events[-1] if events else 0
start_time = time.time()

print(f"[Inicio] Evento: {start_event:,}/548,334")
print("Esperando 60 segundos...")

# Wait 60 seconds
time.sleep(60)

# Read final event count
lines2 = log_file.read_text(encoding='utf-8', errors='ignore').split('\n')
events2 = [int(re.search(r'\[(\d+)/', l).group(1))
           for l in lines2 if 'process_event' in l and re.search(r'\[(\d+)/', l)]
end_event = events2[-1] if events2 else 0
elapsed = time.time() - start_time

# Calculate speed
events_processed = end_event - start_event
speed = events_processed / (elapsed / 60)

print()
print(f"[Final] Evento: {end_event:,}/548,334")
print()
print("=" * 70)
print("RESULTADOS")
print("=" * 70)
print()
print(f"Tiempo transcurrido: {elapsed:.1f} segundos")
print(f"Eventos procesados:  {events_processed}")
print(f"Velocidad medida:    {speed:.1f} eventos/min")
print()
print(f"Archivos escritos:   ~{events_processed * 2} (trades + quotes)")
print(f"Velocidad archivos:  ~{speed * 2:.1f} archivos/min")
