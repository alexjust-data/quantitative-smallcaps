# scripts/ingestion/download_event_news.py
"""
Descarga noticias ±1 día alrededor de cada evento (solo títulos/tiempo/sentimiento).
Usa POLYGON_API_KEY del entorno y crea un parquet por lotes.
"""
import os, time, math, json, gzip
import polars as pl
import requests
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
EVENTS = BASE / "processed" / "events" / "events_daily_20251009.parquet"  # o el anotated si prefieres
OUT_DIR = BASE / "processed" / "news"
OUT_DIR.mkdir(parents=True, exist_ok=True)

API_KEY = os.environ.get("POLYGON_API_KEY")
BASE_URL = "https://api.polygon.io/v2/reference/news"

PER_PAGE = 50
SLEEP = 0.25

def fetch_news(symbol, from_dt, to_dt):
    """Fetch news for symbol in date range"""
    page = 1
    rows = []
    while True:
        params = {
            "ticker": symbol,
            "published_utc.gte": from_dt.isoformat(timespec="seconds")+"Z",
            "published_utc.lte": to_dt.isoformat(timespec="seconds")+"Z",
            "order": "asc",
            "limit": PER_PAGE,
            "apiKey": API_KEY,
        }

        try:
            r = requests.get(BASE_URL, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()

            results = data.get("results", [])
            for x in results:
                rows.append({
                    "symbol": symbol,
                    "published_utc": x.get("published_utc"),
                    "title": x.get("title"),
                    "description": x.get("description"),
                    "source": x.get("source"),
                    "article_url": x.get("article_url"),
                    "amp_url": x.get("amp_url"),
                    "tickers": ",".join(x.get("tickers", [])) if x.get("tickers") else None,
                    "sentiment": x.get("insights", [{}])[0].get("sentiment") if x.get("insights") else None,
                })

            if len(results) < PER_PAGE:
                break

            page += 1
            time.sleep(SLEEP)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # No news for this ticker
                break
            else:
                raise
        except Exception as e:
            print(f"    Error fetching page {page}: {e}")
            break

    return pl.DataFrame(rows) if rows else None

def main():
    print("[OK] Cargando eventos: {}".format(EVENTS))
    ev = pl.read_parquet(EVENTS).select(["symbol","timestamp"]).unique()
    print("[OK] Eventos unicos: {}".format(ev.height))

    # Filter future events
    now_utc = datetime.utcnow()
    ev = ev.with_columns([
        pl.col("timestamp").cast(pl.Datetime).alias("dt")
    ])
    ev = ev.filter(pl.col("dt") <= now_utc)
    print("[OK] Eventos hasta ahora: {}".format(ev.height))

    out_path = OUT_DIR / f"events_news_{datetime.utcnow().strftime('%Y%m%d')}.parquet"
    chunks = []

    for i, row in enumerate(ev.iter_rows()):
        if (i + 1) % 10 == 0:
            print("  Progreso: {}/{}".format(i+1, ev.height))

        sym, ts, dt = row

        # Clamp to_date to now
        frm = dt - timedelta(days=1)
        to  = min(dt + timedelta(days=1), now_utc)

        try:
            df = fetch_news(sym, frm, to)
            if df is not None and df.height:
                df = df.with_columns([
                    pl.lit(sym).alias("event_symbol"),
                    pl.lit(ts).cast(pl.Datetime).alias("event_ts")
                ])
                chunks.append(df)
        except Exception as e:
            print("  Fallo {} {}: {}".format(sym, dt.date(), e))

        time.sleep(SLEEP)

    if chunks:
        final = pl.concat(chunks)
        final.write_parquet(out_path)
        print("[OK] Guardado: {}".format(out_path))
        print("\nEstadisticas:")
        print("  Total noticias: {}".format(final.height))
        print("  Eventos con noticias: {}".format(final.select('event_symbol').unique().height))
    else:
        print("No se descargaron noticias.")

if __name__ == "__main__":
    assert API_KEY, "Falta POLYGON_API_KEY en el entorno"
    main()
