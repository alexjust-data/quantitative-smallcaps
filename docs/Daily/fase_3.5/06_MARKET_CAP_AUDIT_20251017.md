# MARKET CAP AUDIT - FASE 3.5
**Fecha:** 2025-10-17
**Objetivo:** Verificar que el universo de 1,621 símbolos cumple con el criterio de market cap < $2B del README.md

---

## PROBLEMA DETECTADO

Durante FASE 3.2 (descarga de event windows), se descubrió que **22.7% del universo (365 símbolos) está FUERA del target de small-caps** definido en el README.md.

### Criterio del Proyecto (README.md)
```
Small Caps Universe Definition:
- price: $0.50 - $20.00
- market_cap: < $2B        ← CRITERIO FUNDAMENTAL
- float: < 50-100M shares
```

---

## METODOLOGÍA

### Fuentes de Datos
1. **Manifest:** `processed/events/manifest_core_5y_20251017.parquet`
   - Total símbolos: **1,621**

2. **Market Cap Data:** `raw/reference/ticker_details_all.parquet`
   - Descargado en FASE 1 via Polygon `/v3/reference/tickers/{symbol}`
   - Cobertura: 1,611 de 1,621 símbolos (99.4%)
   - Missing: 10 símbolos sin data

### Script de Análisis
Creado: `tools/fase_3.2/analyze_mcap_distribution.py`

```python
# Lee manifest + ticker_details
# Clasifica en 5 brackets de market cap
# Identifica símbolos fuera de target
```

---

## RESULTADOS

### Distribución de Market Cap

| Categoría    | Rango            | Símbolos | % del Total |
|--------------|------------------|----------|-------------|
| **Nano-cap** | < $50M           | 451      | 28.0%       |
| **Micro-cap**| $50M - $300M     | 382      | 23.7%       |
| **Small-cap**| $300M - $2B      | 413      | 25.6%       |
| **Mid-cap**  | $2B - $10B       | 229      | 14.2%       |
| **Large-cap**| > $10B           | 136      | 8.4%        |

### Resumen vs Target

| Categoría               | Símbolos | % del Total |
|-------------------------|----------|-------------|
| ✅ Dentro del target (< $2B) | **1,246** | **77.3%** |
| ⚠️ Fuera del target (≥ $2B)  | **365**   | **22.7%** |

---

## SÍMBOLOS FUERA DEL TARGET

### Top 50 Large-Caps (> $10B)

```
  1. AAPL   - Apple Inc.
  2. AVGO   - Broadcom Inc.
  3. ORCL   - Oracle Corporation
  4. PLTR   - Palantir Technologies
  5. BAC    - Bank of America
  6. MS     - Morgan Stanley
  7. MU     - Micron Technology
  8. SHOP   - Shopify Inc.
  9. APP    - AppLovin Corporation
 10. C      - Citigroup Inc.
 11. AMAT   - Applied Materials
 12. LRCX   - Lam Research
 13. GEV    - GE Vernova
 14. SPOT   - Spotify Technology
 15. UNP    - Union Pacific
 16. KKR    - KKR & Co.
 17. CVS    - CVS Health
 18. NKE    - Nike Inc.
 19. MCK    - McKesson Corporation
 20. NEM    - Newmont Corporation
 21. COIN   - Coinbase Global
 22. BMO    - Bank of Montreal
 23. CDNS   - Cadence Design Systems
 24. MSTR   - MicroStrategy Inc.
 25. AEM    - Agnico Eagle Mines
 26. SNOW   - Snowflake Inc.
 27. SNPS   - Synopsys Inc.
 28. AJG    - Arthur J. Gallagher
 29. MRVL   - Marvell Technology
 30. ABNB   - Airbnb Inc.
 31. PNC    - PNC Financial
 32. EMR    - Emerson Electric
 33. JCI    - Johnson Controls
 34. CRWV   - Crown Castle
 35. APO    - Apollo Global Management
 36. B      - Barnes Group
 37. AXON   - Axon Enterprise
 38. FDX    - FedEx Corporation
 39. NXPI   - NXP Semiconductors
 40. GRMN   - Garmin Ltd.
 41. CVNA   - Carvana Co.
 42. FLUT   - Flutter Entertainment
 43. WBD    - Warner Bros. Discovery
 44. OXY    - Occidental Petroleum
 45. EBAY   - eBay Inc.
 46. UI     - Ubiquiti Inc.
 47. FNV    - Franco-Nevada
 48. DAL    - Delta Air Lines
 49. AU     - AngloGold Ashanti
 50. XYL    - Xylem Inc.
```

