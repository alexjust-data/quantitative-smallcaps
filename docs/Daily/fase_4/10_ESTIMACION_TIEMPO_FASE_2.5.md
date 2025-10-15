# Estimación de Tiempo - FASE 2.5

**Fecha**: 2025-10-14 18:29 UTC
**Status**: 🔄 **EN PROCESO**

---

## Datos Recopilados

### Tiempo de Ejecución Actual

| Métrica | Valor |
|---------|-------|
| **Inicio del run** | 2025-10-14 18:21:16 UTC |
| **Hora actual** | 2025-10-14 18:29:14 UTC |
| **Tiempo transcurrido** | **7 min 58 seg** (478 segundos) |

### Progreso de Símbolos

| Métrica | Valor |
|---------|-------|
| **Checkpoint inicial** (seeded) | 1,255 símbolos |
| **Checkpoint actual** | 1,260 símbolos |
| **Símbolos completados** | **5 símbolos** |
| **Símbolos restantes** | 1,996 - 1,260 = **736 símbolos** |

### Símbolos en Proceso (Heartbeat)

Últimos símbolos registrados en heartbeat (orden cronológico):

```
18:21:16 - UAVS, USEG, USGO, TEM (inicio simultáneo - 4 workers)
18:21:28 - COMM (698 eventos)
18:21:34 - VFF (142 eventos)
18:21:53 - UPWK (383 eventos)
18:22:01 - SATS (1,341 eventos)
18:22:38 - URGN (1,308 eventos)
18:22:40 - QUIK (785 eventos)
18:22:58 - XGN (589 eventos)
18:23:09 - REI (1,604 eventos)
18:23:28 - WWW (918 eventos)
18:23:52 - TILE (1,018 eventos)
18:24:09 - RGTI (1,062 eventos)
```

**Total símbolos iniciados**: 15 símbolos
**Total símbolos completados (checkpoint)**: 5 símbolos
**Símbolos en proceso**: ~10 símbolos

---

## Análisis de Velocidad

### Velocidad Observada

```
Tiempo por símbolo completado = 478 seg / 5 símbolos = 95.6 seg/símbolo
```

### Contexto Importante

- **4 workers en paralelo** procesando símbolos diferentes
- El **heartbeat registra INICIO** de procesamiento
- El **checkpoint registra FINALIZACIÓN** de procesamiento
- Gap entre heartbeat y checkpoint: ~10 símbolos en cola

### Throughput Real

```
Velocidad efectiva = 5 símbolos completados / 478 segundos
                   = 0.0105 símbolos/segundo
                   = 0.63 símbolos/minuto
                   = 37.6 símbolos/hora
```

---

## Proyección de Tiempo Restante

### Escenarios

#### Escenario 1: Velocidad Actual (95.6 seg/símbolo)

```
Símbolos restantes: 736
Tiempo por símbolo: 95.6 seg

Con 4 workers en paralelo:
Tiempo = 736 símbolos × 95.6 seg / 4 workers
       = 70,329 segundos
       = 1,172 minutos
       = 19.5 horas
```

**⚠️ NOTA**: Esta estimación asume velocidad constante, pero ignora:
- Los 10 símbolos ya en proceso (reduce tiempo)
- Variabilidad en tamaño de datos por símbolo
- Símbolos que no tienen datos (skip rápido)

#### Escenario 2: Velocidad Optimista (10 símbolos ya procesados)

Considerando los 10 símbolos en proceso que pronto se marcarán como completados:

```
Símbolos ya procesados (no reflejados): ~10
Símbolos efectivamente restantes: 736 - 10 = 726

Tiempo = 726 × 95.6 / 4 = 17,340 seg = 4.8 horas
```

#### Escenario 3: Velocidad Observada (Throughput Real)

Usando la velocidad de finalización observada:

```
Velocidad = 37.6 símbolos/hora (con 4 workers)

Tiempo = 736 símbolos / 37.6 símbolos/hora
       = 19.6 horas
```

---

## Estimación Final

### Proyección Conservadora

| Componente | Valor |
|------------|-------|
| **Símbolos restantes** | 736 |
| **Velocidad estimada** | 37-40 símbolos/hora |
| **Tiempo estimado** | **18-20 horas** |
| **ETA (desde ahora)** | **2025-10-15 12:00 - 14:00 UTC** |

### Factores que Pueden Acelerar

