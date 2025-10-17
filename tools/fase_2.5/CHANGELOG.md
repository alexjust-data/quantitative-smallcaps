# Changelog - Tools

## 2025-10-16 - Refactorización de Análisis de Duplicados

### Nuevas Funcionalidades

#### 1. Análisis de Heartbeat Log
- **Nueva función:** `analyze_heartbeat_log(tail_lines=500)`
- Analiza el heartbeat log en tiempo real
- Detecta símbolos duplicados durante procesamiento activo
- Muestra top símbolos más duplicados
- Lectura eficiente desde el final del archivo (tail optimizado)

#### 2. Análisis de Checkpoint Actual
- **Nueva función:** `analyze_current_checkpoint()`
- Muestra progreso actual del run
- Calcula % completado y símbolos restantes
- Barra de progreso visual
- Timestamp de última actualización

#### 3. Modo Quick Check
- **Nuevo flag:** `--heartbeat-only`
- Análisis ultra-rápido (~1 segundo)
- Solo heartbeat + checkpoint (sin leer shards)
- Ideal para monitoreo continuo durante ejecución

#### 4. Script de Conveniencia
- **Nuevo archivo:** `tools/quick_check.bat`
- Atajo para `--heartbeat-only`
- Un solo comando para check rápido

### Mejoras en Output

#### Antes (sin refactorización)
```bash
# Solo análisis manual con awk/grep
tail -200 logs/detect_events/heartbeat_*.log | awk '{print $3}' | sort | uniq -c | sort -rn
```

#### Ahora (refactorizado)
```bash
# Análisis automático con interpretación
tools\quick_check.bat

# Output:
Total entries analyzed: 500
Unique symbols: 388
Duplicated symbols: 112
Duplication rate: 9.30%
Status: ✓ GOOD

Top 20 symbols with duplications:
  REKR: 5 times
  RVYL: 3 times
  ...

Progress: [████████████████░░░░] 88.4%
Completed: 1,765 / 1,996
Remaining: 231 symbols
```

### Ventajas

1. **Velocidad:** Quick check toma ~1 segundo vs 30-60 segundos análisis completo
2. **Automatización:** No necesitas recordar comandos awk/grep
3. **Interpretación:** Status automático (EXCELLENT/GOOD/WARNING/CRITICAL)
4. **Progreso visual:** Barra de progreso y estadísticas claras
5. **Cross-platform:** Funciona en Windows (.bat) y Linux/Mac (.py)

### Uso Típico

#### Durante Ejecución (Watchdog Activo)
```bash
# Cada 5-10 minutos para monitorear
tools\quick_check.bat
```

#### Después de Completar
```bash
# Análisis completo de todos los shards
tools\analyze_duplicates.bat
```

#### Para Exportar Resultados
```bash
# Generar CSV para análisis en Excel/Python
python tools/analyze_duplicates.py --export-csv
```

### Archivos Modificados

- `tools/analyze_duplicates.py` (refactorizado)
  - +200 líneas (funciones heartbeat + checkpoint)
  - Nuevos imports: `re`, `Counter`
  - Nueva flag `--heartbeat-only`
  
- `tools/analyze_duplicates.bat` (actualizado)
  - Documentación de uso en header
  
- `tools/quick_check.bat` (nuevo)
  - Atajo para análisis rápido
  
- `tools/README.md` (nuevo)
  - Documentación completa
  - Ejemplos de uso
  - Guía de interpretación

### Testing

Probado con:
- Run 20251016 (4 símbolos, 0% duplicación) ✓
- Run 20251014 (1,765 símbolos, 9.3% duplicación) ✓
- Shards de últimos 7 días (437 shards) ✓
- Archivo merged corrupto (48% duplicación detectada) ✓

---

**Autor:** Claude Code  
**Fecha:** 2025-10-16  
**Fase:** FASE 2.5 - Event Detection Intraday
