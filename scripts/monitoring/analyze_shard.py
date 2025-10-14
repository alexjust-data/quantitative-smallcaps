#!/usr/bin/env python3
"""
Análisis automático de KPIs por shard de eventos intraday.
Genera alertas si algún KPI está fuera de rango esperado.

Usage:
    python scripts/monitoring/analyze_shard.py --shard processed/events/shards/events_intraday_20251012_shard0003.parquet
    python scripts/monitoring/analyze_shard.py --all  # Analiza todos los shards del run actual
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import polars as pl


class ShardAnalyzer:
    """Analiza KPIs de calidad de un shard de eventos intraday."""

    def __init__(self, shard_path: Path):
        self.shard_path = shard_path
        self.shard_name = shard_path.name
        self.df = None
        self.kpis = {}
        self.alerts = []

    def load_shard(self):
        """Carga el shard en memoria."""
        print(f"\n{'='*80}")
        print(f"ANALIZANDO: {self.shard_name}")
        print(f"{'='*80}\n")

        self.df = pl.read_parquet(self.shard_path)
        print(f"[OK] Cargado: {len(self.df):,} eventos")

    def analyze_basic_metrics(self):
        """Métricas básicas del shard."""
        print("\n[1] METRICAS BASICAS")
        print("-" * 80)

        self.kpis["total_events"] = len(self.df)
        self.kpis["total_symbols"] = self.df["symbol"].n_unique()

        print(f"  Total eventos:     {self.kpis['total_events']:,}")
        print(f"  Simbolos unicos:   {self.kpis['total_symbols']}")
        print(f"  Eventos/simbolo:   {self.kpis['total_events'] / self.kpis['total_symbols']:.1f}")

        # Rango temporal
        date_min = self.df["timestamp"].min()
        date_max = self.df["timestamp"].max()
        self.kpis["date_range_days"] = (date_max - date_min).days

        print(f"  Rango temporal:    {date_min} a {date_max}")
        print(f"  Dias cubiertos:    {self.kpis['date_range_days']}")

    def analyze_event_distribution(self):
        """Distribución por tipo de evento."""
        print("\n[2] DISTRIBUCION POR TIPO DE EVENTO")
        print("-" * 80)

        event_counts = (
            self.df.group_by("event_type")
            .agg([pl.len().alias("count")])
            .sort("count", descending=True)
        )

        total = len(self.df)
        self.kpis["event_distribution"] = {}

        for row in event_counts.iter_rows(named=True):
            event_type = row["event_type"]
            count = row["count"]
            pct = count / total * 100

            self.kpis["event_distribution"][event_type] = {
                "count": count,
                "percentage": pct,
            }

            print(f"  {event_type:25s}: {count:6,} ({pct:5.1f}%)")

        # ALERTA: Si algun tipo tiene >60% del total
        for event_type, stats in self.kpis["event_distribution"].items():
            if stats["percentage"] > 60:
                self.alerts.append(
                    f"ALERTA: {event_type} domina con {stats['percentage']:.1f}% (>60%)"
                )

    def analyze_session_distribution(self):
        """Distribución por sesión (PM/RTH/AH)."""
        print("\n[3] DISTRIBUCION POR SESION")
        print("-" * 80)

        session_counts = (
            self.df.group_by("session")
            .agg([pl.len().alias("count")])
            .sort("count", descending=True)
        )

        total = len(self.df)
        self.kpis["session_distribution"] = {}

        for row in session_counts.iter_rows(named=True):
            session = row["session"]
            count = row["count"]
            pct = count / total * 100

            self.kpis["session_distribution"][session] = {
                "count": count,
                "percentage": pct,
            }

            print(f"  {session:12s}: {count:6,} ({pct:5.1f}%)")

        # ALERTA: Si PM tiene >50% (inusual)
        pm_pct = self.kpis["session_distribution"].get("premarket", {}).get(
            "percentage", 0
        )
        if pm_pct > 50:
            self.alerts.append(
                f"ALERTA: Premarket domina con {pm_pct:.1f}% (>50%, inusual)"
            )

        # ALERTA: Si AH tiene >40% (inusual)
        ah_pct = self.kpis["session_distribution"].get("afterhours", {}).get(
            "percentage", 0
        )
        if ah_pct > 40:
            self.alerts.append(
                f"ALERTA: Afterhours domina con {ah_pct:.1f}% (>40%, inusual)"
            )

    def analyze_direction_bias(self):
        """Distribución por dirección (up/down)."""
        print("\n[4] DISTRIBUCION POR DIRECCION")
        print("-" * 80)

        direction_counts = (
            self.df.group_by("direction")
            .agg([pl.len().alias("count")])
            .sort("count", descending=True)
        )

        total = len(self.df)
        self.kpis["direction_distribution"] = {}

        for row in direction_counts.iter_rows(named=True):
            direction = row["direction"]
            count = row["count"]
            pct = count / total * 100

            self.kpis["direction_distribution"][direction] = {
                "count": count,
                "percentage": pct,
            }

            print(f"  {direction:12s}: {count:6,} ({pct:5.1f}%)")

        # ALERTA: Si sesgo es >70% en una dirección
        for direction, stats in self.kpis["direction_distribution"].items():
            if stats["percentage"] > 70:
                self.alerts.append(
                    f"ALERTA: Sesgo {direction} muy alto: {stats['percentage']:.1f}% (>70%)"
                )

    def analyze_duplicates(self):
        """Detecta eventos duplicados en misma ventana temporal (cooldown)."""
        print("\n[5] ANALISIS DE DUPLICADOS (COOLDOWN)")
        print("-" * 80)

        # Agrupar por symbol + event_type + fecha/hora redondeada a 10 min
        df_with_bucket = self.df.with_columns(
            [
                # Redondear timestamp a 10 min
                (
                    pl.col("timestamp").dt.truncate("10m").alias("time_bucket")
                ),
            ]
        )

        duplicates = (
            df_with_bucket.group_by(["symbol", "event_type", "time_bucket"])
            .agg([pl.len().alias("count")])
            .filter(pl.col("count") > 1)
        )

        self.kpis["duplicates"] = {
            "total_duplicate_groups": len(duplicates),
            "total_duplicate_events": duplicates["count"].sum() - len(duplicates),
        }

        dup_pct = (
            self.kpis["duplicates"]["total_duplicate_events"] / len(self.df) * 100
            if len(self.df) > 0
            else 0
        )

        print(
            f"  Grupos con duplicados:      {self.kpis['duplicates']['total_duplicate_groups']}"
        )
        print(
            f"  Eventos duplicados:         {self.kpis['duplicates']['total_duplicate_events']} ({dup_pct:.1f}%)"
        )

        # ALERTA: Si >5% eventos son duplicados
        if dup_pct > 5:
            self.alerts.append(
                f"ALERTA: {dup_pct:.1f}% eventos duplicados (>5%, revisar cooldown)"
            )

        # Mostrar top 5 grupos con más duplicados
        if len(duplicates) > 0:
            top_dups = duplicates.sort("count", descending=True).head(5)
            print("\n  Top 5 grupos con mas duplicados:")
            for row in top_dups.iter_rows(named=True):
                print(
                    f"    {row['symbol']:6s} | {row['event_type']:20s} | {row['time_bucket']} | {row['count']} eventos"
                )

    def analyze_outliers(self):
        """Detecta outliers en spike_x y dollar_volume."""
        print("\n[6] ANALISIS DE OUTLIERS")
        print("-" * 80)

        # Spike_x outliers (si existe la columna)
        if "spike_x" in self.df.columns:
            spike_p99 = self.df["spike_x"].quantile(0.99)
            spike_max = self.df["spike_x"].max()

            self.kpis["spike_x"] = {
                "median": float(self.df["spike_x"].median()),
                "p95": float(self.df["spike_x"].quantile(0.95)),
                "p99": float(spike_p99),
                "max": float(spike_max),
            }

            print(f"  spike_x:")
            print(f"    Mediana:  {self.kpis['spike_x']['median']:.1f}x")
            print(f"    P95:      {self.kpis['spike_x']['p95']:.1f}x")
            print(f"    P99:      {self.kpis['spike_x']['p99']:.1f}x")
            print(f"    Max:      {self.kpis['spike_x']['max']:.1f}x")

            # ALERTA: Si spike_x max es >500x (puede ser split/error)
            if spike_max > 500:
                outliers = self.df.filter(pl.col("spike_x") > 500)
                self.alerts.append(
                    f"ALERTA: {len(outliers)} eventos con spike_x >500x (revisar splits/errores)"
                )

        # Dollar volume outliers
        if "dollar_volume" in self.df.columns:
            dv_median = self.df["dollar_volume"].median()
            dv_p99 = self.df["dollar_volume"].quantile(0.99)
            dv_max = self.df["dollar_volume"].max()

            self.kpis["dollar_volume"] = {
                "median": float(dv_median),
                "p95": float(self.df["dollar_volume"].quantile(0.95)),
                "p99": float(dv_p99),
                "max": float(dv_max),
            }

            print(f"\n  dollar_volume:")
            print(f"    Mediana:  ${self.kpis['dollar_volume']['median']:,.0f}")
            print(f"    P95:      ${self.kpis['dollar_volume']['p95']:,.0f}")
            print(f"    P99:      ${self.kpis['dollar_volume']['p99']:,.0f}")
            print(f"    Max:      ${self.kpis['dollar_volume']['max']:,.0f}")

            # ALERTA: Si mediana es <$50K (baja liquidez)
            if dv_median < 50000:
                self.alerts.append(
                    f"ALERTA: Mediana dollar_volume baja: ${dv_median:,.0f} (<$50K)"
                )

    def analyze_events_per_symbol_day(self):
        """Analiza tasa de eventos por símbolo-día."""
        print("\n[7] EVENTOS POR SIMBOLO-DIA")
        print("-" * 80)

        # Crear columna de fecha (solo dia)
        df_with_date = self.df.with_columns(
            [pl.col("timestamp").dt.date().alias("date")]
        )

        # Contar eventos por symbol-date
        events_per_day = (
            df_with_date.group_by(["symbol", "date"])
            .agg([pl.len().alias("events_count")])
        )

        median_events = events_per_day["events_count"].median()
        p95_events = events_per_day["events_count"].quantile(0.95)
        max_events = events_per_day["events_count"].max()

        self.kpis["events_per_symbol_day"] = {
            "median": float(median_events),
            "p95": float(p95_events),
            "max": int(max_events),
        }

        print(f"  Mediana eventos/simbolo-dia:  {median_events:.1f}")
        print(f"  P95 eventos/simbolo-dia:      {p95_events:.1f}")
        print(f"  Max eventos/simbolo-dia:      {max_events}")

        # ALERTA: Si mediana es >20 eventos/día (demasiado)
        if median_events > 20:
            self.alerts.append(
                f"ALERTA: {median_events:.1f} eventos/dia es muy alto (>20, revisar umbrales)"
            )

        # Mostrar top 5 symbol-days con más eventos
        top_days = events_per_day.sort("events_count", descending=True).head(5)
        print("\n  Top 5 simbolo-dias con mas eventos:")
        for row in top_days.iter_rows(named=True):
            print(f"    {row['symbol']:6s} | {row['date']} | {row['events_count']} eventos")

    def generate_summary(self):
        """Genera resumen final con alertas."""
        print("\n" + "=" * 80)
        print("RESUMEN Y ALERTAS")
        print("=" * 80)

        if self.alerts:
            print(f"\n[!] {len(self.alerts)} ALERTAS DETECTADAS:\n")
            for i, alert in enumerate(self.alerts, 1):
                print(f"  {i}. {alert}")
        else:
            print("\n[OK] No se detectaron alertas. Todos los KPIs dentro de rango esperado.")

        # Guardar KPIs en JSON
        output_path = self.shard_path.parent.parent / "kpis" / f"{self.shard_name}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "shard_name": self.shard_name,
            "analyzed_at": datetime.now().isoformat(),
            "kpis": self.kpis,
            "alerts": self.alerts,
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n[SAVED] KPIs guardados en: {output_path}")

    def run_analysis(self):
        """Ejecuta análisis completo."""
        self.load_shard()
        self.analyze_basic_metrics()
        self.analyze_event_distribution()
        self.analyze_session_distribution()
        self.analyze_direction_bias()
        self.analyze_duplicates()
        self.analyze_outliers()
        self.analyze_events_per_symbol_day()
        self.generate_summary()


def analyze_all_shards(run_date: str = None):
    """Analiza todos los shards de un run específico."""
    if run_date is None:
        run_date = datetime.now().strftime("%Y%m%d")

    shards_dir = Path("processed/events/shards")
    pattern = f"events_intraday_{run_date}_shard*.parquet"

    shard_files = sorted(shards_dir.glob(pattern))

    if not shard_files:
        print(f"[ERROR] No se encontraron shards para {run_date}")
        print(f"        Buscando: {shards_dir / pattern}")
        return

    print(f"\n[INFO] Encontrados {len(shard_files)} shards para analizar\n")

    all_alerts = []

    for shard_file in shard_files:
        analyzer = ShardAnalyzer(shard_file)
        analyzer.run_analysis()
        all_alerts.extend(analyzer.alerts)

    # Resumen global
    print("\n" + "=" * 80)
    print("RESUMEN GLOBAL DE TODOS LOS SHARDS")
    print("=" * 80)

    print(f"\nTotal shards analizados: {len(shard_files)}")
    print(f"Total alertas:           {len(all_alerts)}")

    if all_alerts:
        print("\n[!] ALERTAS CONSOLIDADAS:\n")
        for i, alert in enumerate(all_alerts, 1):
            print(f"  {i}. {alert}")


def main():
    parser = argparse.ArgumentParser(
        description="Analiza KPIs de calidad de shards de eventos intraday"
    )
    parser.add_argument(
        "--shard",
        type=str,
        help="Path a un shard específico para analizar",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Analizar todos los shards del run actual",
    )
    parser.add_argument(
        "--run-date",
        type=str,
        help="Fecha del run (YYYYMMDD). Default: hoy",
    )

    args = parser.parse_args()

    if args.all:
        analyze_all_shards(args.run_date)
    elif args.shard:
        shard_path = Path(args.shard)
        if not shard_path.exists():
            print(f"[ERROR] Shard no encontrado: {shard_path}")
            return

        analyzer = ShardAnalyzer(shard_path)
        analyzer.run_analysis()
    else:
        print("[ERROR] Debes especificar --shard o --all")
        parser.print_help()


if __name__ == "__main__":
    main()
