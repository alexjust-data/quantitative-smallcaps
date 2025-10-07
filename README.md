# Small Caps Algorithmic Trading System

ML-based trading system for small cap momentum patterns using Polygon.io data and DAS Trader Pro execution.

---

## Project Overview

**Objective**: Build a machine learning system to detect and trade momentum patterns in small cap stocks (GEVO, SBOT, DRYS, TOPS, etc.)

**Trading Patterns**:
- Gap & Go / Opening Range Breakout (ORB)
- Parabolic momentum / Exhaustion
- VWAP reclaim/reject
- First pullback
- Halt resumption
- High-of-day breakouts

**Technology Stack**:
- **Data**: Polygon.io Stocks Advanced API
- **Storage**: Parquet (columnar), DuckDB, Polars
- **ML**: LightGBM, XGBoost, PyTorch (TCN/LSTM)
- **Backtesting**: Backtrader, vectorbt
- **Execution**: DAS Trader Pro (via Zimtra prop firm)

---

## Directory Structure

```
D:\04_TRADING_SMALLCAPS\
├── raw/                          # Immutable API data (never modified)
│   ├── market_data/
│   │   ├── bars/
│   │   │   ├── 1min/
│   │   │   ├── 1hour/
│   │   │   └── 1day/
│   │   ├── trades/
│   │   └── quotes/
│   ├── reference/
│   ├── fundamentals/
│   ├── corporate_actions/
│   └── news/
│
├── processed/                    # Cleaned, validated, feature-ready data
│   ├── bars_clean/
│   ├── universe/
│   ├── fundamentals_normalized/
│   ├── corporate_actions_indexed/
│   └── features_engineered/
│
├── models/
│   ├── datasets_ready/
│   ├── trained_models/
│   ├── predictions/
│   └── evaluation/
│
├── logs/
│   ├── ingestion/
│   ├── processing/
│   └── training/
│
├── scripts/
│   ├── ingestion/
│   ├── processing/
│   ├── features/
│   └── modeling/
│
├── notebooks/
│   ├── 01_universe_smallcaps.ipynb
│   ├── 02_patterns_event_study.ipynb
│   └── 03_feature_engineering.ipynb
│
└── docs/
    ├── database_architecture.md
    └── rute_map.md
```

---

## Data Architecture

### Design Philosophy

