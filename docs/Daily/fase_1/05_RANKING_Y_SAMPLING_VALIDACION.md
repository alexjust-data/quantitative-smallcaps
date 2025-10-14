# Ranking de Eventos y Sampling para Validación Manual

## Comando Ejecutado

```bash
python scripts/processing/rank_by_event_count.py --top-n 2000
```

---

## 📊 Resultado del Ranking

### ✅ Archivo Generado
```
processed/rankings/top_2000_by_events_20251009.parquet
```

### 📈 Estadísticas Top-2000

- **Total eventos capturados:** 14,365 de 20,695 (69.4%)
- **Mean eventos/ticker:** 7.2
- **Median eventos/ticker:** 6.0
- **Min eventos (rank 2000):** 4
- **Mean event rate:** 2.92%

### 📊 Símbolos Únicos

- **Total símbolos con eventos:** 4,878
- **Top-2000 seleccionados:** 2,000 (41%)
- **Resto:** 2,878 (59%)

---

## 🎯 Análisis Crítico

### 1. Cobertura de Eventos (69.4%)

**Esperado:** 75%
**Obtenido:** 69.4%
**Evaluación:** ✅ Bueno pero no óptimo

**Implicación:**
- Top-2000 captura ~14k eventos
- Resto 2,878 tiene ~6.3k eventos (30.6%)
- Distribución es **menos concentrada** de lo esperado (más "democrática")

**Posible causa:**
Con preset actual (Gap 5%, RVOL 2.0, sin PM filter), hay muchos tickers con 4-10 eventos cada uno, en lugar de concentración en pocos "hot stocks".

---

### 2. Distribución (Mean 7.2, Median 6.0)

**Evaluación:** ✅ **Excelente**

Mean ≈ Median indica distribución **relativamente uniforme** en el Top-2000.

**Interpretación:**
- No hay 10-20 "super hot stocks" dominando
- Es una distribución más plana (muchos tickers moderadamente activos)

---

### 3. Mínimo 4 Eventos para Entrar Top-2000

**Evaluación:** ✅ **Razonable**

4 eventos en 5 años = ~0.8 eventos/ticker/año = 1 evento cada 15 meses.

**Es un umbral sensato** para considerar "ticker activo".

---

## 🏆 Top-20 Tickers

| Rank | Symbol | Eventos | Gap% medio | RVOL medio | Dollar Vol medio |
|------|--------|---------|------------|------------|------------------|
| 1 | PLRZ | 27 | 26.7% | 7.9x | $57M |
| 2 | WOLF | 24 | 21.9% | 3.7x | $306M |
| 3 | GTI | 24 | 20.0% | 6.3x | $38M |
| 4 | QUBT | 22 | 14.2% | 3.6x | $1.3B |
| 5 | DGLY | 22 | 25.2% | 6.2x | $11M |
| ... | ... | ... | ... | ... | ... |
| 16 | CDT | 19 | 25.3% | 8.5x | $55M |
| 17 | MAIA | 19 | 8.0% | 4.8x | $3.4M |
| 18 | ADTX | 19 | 15.9% | 5.1x | $89M |
| 19 | BON | 19 | 31.2% | 5.9x | $38M |
| 20 | HCTI | 19 | 54.8% | 8.9x | $52M |

---

## ✅ Validación Cualitativa del Top-20

### 1. Son Tickers Small-Cap Reales: ✅

**Ejemplos conocidos:**
- **WOLF** (Wolfspeed) - Semiconductor, muy volátil, conocido
- **QUBT** (Quantum Computing) - Small-cap tech, pump-friendly
- **DGLY** (Digital Ally) - Bodycam company, eventos por news

**Conclusión:** Top-20 parece legítimo (no penny stock spam puro).

---

### 2. Métricas Razonables: ✅

- **Gap promedio:** 15-50% (coherente con small-caps)
- **RVOL promedio:** 3.5-9x (normal para eventos)
- **Dollar volume:** $11M-$1.3B (rango amplio pero tradable)

---

### 3. Frecuencia de Eventos: ✅

