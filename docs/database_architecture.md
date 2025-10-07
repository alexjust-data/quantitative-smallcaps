# Database Architecture for Small Caps ML Trading System

## Polygon.io Stocks Advanced - API Endpoints Analysis

### 1. CORE Market Data Endpoints

#### Aggregates (Bars)
- **Endpoint**: `/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`
- **Fields**: `open, high, low, close, volume, vwap, timestamp, transactions`
- **Intervals**: second, minute, hour, day, week, month, quarter, year
- **Historical**: 20+ years (Stocks Advanced plan)
- **Limit**: 50,000 records per request (pagination supported)
- **Use**: Primary source for OHLCV features

#### Trades
- **Endpoint**: `/v3/trades/{ticker}`
- **Fields**: `price, size, participant_timestamp, sip_timestamp, trf_timestamp, exchange, conditions, tape`
- **Historical**: 20+ years
- **Limit**: 50,000 per request (pagination)
- **Use**: Order flow analysis, delta calculation, aggressor detection

#### Quotes
- **Endpoint**: `/v3/quotes/{ticker}`
- **Fields**: `bid, ask, bid_size, ask_size, timestamp, exchange, conditions`
- **Historical**: 20+ years
- **Use**: Spread analysis, liquidity assessment, microstructure features

### 2. Reference Data Endpoints

#### All Tickers
- **Endpoint**: `/v3/reference/tickers`
- **Fields**: `symbol, name, market, type, active, exchange, locale, currency_name`
- **Filters**: `active` (true/false), `type`, `market`, `exchange`, `search`, `date`
- **Use**: Universe construction, active/delisted filtering

#### Ticker Details
- **Endpoint**: `/v3/reference/tickers/{ticker}`
- **Fields**: `market_cap, outstanding_shares, description, homepage_url, total_employees, list_date`
- **Use**: Fundamental filters, market cap classification

#### Ticker News
- **Endpoint**: `/v2/reference/news`
- **Fields**: `title, description, published_utc, article_url, tickers, sentiment, keywords`
- **Use**: NLP sentiment analysis, catalyst detection

### 3. Fundamentals Endpoints

#### Income Statements
- **Endpoint**: `/vX/reference/financials` (filtered by statement type)
- **Source**: SEC XBRL filings
- **Fields**: `revenues, net_income, eps_basic, eps_diluted, operating_income`
- **Frequency**: Quarterly, Annual
- **Update**: Daily

#### Balance Sheets
- **Fields**: `total_assets, total_liabilities, stockholders_equity, cash, total_debt`
- **Use**: Financial health, leverage ratios

#### Cash Flow Statements
- **Fields**: `operating_cash_flow, capital_expenditure, free_cash_flow`
- **Use**: Liquidity assessment, burn rate

#### Stock Financials (Ratios)
- **Fields**: `pe_ratio, pb_ratio, roe, debt_to_equity, current_ratio`
- **Use**: Valuation features, cross-sectional analysis

### 4. Corporate Actions Endpoints

#### Splits
- **Endpoint**: `/v3/reference/splits`
- **Fields**: `execution_date, split_from, split_to, ticker`
- **Use**: Price adjustment, reverse split flagging (critical for small caps)

#### Dividends
- **Endpoint**: `/v3/reference/dividends`
- **Fields**: `ex_dividend_date, cash_amount, record_date, pay_date`
- **Use**: Corporate event features

### 5. Real-time & Snapshot Endpoints

#### Full Market Snapshot
- **Endpoint**: `/v2/snapshot/locale/us/markets/stocks/tickers`
- **Coverage**: 10,000+ tickers in single response
- **Fields**: `last_price, bid, ask, volume, todaysChange, todaysChangePerc, vwap, prev_day_bar, day_bar, min_bar`
- **Use**: Daily gapper detection, momentum screening

#### Previous Close
- **Endpoint**: `/v2/aggs/ticker/{ticker}/prev`
- **Use**: Gap calculation base

---

## Data Lake Architecture

### Structure Overview

