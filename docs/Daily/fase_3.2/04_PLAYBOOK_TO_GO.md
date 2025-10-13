# FASE 3.2 - Playbook: NO-GO → GO

**Fecha**: 2025-10-13
**Status actual**: NO-GO (4,457 eventos vs 8,000-12,000 objetivo)
**Gap**: -3,543 eventos mínimo, -5,543 eventos objetivo

---

## 🚨 BUG CRÍTICO DETECTADO: Score No Normalizado

### Situación Actual

**Score en datos enriquecidos**:
```python
Min:    0.5
Max:    7,195.4
Median: 3.43
Mean:   NaN (algunos valores extremos)
```

**Problema**: El score NO está normalizado a [0, 1] como especifica MANIFEST_CORE_SPEC.md

### Impacto

1. ❌ **Sanity check inválido**: "Score median: 39.370 (threshold ≥0.7)" - estamos comparando peras con manzanas
2. ❌ **Desempate estable comprometido**: ORDER BY score DESC puede favorecer incorrectamente event_types con scores raw más altos
3. ❌ **Reportes de calidad incorrectos**: Todas las estadísticas de score son engañosas
4. ❌ **Auditoría comprometida**: No podemos defender la selección de eventos si el ranking principal está sesgado

### Solución Requerida

**Normalizar score antes del dry-run**:

```python
# Option A: Min-Max normalization por event_type y session
df = df.with_columns([
    ((pl.col('score') - pl.col('score').min().over(['event_type', 'session'])) /
     (pl.col('score').max().over(['event_type', 'session']) -
      pl.col('score').min().over(['event_type', 'session'])))
    .alias('score_normalized')
])

# Option B: Z-score → Sigmoid (si queremos penalizar outliers)
df = df.with_columns([
    (1 / (1 + pl.col('score').sub(pl.col('score').mean().over(['event_type', 'session']))
                           .div(pl.col('score').std().over(['event_type', 'session']))
                           .mul(-1).exp()))
    .alias('score_normalized')
])
```

**Acción inmediata**: Crear script `normalize_scores.py` y aplicar antes de continuar.

---

## Ruta 1: Esperar Detección Completa (RECOMENDADO)

**Timeline**: 2-3 días
**Riesgo**: Bajo
**Calidad**: Máxima

### Contexto

**Progreso FASE 2.5**:
- Run 20251012: 809 símbolos ✅ COMPLETO
- Run 20251013: 607 símbolos ✅ COMPLETO (actualizado 21:39)
- **Total actual**: 1,416 símbolos (70.9%)
- **Pendiente**: 580 símbolos (29.1%)

**Proyección**:
```
Eventos actuales: 4,457 (con 1,133 símbolos procesados)
Eventos proyectados: 4,457 × (1,996 / 1,133) ≈ 7,850 eventos

Con normalización de scores y re-ranking: ± 10%
Rango esperado: 7,000 - 8,600 eventos
```

### Pasos Detallados

#### Paso 1: Normalizar Scores (CRÍTICO)

**Ubicación**: `scripts/processing/normalize_event_scores.py`

```python
#!/usr/bin/env python3
"""
Normalize event scores to [0, 1] range by event_type and session.
This is required for proper desempate estable and sanity checks.
"""

import polars as pl
from pathlib import Path
from datetime import datetime

def normalize_scores(input_file: Path, output_file: Path):
    """Normalize scores using min-max per event_type and session"""

    print(f"Loading: {input_file}")
    df = pl.read_parquet(input_file)

    print(f"Original score stats:")
    print(f"  Min: {df['score'].min():.2f}")
    print(f"  Max: {df['score'].max():.2f}")
    print(f"  Median: {df['score'].median():.2f}")

    # Min-max normalization by event_type and session
    df = df.with_columns([
        ((pl.col('score') - pl.col('score').min().over(['event_type', 'session'])) /
         (pl.col('score').max().over(['event_type', 'session']) -
          pl.col('score').min().over(['event_type', 'session']))
        ).alias('score_normalized')
    ])

    # Replace original score with normalized (keep backup)
    df = df.with_columns([
        pl.col('score').alias('score_raw'),
        pl.col('score_normalized').alias('score')
    ]).drop('score_normalized')

    print(f"\nNormalized score stats:")
    print(f"  Min: {df['score'].min():.2f}")
    print(f"  Max: {df['score'].max():.2f}")
    print(f"  Median: {df['score'].median():.2f}")

    # Save
    df.write_parquet(output_file)
    print(f"\nSaved: {output_file}")

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[2]

    # Find latest enriched file
    events_dir = base_dir / "processed" / "events"
    enriched_files = sorted(events_dir.glob("events_intraday_enriched_*.parquet"))

    if not enriched_files:
        raise FileNotFoundError("No enriched events found")

    input_file = enriched_files[-1]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = events_dir / f"events_intraday_enriched_normalized_{timestamp}.parquet"

    normalize_scores(input_file, output_file)
```

