# FASE 3.2 - Validation Checklist GO/NO-GO

**Propósito**: Validar manifest CORE en <10 minutos antes de lanzar FASE 3.2

**Fecha**: 2025-10-13

---

## 🎯 Checklist Completo (13 checks obligatorios)

### 1. Sanity Check: Total Events

```python
import polars as pl

df = pl.read_parquet("processed/events/manifest_core_YYYYMMDD.parquet")
total = len(df)

assert 8000 <= total <= 12000, f"Total events {total} outside range [8K, 12K]"
print(f"✅ Total events: {total:,}")
```

**Target**: 8,000 - 12,000 eventos
**Status**: [ ] PASS / [ ] FAIL

---

### 2. Sanity Check: Unique Symbols

```python
symbols = df['symbol'].n_unique()

assert symbols >= 400, f"Only {symbols} symbols, need ≥400"
print(f"✅ Unique symbols: {symbols:,}")
```

**Target**: ≥400 símbolos
**Status**: [ ] PASS / [ ] FAIL

---

### 3. Quality Check: Score Median

```python
score_median = df['score'].median()
score_p25 = df['score'].quantile(0.25)
score_p75 = df['score'].quantile(0.75)

assert score_median >= 0.70, f"Score median {score_median:.3f} < 0.70"
print(f"✅ Score: p25={score_p25:.3f}, median={score_median:.3f}, p75={score_p75:.3f}")
```

**Target**: Mediana ≥ 0.70
**Status**: [ ] PASS / [ ] FAIL

---

### 4. Quality Check: RVol Day Median

```python
# Filter valid rvol (not missing)
df_valid_rvol = df.filter(~pl.col('rvol_day_missing'))
rvol_median = df_valid_rvol['rvol_day'].median()
rvol_p25 = df_valid_rvol['rvol_day'].quantile(0.25)
rvol_p75 = df_valid_rvol['rvol_day'].quantile(0.75)

assert rvol_median >= 2.0, f"RVol median {rvol_median:.2f}x < 2.0x"
print(f"✅ RVol Day: p25={rvol_p25:.2f}x, median={rvol_median:.2f}x, p75={rvol_p75:.2f}x")
```

**Target**: Mediana ≥ 2.0x
**Status**: [ ] PASS / [ ] FAIL

---

### 5. Diversity Check: Top-20 Concentration

```python
top20 = df.group_by('symbol').agg(pl.len().alias('count')).sort('count', descending=True).head(20)
top20_pct = top20['count'].sum() / total

assert top20_pct < 0.25, f"Top-20 concentration {top20_pct:.1%} ≥ 25%"
print(f"✅ Top-20 concentration: {top20_pct:.1%}")
print(f"\nTop 10 symbols:")
for row in top20.head(10).to_dicts():
    print(f"  {row['symbol']:6s}: {row['count']:>4,} events ({row['count']/total:.1%})")
```

**Target**: < 25%
**Status**: [ ] PASS / [ ] FAIL

---

### 6-8. Session Distribution Checks

```python
session_counts = df.group_by('session').agg(pl.len().alias('count'))
session_pcts = {row['session']: row['count'] / total for row in session_counts.to_dicts()}

# PM check
pm_pct = session_pcts.get('PM', 0)
assert 0.10 <= pm_pct <= 0.20, f"PM {pm_pct:.1%} outside [10%, 20%]"
print(f"✅ PM session: {pm_pct:.1%} (target 15%, range [10%, 20%])")

# RTH check
rth_pct = session_pcts.get('RTH', 0)
assert 0.75 <= rth_pct <= 0.85, f"RTH {rth_pct:.1%} outside [75%, 85%]"
print(f"✅ RTH session: {rth_pct:.1%} (target 80%, range [75%, 85%])")

# AH check
ah_pct = session_pcts.get('AH', 0)
assert 0.03 <= ah_pct <= 0.10, f"AH {ah_pct:.1%} outside [3%, 10%]"
print(f"✅ AH session: {ah_pct:.1%} (target 5%, range [3%, 10%])")
```

**Targets**:
- PM: 10-20%
- RTH: 75-85%
- AH: 3-10%

**Status**: [ ] PASS / [ ] FAIL

---

### 9. Storage Estimation (p90)

```python
# From config (placeholder - update with pilot data)
STORAGE_MB_P90_TRADES = 25.0
STORAGE_MB_P90_QUOTES = 12.0

storage_p90_gb = total * (STORAGE_MB_P90_TRADES + STORAGE_MB_P90_QUOTES) / 1024

assert storage_p90_gb < 250, f"Storage p90 {storage_p90_gb:.1f} GB ≥ 250 GB"
print(f"✅ Storage p90 estimate: {storage_p90_gb:.1f} GB")
print(f"  Trades: {total * STORAGE_MB_P90_TRADES / 1024:.1f} GB")
print(f"  Quotes: {total * STORAGE_MB_P90_QUOTES / 1024:.1f} GB")
```

**Target**: < 250 GB
**Status**: [ ] PASS / [ ] FAIL

---

### 10. Time Estimation (p90)