```
D:\04_TRADING_SMALLCAPS\
├── raw/                          # Immutable source data (never modified)
│   ├── market_data/
│   │   ├── bars/
│   │   │   ├── 1min/
│   │   │   │   └── year=2023/month=06/symbol=GEVO/
│   │   │   │       └── date=2023-06-15.parquet
│   │   │   ├── 1hour/
│   │   │   └── 1day/
│   │   ├── trades/
│   │   │   └── symbol=SBOT/date=2023-06-15/
│   │   │       └── trades.parquet
│   │   └── quotes/
│   │       └── symbol=DRYS/date=2023-06-15/
│   │           └── quotes.parquet
│   ├── reference/
│   │   ├── tickers_snapshot_YYYYMMDD.parquet
│   │   └── ticker_details/symbol=GEVO/fetched_YYYYMMDD.parquet
│   ├── fundamentals/
│   │   ├── income_statements_raw.parquet
│   │   ├── balance_sheets_raw.parquet
│   │   └── cash_flow_raw.parquet
│   ├── corporate_actions/
│   │   ├── splits_raw.parquet
│   │   └── dividends_raw.parquet
│   └── news/
│       └── year=2023/month=06/date=2023-06-15.parquet
│
├── processed/                    # Cleaned, validated, synchronized data
│   ├── bars_clean/
│   │   ├── 1min/
│   │   │   └── symbol=GEVO/date=2023-06-15.parquet
│   │   ├── 1hour/
│   │   └── 1day/
│   ├── trades_clean/
│   ├── quotes_clean/
│   ├── universe/
│   │   ├── small_caps_active.parquet
│   │   ├── small_caps_delisted.parquet
│   │   └── universe_daily_snapshots/date=YYYYMMDD.parquet
│   ├── fundamentals_normalized/
│   │   └── combined_fundamentals.parquet
│   ├── corporate_actions_indexed/
│   │   └── events_by_symbol_date.parquet
│   └── features_engineered/
│       ├── momentum_features/
│       ├── volume_features/
│       ├── microstructure_features/
│       └── fundamental_features/
│
├── models/
│   ├── datasets_ready/
│   │   └── train_YYYYMMDD_validation_YYYYMMDD.parquet
│   ├── trained_models/
│   │   └── lightgbm_v1_YYYYMMDD/
│   ├── predictions/
│   └── evaluation/
│
├── logs/
│   ├── ingestion/
│   │   └── polygon_download_YYYYMMDD.log
│   ├── processing/
│   └── training/
│
└── scripts/
    ├── ingestion/
    ├── processing/
    ├── features/
    └── modeling/
```

### Design Rationale: raw/ vs processed/

| Aspect | raw/ (Immutable) | processed/ (Curated) |
|--------|------------------|----------------------|
| **Purpose** | Store data exactly as received from API | Store cleaned, validated, feature-ready data |
| **Modification** | Never modified after download | Updated when pipeline logic changes |
| **Versioning** | Timestamped by download date | Versioned by processing date |
| **Reproducibility** | Full reprocessing always possible | Dependent on pipeline version |
| **Data Leakage Risk** | None (source of truth) | Controlled via processing logs |
| **Storage Efficiency** | May contain duplicates/errors | Deduplicated, optimized |
| **Use Case** | Source for ETL pipelines | Direct input to feature engineering |

### Workflow Dynamics Comparison

| Stage | Monolithic Structure | raw/ + processed/ Pipeline |
|-------|---------------------|---------------------------|
| **Ingestion** | Overwrites existing data | Appends to raw/, never modifies |
| **Cleaning** | In-place modification (risk of data loss) | Creates new version in processed/ |
| **Feature Engineering** | Unclear data version dependency | Clear lineage: raw → processed → features |
| **Model Training** | Direct from mixed-version data | From versioned, frozen datasets |
| **Debugging** | Cannot reproduce exact training conditions | Full reproduction via dataset snapshots |
| **Incremental Updates** | Regenerate all | Process only new raw/ data |
| **Rollback** | Impossible without backups | Reprocess from raw/ with any date range |

---

## Schema Definitions

### 1. bars_1min (Core Table)
```python
{
    'symbol': 'str',
    'timestamp': 'datetime64[ns, UTC]',
    'open': 'float32',
    'high': 'float32',
    'low': 'float32',
    'close': 'float32',
    'volume': 'int64',
    'vwap': 'float32',
    'transactions': 'int32',
    'date': 'date',  # partition key
    'year': 'int16',  # partition key
    'month': 'int8'   # partition key
}
```

### 2. trades (Order Flow)
```python
{
    'symbol': 'str',
    'timestamp': 'datetime64[ns, UTC]',
    'price': 'float32',
    'size': 'int32',
    'exchange': 'int8',
    'conditions': 'list[int]',
    'tape': 'int8',  # 1=NYSE, 2=ARCA, 3=NASDAQ
    'date': 'date'
}
```

