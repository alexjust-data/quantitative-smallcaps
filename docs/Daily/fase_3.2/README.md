# FASE 3.2 - Documentación Completa

**Objetivo**: Descargar ventanas de microestructura (trades+quotes) para ~10K eventos intraday de máxima calidad

**Estado**: ✅ Documentación completa | ⏳ Esperando FASE 2.5

---

## 📚 Índice de Documentos

### 1. [00_FASE_3.2_ROADMAP.md](00_FASE_3.2_ROADMAP.md)
**Pipeline completo end-to-end**

- Pipeline de 5 etapas (2.5 → enrich → dry-run → manifest → 3.2)
- Esquema completo de columnas (25 campos)
- Filtros CORE detallados (5 etapas)
- Config.yaml updates
- Timeline y estimaciones
- Comandos operativos

**Cuándo leer**: Cuando necesites entender el flujo completo o implementar scripts

---

### 2. [01_VALIDATION_CHECKLIST.md](01_VALIDATION_CHECKLIST.md)
**13 checks obligatorios GO/NO-GO**

- Sanity checks (total events, symbols)
- Quality checks (score, rvol_day)
- Diversity checks (top-20 concentration)
- Session distribution (PM/RTH/AH)
- Storage/time estimations
- Data quality (NaN, missing values)
- Troubleshooting guide

**Cuándo leer**: Antes de lanzar FASE 3.2, para validar manifest en <10 minutos

---

### 3. [02_EXECUTIVE_SUMMARY.md](02_EXECUTIVE_SUMMARY.md)
**Resumen ejecutivo de alto nivel**

- Estado actual (qué está listo, qué falta)
- Números clave proyectados
- Pipeline status visual
- Problemas resueltos
- Timeline proyectado
- Próximos pasos en orden

**Cuándo leer**: Para obtener visión general rápida del proyecto

---

### 4. [MANIFEST_CORE_SPEC.md](MANIFEST_CORE_SPEC.md)
**Especificación técnica detallada (600+ líneas)**

- Esquema de 25 columnas con tipos
- 5 etapas de filtrado con SQL-like logic
- Desempate estable (orden determinístico)
- Cuotas de sesión con fallback
- 13 sanity checks obligatorios + 5 recomendados
- Calibración con pilot data
- Reproducibilidad (checksums, config_hash)

**Cuándo leer**: Al implementar scripts de filtrado, manifest generation, o debugging

---

## 🚀 Quick Start

### Para Ejecutar Pipeline Completo

```bash
# 1. Enriquecer eventos (cuando FASE 2.5 tenga ≥500 símbolos)
python scripts/processing/enrich_events_with_daily_metrics.py

# 2. Dry-run completo
python scripts/analysis/generate_core_manifest_dryrun.py \
  --input processed/events/events_intraday_enriched_*.parquet \
  --profile core

# 3. Validar (revisar 01_VALIDATION_CHECKLIST.md)
python scripts/analysis/validate_core_manifest.py \
  --manifest processed/events/manifest_core_*.parquet

# 4. Si GO → Generar manifest
python scripts/processing/build_intraday_manifest.py \
  --input processed/events/events_intraday_enriched_*.parquet \
  --output processed/events/manifest_core_*.parquet \
  --profile core --enforce-quotas

# 5. Lanzar FASE 3.2
python scripts/ingestion/download_trades_quotes_intraday.py \
  --events processed/events/manifest_core_*.parquet \
  --resume
```

---

## 📊 Estado Actual

| Etapa | Status | Progreso |
|-------|--------|----------|
| **FASE 2.5 - Detección** | 🟡 En curso | 58/1,996 símbolos (2.9%) |
| **Documentación** | ✅ Completa | 4 documentos |
| **Scripts** | 🟡 Parcial | Enrich ✅, Dry-run proxy ✅, resto pendiente |
| **Validación** | ⏳ Pendiente | Checklist listo |
| **FASE 3.2** | ⏳ Pendiente | Esperando manifest |

---

## 🎯 Archivos Clave Generados

