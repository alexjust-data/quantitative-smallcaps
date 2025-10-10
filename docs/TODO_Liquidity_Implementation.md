# TODO: Implementación de Liquidity Features & Execution Simulation

**Fase**: Phase 3 (Feature Engineering) y Phase 4 (Backtesting)
**Status**: Pendiente - Ejecutar después de completar Phase 2.1 (Data Ingestion)
**Prioridad**: Alta (crítico para evitar sesgos de backtesting)

---

## Contexto

Durante Phase 2.1 identificamos el problema de **contrapartida/liquidez**: tener una vela de 1 minuto con OHLCV no garantiza que podamos ejecutar órdenes reales. Este documento especifica la implementación completa de la solución en 4 niveles.

**Archivos ya implementados** (estructura base):
- `config/liquidity_filters.yaml` - Configuración parametrizable de todos los umbrales
- `scripts/utils/ssr_calculator.py` - Calculador de SSR según Reg SHO Rule 201
- `scripts/features/liquidity_filters.py` - Filtros de liquidez (Nivel 1) para event detection

**Referencias**:
- Decisiones metodológicas validadas en conversación del 2025-10-10
- Basado en Reg SHO Rule 201 (SSR), best practices de market microstructure
- Config YAML: `config/liquidity_filters.yaml`

---

## Nivel 2: Features de Liquidez (Phase 3 - Feature Engineering)

**Objetivo**: Generar features que el modelo ML aprenda a penalizar para eventos ilíquidos.

### 2.1. Dollar Volume Z-Score con Estacionalidad Intradía

**Archivo**: `scripts/features/liquidity_features.py`

**Especificación**:
```python
def compute_dollar_volume_zscore(df: pl.DataFrame, lookback_days: int = 60) -> pl.DataFrame:
    """
    Calcula z-score de dollar_volume normalizado por minuto-del-día.

    Args:
        df: DataFrame con columnas [symbol, timestamp, volume, vwap, date]
        lookback_days: Días para baseline (60-90 recomendado)

    Returns:
        DataFrame con columnas adicionales:
            - hour, minute (extraídos de timestamp)
            - dv_baseline_by_minute (mediana de dollar_volume para ese (hour, minute) en últimos N días)
            - dv_mad_by_minute (MAD para método robusto)
            - dv_zscore (z-score robusto: (dv - median) / MAD)

    Proceso:
        1. Extraer hour, minute de timestamp
        2. Group by (symbol, hour, minute)
        3. Para cada grupo, calcular median y MAD de dollar_volume en últimos 60 días
           EXCLUYENDO día actual (para evitar look-ahead)
        4. Winsorizar p1-p99 para evitar outliers en baseline
        5. Calcular z-score robusto: (dv - median) / (MAD * 1.4826)
           (factor 1.4826 convierte MAD a equivalente de std para normal)

    Notas:
        - Usar pl.col("date") < current_date para excluir día actual
        - Estacionalidad: 09:30 ≠ 15:59, usar (hour, minute) como key
        - Si lookback insuficiente (< 20 días), marcar como NaN
    """
    pass
```

**Config relevante** (`config/liquidity_filters.yaml`):
```yaml
features:
  dollar_volume_zscore:
    lookback_days: 60
    winsorize_percentiles: [1, 99]
    zscore_method: "robust_mad"
```

### 2.2. Volatility-Adjusted Spread

**Especificación**:
```python
def compute_volatility_adjusted_spread(df: pl.DataFrame, atr_periods: int = 5) -> pl.DataFrame:
    """
    Spread normalizado por volatilidad reciente (ATR).

    Args:
        df: DataFrame con [symbol, timestamp, high, low, close, vwap]
        atr_periods: Períodos para ATR (5 minutos recomendado)

    Returns:
        DataFrame con:
            - atr_5m (Average True Range de 5 períodos)
            - spread_raw ((high - low) / vwap)
            - spread_vol_adj (spread_raw / atr_5m)
            - is_spread_anomaly (True si spread_vol_adj > 1.5)

    Interpretación:
        - spread_vol_adj ~ 1.0: spread normal para régimen actual
        - spread_vol_adj > 1.5: spread anómalo (posible spike no tradeable)
        - spread_vol_adj < 0.5: compresión extrema (baja volatilidad)
    """
    pass
```