```python
# From config (placeholder - update with pilot data)
TIME_SEC_P90 = 18  # seconds per event (max of trades/quotes)

time_p90_hours = total * TIME_SEC_P90 / 3600
time_p90_days = time_p90_hours / 24

assert time_p90_days < 3.0, f"Time p90 {time_p90_days:.2f} days ≥ 3 days"
print(f"✅ Time p90 estimate: {time_p90_hours:.1f} hours ({time_p90_days:.2f} days)")
```

**Target**: < 3 días
**Status**: [ ] PASS / [ ] FAIL

---

### 11. Data Quality: No NaN in Key Metrics

```python
key_metrics = ['dollar_volume_bar', 'volume', 'spread_proxy', 'dollar_volume_day', 'rvol_day']

for metric in key_metrics:
    null_count = df[metric].null_count()
    assert null_count == 0, f"Found {null_count} NaN in {metric}"
    print(f"✅ {metric}: 0 NaN")
```

**Target**: 0 NaN en métricas clave
**Status**: [ ] PASS / [ ] FAIL

---

### 12. Data Quality: RVol Day Coverage

```python
missing_rvol = df['rvol_day_missing'].sum()
missing_pct = missing_rvol / total

assert missing_pct == 0, f"Found {missing_rvol} events with rvol_day_missing=True"
print(f"✅ RVol coverage: {(1-missing_pct):.1%} ({total - missing_rvol:,}/{total:,})")
```

**Target**: 100% (todos con rvol_day válido)
**Status**: [ ] PASS / [ ] FAIL

---

### 13. Reproducibility: Metadata Present

```python
# Check required metadata columns
required_meta = ['config_hash', 'enrichment_version', 'enriched', 'enriched_at']

for col in required_meta:
    assert col in df.columns, f"Missing metadata column: {col}"
    non_null = df[col].null_count() == 0
    assert non_null, f"Found NaN in metadata: {col}"

config_hash = df['config_hash'][0]
enrichment_version = df['enrichment_version'][0]

print(f"✅ Reproducibility metadata present:")
print(f"  config_hash: {config_hash}")
print(f"  enrichment_version: {enrichment_version}")
```

**Target**: Metadata completa y no-null
**Status**: [ ] PASS / [ ] FAIL

---

## 📊 Summary Report Template

```python
print("\n" + "="*80)
print("MANIFEST VALIDATION SUMMARY")
print("="*80)

checks_passed = 0
checks_total = 13

# Run all checks and count passes
# ... (code above)

print(f"\n{'='*80}")
print(f"CHECKS PASSED: {checks_passed}/{checks_total}")
print(f"OVERALL STATUS: {'✅ GO' if checks_passed == checks_total else '❌ NO-GO'}")
print(f"{'='*80}\n")
```

---

## 🚨 Troubleshooting Guide

### Si falla Check #1 (Total Events)

**Causa**: Filtros demasiado estrictos o cap global muy bajo

**Solución**:
1. Revisar cuántos eventos pasaron cada etapa (descarte attribution)
2. Si filtro liquidez descarta >80%: relajar 10% en PM
3. Si cap símbolo es limitante: aumentar de 5 a 7
4. Si cap global 10K no se alcanza: verificar diversidad caps

### Si falla Check #6-8 (Sesiones)

**Causa**: Distribución horaria de eventos raw sesgada

**Solución**:
1. Si PM < 10%: aplicar fallback -10% dollar_volume_bar solo en PM
2. Si PM < 10% persiste: relajar -0.1 rvol_day solo en PM
3. Si AH > 10%: recortar eventos AH por score hasta entrar en rango
4. Re-generar manifest con `--enforce-quotas`

### Si falla Check #11 (NaN)

**Causa**: Join diario incompleto

**Solución**:
1. Verificar que `date_et` se usó para join (no UTC)
2. Verificar cobertura de 1d_raw para símbolos en eventos
3. Filtrar eventos sin daily match antes de manifest

### Si falla Check #12 (RVol Missing)

**Causa**: Eventos muy recientes (< 20 días histórico)

**Solución**:
1. Filtrar eventos donde `rvol_day_missing == True`
2. Verificar que rolling usa `closed='left'`
3. Ajustar periodo mínimo de eventos (ej. desde 2023 en vez de 2022)

---

## 🎯 Quick Validation Script

```bash
python scripts/analysis/validate_core_manifest.py \
  --manifest processed/events/manifest_core_YYYYMMDD.parquet \
  --output analysis/manifest_validation_YYYYMMDD.json
```

**Output**: JSON con todos los checks + GO/NO-GO decision

---

## ✅ Final Sign-Off

Una vez TODOS los checks pasan:

```bash
# Create GO stamp
echo "GO_APPROVED: $(date -Iseconds)" > processed/events/manifest_core_YYYYMMDD.GO

# Log decision
echo "Manifest validated at $(date)" >> logs/manifest_validations.log
echo "  Total events: $total" >> logs/manifest_validations.log
echo "  Symbols: $symbols" >> logs/manifest_validations.log
echo "  Status: GO" >> logs/manifest_validations.log
```

Ahora puedes lanzar **FASE 3.2** con confianza.

---

**Última actualización**: 2025-10-13
**Tiempo estimado de validación**: 5-10 minutos