### Scripts Creados
- ✅ `scripts/processing/enrich_events_with_daily_metrics.py`
- ✅ `scripts/processing/generate_core_manifest_dryrun_proxy.py`

### Scripts Pendientes
- ⏳ `scripts/processing/generate_core_manifest_dryrun.py` (versión completa)
- ⏳ `scripts/processing/build_intraday_manifest.py`
- ⏳ `scripts/ingestion/download_trades_quotes_intraday.py`
- ⏳ `scripts/analysis/validate_core_manifest.py`

---

## 🔍 Problemas Conocidos y Soluciones

### ✅ PM Session = 0% → RESUELTO
**Solución**: Recalc sesiones en enrichment usando ET timezone
**Resultado**: PM=18.2% tras recalc

### ✅ Métricas Faltantes → RESUELTO
**Solución**: Script enriquecimiento con join a 1d_raw
**Resultado**: dollar_volume_day y rvol_day agregados

### ✅ Estructura Daily Bars → RESUELTO
**Solución**: Ajustado a archivos planos (symbol.parquet)
**Resultado**: Listo para ejecutar

---

## 💡 Conceptos Clave

### Filtros CORE (5 Etapas)
1. **Calidad**: score ≥0.60, no NaN
2. **Liquidez Intradía**: $100K bar, 10K shares, spread ≤5%
3. **Liquidez Diaria**: $500K day, rvol ≥1.5x
4. **Diversidad**: 1 min/symbol + fill hasta 5, caps por día/mes
5. **Sesiones**: PM 10-20%, RTH 75-85%, AH 3-10% (enforced)

### Desempate Estable
```sql
ORDER BY score DESC, rvol_day DESC, dollar_volume_bar DESC, timestamp ASC
```

### Métricas Críticas
- `dollar_volume_day`: volume_d × vwap_d (RAW)
- `rvol_day`: dv_day / mean(20d previos, left-closed)
- `spread_proxy`: (high-low)/vwap (proxy hasta NBBO)

---

## 📈 Estimaciones

| Métrica | Valor Proyectado |
|---------|-----------------|
| Input (FASE 2.5) | ~700K eventos |
| Después filtros CORE | ~10K eventos |
| Símbolos únicos | ≥400 |
| Storage p90 | <250 GB |
| Tiempo descarga p90 | <3 días |

---

## ⏱️ Timeline

- **FASE 2.5 (resto)**: ~2.8 días
- **Enriquecimiento**: ~30 min
- **Dry-run + validación**: ~15 min
- **Manifest**: ~2 min
- **FASE 3.2**: ~2.1 días

**Total**: ~5 días calendario

---

## 📞 Referencias Rápidas

### Cuotas de Sesión
- PM: 10-20% (target 15%)
- RTH: 75-85% (target 80%)
- AH: 3-10% (target 5%)

### Caps de Diversidad
- Max 5 eventos/símbolo (1 cobertura + 4 fill)
- Max 1 evento/símbolo/día
- Max 20 eventos/símbolo/mes

### Ventanas FASE 3.2
- Antes: 3 minutos
- Después: 7 minutos
- Total: 11 minutos (660 segundos)

---

## 🔗 Dependencias

```
FASE 2.5 (detección)
    ↓
Enriquecimiento (métricas diarias)
    ↓
Dry-run completo (validación)
    ↓
Validación GO/NO-GO (13 checks)
    ↓
Manifest CORE (selección final)
    ↓
FASE 3.2 (descarga trades+quotes)
```

---

## 📝 Notas Importantes

1. **No esperar 100% FASE 2.5**: Con 500-800 símbolos ya puedes ejecutar batch inicial
2. **Calibrar estimaciones**: Usar pilot data (10-20 eventos) para p50/p90 reales
3. **Monitorear PM**: Si PM raw <5% total, considerar relajar targets
4. **Paralelismo conservador**: Empezar con 1 worker, escalar según 429 rate

---

**Última actualización**: 2025-10-13 20:28 UTC
**Mantenido por**: Claude Code (Anthropic)
**Versión**: 1.0