### 3. quotes (Spread Analysis)
```python
{
    'symbol': 'str',
    'timestamp': 'datetime64[ns, UTC]',
    'bid': 'float32',
    'ask': 'float32',
    'bid_size': 'int32',
    'ask_size': 'int32',
    'spread': 'float32',  # derived: ask - bid
    'spread_pct': 'float32',  # derived: spread / mid * 100
    'mid': 'float32',  # derived: (bid + ask) / 2
    'date': 'date'
}
```

### 4. tickers_universe (Master List)
```python
{
    'symbol': 'str',
    'name': 'str',
    'market': 'str',
    'type': 'str',  # 'CS' = Common Stock, 'ETF', 'ADRC'
    'active': 'bool',
    'delisted_utc': 'datetime64[ns, UTC]',  # null if active
    'primary_exchange': 'str',
    'currency_name': 'str',
    'market_cap': 'float64',
    'outstanding_shares': 'int64',
    'locale': 'str',
    'snapshot_date': 'date',
    'last_updated': 'datetime64[ns, UTC]'
}
```

### 5. fundamentals_combined
```python
{
    'symbol': 'str',
    'cik': 'str',
    'filing_date': 'date',
    'period_end_date': 'date',
    'fiscal_period': 'str',  # 'Q1', 'Q2', 'FY'
    'fiscal_year': 'int16',

    # Income Statement
    'revenues': 'float64',
    'cost_of_revenue': 'float64',
    'gross_profit': 'float64',
    'operating_income': 'float64',
    'net_income': 'float64',
    'eps_basic': 'float32',
    'eps_diluted': 'float32',

    # Balance Sheet
    'total_assets': 'float64',
    'current_assets': 'float64',
    'cash_and_equivalents': 'float64',
    'total_liabilities': 'float64',
    'current_liabilities': 'float64',
    'total_debt': 'float64',
    'stockholders_equity': 'float64',

    # Cash Flow
    'operating_cash_flow': 'float64',
    'capital_expenditure': 'float64',
    'free_cash_flow': 'float64',

    # Derived Ratios
    'pe_ratio': 'float32',
    'pb_ratio': 'float32',
    'debt_to_equity': 'float32',
    'current_ratio': 'float32',
    'roe': 'float32'
}
```

### 6. corporate_actions
```python
{
    'symbol': 'str',
    'event_type': 'str',  # 'split', 'reverse_split', 'dividend'
    'event_date': 'date',
    'ex_date': 'date',
    'split_from': 'float32',  # null for dividends
    'split_to': 'float32',    # null for dividends
    'split_ratio': 'float32', # derived: split_to / split_from
    'dividend_amount': 'float32',  # null for splits
    'announcement_date': 'date'
}
```

### 7. news_sentiment
```python
{
    'article_id': 'str',
    'published_utc': 'datetime64[ns, UTC]',
    'title': 'str',
    'description': 'str',
    'article_url': 'str',
    'tickers': 'list[str]',
    'keywords': 'list[str]',
    'sentiment': 'str',  # 'positive', 'negative', 'neutral'
    'sentiment_score': 'float32',  # if available
    'publisher': 'str',
    'date': 'date'
}
```

### 8. daily_snapshots (Gapper Detection)
```python
{
    'symbol': 'str',
    'date': 'date',
    'timestamp': 'datetime64[ns, UTC]',

    # Previous day
    'prev_close': 'float32',
    'prev_volume': 'int64',
    'prev_vwap': 'float32',

    # Current day
    'open': 'float32',
    'high': 'float32',
    'low': 'float32',
    'close': 'float32',
    'volume': 'int64',
    'vwap': 'float32',

    # Derived metrics
    'gap_pct': 'float32',  # (open - prev_close) / prev_close * 100
    'change_pct': 'float32',  # (close - prev_close) / prev_close * 100
    'rvol': 'float32',  # volume / avg_volume_20d
    'range_pct': 'float32',  # (high - low) / open * 100

    # Real-time snapshot
    'last_price': 'float32',
    'bid': 'float32',
    'ask': 'float32',
    'spread': 'float32'
}
```

---

## Data Ingestion Strategy (Month 1 - $199 Plan)