**Ejecutar**:
```bash
cd D:/04_TRADING_SMALLCAPS
python scripts/processing/normalize_event_scores.py
```

**Validación**:
```bash
python -c "import polars as pl; df=pl.read_parquet('processed/events/events_intraday_enriched_normalized_*.parquet'); print('Min:', df['score'].min()); print('Max:', df['score'].max()); print('Median:', df['score'].median())"
```

**Resultado esperado**: Min≈0.0, Max≈1.0, Median≈0.6-0.8

---

#### Paso 2: Esperar Completitud de FASE 2.5

**Monitoreo**:
```bash
# Check progress
python -c "import json; f=open('logs/checkpoints/events_intraday_20251013_completed.json'); data=json.load(f); print(f'Completed: {data[\"total_completed\"]} symbols')"

# Check if ultra_robust_orchestrator is running
ps aux | grep ultra_robust

# Check recent shards
ls -lth processed/events/shards/ | head -20
```

**Criterio de completitud**:
- `total_completed` ≥ 1,900 símbolos (95%+)
- No más shards generados en últimas 2 horas

**Estimación**: 2-3 días (basado en tasa actual de ~200-300 símbolos/día)

---

#### Paso 3: Re-enriquecer Dataset Completo

**Razón**: Nuevos eventos necesitan dollar_volume_day, rvol_day, session recalc

```bash
cd D:/04_TRADING_SMALLCAPS
python scripts/processing/enrich_events_with_daily_metrics.py
```

**Duración esperada**: ~45-60 minutos (para ~1,996 símbolos)

**Validación**:
```python
import polars as pl
df = pl.read_parquet('processed/events/events_intraday_enriched_*.parquet')

print(f"Total events: {len(df):,}")
print(f"Unique symbols: {df['symbol'].n_unique()}")
print(f"Missing dollar_volume_day: {df['dollar_volume_day'].null_count()} ({df['dollar_volume_day'].null_count()/len(df)*100:.1f}%)")
print(f"Missing rvol_day: {df['rvol_day'].null_count()} ({df['rvol_day'].null_count()/len(df)*100:.1f}%)")
print(f"\nSession distribution:")
print(df.group_by('session').agg(pl.len().alias('count')).sort('session'))
```

---

#### Paso 4: Normalizar Scores del Dataset Completo

```bash
cd D:/04_TRADING_SMALLCAPS
python scripts/processing/normalize_event_scores.py
```

---

#### Paso 5: Re-ejecutar Dry-Run Completo

```bash
cd D:/04_TRADING_SMALLCAPS
python scripts/processing/generate_core_manifest_dryrun.py
```

**Resultado esperado**:
```
Total events: 7,000 - 8,600
Unique symbols: ~1,900
Session PM: 10-20% ✅
Session RTH: 75-85% ✅
Session AH: 3-10% ✅
Score median: 0.65-0.85 ✅
RVol median: >2.0x ✅
Sanity checks: 10/10 PASS ✅
```

---

#### Paso 6: Validación Final

**Checklist**:

```bash
# 1. Total events in range
# 2. Score normalized
python -c "import polars as pl; df=pl.read_parquet('analysis/manifest_core_dryrun_*.parquet'); assert df['score'].min() >= 0.0; assert df['score'].max() <= 1.0; print('✅ Score normalized')"

# 3. Session quotas met
python -c "import polars as pl; df=pl.read_parquet('analysis/manifest_core_dryrun_*.parquet'); sessions = df.group_by('session').agg(pl.len().alias('n')); pm_pct = sessions.filter(pl.col('session')=='PM')['n'][0] / len(df); assert 0.10 <= pm_pct <= 0.20; print('✅ PM quota met')"

# 4. No duplicate symbol-date
python -c "import polars as pl; df=pl.read_parquet('analysis/manifest_core_dryrun_*.parquet'); dupes = df.group_by(['symbol','date_et']).agg(pl.len().alias('n')).filter(pl.col('n')>1); assert len(dupes)==0; print('✅ No duplicates')"

# 5. All events have required metrics
python -c "import polars as pl; df=pl.read_parquet('analysis/manifest_core_dryrun_*.parquet'); assert df['dollar_volume_bar'].null_count() == 0; assert df['spread_proxy'].null_count() == 0; print('✅ All metrics present')"
```

