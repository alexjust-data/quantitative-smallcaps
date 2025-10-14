# Plan de Descarga Week 2-3 - Barras de 1 Minuto

**Fecha**: 2025-10-09
**Status**: ✅ APROBADO PARA EJECUCIÓN

---

## 📊 Resumen del Estado Actual

### Week 1 - COMPLETO ✅
- **Daily bars**: 5,227/5,005 (104.4%) ✅
- **Hourly bars**: 4,794/5,005 (95.8%) ✅
- **Duración**: ~5 horas

### Event Detection - COMPLETO ✅
- **Total eventos detectados**: 7,288
- **Event rate**: 0.61%
- **Símbolos con eventos**: 4,878
- **Validación manual**: 71% precision (>70% target) ✅

### Ranking - COMPLETO ✅
- **Top-2000 generado**: 6,100 eventos capturados (83.7%)
- **Mean eventos/símbolo**: 3.0
- **Median**: 2.0

---

## 🎯 Calibración Final del Detector

### Configuración Estable - NO MODIFICAR

```yaml
processing:
  events:
    # Branch 1: Gap Play
    gap_pct_threshold: 5.0
    rvol_threshold: 2.0

    # Branch 2: Intraday Range Explosion (IRE)
    ire_pct_threshold: 30.0

    # Branch 3: Volume Spike Without Gap (VSWG)
    rvol_vswg_threshold: 5.0
    gap_vswg_min: 2.0

    # Branch 4: ATR Breakout
    atr_pct_percentile: 88
    rvol_threshold_alt: 1.8

    # Branch 5: Flush Reversal (no activo)
    rvol_flush_threshold: 2.5
    drawdown_flush_threshold: 20.0

    # Global filters
    min_dollar_volume_event: 600000
    bullish_only: true
    use_hourly_premarket_filter: false
```

### Branches Activos

| Branch | Eventos | % | Status |
|--------|---------|---|--------|
| Gap Play | 4,595 | 63.0% | ✅ Funciona |
| IRE | 2,543 | 34.9% | ✅ Funciona |
| VSWG | 2,468 | 33.9% | ✅ Funciona |
| ATR | 1,356 | 18.6% | ✅ Funciona |
| Flush | 0 | 0.0% | ⚠️ Threshold muy estricto |

**Nota**: Algunos eventos activan múltiples branches (overlap esperado).

---

## 🚀 Plan de Descarga Week 2-3

### Comando a Ejecutar

```bash
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 2000 --events-preset compact
```

### Parámetros

- **Weeks**: 2 y 3 (3 años de datos: 2022-10-01 a 2025-09-30)
- **Top-N**: 2,000 símbolos (los más activos)
- **Events preset**: `compact` (D-2 a D+2)
- **Granularidad**: 1 minuto

### Storage Estimado

**Top-2000 (full 3 years)**:
- Por símbolo: ~1.7 MB (comprimido con zstd)
- Total: 2,000 × 1.7 MB = **~3.4 GB**

**Resto ~3,000 (event windows only)**:
- Por símbolo: ~500 KB (solo ventanas D-2 a D+2)
- Total: 3,000 × 500 KB = **~1.5 GB**

**TOTAL ESTIMADO**: **~4.9 GB**

### Duración Estimada

- **Rate limit**: ~300 requests/min (Polygon.io)
- **Total días**: 3 años × 252 días × 2,000 tickers = ~1.5M requests
- **Tiempo estimado**: 4-7 días (depende de throttling y reintentos)

---

## 📝 Ventanas de Evento (Preset: Compact)

```yaml
compact:
  d_minus_2: [["09:30","16:00"]]         # 6.5 horas
  d_minus_1: [["09:30","10:30"], ["14:00","16:00"]]  # 3.5 horas
  d:         [["07:00","16:00"]]          # 9 horas (incluye premarket)
  d_plus_1:  [["09:30","12:30"]]          # 3 horas
  d_plus_2:  [["09:30","12:30"]]          # 3 horas
```

**Total por evento**: ~25.5 horas de datos 1-minute

---

## 🔧 Opciones de Paralelización

### Opción 1: Descarga Secuencial (Recomendada)
```bash
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 2000 --events-preset compact
```

**Ventajas**:
- Manejo automático de rate limits
- Reintentos automáticos
- Checkpointing (resume si falla)

**Desventajas**:
- Más lento (4-7 días)