**raw/** - Immutable source data
- Never modified after download
- Timestamped by ingestion date
- Enables full pipeline reprocessing
- Provides audit trail

**processed/** - Curated ML-ready data
- Cleaned and validated
- Synchronized timestamps (ET timezone)
- Split-adjusted prices
- Versioned by processing date

### Advantages

| Feature | Benefit |
|---------|---------|
| Reproducibility | Reprocess entire pipeline from raw/ |
| Data integrity | Isolate API changes from processed data |
| Version control | Track data lineage: raw → processed → features → model |
| Rollback capability | Restore any historical date range |
| Incremental updates | Process only new data daily |
| Leakage prevention | Controlled temporal sequencing |

---

## Data Sources

### Primary: Polygon.io Stocks Advanced ($199/month)

**Core Data**:
- Aggregates (OHLCV): 1-second to 1-month bars, 20+ years history
- Trades: Tick-by-tick data with exchange/conditions
- Quotes: Level 1 bid/ask with timestamps
- Snapshots: Real-time market overview (10k+ tickers)

**Reference Data**:
- All tickers (active + delisted)
- Ticker details (market cap, shares outstanding)
- News with sentiment

**Fundamentals**:
- Income statements, balance sheets, cash flow (quarterly)
- Financial ratios (P/E, P/B, debt-to-equity)

**Corporate Actions**:
- Splits (including reverse splits)
- Dividends

### Complementary (Free)

| Source | Data | Use Case |
|--------|------|----------|
| SEC EDGAR API | 8-K, S-1, S-3, 424B5 filings | Dilution/offering detection |
| FINRA | Daily short volume | Short squeeze signals |
| Nasdaq | Trading halts RSS feed | Halt events |
| Yahoo Finance | Basic fundamentals | Backup reference data |

---

## Small Caps Universe Definition

### Screening Criteria

```python
price: $0.50 - $20.00
market_cap: < $2B
float: < 50-100M shares
rvol_premarket: > 2
gap_pct: >= 10%
volume_premarket: > 100k
exclude: ETFs, ADRs (optional), OTC (optional)
```

### Enrichment Factors

- Recent SEC filings (S-3, 424B5 ATM offerings)
- Halt history (frequency, duration)
- Short volume ratio (FINRA)
- Reverse split history
- News sentiment

**Expected Universe Size**: 3,000-5,000 active tickers, 500 high-priority volatile tickers

---

## Data Ingestion Plan (Month 1)

### Week 1: Foundation
```
Priority: CRITICAL

1. Download all tickers (active + delisted)
   Endpoints: /v3/reference/tickers?active=true|false
   Output: raw/reference/tickers_snapshot_YYYYMMDD.parquet
   Size: ~50k tickers

2. Filter small caps universe
   Criteria: market_cap < $2B, price $0.50-$20
   Output: processed/universe/small_caps_active.parquet
   Size: ~3-5k tickers

3. Download 1-day bars (5 years, all small caps)
   Endpoint: /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}
   Period: 2019-01-01 to 2024-12-31
   Output: raw/market_data/bars/1day/
   Size: ~500 MB compressed

4. Download corporate actions (5 years)
   Endpoints: /v3/reference/splits, /v3/reference/dividends
   Output: raw/corporate_actions/
   Size: ~50 MB
```

### Week 2-3: Core Intraday Data
```
Priority: CRITICAL

1. Identify top 500 volatile small caps
   Criteria: avg_gap > 10%, avg_rvol > 2, volatility > 5%/day

2. Download 1-min bars (3 years, top 500)
   Endpoint: /v2/aggs/ticker/{ticker}/range/1/minute/{from}/{to}
   Period: 2022-01-01 to 2024-12-31
   Output: raw/market_data/bars/1min/
   Size: 50-100 GB compressed
   Rate: ~3M API requests over 2 weeks

3. Download 1-hour bars (5 years, all small caps)
   Output: raw/market_data/bars/1hour/
   Size: ~5 GB
```

### Week 4: Complementary Data
```
Priority: IMPORTANT

1. Fundamentals (5 years, quarterly)
   Endpoints: /vX/reference/financials
   Size: ~200 MB

2. News with sentiment (2 years)
   Endpoint: /v2/reference/news
   Size: ~1-2 GB

Optional (if time permits):
3. Trades (1 year, top 50 tickers): ~20-30 GB
4. Quotes (1 year, top 50 tickers): ~30-50 GB
```

### Total Storage

| Data Type | Coverage | Size | Priority |
|-----------|----------|------|----------|
| 1-day bars | 5yr, all small caps | ~500 MB | CRITICAL |
| 1-hour bars | 5yr, all small caps | ~5 GB | IMPORTANT |
| 1-min bars | 3yr, top 500 | 50-100 GB | CRITICAL |
| Fundamentals | 5yr | ~200 MB | CRITICAL |
| Corporate actions | 5yr | ~50 MB | CRITICAL |
| News | 2yr | ~1-2 GB | IMPORTANT |
| Trades (optional) | 1yr, top 50 | ~20-30 GB | OPTIONAL |
| Quotes (optional) | 1yr, top 50 | ~30-50 GB | OPTIONAL |
| **Total** | | **150-200 GB** | |

---

## Feature Engineering

### 1. Price/Volume (from bars)
- Gap percentage: `(open - prev_close) / prev_close * 100`
- Relative volume (RVOL): `volume / sma(volume, 20)`
- VWAP deviation: `(close - vwap) / vwap * 100`
- Range expansion: `(high - low) / sma(high - low, 20)`
- Parabolic slope: linear regression of price over 15min window
- High-of-day break: `close == high`
- Volume profile concentration (Gini coefficient)

### 2. Order Flow (from trades)
- Buy/sell delta: `sum(size @ ask) - sum(size @ bid)`
- Delta ratio: `delta / total_volume`
- Large print detection: `trades > 3 * std(size)`
- Volume burst: `volume_1min / sma(volume_1min, 20) > 3`
- Exhaustion: large print + price reversal

### 3. Microstructure (from quotes)
- Bid-ask spread: `(ask - bid) / mid * 100`
- Spread expansion: `spread / sma(spread, 20)`
- Bid-ask imbalance: `(bid_size - ask_size) / (bid_size + ask_size)`
- Liquidity depth: `bid_size + ask_size`

### 4. Fundamentals
- Market cap changes (dilution tracking)
- Debt-to-equity trend
- Cash burn rate: `operating_cash_flow / quarters`
- Revenue growth QoQ, YoY

### 5. Corporate Events
- Days since reverse split
- Days since last offering
- Split frequency (rolling 12M)
- Recent filing flags (8-K, S-3, 424B5)

### 6. Sentiment (from news)
- News count (1d, 7d, 30d rolling)
- Sentiment score (positive, negative, neutral)
- Keyword detection (bankruptcy, merger, FDA, halt, offering)

---

## Machine Learning Pipeline

### Labels (Target Generation)

**Triple Barrier Method**:
```python
take_profit = +15%
stop_loss = -10%
timeout = 15 minutes

label = +1  # if TP hit first
label = -1  # if SL hit first
label = 0   # if timeout
```

**Forward Return Method**:
```python
return_5min = (price_t+5 - price_t) / price_t
return_15min = (price_t+15 - price_t) / price_t

label = +1 if return_15min > 0.15
label = -1 if return_15min < -0.10
label = 0 otherwise
```

### Models

**Baseline**:
- LightGBM / XGBoost (tabular features)
- CatBoost (with categorical features: sector, exchange)

**Sequential**:
- TCN (Temporal Convolutional Networks)
- GRU/LSTM with ticker embeddings

**Multi-modal**:
- FinBERT embeddings (news) + numeric features fusion

**Clustering**:
- DBSCAN / UMAP for pattern discovery
- Identify families: pump, dump, sideways, grind

### Validation

**Walk-Forward Analysis**:
- Train: months 1-6
- Validate: month 7
- Test: month 8
- Roll forward monthly

**Purged K-Fold**:
- Remove temporal leakage
- Purge buffer: 1 day before/after validation set

**Metrics**:
- Expectancy per trade
- Profit factor
- Sharpe ratio
- CAR/MDD
- Hit rate by pattern
- Tail risk (95th percentile loss)

---

## Backtesting Framework

**Engine**: Backtrader (event-driven) or vectorbt (vectorized)

**Cost Model**:
```python
ecn_fees = $0.003 per share
sec_fees = $0.0000278 per dollar sold
slippage = f(spread, liquidity, ssr_flag)
  - avg_spread * 0.5 (normal)
  - avg_spread * 2.0 (during SSR)
  - adjusted by queue depth proxy
```

**Risk Controls**:
- Max loss per day: $X
- Max position size: f(ATR, account_size)
- Max open positions: N
- Trading hours: 09:30-16:00 ET
- No trading during halts
- Kill switch on drawdown threshold

**Slippage Model**:
```python
if ssr_active:
    slippage_factor = 2.0
else:
    slippage_factor = 0.5

slippage = avg_spread * slippage_factor * (1 + volume_imbalance)
```

---

## Execution (DAS Trader Pro via Zimtra)

### Architecture

```
Python Core (Signal Generation)
  ↓
Bridge (C# DAS API wrapper)
  ↓
DAS Trader Pro
  ↓
Market Execution
```

### Requirements

1. Zimtra account with DAS Trader Pro access
2. DAS API certification and subscription
3. Confirm with Zimtra: DAS API enabled on account

### Risk Management

- Max loss per day (enforced in Python core)
- Hard stop per symbol (enforced in DAS)
- Time-based kill switch (no trades after 15:45 ET)
- Halt detection (auto-cancel pending orders)
- SSR flag monitoring (adjust execution logic)

### Logging

- Order lifecycle: signal → order → fill → exit
- Execution slippage vs model assumption
- Drop copy from DAS (CSV export for reconciliation)

---

## Development Roadmap

### Phase 1: Data Infrastructure (Weeks 1-4)
- [ ] Set up directory structure (raw/, processed/, models/)
- [ ] Create Polygon.io ingestion scripts with logging
- [ ] Download Week 1 data (tickers, daily bars, corporate actions)
- [ ] Download Week 2-3 data (1-min bars for top 500 tickers)
- [ ] Download Week 4 data (fundamentals, news)
- [ ] Validate data quality (missing dates, duplicates, outliers)

### Phase 2: Processing Pipeline (Weeks 5-6)
- [ ] Build raw → processed pipeline with validation
- [ ] Implement timezone normalization (ET)
- [ ] Apply split adjustments
- [ ] Generate universe snapshots (daily)
- [ ] Create feature engineering modules

### Phase 3: Exploratory Analysis (Weeks 7-8)
- [ ] Notebook: Universe analysis (gap, rvol, float distributions)
- [ ] Notebook: Pattern event studies (Gap-&-Go, ORB, VWAP)
- [ ] Label generation (triple barrier, forward returns)
- [ ] Feature importance analysis (Mutual Info, SHAP)

### Phase 4: Model Development (Weeks 9-12)
- [ ] Baseline models (LightGBM, XGBoost)
- [ ] Hyperparameter optimization (Bayesian, Random Search)
- [ ] Walk-forward validation
- [ ] Ensemble methods
- [ ] Sequential models (TCN, LSTM)

### Phase 5: Backtesting (Weeks 13-14)
- [ ] Implement cost model (ECN fees, slippage)
- [ ] Backtest on 1-year out-of-sample
- [ ] Risk metrics analysis
- [ ] Parameter sensitivity analysis

### Phase 6: Paper Trading (Weeks 15-16)
- [ ] DAS Market Replay practice (20 historical sessions)
- [ ] TraderSync journal integration
- [ ] Live paper trading (signals only, manual execution)

### Phase 7: Live Execution (Week 17+)
- [ ] DAS API certification
- [ ] Build C# bridge
- [ ] Deploy risk controls
- [ ] Start with small position sizes
- [ ] Monitor and iterate

---

## Key Technical Decisions

### Why Polygon.io Stocks Advanced?
- 20+ years historical data
- Real-time + delayed data in one plan
- Comprehensive coverage (tickers, trades, quotes, fundamentals)
- Unlimited API calls
- $199/month vs $3,000 one-time (Kibot)

### Why raw/ + processed/ structure?
- Reproducibility: reprocess entire pipeline
- Data integrity: isolate API changes
- Version control: track data lineage
- Rollback capability: restore historical states
- Incremental updates: process only new data
- Leakage prevention: controlled temporal flow

### Why Parquet + DuckDB/Polars?
- Columnar storage: fast analytical queries
- Compression: 5-10x smaller than CSV
- Schema enforcement: type safety
- Partition pruning: query only relevant dates/symbols
- Zero-copy reads: minimal memory overhead

### Why small caps?
- Higher volatility: more predictable momentum patterns
- Lower competition: less algo saturation vs large caps
- Retail-driven: sentiment and order flow more influential
- Catalyst-rich: offerings, halts, news create tradeable events

---

## Risk Warnings

### Survivorship Bias
Polygon.io active tickers may exclude some delistings. Mitigate:
- Use `active=false` parameter to fetch delisted tickers
- Cross-reference with Norgate Data or Sharadar if budget allows
- Be conservative in backtest performance claims

### Data Quality
- Verify no missing dates (holidays, API downtime)
- Check for duplicate timestamps
- Validate split adjustments
- Monitor for outliers (fat-finger trades)

### Model Overfitting
- Use walk-forward validation (not static train/test split)
- Limit hyperparameters (5-7 max)
- Purge temporal leakage in cross-validation
- Test on unseen tickers (not just unseen dates)

### Execution Risk
- Slippage in small caps can be 2-5x model assumptions
- Halts can trap positions
- Low liquidity stocks may not fill limit orders
- Short squeezes can cause extreme losses

### Regulatory Risk
- Small caps subject to SEC scrutiny (pump & dump)
- Pattern day trader rule (US residents)
- Prop firm rules vary (Zimtra, etc.)
- DAS API requires certification

---

## References

### Documentation
- [Polygon.io API Docs](https://polygon.io/docs/stocks)
- [DAS Trader Pro Docs](https://dastrader.com/docs)
- [Database Architecture](docs/database_architecture.md)
- [Route Map](docs/rute_map.md)

### Data Providers
- Polygon.io: https://polygon.io
- SEC EDGAR: https://www.sec.gov/edgar
- FINRA Short Volume: https://www.finra.org/finra-data
- Nasdaq Halts: https://www.nasdaqtrader.com/trader.aspx?id=tradehalts

### Execution
- Zimtra: https://zimtra.com
- DAS Trader Pro: https://dastrader.com
- TraderSync Journal: https://tradersync.com

---

## Contact & Support

For questions or collaboration:
- GitHub Issues: [Create Issue]
- Project Lead: [Your contact]

---

## License

[Specify license - MIT, Apache 2.0, etc.]

---

Last Updated: 2025-01-07