### Week 1: Foundation
**Priority: CRITICAL**
```
1. Download all tickers (active + delisted)
   - Endpoint: /v3/reference/tickers?active=true
   - Endpoint: /v3/reference/tickers?active=false
   - Storage: raw/reference/tickers_snapshot_YYYYMMDD.parquet
   - Estimated: ~50k tickers total

2. Filter small caps universe
   - Criteria: market_cap < $2B, price $0.50-$20
   - Exclude: ETFs, ADRs (optional), OTC (optional)
   - Storage: processed/universe/small_caps_active.parquet
   - Estimated: ~3000-5000 tickers

3. Download 1-day bars (5 years, all small caps)
   - Endpoint: /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}
   - Period: 2019-01-01 to 2024-12-31
   - Storage: raw/market_data/bars/1day/
   - Estimated size: ~500 MB compressed

4. Download corporate actions
   - Splits: /v3/reference/splits
   - Dividends: /v3/reference/dividends
   - Period: Last 5 years
   - Storage: raw/corporate_actions/
   - Estimated size: ~50 MB
```

### Week 2-3: Core Intraday Data
**Priority: CRITICAL**
```
1. Identify top 500 volatile small caps
   - Criteria: avg_gap > 10%, avg_rvol > 2, price volatility > 5%/day
   - Use processed 1-day bars for screening

2. Download 1-min bars (3 years, top 500 tickers)
   - Endpoint: /v2/aggs/ticker/{ticker}/range/1/minute/{from}/{to}
   - Period: 2022-01-01 to 2024-12-31
   - Partition: by year/month/symbol/date
   - Storage: raw/market_data/bars/1min/
   - Estimated size: 50-100 GB compressed
   - Rate: ~50k records/request, ~390 trading mins/day = 8 requests/ticker/day
   - Total: 500 tickers * 750 days * 8 requests = 3M requests (spread over 2 weeks)

3. Download 1-hour bars (5 years, all small caps)
   - For medium-term feature engineering
   - Estimated size: ~5 GB
```

### Week 4: Complementary Data
**Priority: IMPORTANT**
```
1. Download fundamentals (5 years)
   - Income statements (quarterly): /vX/reference/financials
   - Balance sheets (quarterly)
   - Cash flow statements (quarterly)
   - Storage: raw/fundamentals/
   - Estimated size: ~200 MB

2. Download news with sentiment (2 years)
   - Endpoint: /v2/reference/news
   - Filter: tickers in small caps universe
   - Storage: raw/news/
   - Estimated size: ~1-2 GB

3. Download trades (1 year, top 50 tickers only)
   - Endpoint: /v3/trades/{ticker}
   - Use: Advanced order flow analysis
   - Storage: raw/market_data/trades/
   - Estimated size: ~20-30 GB
   - Priority: OPTIONAL (only if time permits)

4. Download quotes (1 year, top 50 tickers only)
   - Endpoint: /v3/quotes/{ticker}
   - Use: Spread/liquidity analysis
   - Storage: raw/market_data/quotes/
   - Estimated size: ~30-50 GB
   - Priority: OPTIONAL (only if time permits)
```

### Storage Summary

| Data Type | Timeframe | Coverage | Size (compressed) | Priority |
|-----------|-----------|----------|-------------------|----------|
| 1-day bars | 5 years | All small caps (~5k) | ~500 MB | CRITICAL |
| 1-hour bars | 5 years | All small caps | ~5 GB | IMPORTANT |
| 1-min bars | 3 years | Top 500 volatile | 50-100 GB | CRITICAL |
| Fundamentals | 5 years | All small caps | ~200 MB | CRITICAL |
| Corporate actions | 5 years | All small caps | ~50 MB | CRITICAL |
| News | 2 years | Small caps universe | ~1-2 GB | IMPORTANT |
| Trades | 1 year | Top 50 | ~20-30 GB | OPTIONAL |
| Quotes | 1 year | Top 50 | ~30-50 GB | OPTIONAL |
| **Total (without optional)** | | | **~150-200 GB** | |
| **Total (with optional)** | | | **~200-280 GB** | |

---

## Feature Engineering Categories

### 1. Price/Volume Features (from bars)
- Gap percentage at open: `(open - prev_close) / prev_close`
- Relative volume (RVOL): `volume / sma(volume, 20)`
- VWAP deviation: `(close - vwap) / vwap`
- Range expansion rate: `(high - low) / sma(high - low, 20)`
- Intraday return: `(close - open) / open`
- High-of-day break: `close == high`
- Low-of-day break: `close == low`
- Volume profile concentration (Gini coefficient)
- Price velocity: `(close - close_5min_ago) / 5min`
- Parabolic slope: linear regression of price over 15min window