**Config**:
```yaml
features:
  volatility_adjusted_spread:
    atr_periods: 5
    anomaly_threshold: 1.5
```

### 2.3. Imbalance Proxy (Presión Direccional)

**Especificación**:
```python
def compute_imbalance_proxy(df: pl.DataFrame) -> pl.DataFrame:
    """
    Proxy de presión compradora/vendedora sin acceso a bid/ask.

    Formula: (close - open) / (high - low)

    Returns:
        DataFrame con:
            - imbalance_proxy ∈ [-1, 1]
                +1: toda la vela fue compradora (close = high, open = low)
                -1: toda la vela fue vendedora (close = low, open = high)
                 0: balanceado
            - is_buyer_pressure (True si imbalance > 0.5)
            - is_seller_pressure (True si imbalance < -0.5)

    Uso en ML:
        - Feature para detectar direccionalidad sostenida
        - Combinar con volumen: high_volume + buyer_pressure = strong signal
    """
    pass
```

### 2.4. Size vs Flow (Fricción por Tamaño de Posición)

**Especificación**:
```python
def compute_size_vs_flow(df: pl.DataFrame, position_usd: float, flow_multiplier: int = 10) -> pl.DataFrame:
    """
    Estima fricción de ejecutar una posición de tamaño X vs flujo disponible.

    Args:
        df: DataFrame con [dollar_volume]
        position_usd: Tamaño objetivo de posición en USD (ej: 50000)
        flow_multiplier: Multiplicador de seguridad (10-20x recomendado)

    Returns:
        DataFrame con:
            - size_vs_flow_ratio (position_usd / (k * dollar_volume))
            - friction_level (categorical: low/medium/high/extreme)
                low: ratio < 0.01 (posición es 1% del flow 10x)
                medium: 0.01-0.05
                high: 0.05-0.10
                extreme: > 0.10
            - is_executable (True si friction_level <= medium)

    Interpretación:
        - Si ratio > 0.05, esperar slippage significativo y partial fills
        - Usar para filtrar eventos donde no podríamos ejecutar tamaño objetivo
    """
    pass
```

**Config**:
```yaml
features:
  size_vs_flow:
    flow_multiplier: 10
    high_friction_threshold: 0.05
```

### 2.5. Trade Difficulty (Métrica Compuesta)

**Especificación**:
```python
def compute_trade_difficulty(df: pl.DataFrame) -> pl.DataFrame:
    """
    Métrica compuesta de dificultad de ejecución.

    Formula: spread_pct / (volume / avg_volume_20d)

    Componentes:
        - Spread alto → difícil
        - Volumen bajo vs histórico → difícil
        - Spread bajo + volumen alto → fácil

    Returns:
        DataFrame con:
            - trade_difficulty (float, mayor = más difícil)
            - difficulty_quartile (1-4, donde 4 = más difícil)
            - is_tradeable (True si difficulty < p75)
    """
    pass
```

---

## Nivel 3: Slippage Simulator (Phase 4 - Backtesting)

**Objetivo**: Simular ejecución realista con slippage, partial fills y fricción contextual.

### 3.1. Base Slippage Calculator

**Archivo**: `scripts/backtest/execution_simulator.py`

**Especificación**:
```python
class ExecutionSimulator:
    """Simula ejecución de órdenes con slippage realista"""

    def __init__(self, config_path: Path = None):
        # Cargar config/liquidity_filters.yaml (sección execution)
        pass

    def calculate_base_slippage(self, price: float) -> float:
        """
        Slippage base según precio de la acción.

        Args:
            price: Precio de la acción

        Returns:
            Slippage base (0.0075 para < $2, 0.005 para $2-$10, 0.0035 para > $10)

        Config:
            execution.base_slippage.price_lt_2: 0.0075
            execution.base_slippage.price_2_to_10: 0.0050
            execution.base_slippage.price_gt_10: 0.0035
        """
        pass

    def calculate_spread_slippage(self, spread_est: float) -> float:
        """
        Slippage adicional por spread ancho.

        Formula: max(0, spread_est - 1%) * 0.6

        Config:
            execution.spread_slippage.threshold_pct: 0.01
            execution.spread_slippage.multiplier: 0.6
        """
        pass

    def calculate_size_slippage(self, position_usd: float, dollar_volume: float) -> float:
        """
        Slippage adicional por tamaño de orden vs volumen disponible.

        Formula:
            size_ratio = position_usd / dollar_volume
            if size_ratio < 0.01: return 0
            else: return size_ratio * 0.1

        Config:
            execution.size_slippage.threshold_ratio: 0.01
            execution.size_slippage.multiplier: 0.10
        """
        pass
```