### Opción 2: Descarga en Bloques (Avanzada)
```bash
# Bloque 1: Rank 1-500
python scripts/ingestion/download_all.py --weeks 2 3 --top-n 500 --events-preset compact

# Bloque 2: Rank 501-1000
python scripts/ingestion/download_all.py --weeks 2 3 --rank-range 501 1000 --events-preset compact

# Bloque 3: Rank 1001-1500
python scripts/ingestion/download_all.py --weeks 2 3 --rank-range 1001 1500 --events-preset compact

# Bloque 4: Rank 1501-2000
python scripts/ingestion/download_all.py --weeks 2 3 --rank-range 1501 2000 --events-preset compact
```

**Ventajas**:
- Puede paralelizar en múltiples terminales/máquinas
- Más rápido si tienes recursos

**Desventajas**:
- Requiere implementar `--rank-range` flag (no existe actualmente)
- Más propenso a errores de sincronización

**Recomendación**: Usar Opción 1 (secuencial) por ahora.

---

## 📊 Branch Metadata en Parquets

### Columnas a Incluir en eventos.parquet

El archivo `processed/events/events_daily_20251009.parquet` ya incluye:

```
- symbol
- date
- timestamp
- event_id
- open, high, low, close, volume
- gap_pct, rvol, atr_pct, ire_pct, dollar_volume
- branch_gap_play      (bool)
- branch_ire           (bool)
- branch_vswg          (bool)
- branch_atr           (bool)
- branch_flush         (bool)
- is_event             (bool)
```

### Uso en Phase 2

Cuando entrenes el modelo, podrás:

1. **Filtrar por branch**:
   ```python
   gap_only = events.filter(pl.col('branch_gap_play') & ~pl.col('branch_ire'))
   ire_only = events.filter(pl.col('branch_ire') & ~pl.col('branch_gap_play'))
   ```

2. **Evaluar performance por patrón**:
   ```python
   # ¿Qué branch genera mejor Sharpe?
   for branch in ['branch_gap_play', 'branch_ire', 'branch_vswg', 'branch_atr']:
       events_subset = events.filter(pl.col(branch))
       sharpe = evaluate_strategy(events_subset)
       print(f'{branch}: Sharpe = {sharpe}')
   ```

3. **Entrenar modelos especializados**:
   - Modelo A: Solo Gap Plays
   - Modelo B: Solo IRE (explosiones intraday)
   - Modelo C: Solo VSWG (volume spikes)
   - Modelo Ensemble: Combinar predicciones

---

## ✅ Checklist Pre-Descarga

- [x] Week 1 completo (daily + hourly)
- [x] Event detection ejecutado (7,288 eventos)
- [x] Ranking Top-2000 generado
- [x] Validación manual >70% (71% achieved)
- [x] Configuración estable documentada
- [x] Branch metadata incluido en parquets
- [ ] Lanzar descarga Week 2-3

---

## 🚦 Próximos Pasos

### Inmediato
1. ✅ Ejecutar: `python scripts/ingestion/download_all.py --weeks 2 3 --top-n 2000 --events-preset compact`
2. ⏳ Monitorear progreso con: `python scripts/ingestion/check_download_status.py`

### Durante Descarga (4-7 días)
- Revisar logs cada 24h
- Verificar espacio en disco (target: ~5 GB)
- Si falla, reiniciar automáticamente (checkpointing habilitado)

### Post-Descarga
1. Validar integridad de datos (DQ checks)
2. Generar estadísticas de cobertura
3. Comenzar Phase 2: Feature Engineering + Labeling

---

## 🎯 Objetivo Final

**Tener 3 años de barras de 1-minuto para Top-2000 tickers**, listas para:

1. Feature engineering (volume profile, VWAP, microstructure)
2. Triple-barrier labeling
3. Entrenamiento de modelo ML
4. Backtesting con datos reales

**Timeline**: Week 2-3 download (4-7 días) → Phase 2 start (~2025-10-16)

---

## 📌 Notas Importantes

1. **NO modificar thresholds** hasta tener datos 1-min y evaluar performance real
2. **Branch metadata** ya está guardado - listo para análisis
3. **Preset compact** es suficiente para mayoría de estrategias intraday
4. **Flush branch** no activo (0 eventos) - ajustar a -15% en future iteration

**STATUS**: ✅ **READY TO LAUNCH**