### 2. Order Flow Features (from trades)
- Buy/sell aggressor delta: `sum(size where price >= ask) - sum(size where price <= bid)`
- Delta ratio: `delta / total_volume`
- Trade size distribution (mean, median, 95th percentile)
- Large print detection: trades > 3*std(size)
- Volume burst: `volume_1min / sma(volume_1min, 20) > 3`
- Trade frequency: `count(trades) per minute`
- Exhaustion detection: large print + price reversal

### 3. Microstructure Features (from quotes)
- Bid-ask spread: `ask - bid`
- Spread percentage: `(ask - bid) / mid * 100`
- Spread expansion: `spread / sma(spread, 20)`
- Bid-ask imbalance: `(bid_size - ask_size) / (bid_size + ask_size)`
- Quote stability: rolling std of mid price
- Liquidity depth proxy: `bid_size + ask_size`

### 4. Fundamental Features
- Market cap changes (dilution tracking)
- Float changes (from shares outstanding)
- Debt-to-equity trend
- Cash burn rate: `operating_cash_flow / quarters`
- Revenue growth: `(revenue_Q - revenue_Q-4) / revenue_Q-4`
- EPS surprise: `(eps_actual - eps_consensus) / eps_consensus` (requires consensus data)

### 5. Corporate Event Features
- Days since reverse split
- Days since last offering/dilution
- Split frequency (rolling 12 months)
- Dividend history (binary flag for small caps)
- Recent filing flags (8-K, S-3, 424B5)

### 6. Sentiment Features (from news)
- News count (rolling 1d, 7d, 30d)
- Sentiment score (positive, negative, neutral counts)
- Keyword detection (bankruptcy, merger, FDA, halt, offering)
- Publishing velocity (news/hour during market hours)

---

## ML Workflow Advantages

### Monolithic Structure
| Aspect | Impact |
|--------|--------|
| Feature drift | High risk: rewriting data changes features silently |
| Temporal leakage | Possible if future data accidentally mixed |
| Training/validation splits | Difficult to reproduce exact splits |
| Incremental learning | Must regenerate entire dataset |
| Debugging | Cannot trace feature to data version |
| Scalability | Poor: must reload all data for each change |

### raw/ + processed/ Pipeline
| Aspect | Impact |
|--------|--------|
| Feature drift | Controlled: each feature version linked to processed data version |
| Temporal leakage | Prevented: processed/ generated sequentially by date |
| Training/validation splits | Reproducible: frozen datasets in models/datasets_ready/ |
| Incremental learning | Efficient: load only new dates from processed/ |
| Debugging | Traceable: raw → processed → features → model lineage |
| Scalability | High: parallel processing of date partitions |

---

## When to Use Monolithic Structure

Optimal if:
- Dataset < 100 GB
- Single user, exploratory work
- No automated pipelines required
- Rapid prototyping phase
- No model reproducibility requirements

Use Pipeline Structure if:
- Dataset > 100 GB
- Multi-user collaboration
- Production ML system
- Regulatory/audit requirements
- Incremental updates needed
- Model versioning critical

---

## Implementation Priorities

### Immediate (Before Polygon subscription)
1. Create directory structure (raw/, processed/, models/, logs/)
2. Set up Python environment (polars, duckdb, pyarrow, requests)
3. Create ingestion scripts with logging
4. Test with 1-2 tickers (free tier or sample data)

### Month 1 (Active subscription)
1. Week 1: Download reference data + daily bars + corporate actions
2. Week 2-3: Download 1-min bars for top 500 volatile tickers
3. Week 4: Download fundamentals, news, optional trades/quotes
4. Validate data quality (missing dates, duplicates, outliers)

### Post-download
1. Build processing pipelines (raw → processed)
2. Feature engineering scripts
3. Initial exploratory analysis
4. Label generation (triple-barrier, forward returns)
5. Baseline model training

---

## Next Steps

1. Create ingestion scripts with rate limiting and error handling
2. Design processing pipeline with validation checkpoints
3. Build feature engineering modules
4. Set up experiment tracking (MLflow, Weights & Biases)
5. Create ETL workflow diagram (raw → processed → features → model)