### 3.2. Context Slippage (Apertura, Halts, SSR)

**Especificación**:
```python
    def calculate_context_slippage(
        self,
        timestamp: datetime,
        is_halt_nearby: bool = False,
        is_ssr_active: bool = False,
        side: str = "buy"
    ) -> float:
        """
        Slippage adicional por contexto de mercado.

        Args:
            timestamp: Timestamp de la orden
            is_halt_nearby: True si hay halt en ±15 minutos
            is_ssr_active: True si SSR activo (para shorts)
            side: "buy" o "sell"

        Returns:
            Slippage adicional acumulado

        Lógica:
            - Si 09:30-09:35 (opening range): +0.4%
            - Si is_halt_nearby: +1.0%
            - Si is_ssr_active AND side == "sell": base_slippage * 2.0

        Config:
            execution.context_slippage.opening_range_minutes: 5
            execution.context_slippage.opening_slippage_add: 0.004
            execution.context_slippage.halt_window_minutes: 15
            execution.context_slippage.halt_slippage_add: 0.010
            execution.context_slippage.ssr_short_slippage_mult: 2.0
        """
        pass
```

### 3.3. Partial Fill Calculator

**Especificación**:
```python
    def calculate_fill_ratio(
        self,
        position_usd: float,
        dollar_volume: float,
        is_halt_nearby: bool = False
    ) -> float:
        """
        Calcula qué % de la orden se puede ejecutar.

        Args:
            position_usd: Tamaño objetivo de orden
            dollar_volume: Dollar volume de la vela
            is_halt_nearby: True si hay halt cercano

        Returns:
            Fill ratio ∈ [0, 1]

        Lógica:
            - Regla base: max_fill = dollar_volume / (position_usd * 10)
            - Si > 1.0: fill_ratio = 1.0 (100% fill)
            - Si is_halt_nearby: cap a 0.25 (25% fill máximo)

        Config:
            execution.partial_fill.min_flow_multiplier: 10
            execution.context_slippage.halt_max_fill_ratio: 0.25
        """
        pass
```

### 3.4. Staged Fill (Llenado Escalonado)

**Especificación**:
```python
    def simulate_staged_fill(
        self,
        position_usd: float,
        bars: List[Dict],  # Lista de velas consecutivas
        side: str = "buy"
    ) -> Dict:
        """
        Simula llenado escalonado en múltiples minutos.

        Args:
            position_usd: Tamaño total objetivo
            bars: Lista de velas consecutivas (hasta 3 minutos)
            side: "buy" o "sell"

        Returns:
            {
                "total_filled_usd": float,
                "avg_fill_price": float,
                "total_slippage_pct": float,
                "num_stages": int,
                "stages": [
                    {"minute": 1, "filled_usd": X, "price": Y, "slippage": Z},
                    ...
                ]
            }

        Lógica:
            1. Si position_usd / dollar_volume_first_bar > 1%: activar staged fill
            2. Dividir position_usd en 3 partes iguales
            3. Para cada minuto:
                - Max fill por minuto: min(portion, 20% de dollar_volume)
                - Calcular slippage acumulativo (incrementa con cada stage)
                - Acumular filled_usd
            4. Si no se completa en 3 minutos: partial fill

        Config:
            execution.staged_fill.enabled: true
            execution.staged_fill.trigger_ratio: 0.01
            execution.staged_fill.num_stages: 3
            execution.staged_fill.max_fill_per_stage: 0.20
        """
        pass
```

### 3.5. Main Execution Method (Orquestador)