---

#### Paso 7: GO Decision

**Si 10/10 sanity checks PASS**:
```bash
echo "✅ GO PARA FASE 3.2" > docs/Daily/fase_3.2/GO_STATUS.txt
```

**Proceder a**:
- Crear manifest final (no dry-run)
- Ejecutar downloader de trades+quotes
- Monitorear progreso

---

## Ruta 2: GO Inmediato con Ajustes (Si No Puedes Esperar)

**Timeline**: Hoy (2-3 horas)
**Riesgo**: Medio
**Calidad**: Alta (pero no máxima)

### Justificación

Si necesitas comenzar FASE 3.2 inmediatamente sin esperar a que termine FASE 2.5:
- Prioridad business sobre completitud técnica
- Proof of concept urgente
- Validar pipeline end-to-end cuanto antes

### Pasos Detallados

#### Paso 1: Normalizar Scores (OBLIGATORIO)

**Mismo que Ruta 1, Paso 1** - No negociable, debe hacerse primero.

```bash
cd D:/04_TRADING_SMALLCAPS
python scripts/processing/normalize_event_scores.py
```

---

#### Paso 2: Ajustar max_per_symbol

**Cambio**: 5 → 7 eventos por símbolo

**Editar**: `scripts/processing/generate_core_manifest_dryrun.py`

```python
CORE_CONFIG = {
    "max_events": 10000,
    "max_per_symbol": 7,  # Was 5, now 7 (+40%)
    "max_per_symbol_day": 1,  # Keep at 1 (diversidad temporal)
    "max_per_symbol_month": 20,  # Keep at 20
    ...
}
```

**Proyección**:
```
Current: 1,133 symbols × 5 events/symbol ≈ 4,457 eventos
New:     1,133 symbols × 7 events/symbol ≈ 6,200-6,500 eventos
```

**Validación post-cambio**:
- Total events: 6,000-7,000 (esperado)
- Top 20 concentration: Debe permanecer <25%

---

#### Paso 3: Relajar Filtros de Liquidez PM (Fino)

**Cambio**: Reducir umbrales PM en 10-15%

**Editar**: `scripts/processing/generate_core_manifest_dryrun.py`

```python
"liquidity_filters": {
    "RTH": {
        "min_dollar_volume_bar": 100000,    # No cambiar
        "min_absolute_volume_bar": 10000,   # No cambiar
        "min_dollar_volume_day": 500000,    # No cambiar
        "rvol_day_min": 1.5,                # No cambiar
        "max_spread_proxy_pct": 5.0,        # No cambiar
    },
    "PM": {
        "min_dollar_volume_bar": 25000,     # Was 30K, now 25K (-17%)
        "min_absolute_volume_bar": 2500,    # Was 3K, now 2.5K (-17%)
        "min_dollar_volume_day": 250000,    # Was 300K, now 250K (-17%)
        "rvol_day_min": 0.9,                # Was 1.0, now 0.9 (-10%)
        "max_spread_proxy_pct": 8.5,        # Was 8.0, now 8.5 (+6%)
    },
    "AH": {
        # Keep AH as is - already in range (4.5%)
        "min_dollar_volume_bar": 30000,
        "min_absolute_volume_bar": 3000,
        "min_dollar_volume_day": 300000,
        "rvol_day_min": 1.0,
        "max_spread_proxy_pct": 8.0,
    }
}
```

**Proyección**: +500-1,000 eventos adicionales de PM

**Riesgo**:
- ⚠️ Spread promedio de PM podría aumentar ligeramente
- ⚠️ RVol de PM podría bajar a ~1.8-2.0x (desde ~2.5x)
- ✅ Aún dentro de rangos aceptables para microstructure analysis

---

#### Paso 4: Re-ejecutar Dry-Run

```bash
cd D:/04_TRADING_SMALLCAPS
python scripts/processing/generate_core_manifest_dryrun.py
```

