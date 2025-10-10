El trading algorítmico en small caps puede parecer, a simple vista, igual que en cualquier otro mercado. Pero basta con intentar operarlas en real para descubrir que, si los datos no están perfectamente alineados con la realidad, el backtesting puede dar resultados tan distorsionados que se vuelven inútiles.

En este artículo vamos a repasar los errores más comunes al hacer backtesting en small caps y cómo pueden llevarte a engañarte sin darte cuenta.

## Universo sesgado: el lookahead bias

Una trampa clásica: disponer solo de las empresas que siguen cotizando hoy. Esto elimina automáticamente todas las que fueron deslistadas, absorbidas, quebradas o excluidas por capitalización o volumen.

¿El problema? Reduces artificialmente el universo y operas como si, en aquel momento, solo existieran empresas "sanas". Tu backtest ya no refleja la realidad histórica.

>*Cómo lo resolvemos aquí:*
>
>En este proyecto descargamos **dos universos separados** desde Polygon.io: tickers activos (`active=true`) y tickers deslistados (`active=false`). Concatenamos ambos datasets antes de aplicar cualquier filtro de small-cap. Resultado: un universo de ~34,000 tickers donde el 65% son delisted.
>
>Esto garantiza que una small-cap que quebró en 2023 tras un pump&dump en 2022 entre en nuestro histórico. Sin esto, eliminaríamos sistemáticamente los mejores movers históricos que ya no cotizan, sesgando el backtest hacia resultados demasiado optimistas.

## Precios ajustados por splits: datos que nunca existieron

El gráfico puede estar ajustado por splits y contrasplits, pero si usas esos precios para tomar decisiones en el backtest, estás trabajando con valores que no existieron en ese momento.

Esto distorsiona filtros por precio de acción o su relación con la capitalización. Hemos visto casos donde el precio histórico triplicaba su capitalización real, solo por el ajuste retroactivo.

>*Cómo lo resolvemos aquí:*
>
>Descargamos **dos versiones completas de precios** desde Polygon.io:
>- **Precios ajustados** (`adjusted=true`): guardados en `/raw/market_data/bars/>{timespan}/` para análisis técnico, indicadores y ML (RSI, MACD, Bollinger, etc.)
>- **Precios raw** (`adjusted=false`): guardados en `/raw/market_data/bars/{timespan}_raw/` para filtros de precio ($2-$10), cálculo de capitalización y detección de gaps reales
>
>De esta forma, los indicadores técnicos mantienen continuidad histórica (sin saltos falsos por splits), mientras que los filtros y cálculos usan el precio que realmente existía ese día en el mercado.
>
>Ejemplo: AAPL el 2020-01-02 cotizaba a $300.35 (precio real), pero tras un split 4:1 en 2020-08-31, el precio ajustado retrospectivamente muestra $75.09. Si filtráramos por "$50-$100", estaríamos incluyendo falsamente una acción que en realidad cotizaba a $300.

## Contrapartida: ¿había alguien al otro lado?

Que haya una vela de 1 minuto o un tick no significa que hubiera volumen suficiente para ejecutar tu orden, ni que hubiese bid/ask en ese instante.

Si trabajas con datos agregados (como velas de 1 minuto), puede parecer que entras y sales sin problema. Pero si no modelas cuándo habrías encontrado contrapartida real, el backtest pierde validez.

Además, manejar datos de ticks para miles de activos y varios años puede volverse inviable por tamaño. Hay que buscar un equilibrio entre precisión y volumen, sin ignorar la lógica de ejecución real.

**GPT**  
🚨 Problema: El sistema podría asumir que puedes entrar en cualquier vela de 1m, cuando el volumen fue de 100 acciones o el spread del 10%.

🧠 Solución práctica: Agrega una métrica de liquidez mínima simulada:
> `df = df.filter(pl.col("volume") * pl.col("vwap") > 1_000_000)`
(al menos $1M negociado por minuto → entrada/salida plausible)

En la fase ML, añade feature:
> `liquidity_score = dollar_volume / spread_estimate`

Más adelante, si amplías el tier de Polygon, descarga /trades y /quotes solo para los top eventos (Branch 1–3), no todo el universo.

>*Cómo lo resolvemos aquí:*
>
>Implementamos **filtros de liquidez en 4 niveles** (especificación completa en `docs/TODO_Liquidity_Implementation.md`):
>- **Nivel 1** (Event Detection): Dollar volume contextual ($300k premarket, $1M RTH, $2M si precio<$2), spread proxy winsorizado p95, continuidad temporal (≥70% minutos activos), RVOL con estacionalidad intradía, y detección de SSR (Reg SHO Rule 201).
>- **Nivel 2** (ML Features): `dollar_volume_zscore` por minuto-del-día, `volatility_adjusted_spread`, `imbalance_proxy`, `size_vs_flow`, y `trade_difficulty`.
>- **Nivel 3** (Backtest Slippage): Base slippage por precio (0.75% <$2, 0.5% $2-$10, 0.35% >$10), context slippage (apertura +0.4%, halts +1%, SSR 2x shorts), partial fills, y staged fill en 3 minutos si `position_usd / dollar_volume > 1%`.
>- **Nivel 4** (Futuro): `/trades` y `/quotes` solo para top 200 eventos/mes con `liquidity_score > p90` y `daily_dollar_volume > $5M` (ventana ±60min, ~260M trades total vs 50-80 GB).
>
>Config parametrizable: `config/liquidity_filters.yaml`.