- **Top-1:** 27 eventos en 5 años = **5.4 eventos/año** (razonable)
- **Top-20:** 19 eventos en 5 años = **3.8 eventos/año**

**No son frecuencias absurdas** (si hubiera 100+ eventos/año sería señal de ruido).

---

## 🚀 Decisión: Opción B - Validación Manual

### Sampling Estratificado para Validación

**Estrategia:**
- 10 eventos de Top-100 (hot tickers)
- 10 eventos de Rank 500-1000 (mid-tier)
- 10 eventos de Rank 1500-2000 (cold-tier)

**Total:** 30 eventos

---

## 📋 Lista de 30 Eventos para Validación en TradingView

### Tier 1: Hot Tickers (Top-100) - 10 eventos

1. **BTOG** (2025-04-23) | Gap: 43.87% RVOL: 4.30x DV:$ 24.28M
2. **DPRO** (2025-07-16) | Gap: 19.53% RVOL:10.10x DV:$191.52M
3. **GTI** (2025-06-12) | Gap: 21.31% RVOL: 3.26x DV:$ 13.30M
4. **BLNE** (2025-08-27) | Gap: 19.52% RVOL: 7.77x DV:$ 21.19M
5. **RCAT** (2025-06-02) | Gap: 8.57% RVOL: 2.07x DV:$ 74.51M
6. **CTM** (2024-12-26) | Gap: 39.66% RVOL:10.74x DV:$144.22M
7. **QUBT** (2024-11-25) | Gap: 22.46% RVOL: 2.80x DV:$1038.74M ⭐
8. **BHAT** (2025-01-31) | Gap: 0.00% RVOL: 2.37x DV:$ 8.54M
9. **WLDS** (2025-01-06) | Gap: 9.65% RVOL: 2.57x DV:$ 2.35M
10. **DGLY** (2025-02-20) | Gap: 0.00% RVOL: 1.89x DV:$ 4.80M

---

### Tier 2: Mid-Tier (Rank 500-1000) - 10 eventos

11. **MXCT** (2025-03-12) | Gap: 10.37% RVOL: 3.22x DV:$ 6.81M
12. **MACI** (2025-06-26) | Gap: 0.00% RVOL: 4.09x DV:$ 4.49M
13. **MNTS** (2025-06-30) | Gap: 22.70% RVOL:16.01x DV:$ 59.91M ⭐
14. **FCN** (2025-02-20) | Gap: 3.40% RVOL: 3.86x DV:$137.47M
15. **KEQU** (2024-12-12) | Gap: 15.06% RVOL: 3.67x DV:$ 3.34M
16. **TCMD** (2025-05-07) | Gap: 1.52% RVOL: 2.35x DV:$ 6.77M
17. **NMTC** (2024-12-17) | Gap: 11.04% RVOL: 5.29x DV:$ 1.11M
18. **UOKA** (2024-12-09) | Gap: 44.94% RVOL: 4.68x DV:$ 47.44M ⭐
19. **ANSC** (2025-04-02) | Gap: 0.00% RVOL: 4.53x DV:$ 2.09M
20. **APO** (2024-12-09) | Gap: 6.44% RVOL: 4.28x DV:$3337.54M ⭐⭐

---

### Tier 3: Cold-Tier (Rank 1500-2000) - 10 eventos

21. **CVEO** (2025-02-27) | Gap: 11.01% RVOL: 2.91x DV:$ 11.08M
22. **DRMA** (2025-01-21) | Gap: 5.26% RVOL: 9.35x DV:$ 5.04M
23. **UK** (2024-10-24) | Gap: 5.93% RVOL: 2.71x DV:$ 1.06M
24. **PGNY** (2024-12-27) | Gap: 7.48% RVOL: 2.42x DV:$ 72.97M
25. **CHWY** (2024-11-04) | Gap: 6.23% RVOL: 2.92x DV:$400.11M ⭐
26. **UWMC** (2025-05-13) | Gap: 1.88% RVOL: 2.46x DV:$ 45.71M
27. **RFIL** (2025-09-15) | Gap: 0.13% RVOL: 1.99x DV:$ 2.52M
28. **VEEE** (2025-09-05) | Gap: 61.34% RVOL:18.65x DV:$226.14M ⭐⭐
29. **BYND** (2025-09-30) | Gap: 0.55% RVOL: 2.40x DV:$ 26.37M
30. **EHTH** (2024-11-06) | Gap: 5.70% RVOL: 7.86x DV:$ 6.19M

