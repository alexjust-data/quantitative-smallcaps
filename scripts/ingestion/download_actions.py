# scripts/ingestion/download_actions.py
"""
Baja splits y dividends por símbolo (una sola vez) y guarda una tabla unificada para ajustes.
"""
import os, time, requests
import polars as pl
from pathlib import Path
from datetime import datetime

API_KEY = os.environ.get("POLYGON_API_KEY")
SPLITS_URL = "https://api.polygon.io/v3/reference/splits"
DIVS_URL   = "https://api.polygon.io/v3/reference/dividends"

BASE = Path(__file__).resolve().parents[2]
EVENTS = BASE / "processed" / "events" / "events_daily_20251009.parquet"
OUT = BASE / "processed" / "reference" / f"corporate_actions_{datetime.utcnow().strftime('%Y%m%d')}.parquet"
OUT.parent.mkdir(parents=True, exist_ok=True)

def fetch_paginated(url, params):
    """Fetch all pages from paginated endpoint"""
    results = []
    while True:
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            j = r.json()
            results.extend(j.get("results", []))

            nxt = j.get("next_url")
            if not nxt:
                break

            # Polygon "next_url" ya incluye apiKey; si no, añádelo:
            url = nxt
            params = {}
            time.sleep(0.2)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # No data for this ticker
                break
            else:
                raise
        except Exception as e:
            print(f"    Error during pagination: {e}")
            break

    return results

def main():
    print("[OK] Cargando eventos: {}".format(EVENTS))
    ev = pl.read_parquet(EVENTS).select("symbol").unique()
    syms = ev["symbol"].to_list()
    print("[OK] Simbolos unicos: {}".format(len(syms)))

    rows = []
    for i, s in enumerate(syms):
        if (i + 1) % 100 == 0:
            print("  Progreso: {}/{}".format(i+1, len(syms)))

        # Splits
        try:
            sp = fetch_paginated(SPLITS_URL, {"ticker": s, "apiKey": API_KEY})
            for x in sp:
                rows.append({
                    "symbol": s,
                    "type": "split",
                    "execution_date": x.get("execution_date"),
                    "split_from": x.get("split_from"),
                    "split_to": x.get("split_to"),
                    "declaration_date": None,
                    "ex_dividend_date": None,
                    "pay_date": None,
                    "cash_amount": None,
                })
        except Exception as e:
            print("  Error fetching splits for {}: {}".format(s, e))

        # Dividends - skip 401 errors (API tier limitation)
        try:
            dv = fetch_paginated(DIVS_URL, {"ticker": s, "apiKey": API_KEY})
            for x in dv:
                rows.append({
                    "symbol": s,
                    "type": "dividend",
                    "execution_date": None,
                    "split_from": None,
                    "split_to": None,
                    "declaration_date": x.get("declaration_date"),
                    "ex_dividend_date": x.get("ex_dividend_date"),
                    "pay_date": x.get("pay_date"),
                    "cash_amount": x.get("cash_amount"),
                })
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # Skip dividends if unauthorized (API tier limitation)
                pass
            else:
                print("  Error fetching dividends for {}: {}".format(s, e))
        except Exception as e:
            print("  Error fetching dividends for {}: {}".format(s, e))

        time.sleep(0.1)

    if rows:
        df = pl.DataFrame(rows)
        df.write_parquet(OUT)
        print("[OK] Guardado: {}".format(OUT))
        print("\nEstadisticas:")
        print("  Total acciones corporativas: {}".format(df.height))
        print("  Splits: {}".format(df.filter(pl.col('type') == 'split').height))
        print("  Dividendos: {}".format(df.filter(pl.col('type') == 'dividend').height))
    else:
        print("Sin acciones corporativas (lista de simbolos vacia?).")

if __name__ == "__main__":
    assert API_KEY, "Falta POLYGON_API_KEY"
    main()