**Especificación**:
```python
    def simulate_order_fill(
        self,
        bar: Dict,  # Vela actual con OHLCV
        position_usd: float,
        side: str = "buy",
        is_halt_nearby: bool = False,
        is_ssr_active: bool = False,
        use_staged_fill: bool = True,
        subsequent_bars: List[Dict] = None  # Para staged fill
    ) -> Dict:
        """
        Método principal: simula ejecución completa de orden.

        Args:
            bar: Dict con {timestamp, open, high, low, close, vwap, volume, spread_est}
            position_usd: Tamaño de posición objetivo
            side: "buy" o "sell"
            is_halt_nearby: Flag de halt cercano
            is_ssr_active: Flag de SSR activo
            use_staged_fill: Si True, usar llenado escalonado si necesario
            subsequent_bars: Velas siguientes para staged fill (opcional)

        Returns:
            {
                "fill_price": float,          # Precio promedio de ejecución
                "fill_ratio": float,          # % ejecutado [0, 1]
                "executed_usd": float,        # USD realmente ejecutados
                "total_slippage_pct": float,  # Slippage total
                "slippage_breakdown": {
                    "base": float,
                    "spread": float,
                    "size": float,
                    "context": float
                },
                "is_staged": bool,            # True si usó staged fill
                "num_stages": int,            # Número de minutos usados
                "execution_quality": str      # "excellent", "good", "poor", "very_poor"
            }

        Proceso:
            1. Calcular slippage total:
                - base = calculate_base_slippage(bar["close"])
                - spread = calculate_spread_slippage(bar["spread_est"])
                - size = calculate_size_slippage(position_usd, bar["dollar_volume"])
                - context = calculate_context_slippage(timestamp, is_halt, is_ssr, side)
                - total = base + spread + size + context

            2. Decidir estrategia de fill:
                - Si position_usd / dollar_volume > 1% AND use_staged_fill:
                    → simulate_staged_fill()
                - Else:
                    → single fill

            3. Calcular fill_price:
                - Si side == "buy": fill_price = vwap * (1 + total_slippage)
                - Si side == "sell": fill_price = vwap * (1 - total_slippage)

            4. Calcular fill_ratio:
                - calculate_fill_ratio(position_usd, dollar_volume, is_halt)

            5. Clasificar execution_quality:
                - excellent: slippage < 0.5%, fill_ratio = 1.0
                - good: slippage < 1.0%, fill_ratio >= 0.8
                - poor: slippage < 2.0%, fill_ratio >= 0.5
                - very_poor: slippage >= 2.0% OR fill_ratio < 0.5

            6. Return dict completo
        """
        pass
```

---

## Nivel 4: Top Events L2 Data (Futuro - Upgrade de Polygon Tier)

**Objetivo**: Descargar `/trades` y `/quotes` solo para top eventos detectados.

**Especificación** (para cuando upgradeemos tier):

```python
# scripts/ingestion/download_l2_for_top_events.py

def select_top_events_for_l2(
    events_df: pl.DataFrame,
    max_events_per_month: int = 200
) -> pl.DataFrame:
    """
    Selecciona top eventos para descargar L2 data.

    Criterios (desde config):
        - liquidity_score > p90
        - rvol > p90
        - daily_dollar_volume > $5M
        - Limit: 200 eventos/mes

    Returns:
        DataFrame con eventos seleccionados + ventana de descarga
    """
    pass

def download_trades_for_event(
    symbol: str,
    event_timestamp: datetime,
    pre_minutes: int = 15,
    post_minutes: int = 45
) -> pl.DataFrame:
    """
    Descarga /trades para ventana [-15, +45] min alrededor del evento.

    Polygon endpoint: /v3/trades/{ticker}

    Returns:
        DataFrame con: timestamp, price, size, exchange, conditions
    """
    pass

def download_quotes_for_event(
    symbol: str,
    event_timestamp: datetime,
    pre_minutes: int = 15,
    post_minutes: int = 45
) -> pl.DataFrame:
    """
    Descarga /quotes (NBBO) para ventana.

    Polygon endpoint: /v3/quotes/{ticker}

    Returns:
        DataFrame con: timestamp, bid, ask, bid_size, ask_size, bid_exchange, ask_exchange
    """
    pass

def compute_l2_metrics(
    trades_df: pl.DataFrame,
    quotes_df: pl.DataFrame
) -> Dict:
    """
    Calcula métricas adicionales con L2 data:
        - nbbo_spread_real (ask - bid) / mid
        - cross_rate (trades que cruzan spread vs total)
        - uptick_downtick_ratio
        - burstiness_poisson (test de Poisson para detectar algo-driven)

    Returns:
        Dict con métricas calculadas
    """
    pass
```