## Ignorar el premarket es operar a ciegas

En muchos casos, las small caps se activan en el premarket: se publica una noticia, entra volumen, y cuando abre el mercado ya ha explotado.

No disponer de datos de las horas previas a la apertura implica correr el riesgo de operar señales que ya están agotadas, o directamente de entrar con desventaja.

**GPT**  
🚨 Problema:
Los patrones “explosivos” (como los de tus imágenes) nacen en el premarket.
Si no descargas 7:00–9:30, los verás como gaps al abrir, y los clasificas tarde.

🧠 Solución: En el config añade:

ingestion:
> `include_premarket: true` 

En ingest_polygon.download_aggregates(), usa:
>`params["adjusted"] = True`  
>`params["include_otc"] = True`  

y extiende el rango horario al completo (7:00–20:00). De esa forma detectas explosiones en tiempo real preapertura, y tus features (como PMH, gap%) serán reales, no artefactos.

>*Cómo lo resolvemos aquí:*  
>El endpoint `/v2/aggs` de Polygon.io **incluye premarket/postmarket por defecto** cuando usamos `adjusted=true`. Nuestras descargas cubren todo el horario extended (04:00-20:00 ET) sin configuración adicional. Los filtros de liquidez (Nivel 1) distinguen entre premarket ($300k/min mínimo) y RTH ($1M/min) usando detección de sesión por timestamp.

## Velas huecas, indicadores rotos

La falta de liquidez genera datos con velas faltantes. Si calculas un RSI de 14, ¿esas 14 velas son consecutivas en tiempo o están recogiendo un periodo mucho mayor del esperado?

No tenerlo en cuenta lleva a cálculos inconsistentes y a señales que, en real, no se habrían generado.

**GPT**

🚨 Problema: Un RSI de 14 sobre una serie con huecos puede representar 14 días efectivos, no 14 días consecutivos.

🧠 Solución práctica: Antes de aplicar indicadores:

`df = df.filter(pl.col("volume") > 0)`  
`df = df.with_columns(pl.col("t").diff().alias("delta_t"))`  
  

y verifica que delta_t < 2×bar_size (por ejemplo, < 2 min). Si hay gaps temporales, marca:

`df["valid_window"] = delta_t <= 2*bar_size`

Usa valid_window como máscara para RSI/ATR/EMA,
para que solo se calculen sobre tramos líquidos.

>*Cómo lo resolvemos aquí:*
>
>**Nivel 1** (Event Detection): Filtro de continuidad temporal que rechaza eventos donde <70% de minutos tienen volumen>0 en la última hora (config: `continuity.min_active_ratio: 0.70`).
>
>**Nivel 2** (Feature Engineering - pendiente Phase 3):
>- Forward-fill limitado a máximo 5 minutos consecutivos, marcando velas rellenadas con flag `is_filled_candle`
>- Indicadores "gap-aware": RSI/MACD calculados solo sobre velas reales, retornan NaN si ventana tiene <14 velas activas
>- Metadata de calidad: columna `data_quality_score` = % velas activas en última hora, features rechazados si score <0.7
>
>Esto evita calcular RSI(14) sobre "14 velas" que en realidad abarcan 45 minutos por gaps de liquidez.

## Halts y eventos especiales

En estos activos son frecuentes los parones por volatilidad o por noticias. Si el sistema entra justo antes de un halt, o asume que puede salir durante uno, el resultado del backtest deja de tener sentido.

Simular correctamente estos eventos es esencial para no sobrevalorar los resultados.

>*Cómo lo resolvemos aquí:*
Polygon.io **no tiene endpoint de halts**. Usamos **enfoque híbrido**:
>
>**Fuente 1 - FINRA/NASDAQ Trader** (ground truth):
Descargamos datos oficiales de halts desde http://www.nasdaqtrader.com/dynamic/symdir/tradinghalt.txt (formato pipe-delimited con `Halt Date/Time`, `Resumption Date/Time`, `Symbol`, `Reason Code`). Guardamos en `raw/reference/trading_halts_{date}.parquet`.
>
>**Fuente 2 - Detección heurística** (complemento):
Para halts no reportados, detectamos patrones en barras 1m:
>- Vela plana con volumen cero: `high == low AND volume == 0`
>- Gap extremo >20% + volumen explosion 10x en vela siguiente
>- Secuencia de 3+ velas consecutivas planas
>
>**Aplicación en backtest** (Nivel 3):
>- Si evento ocurre ±15min de halt: marcar `halt_flag = True`
>- Slippage adicional: +1.0% en ventana de halt
>- Max fill ratio: 25% (partial fills extremos)
>- Rechazar entrada si halt activo en minuto de señal
>
>**Implementación completada**: `scripts/features/halt_detector.py` (detector heurístico funcional) + `scripts/ingestion/download_halt_data.py` (downloader FINRA - API no disponible). Integrado en `scripts/features/liquidity_filters.py` con flag `include_halt_detection=True` por defecto.