---

## 🔍 Observaciones Iniciales

### ✅ Positivo

**1. Algunos eventos muy fuertes:**
- **VEEE:** Gap 61%, RVOL 18.7x → Mega evento
- **QUBT, APO, CHWY:** $400M-$3.3B volume → Muy líquidos
- **MNTS:** RVOL 16x → Volumen explosivo

**2. Tickers conocidos aparecen:**
- **CHWY** (Chewy) - conocido retail stock
- **BYND** (Beyond Meat) - conocido
- **APO** (Apollo Global) - large cap pero volátil

---

### ⚠️ Preocupaciones

**1. Varios eventos con Gap=0%:**
- BHAT, DGLY, MACI, ANSC, RFIL → Entraron por branch ATR (alta volatilidad intraday)
- **Pregunta:** ¿Son tradables o ruido?

**2. Gaps pequeños (1-3%):**
- FCN, TCMD, UWMC, RFIL, BYND → Barely movimientos
- **Pregunta:** ¿Son realmente "eventos"?

**3. Volúmenes bajos en algunos:**
- UK: $1M, NMTC: $1.1M, WLDS: $2.3M → Puede ser ilíquido

---

## 📊 Proceso de Validación

### Para cada evento, ir a TradingView:

1. Buscar: `{SYMBOL}`
2. Ver daily chart en fecha indicada
3. Preguntar:
   - ✅ ¿Hay gap visible? (Si Gap%>0)
   - ✅ ¿Volumen claramente más alto que días previos?
   - ✅ ¿Se ve líquido? (no un solo print gigante)
   - ✅ ¿Parece oportunidad tradable?

### Contar:

- **Plausibles:** Eventos que pasan ≥3 de 4 checks
- **Cuestionables:** Pasan 2 checks
- **Falsos:** Pasan <2 checks

### Criterio GO/NO-GO:

```
Plausibles ≥ 21/30 (70%) → GO para Week 2-3
Plausibles 15-20 (50-70%) → Ajustar levemente y re-run
Plausibles < 15 (<50%) → Problema serio, revisar lógica
```

---

## 📋 Resumen del Estado Actual

### ✅ Completado:

1. **Week 1:** 100% (daily + hourly bars)
2. **Detección de eventos:** 20,695 eventos (1.72%)
3. **Ranking generado:** Top-2000 tickers
4. **Sampling preparado:** 30 eventos estratificados para validación

### ⏳ Pendiente - TU TAREA:

**Validar 30 eventos en TradingView** (lista arriba)
- **Target:** ≥21/30 plausibles (70%)
- **Tiempo estimado:** 30-45 minutos

### 🚀 Próximo Paso (después de validación):

**Si validación OK → Lanzar Week 2-3 descarga**

---

## 📝 Instrucciones Finales

1. **Abre TradingView**
2. **Para cada evento de la lista:**
   - Busca el ticker
   - Ve a la fecha indicada (daily chart)
   - Verifica: gap visible, volumen alto, tradable
3. **Cuenta cuántos son plausibles**
4. **Reporta el resultado:**
   - Si ≥21/30 → **GO para descarga**
   - Si 15-20/30 → Ajustar y re-run
   - Si <15/30 → Revisar lógica

---

## 🔧 Script de Sampling Utilizado

El script está disponible en:
```
scripts/analysis/sample_events_for_validation.py
```

**Ejecución:**
```bash
python scripts/analysis/sample_events_for_validation.py
```

**Función:** Genera sampling estratificado de 30 eventos (10 por tier) con seed fijo (42) para reproducibilidad.