**Cálculo de viabilidad** (del documento original):
- Top 200 eventos/mes × 12 meses × 3 años = 7,200 eventos
- 60 minutos × 60 seg × ~10 trades/seg = ~36,000 trades/evento
- 7,200 eventos × 36K trades = ~260M trades (manejable en Parquet particionado)

**Storage estimado**: ~50-80 GB para 3 años de L2 data en top eventos

---

## Plan de Ejecución

### Timing
1. **Ahora**: Continuar con Phase 2.1 (Data Ingestion) - descargas en progreso
2. **Después de completar descargas**: Implementar Nivel 2 (Features)
3. **Durante Phase 4**: Implementar Nivel 3 (Slippage Simulator)
4. **Futuro** (si ROI justifica upgrade): Implementar Nivel 4 (L2 Data)

### Orden de implementación recomendado
**Nivel 2 (Features)**:
1. Imbalance proxy (más simple)
2. Volatility-adjusted spread (requiere ATR)
3. Dollar volume z-score (más complejo - estacionalidad)
4. Size vs flow (simple pero requiere parametrización)
5. Trade difficulty (compuesta - usa anteriores)

**Nivel 3 (Slippage)**:
1. Base slippage calculator
2. Spread & size slippage
3. Context slippage (apertura, SSR)
4. Partial fill calculator
5. Staged fill (más complejo)
6. Main execution method (orquestador)

### Tests requeridos
- [ ] Unit tests para cada feature (Nivel 2)
- [ ] Integration test: aplicar todas las features a 1 evento real
- [ ] Slippage simulator test: comparar con ejecuciones reales conocidas
- [ ] End-to-end test: backtest simple con/sin slippage → verificar impacto en Sharpe

---

## Validación Metodológica

**Decisiones cerradas** (conversación 2025-10-10):

1. **Spread proxy**: `(high-low)/vwap` con ventana 10min + winsorizar p95 + z robusto; flag wicky con `|close-open|/vwap`
2. **RVOL**: daily (20d, excl. hoy) + intradía estacional (60d, excl. hoy; cumulativo y por-bar)
3. **SSR**: cálculo propio con Reg SHO (−10% vs cierre previo en RTH; vigente resto del día + día siguiente)
4. **Estacionalidad**: z-score robusto por minuto-del-día, lookback 60-90d, excluyendo hoy
5. **Config**: archivo `config/liquidity_filters.yaml` con todos los umbrales

**Referencias regulatorias**:
- SEC Reg SHO Rule 201: https://www.sec.gov/divisions/marketreg/rule201faq.htm
- FINRA Short Sale Volume: https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data

---

## Métricas de Éxito

**Nivel 2 (Features)**:
- [ ] Features generadas para 100% de eventos detectados
- [ ] Correlación entre `trade_difficulty` y real P&L post-evento < -0.3 (alta dificultad → peor P&L)
- [ ] `liquidity_score` distingue claramente eventos ejecutables vs no-ejecutables

**Nivel 3 (Slippage)**:
- [ ] Sharpe ratio de backtest cae 20-40% al activar slippage realista (señal de conservadurismo correcto)
- [ ] Win rate cae 10-15% por partial fills en eventos ilíquidos
- [ ] Max drawdown aumenta 15-25% al incluir context slippage (halts, apertura)

**Nivel 4 (L2 Data)**:
- [ ] NBBO spread real vs proxy estimado: MAE < 0.5%
- [ ] Detección de algo-driven bursts: precision > 80%
- [ ] Storage < 100 GB para 3 años de L2 en top eventos

---

## Notas Finales

- Todos los umbrales están parametrizados en `config/liquidity_filters.yaml`
- SSR calculator ya implementado y tested (`scripts/utils/ssr_calculator.py`)
- Liquidity filters (Nivel 1) ya implementados (`scripts/features/liquidity_filters.py`)
- Este documento es la spec completa para continuar cuando terminemos Phase 2.1

**Autor**: Implementación especificada 2025-10-10
**Review**: Pendiente después de Phase 2.1
**Última actualización**: 2025-10-10