## Formato de tiempo y sincronización

Los errores de timestamp no suelen verse a simple vista, pero pueden romper totalmente la lógica temporal del sistema. Es fundamental alinear correctamente el formato de los datos con el horario del mercado.

Un desfase de minutos o una zona horaria mal ajustada puede invalidar cualquier decisión basada en el tiempo.

>*Cómo lo resolvemos aquí:*
>**Storage**: Polygon.io devuelve timestamps en Unix milliseconds (UTC). Los convertimos y guardamos como `pl.Datetime` con `time_zone="UTC"` en Polars/Parquet.
>
>**Conversión a ET**: Creamos módulo `scripts/utils/time_utils.py` con funciones estandarizadas:
>```python
>from scripts.utils.time_utils import to_market_time, add_market_time_columns
>
># Convertir timestamp UTC a ET (maneja DST automáticamente)
>df = df.with_columns([
>    to_market_time(pl.col("timestamp")).alias("timestamp_et")
>])
>
># Añadir columnas de sesión (premarket/RTH/postmarket)
>df = add_market_time_columns(df)  # Añade: timestamp_et, session, is_market_hours
>```
>
>**Regla crítica**: NUNCA comparar timestamps UTC contra horarios de mercado >(09:30-16:00). SIEMPRE convertir a ET primero con `to_market_time()`. Un evento a las 13:30 UTC es 09:30 ET (apertura), pero 13:30 ET es 17:30 UTC (after-hours).
>
>**DST handling**: `ZoneInfo("America/New_York")` maneja DST automáticamente:
>- EST (UTC-5): Noviembre-Marzo
>- EDT (UTC-4): Marzo-Noviembre

## Datos fundamentales: ¿cuándo los conocíamos?

Los filtros por fundamentales (capitalización, float, ingresos, etc.) deben aplicarse con cautela. No siempre se dispone del dato tal y como se conocía ese día: puede llegar con retraso, o con correcciones posteriores que los históricos ya incluyen.


**GPT**
🚨 Problema: Si filtras por “float”, “ingresos” o “market cap” usando esos datos,
puedes introducir lookahead bias (usando cifras conocidas solo meses después).

🧠 Solución: Usa fundamentales solo para caracterización, no para señales o filtros temporales.

Si más adelante necesitas backtest fundamental, crea una versión con “lag artificial”:

`df = df.with_columns(pl.col("publish_date") + timedelta(days=30))`

para simular un retraso razonable de publicación.


>*Cómo lo resolvemos aquí:*  
>**Restricción de uso**: Los fundamentals (market cap, float, shares outstanding) se usan **solo para caracterización post-evento**, NUNCA como filtros temporales en event detection.
>
>**Config actual** (`config.yaml`):
>```yaml
>universe:
>  market_cap_max: 2_000_000_000  # $2B (solo para definir small-cap)
>  float_max: 100_000_000  # 100M shares (caracterización)
>```
>
>**Estrategia**:
>1. **Phase 2.1** (Ingestion): Descargamos ticker details sin filtrar por fundamentals
>2. **Phase 2.2** (Event Detection): Filtros basados SOLO en price action (gaps, volume, halts)
>3. **Phase 3** (Features): Añadimos fundamentals como features descriptivas con lag artificial:
>   ```python
>   # Simulamos delay de publicación (30-60 días)
>   df = df.with_columns([
>       pl.col("market_cap").shift(30).over("symbol").alias("market_cap_known"),
>       pl.col("float").shift(60).over("symbol").alias("float_known")
>   ])
>   ```
>4. **Phase 4** (ML): El modelo puede usar fundamentals lagged, pero NO para señales directas
>
>**Punto-in-time correctness**: Si en futuro necesitamos fundamentals precisos, integrar con fuente que incluya `filing_date` y `publish_date` (ej: SEC Edgar), NO solo `fiscal_period`.

## Y es que... 

En un entorno donde la liquidez es baja, los eventos extremos son frecuentes y la calidad de los datos varía enormemente entre fuentes, hacer un backtest sin tener en cuenta todos estos factores es una forma elegante de autoengañarse.

Un sistema que funciona sobre datos perfectos no tiene mérito. Lo importante es que sobreviva en condiciones reales, con datos reales, y con todas las imperfecciones del mercado incluidas.

Porque si hay algo que tienen las small caps… es que no perdonan errores.