**Resultado esperado**:
```
Total events: 7,000 - 8,000 (combinando max_per_symbol=7 + PM relajado)
Unique symbols: ~1,050-1,100
Session PM: 13-17% ✅ (ligeramente más alto por relajación)
Session RTH: 77-82% ✅
Session AH: 4-6% ✅
Score median: 0.65-0.80 ✅ (normalizado)
RVol median: 2.0-2.3x ✅ (ligeramente más bajo)
Sanity checks: 10/10 PASS ✅ (si total ≥8K)
```

---

#### Paso 5: Validación y Monitoring

**Si 10/10 sanity checks PASS**:
```bash
echo "✅ GO PARA FASE 3.2 (ACELERADO)" > docs/Daily/fase_3.2/GO_STATUS.txt
echo "⚠️ Dataset at 57% completeness - quality acceptable" >> docs/Daily/fase_3.2/GO_STATUS.txt
```

**Monitoring adicional**:
```python
# After manifest is created
import polars as pl
df = pl.read_parquet('analysis/manifest_core_dryrun_*.parquet')

# Check PM quality specifically
pm_events = df.filter(pl.col('session') == 'PM')
print("PM Quality Check:")
print(f"  Score median: {pm_events['score'].median():.3f}")
print(f"  RVol median: {pm_events['rvol_day'].drop_nulls().median():.2f}x")
print(f"  Spread median: {pm_events['spread_proxy'].median():.4f}")

# If PM quality is too low:
if pm_events['score'].median() < 0.55 or pm_events['spread_proxy'].median() > 0.08:
    print("⚠️ WARNING: PM quality degraded - consider reverting PM relaxation")
```

---

#### Paso 6: Documentar Trade-offs

**Crear**: `docs/Daily/fase_3.2/05_TRADEOFFS_GO_ACELERADO.md`

```markdown
# Trade-offs de GO Acelerado

## Decisión
Proceder con FASE 3.2 a 57% completitud de FASE 2.5

## Ajustes Aplicados
1. Score normalizado (CRÍTICO - arreglado)
2. max_per_symbol: 5 → 7 (+40%)
3. PM liquidity filters relajados (~15%)

## Impacto en Calidad
- RVol median: 2.5x → 2.1x (aún excelente)
- PM spread: 3.5% → 4.2% (aún dentro de límites)
- Score median: 0.70-0.75 (normalizado, correcto)

## Justificación
[Razones business para GO acelerado]

## Plan de Validación Posterior
- Cuando FASE 2.5 complete (100%), re-ejecutar manifest
- Comparar calidad: acelerado vs completo
- Si calidad mejora significativamente, considerar re-download
```

---

## Ruta 3: NO Recomendada (Solo por Completitud)

### Opción 3A: Aflojar RTH (NO HACER)

**Cambio**: Reducir filtros RTH en 20%

**Por qué NO**:
- ❌ RTH es la sesión MÁS IMPORTANTE (82% del manifest)
- ❌ Compromete calidad de la mayoría del dataset
- ❌ RVol median podría caer <2.0x (falla sanity check)
- ❌ No es necesario - RTH ya aporta suficientes eventos

### Opción 3B: Eliminar Daily Cap (NO HACER)

**Cambio**: `max_per_symbol_day: 1 → 2`

**Por qué NO**:
- ❌ Crea sobre-muestreo de días específicos
- ❌ Sesgo temporal (favorece días con múltiples eventos)
- ❌ Reduce diversidad (objetivo clave del CORE manifest)
- ❌ Puede introducir autocorrelación en microstructure analysis

### Opción 3C: Bajar Threshold de Score (NO HACER)

**Cambio**: `min_event_score: 0.60 → 0.50`

**Por qué NO**:
- ❌ Introduce eventos de baja calidad
- ❌ Score <0.60 indica eventos marginales o ruidosos
- ❌ Compromete confianza en detecciones
- ❌ No vale la pena por +500-800 eventos adicionales

---

## Comparación de Rutas

| Criterio | Ruta 1 (Esperar) | Ruta 2 (Acelerado) | Ruta 3 (No Recomendado) |
|----------|------------------|---------------------|------------------------|
| **Timeline** | 2-3 días | 2-3 horas | 1 hora |
| **Eventos esperados** | 7,850-8,600 | 7,000-8,000 | 8,000+ (baja calidad) |
| **Score normalizado** | ✅ | ✅ | ❌ (si no se hace) |
| **RVol median** | >2.5x | ~2.1x | <2.0x |
| **Spread median** | <3.5% | ~4.0% | >5.0% |
| **Symbol coverage** | ~95% | ~57% | ~57% |
| **Sanity checks** | 10/10 PASS | 10/10 PASS | 7-8/10 PASS |
| **Auditable** | ✅✅✅ | ✅✅ | ❌ |
| **Riesgo** | Bajo | Medio | Alto |
| **Recomendación** | ✅ SÍ | ⚠️ Solo si urgente | ❌ NO |