**Total Large-Caps (> $10B): 136 símbolos**

### Mid-Caps ($2B - $10B)

**Total Mid-Caps: 229 símbolos**

(No listados individualmente para brevedad, pero incluyen símbolos como SMCI, STLA, PINS, OKTA, etc.)

---

## IMPACTO EN FASE 3.2

### Estado Actual de la Descarga
- **Total eventos en manifest:** 572,850
- **Progreso descarga:** 4.7% (26,981 eventos)
- **ETA:** ~3.2 días restantes

### Desperdicio Estimado

Asumiendo distribución uniforme de eventos:
- **Eventos de símbolos fuera de target:** ~130,000 (22.7%)
- **Tiempo de descarga desperdiciado:** ~18 horas de ~80 horas totales
- **Costo API desperdiciado:** ~130K requests de ~573K totales

---

## ANÁLISIS DE CAUSA RAÍZ

### ¿Por qué se incluyeron estos símbolos?

Revisando `scripts/features/liquidity_filters.py`:

```python
# Filtros aplicados en FASE 2.5:
self.min_price = self.event_cfg["price_range"]["min_price"]      # $0.50
self.max_price = self.event_cfg["price_range"]["max_price"]      # $20.00
self.dv_premarket = self.event_cfg["min_dollar_volume"]["premarket"]
self.dv_rth = self.event_cfg["min_dollar_volume"]["rth"]

# ❌ NO HAY FILTRO POR MARKET CAP
```

**Conclusión:** En FASE 2.5 se filtraron los eventos por:
1. ✅ Precio ($0.50 - $20.00)
2. ✅ Dollar volume (liquidez)
3. ✅ Spread
4. ✅ Continuidad
5. ❌ **FALTA:** Market cap (< $2B)

**El filtro de precio permitió que large-caps con precio bajo entraran al universo.**

Ejemplos:
- **PLTR:** $60B market cap, pero precio ~$10 (dentro de rango)
- **SNAP:** $10B+ market cap, pero precio ~$10
- **IONQ:** $10B+ market cap, precio ~$5

---

## OPCIONES DE ACCIÓN

### Opción 1: CONTINUAR COMO ESTÁ
**Ventajas:**
- No perder el progreso actual (4.7%)
- Completar descarga en 3.2 días
- Filtrar símbolos en análisis posterior

**Desventajas:**
- Desperdiciar ~130K eventos (~18 horas de descarga)
- Usar ~22% de capacidad API innecesariamente
- Archivos de large-caps ocupan espacio en disco

**Recomendación:** Solo si el tiempo es crítico y no podemos esperar.

---

### Opción 2: PARAR Y REFILTRAR
**Pasos:**
1. Detener proceso actual (kill PID)
2. Crear nuevo manifest filtrado por market cap < $2B
3. Reiniciar descarga desde cero

**Ventajas:**
- Universo limpio y correcto
- Ahorro de ~22% en tiempo/API/disco
- Alineado con spec del README

**Desventajas:**
- Perder progreso actual (26,981 eventos)
- Reiniciar desde 0
- Tiempo total: ~3.2 días (igual que continuar)

**Recomendación:** SI el universo final debe ser estrictamente < $2B.

**Script necesario:**
```python
# tools/fase_3.5/create_smallcap_manifest.py
# 1. Read manifest_core_5y_20251017.parquet
# 2. Read ticker_details_all.parquet
# 3. Filter symbols where market_cap < 2B
# 4. Write manifest_smallcaps_5y_20251017.parquet
# 5. Update launch script to use new manifest
```

---

### Opción 3: FILTRAR Y RESUMIR
**Pasos:**
1. Crear nuevo manifest solo con símbolos < $2B
2. Eliminar archivos ya descargados de large-caps
3. Continuar descarga solo para símbolos que faltan del nuevo universo

**Ventajas:**
- Aprovechar descarga de símbolos válidos ya completados
- No desperdiciar el 4.7% de progreso en símbolos correctos
- Universo final limpio

**Desventajas:**
- Complejidad: necesita reconciliar qué eventos descargar
- Requiere borrar archivos de símbolos excluidos

**Recomendación:** Óptimo si queremos aprovechar trabajo ya hecho.

**Script necesario:**
```python
# tools/fase_3.5/resume_with_filtered_manifest.py
# 1. Create filtered manifest (< $2B)
# 2. Scan event_windows directory
# 3. Identify completed events for valid symbols
# 4. Remove files for excluded symbols
# 5. Resume download with new manifest
```