1. ✅ **Símbolos sin datos**: Algunos símbolos no tienen barras 1m → skip inmediato
2. ✅ **Símbolos con pocos días**: Menos datos → procesamiento más rápido
3. ✅ **Checkpoint cada 10 símbolos**: Reduce overhead de escritura
4. ✅ **Workers ya en ritmo**: Pipeline de procesamiento estabilizado

### Factores que Pueden Ralentizar

1. ⚠️ **Símbolos con muchos eventos**: Más eventos → más tiempo de escritura
2. ⚠️ **Memoria**: Si RAM sube mucho, puede haber GC overhead
3. ⚠️ **I/O disk**: Escritura de shards puede ser cuello de botella

---

## Velocidad Real vs Estimación Inicial

### Estimación Inicial (en documento anterior)
```
Estimado: 15-20 seg/símbolo → ~3 horas para 741 símbolos
```

### Realidad Observada
```
Observado: 95.6 seg/símbolo → ~19 horas para 736 símbolos
```

### Diferencia
```
Factor de diferencia: 95.6 / 17.5 = 5.5x más lento
```

**Razones**:
1. Estimación inicial no consideró **todos los días históricos** por símbolo
2. Cada símbolo procesa **múltiples años de datos** (no solo días recientes)
3. Detección de eventos es **CPU-intensive** (VWAP, momentum, consolidation, etc.)
4. Escritura de shards + manifests tiene overhead

---

## Recomendaciones

### Monitoreo Continuo

```powershell
# Ver progreso cada 5 minutos
while ($true) {
    $checkpoint = Get-Content "D:\04_TRADING_SMALLCAPS\logs\checkpoints\events_intraday_20251014_completed.json" | ConvertFrom-Json
    $completed = $checkpoint.total_completed
    $remaining = 1996 - $completed
    $percent = [math]::Round(($completed / 1996) * 100, 1)

    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] Completados: $completed/1996 ($percent%) - Restantes: $remaining"
    Start-Sleep -Seconds 300
}
```

### Checkpoint Intermedio (Opcional)

Si necesitas validar que no hay duplicación antes de finalizar:

```powershell
# Detener workers temporalmente
python scripts/processing/restart_parallel.py

# Verificar shards actuales (dry-run)
python scripts/processing/deduplicate_events.py `
  --input "processed/events/shards/**/*20251014*.parquet" `
  --dry-run

# Si todo OK, relanzar
python scripts/processing/launch_parallel_detection.py --workers 4 --batch-size 50 --yes
```

### Ajuste de Workers (Si Necesario)

Si ves que un worker está idle o hay recursos disponibles:

```powershell
# Relanzar con más workers (máximo recomendado: 6-8)
python scripts/processing/restart_parallel.py
python scripts/processing/launch_parallel_detection.py --workers 6 --batch-size 50 --yes
```

⚠️ **Precaución**: Más workers = más RAM. Monitorear memoria antes de aumentar.

---

## Conclusión

### Tiempo Estimado de Finalización

| Métrica | Valor |
|---------|-------|
| **Inicio** | 2025-10-14 18:21 UTC |
| **Hora actual** | 2025-10-14 18:29 UTC |
| **Progreso** | 1,260 / 1,996 (63.1%) |
| **Tiempo transcurrido** | 8 minutos |
| **Símbolos restantes** | 736 |
| **Velocidad observada** | 37.6 símbolos/hora |
| **Tiempo restante estimado** | **18-20 horas** |
| **ETA Final** | **2025-10-15 12:00-14:00 UTC** |

### Próximos Hitos

1. **~2 horas (20:30 UTC)**: ~80 símbolos completados → checkpoint ~1,340
2. **~6 horas (00:30 UTC)**: ~225 símbolos completados → checkpoint ~1,485
3. **~12 horas (06:30 UTC)**: ~450 símbolos completados → checkpoint ~1,710
4. **~18 horas (12:30 UTC)**: ~675 símbolos completados → checkpoint ~1,935
5. **~20 horas (14:30 UTC)**: **COMPLETADO** → 1,996 símbolos

### Acción Recomendada

✅ **Dejar correr durante la noche** - El sistema está funcionando correctamente sin duplicación.

🔍 **Revisar mañana** (2025-10-15 06:00-08:00 UTC) para verificar progreso intermedio.

✅ **Validar al finalizar** con deduplicación para confirmar < 1% duplicados.

---

**Documento generado**: 2025-10-14 18:29 UTC
**Próxima actualización recomendada**: 2025-10-15 06:00 UTC
