#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FASE 2.5 - Data & Duplicates Analysis Tool

Análisis completo y 100% verificable de:
1. Datos físicos en disco (escaneo real de shards)
2. Checkpoints vs realidad (discrepancias)
3. Duplicados en tiempo real (heartbeat log)
4. Duplicados en shards (análisis de parquets)

Uso:
    python tools/analyze_data_duplicates.py
    python tools/analyze_data_duplicates.py --quick
    python tools/analyze_data_duplicates.py --export-csv
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json
import argparse
from collections import Counter, defaultdict

# Fix Windows console encoding
if sys.platform == "win32":
    os.system("")  # Enable ANSI escape codes
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import polars as pl
except ImportError:
    print("ERROR: polars not installed. Run: pip install polars")
    sys.exit(1)


class DataDuplicateAnalyzer:
    """Analizador completo de datos y duplicados para FASE 2.5"""

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or PROJECT_ROOT
        self.shards_dir = self.project_root / "processed" / "events" / "shards"
        self.events_dir = self.project_root / "processed" / "events"
        self.checkpoint_dir = self.project_root / "logs" / "checkpoints"
        self.heartbeat_dir = self.project_root / "logs" / "detect_events"

    def scan_physical_shards(self) -> dict:
        """Escanea FÍSICAMENTE todos los shards en disco"""
        print(f"\n{'='*80}")
        print(f"ESCANEANDO SHARDS FISICOS EN DISCO (100% Verificable)")
        print(f"{'='*80}\n")

        all_symbols = set()
        events_by_run = defaultdict(int)
        symbols_by_run = defaultdict(set)
        duplicates_by_run = defaultdict(int)
        shard_count = 0
        total_size_bytes = 0

        print("Esto puede tomar 30-60 segundos...")
        print()

        # Escanear todos los subdirectorios
        for shard_file in self.shards_dir.rglob('events_intraday_*.parquet'):
            try:
                # Extraer run_id del nombre del archivo
                parts = shard_file.stem.split('_')
                if len(parts) >= 3:
                    run_id = f'{parts[0]}_{parts[1]}_{parts[2]}'  # events_intraday_YYYYMMDD
                else:
                    run_id = 'unknown'

                # Leer shard
                df = pl.read_parquet(shard_file)

                # Contar símbolos
                symbols = df.select('symbol').unique().to_series().to_list()
                all_symbols.update(symbols)
                symbols_by_run[run_id].update(symbols)

                # Contar eventos
                total_events = len(df)
                events_by_run[run_id] += total_events

                # Detectar duplicados en este shard
                key_cols = ['symbol', 'timestamp', 'event_type']
                unique_events = df.select(key_cols).n_unique()
                duplicates = total_events - unique_events
                duplicates_by_run[run_id] += duplicates

                # Tamaño del archivo
                total_size_bytes += shard_file.stat().st_size

                shard_count += 1

                if shard_count % 50 == 0:
                    print(f'  Procesados {shard_count} shards...')

            except Exception as e:
                print(f'  ERROR en {shard_file.name}: {e}')
                continue

        print(f'\n[OK] Total shards escaneados: {shard_count}\n')

        # Calcular tamaño total
        total_size_mb = total_size_bytes / (1024 * 1024)

        # Imprimir resultados
        print(f"{'='*80}")
        print(f"RESULTADOS POR RUN")
        print(f"{'='*80}\n")

        for run_id in sorted(symbols_by_run.keys()):
            dup_pct = (duplicates_by_run[run_id] / events_by_run[run_id] * 100) if events_by_run[run_id] > 0 else 0
            print(f'{run_id}:')
            print(f'  Simbolos unicos: {len(symbols_by_run[run_id]):,}')
            print(f'  Eventos totales: {events_by_run[run_id]:,}')
            print(f'  Duplicados: {duplicates_by_run[run_id]:,} ({dup_pct:.2f}%)')
            print()

        total_events = sum(events_by_run.values())
        total_duplicates = sum(duplicates_by_run.values())
        total_dup_pct = (total_duplicates / total_events * 100) if total_events > 0 else 0

        print(f"{'='*80}")
        print(f"TOTAL ACUMULADO (DATOS REALES EN DISCO)")
        print(f"{'='*80}")
        print(f'Total shards: {shard_count:,}')
        print(f'Simbolos unicos: {len(all_symbols):,}')
        print(f'Eventos totales: {total_events:,}')
        print(f'Duplicados totales: {total_duplicates:,} ({total_dup_pct:.2f}%)')
        print(f'Tamanio en disco: {total_size_mb:.1f} MB')
        print()

        return {
            'total_shards': shard_count,
            'unique_symbols': len(all_symbols),
            'total_events': total_events,
            'total_duplicates': total_duplicates,
            'dup_rate_pct': total_dup_pct,
            'size_mb': total_size_mb,
            'by_run': {
                run_id: {
                    'symbols': len(symbols_by_run[run_id]),
                    'events': events_by_run[run_id],
                    'duplicates': duplicates_by_run[run_id],
                    'dup_pct': (duplicates_by_run[run_id] / events_by_run[run_id] * 100) if events_by_run[run_id] > 0 else 0
                }
                for run_id in symbols_by_run.keys()
            }
        }

    def analyze_all_checkpoints(self) -> dict:
        """Analiza todos los checkpoints y compara con realidad"""
        print(f"\n{'='*80}")
        print(f"ANALIZANDO CHECKPOINTS (Lo que dicen vs Realidad)")
        print(f"{'='*80}\n")

        checkpoints = {}

        for ckpt_file in sorted(self.checkpoint_dir.glob('events_intraday_*_completed.json')):
            try:
                data = json.load(open(ckpt_file, encoding='utf-8'))
                run_id = data.get('run_id', 'unknown')
                date_str = run_id.split('_')[-1] if '_' in run_id else 'unknown'

                checkpoints[run_id] = {
                    'file': ckpt_file.name,
                    'total_completed': data.get('total_completed', 0),
                    'last_updated': data.get('last_updated', 'N/A'),
                    'date': date_str
                }

                print(f"{ckpt_file.name}:")
                print(f"  Total completados: {data.get('total_completed', 0):,}")
                print(f"  Ultima actualizacion: {data.get('last_updated', 'N/A')}")
                print()

            except Exception as e:
                print(f"  ERROR en {ckpt_file.name}: {e}")
                continue

        return checkpoints

    def analyze_heartbeat_log(self, tail_lines: int = 500) -> dict:
        """Analiza heartbeat log para detectar duplicados en tiempo real"""
        print(f"\n{'='*80}")
        print(f"ANALIZANDO HEARTBEAT LOG (Procesamiento en Tiempo Real)")
        print(f"{'='*80}\n")

        # Buscar heartbeat más reciente
        candidates = sorted(self.heartbeat_dir.glob("heartbeat_*.log"), reverse=True)
        if not candidates:
            print(f"ERROR: No heartbeat log found in {self.heartbeat_dir}")
            return {}

        heartbeat_file = candidates[0]
        print(f"Archivo: {heartbeat_file.name}")
        print(f"Analizando ultimas {tail_lines} entradas...\n")

        try:
            # Leer últimas N líneas
            with open(heartbeat_file, 'r', encoding='utf-8') as f:
                f.seek(0, 2)
                file_size = f.tell()

                block_size = 8192
                blocks = []
                lines_found = 0

                while file_size > 0 and lines_found < tail_lines:
                    read_size = min(block_size, file_size)
                    f.seek(file_size - read_size)
                    block = f.read(read_size)
                    blocks.append(block)
                    lines_found += block.count('\n')
                    file_size -= read_size

                content = ''.join(reversed(blocks))
                lines = content.splitlines()[-tail_lines:]

            # Parsear símbolos (formato: YYYY-MM-DD HH:MM:SS.mmm    SYMBOL    ...)
            symbols = []
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    symbol = parts[2]
                    symbols.append(symbol)

            # Contar duplicados
            symbol_counts = Counter(symbols)
            total_symbols = len(symbols)
            unique_symbols = len(symbol_counts)
            duplicated_symbols = {sym: count for sym, count in symbol_counts.items() if count > 1}
            total_duplications = sum(count - 1 for count in duplicated_symbols.values())
            dup_rate = (total_duplications / total_symbols * 100) if total_symbols > 0 else 0

            print(f"Entradas analizadas: {total_symbols:,}")
            print(f"Simbolos unicos: {unique_symbols:,}")
            print(f"Simbolos con duplicados: {len(duplicated_symbols):,}")
            print(f"Duplicaciones totales: {total_duplications:,}")
            print(f"Tasa de duplicacion: {dup_rate:.2f}%")
            print()

            # Status
            if dup_rate < 5:
                status = "EXCELLENT"
            elif dup_rate < 10:
                status = "GOOD"
            elif dup_rate < 20:
                status = "WARNING"
            else:
                status = "CRITICAL"

            print(f"Status: {status}")
            print()

            # Top duplicados
            if duplicated_symbols:
                top_dups = sorted(duplicated_symbols.items(), key=lambda x: x[1], reverse=True)[:10]
                print(f"Top 10 simbolos mas duplicados:")
                for symbol, count in top_dups:
                    print(f"  {symbol:8s}: {count:2d} veces (duplicado {count-1} veces)")
                print()

            return {
                'heartbeat_file': heartbeat_file.name,
                'total_entries': total_symbols,
                'unique_symbols': unique_symbols,
                'duplicated_symbols': len(duplicated_symbols),
                'total_duplications': total_duplications,
                'dup_rate_pct': dup_rate,
                'status': status,
                'top_duplicates': top_dups[:10] if duplicated_symbols else []
            }

        except Exception as e:
            print(f"ERROR: {e}")
            return {'error': str(e)}

    def run_full_analysis(self, quick: bool = False, export_csv: bool = False):
        """Ejecuta análisis completo"""
        print(f"\n{'='*80}")
        print(f"FASE 2.5 - ANALISIS COMPLETO DE DATOS Y DUPLICADOS")
        print(f"{'='*80}")
        print(f"Project root: {self.project_root}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

        results = {}

        # 1. Escaneo físico de shards (SIEMPRE - es la fuente de verdad)
        physical_data = self.scan_physical_shards()
        results['physical_data'] = physical_data

        # 2. Checkpoints
        checkpoints = self.analyze_all_checkpoints()
        results['checkpoints'] = checkpoints

        # 3. Heartbeat (solo si no es quick)
        if not quick:
            heartbeat_data = self.analyze_heartbeat_log(tail_lines=500)
            results['heartbeat'] = heartbeat_data

        # RESUMEN FINAL
        print(f"\n{'='*80}")
        print(f"RESUMEN FINAL")
        print(f"{'='*80}\n")

        print(f"[DATOS FISICOS EN DISCO - 100% VERIFICADO]")
        print(f"  Simbolos procesados: {physical_data['unique_symbols']:,} / 1,996")
        print(f"  Progreso real: {physical_data['unique_symbols'] / 1996 * 100:.1f}%")
        print(f"  Eventos guardados: {physical_data['total_events']:,}")
        print(f"  Duplicados en shards: {physical_data['total_duplicates']:,} ({physical_data['dup_rate_pct']:.2f}%)")
        print(f"  Tamanio en disco: {physical_data['size_mb']:.1f} MB")
        print()

        print(f"[CHECKPOINTS vs REALIDAD]")
        total_checkpoint = sum(cp['total_completed'] for cp in checkpoints.values())
        discrepancy = abs(total_checkpoint - physical_data['unique_symbols'])
        print(f"  Checkpoints dicen: {total_checkpoint:,} simbolos completados")
        print(f"  Shards reales: {physical_data['unique_symbols']:,} simbolos")
        print(f"  Discrepancia: {discrepancy:,} simbolos")
        if discrepancy > 100:
            print(f"  [WARNING] Gran discrepancia - checkpoints no fiables")
        print()

        if not quick and 'heartbeat' in results and 'error' not in results['heartbeat']:
            hb = results['heartbeat']
            print(f"[PROCESAMIENTO EN TIEMPO REAL]")
            print(f"  Tasa de duplicacion actual: {hb['dup_rate_pct']:.2f}%")
            print(f"  Status: {hb['status']}")
            print()

        print(f"{'='*80}")
        print(f"ANALISIS COMPLETO")
        print(f"{'='*80}\n")

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Analisis completo de datos y duplicados en FASE 2.5"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Analisis rapido (sin heartbeat)"
    )
    parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Exportar resultados a CSV"
    )

    args = parser.parse_args()

    analyzer = DataDuplicateAnalyzer()
    analyzer.run_full_analysis(quick=args.quick, export_csv=args.export_csv)


if __name__ == "__main__":
    main()