---

## RECOMENDACIÓN FINAL

### Análisis de Trade-offs

| Criterio                    | Opción 1 | Opción 2 | Opción 3 |
|-----------------------------|----------|----------|----------|
| Tiempo hasta completar      | 3.2 días | 3.2 días | 2.8 días |
| Universo final correcto     | ❌ No    | ✅ Sí    | ✅ Sí    |
| Aprovecha progreso actual   | ✅ Sí    | ❌ No    | ✅ Parcial|
| Complejidad implementación  | Baja     | Baja     | Alta     |
| Desperdicio API/disco       | Alto     | Ninguno  | Bajo     |

### Decisión Recomendada: **OPCIÓN 2 - PARAR Y REFILTRAR**

**Razones:**
1. **Integridad del universo:** El proyecto se llama "TRADING_SMALLCAPS" y el README especifica < $2B
2. **Mismo tiempo total:** Perder 4.7% ahora vs desperdiciar 22.7% después = mismo ETA
3. **Simplicidad:** Implementación directa sin complejidad de reconciliación
4. **Limpieza:** Universo final alineado con spec desde el inicio

### Plan de Ejecución (Opción 2)

```bash
# 1. Detener descarga actual
taskkill /PID <current_pid> /F

# 2. Crear manifest filtrado
python tools/fase_3.5/create_smallcap_manifest.py

# 3. Validar nuevo manifest
python tools/fase_3.5/validate_smallcap_manifest.py

# 4. Lanzar descarga con nuevo manifest
python tools/fase_3.2/launch_with_rate_025s.py \
    --manifest processed/events/manifest_smallcaps_5y_20251017.parquet
```

**Tiempo estimado implementación:** 30 minutos
**Tiempo descarga nuevo universo:** 2.5 días (77% de 3.2 días)

---

## LECCIONES APRENDIDAS

### Para FASE 2.5 (Event Detection)

**Problema:** El filtro de liquidez no incluyó market cap.

**Solución futura:** Agregar filtro de market cap en `scripts/features/liquidity_filters.py`:

```python
def compute_market_cap_filter(self, df: pl.DataFrame, ticker_details: pl.DataFrame) -> pl.DataFrame:
    """
    Filter by market cap threshold.

    Requires: symbol
    Adds: market_cap, market_cap_pass
    """
    df = df.join(
        ticker_details.select(["ticker", "market_cap"]),
        left_on="symbol",
        right_on="ticker",
        how="left"
    )

    df = df.with_columns([
        (pl.col("market_cap") < self.max_market_cap).alias("market_cap_pass")
    ])

    return df
```

### Para Validación de Universos

**Crear checkpoint de validación antes de descargas masivas:**

```python
# tools/validation/validate_universe_before_download.py
# 1. Check market cap distribution
# 2. Check price distribution
# 3. Check symbol count vs expected
# 4. Flag outliers (AAPL, etc.)
# 5. Require manual approval if anomalies detected
```

---

## ARCHIVOS GENERADOS

1. **Análisis:**
   - `tools/fase_3.2/analyze_mcap_distribution.py` - Script de análisis

2. **Documentación:**
   - `docs/Daily/fase_3.5/MARKET_CAP_AUDIT_20251017.md` - Este documento

3. **Pendientes (según decisión):**
   - `tools/fase_3.5/create_smallcap_manifest.py` - Crear manifest filtrado
   - `tools/fase_3.5/validate_smallcap_manifest.py` - Validar nuevo manifest
   - `processed/events/manifest_smallcaps_5y_20251017.parquet` - Manifest limpio

---

## SIGUIENTE PASO

**DECISIÓN REQUERIDA:** Elegir entre las 3 opciones descritas arriba.

**Factores a considerar:**
- ¿Es el market cap < $2B un requisito estricto?
- ¿Preferimos velocidad (continuar) o limpieza (refiltrar)?
- ¿Hay valor en analizar large-caps también? (si no, refiltrar)

**Tiempo estimado según decisión:**
- Opción 1: Continuar → 3.2 días desde ahora
- Opción 2: Refiltrar → 30 min setup + 2.5 días descarga
- Opción 3: Resumir → 2 horas setup + 2.8 días descarga

---

**Documentado por:** Claude Code
**Timestamp:** 2025-10-17 20:35 UTC
**FASE:** 3.5 - Market Cap Validation