---

## Comandos Rápidos (Resumen)

### Ruta 1 (Recomendado)
```bash
# 1. Normalizar scores
python scripts/processing/normalize_event_scores.py

# 2. Esperar FASE 2.5 (monitorear)
watch -n 300 'python -c "import json; f=open(\"logs/checkpoints/events_intraday_20251013_completed.json\"); print(json.load(f)[\"total_completed\"])"'

# 3. Re-enriquecer (cuando complete)
python scripts/processing/enrich_events_with_daily_metrics.py

# 4. Normalizar scores del dataset completo
python scripts/processing/normalize_event_scores.py

# 5. Dry-run final
python scripts/processing/generate_core_manifest_dryrun.py

# 6. Validar GO
python scripts/analysis/validate_core_manifest.py

# 7. Si GO → ejecutar FASE 3.2
python scripts/ingestion/download_trades_quotes_intraday.py --resume
```

### Ruta 2 (Acelerado)
```bash
# 1. Normalizar scores
python scripts/processing/normalize_event_scores.py

# 2. Ajustar config (manual edit)
# - max_per_symbol: 5 → 7
# - PM filters: -15%

# 3. Dry-run
python scripts/processing/generate_core_manifest_dryrun.py

# 4. Si GO → documentar trade-offs
echo "GO ACELERADO - ver 05_TRADEOFFS" > docs/Daily/fase_3.2/GO_STATUS.txt

# 5. Ejecutar FASE 3.2
python scripts/ingestion/download_trades_quotes_intraday.py --resume
```

---

## Criterios de GO (Universal)

Ambas rutas requieren cumplir:

1. ✅ **Total events**: 8,000 - 12,000
2. ✅ **Score normalizado**: Min≈0, Max≈1, Median 0.65-0.85
3. ✅ **Unique symbols**: ≥400
4. ✅ **RVol median**: ≥2.0x
5. ✅ **Top20 concentration**: <25%
6. ✅ **Session PM**: 10-20%
7. ✅ **Session RTH**: 75-85%
8. ✅ **Session AH**: 3-10%
9. ✅ **Storage p90**: <250 GB
10. ✅ **Time p90**: <3 days

**Status actual sin corrección de score**: 9/10 PASS (falta #1: total events)
**Status actual CON corrección de score**: 8/10 PASS (falta #1: total events, #2: score normalizado)

---

## Next Steps Recomendados

**AHORA MISMO (Urgente)**:
1. ✅ Crear `normalize_event_scores.py`
2. ✅ Ejecutar normalización
3. ✅ Validar score range [0, 1]
4. ✅ Re-ejecutar dry-run para ver impacto

**Después de normalización**:
- **Si tienes tiempo**: Ruta 1 (esperar FASE 2.5)
- **Si es urgente**: Ruta 2 (ajustar y GO)

**NO HACER**:
- ❌ Proceder sin normalizar scores
- ❌ Aplicar Ruta 3 (aflojar demasiado)
- ❌ Saltar validaciones

---

## Conclusión

**Recomendación final**:

1. **Prioridad #1**: Normalizar scores (CRÍTICO, no negociable)
2. **Prioridad #2**: Decidir entre Ruta 1 vs Ruta 2 basado en urgencia business
3. **Prioridad #3**: Ejecutar playbook elegido step-by-step
4. **Prioridad #4**: Validar GO con 10/10 sanity checks PASS

El bug de score es el bloqueo más crítico. Una vez corregido, cualquiera de las dos rutas recomendadas te llevará a GO status con calidad aceptable.

---

**Archivos relacionados**:
- Estado: [00_ESTADO_ACTUAL.md](00_ESTADO_ACTUAL.md)
- Resultados: [03_DRY_RUN_RESULTS.md](03_DRY_RUN_RESULTS.md)
- Spec: [MANIFEST_CORE_SPEC.md](MANIFEST_CORE_SPEC.md)
- Validación: [01_VALIDATION_CHECKLIST.md](01_VALIDATION_CHECKLIST.md)
