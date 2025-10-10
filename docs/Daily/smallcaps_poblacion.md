Quieres **un repositorio masivo** para I+D ahora y screening en tiempo real después. Vamos por partes y cierro con un plan concreto que equilibra “máximo nº de ejemplos” vs. overfitting/coste.

# 1) ¿Descargar 1-min para **todas** las small caps?

Se puede, pero sé crítico con dos cosas: **tiempo** y **utilidad**.

* **Utilidad**: el 1-min solo aporta señal cuando el ticker está **activo** (RVOL alto, prints continuos). Días “muertos” inundan el dataset de negativo trivial y empeoran la generalización si no haces *active-day masking*.
* **Tiempo/429**: bajar 3 años × ~5.000 tickers en 1-min es factible, pero es **varios cientos de GB** y **muchas horas/días** a ritmo Advanced (depende de cómo paralelicemos y la actividad media real de cada ticker). Como tú pagas y tienes disco, **no lo descarto** — solo lo haría **en oleadas** con buenas reglas de calidad.

## Mi recomendación (equilibrada y pro-I+D)

* **1d + 1h para 100%** del universo (esto ya está).
* **1-min “completo (3y)” para Top-2000** (no 500): más diversidad → menos overfitting a unos pocos tickers “famosos”.
* **Para los ~3.000 restantes**: **ventanas de evento** (D-2…D+2) en 1-min (así capturas *todos* los spikes útiles sin pagar por 3 años de días muertos).
* **Más adelante**, si quieres **todo 1-min para 5.000**, lo hacemos como backfill en **lotes** (letras/oleadas) mientras entrenas. No te bloquea.

> Resultado: un dataset **gigante en ejemplos de eventos**, con **diversidad de tickers**, pero sin arrastrar toneladas de 1-min inútil.

# 2) ¿Top-500, Top-1000 o Top-2000?

Con tu objetivo (maximizar población de *eventos* y reducir overfitting), **Top-2000** me gusta más:

* Eleva mucho la diversidad de regímenes y microestructura.
* Evita que el modelo “memorice” 200 nombres de siempre.
* Con *active-day masking* (ver abajo) el ruido se controla.

# 3) ¿“Desechar lo no-evento”?

Para **1-min**, sí: fuera de **Top-2000**, guarda solo **ventanas de evento**.
Para **1d/1h**, **no**: mantener todo 5 años es barato y te da el contexto/negativos bien balanceados.

# 4) ¿Cómo definimos y guardamos un evento?

Tu propuesta de **D-2 a D+2** es razonable para *swing*. Mi pauta exacta:

* **Marcado del evento (día D)** con un **triple-gate** sobre 1d (y opcional 1h):

  * Gap% ≥ 10% **o** percentil 95 del universo,
  * RVOL ≥ 3 **o** p95,
  * ATR% (rolling 60d) ≥ p95.
    Evento si (Gap y RVOL) **o** (RVOL y ATR). Ajustas thresholds para lograr densidad objetivo (p.ej., 40–80 eventos/mes/universo).
* **Ventana 1-min a guardar** (preset swing):

  * **D-2**: RTH completo (09:30–16:00)
  * **D-1**: 14:00–16:00 (setup tarde)
  * **D**: 07:00–16:00 (premarket + sesión)
  * **D+1 y D+2**: 09:30–11:30 (continuación/mean-revert)
* **Contexto 1h**: ya lo tienes 5y y sirve para el “tail” del movimiento sin gastar 1-min extra.

# 5) Anti-overfitting (clave con datasets enormes)

* **Active-day masking** (imprescindible): al entrenar, usa 1-min **solo** si el día cumple:
  `RVOL_day ≥ 1.5`, `dollar_volume ≥ $1M`, `%minutos con trades ≥ 70%`.
  Esto limpia el 90% del ruido de días muertos.
* **Negativos emparejados**: por cada evento, añade 1–2 días *no evento* del mismo símbolo (fechas cercanas o emparejadas por precio/ADV).
* **Validación purgada** (walk-forward + embargo) y **agrupación por ticker** en CV para no “filtrar” patrones del mismo nombre a test.
* **Costes/slippage SSR-aware** (como tienes en config) para realismo.

# 6) Cómo encaja con tu operativa (scanner intradía)

Tu flujo real es **two-stage**:

1. **Screener intradía** (modelo que decide *si vale la pena mirar*). Entrena con muestras por minuto sobre el *universo del escáner* (top por RVOL/GAP al momento) → evita *dataset shift*.
2. **Timing/entrada** (clasificador o política) sobre el subconjunto del screener.

> Conservar **mucho 1-min** es útil: puedes simular ese screener sobre historia (top 20 al minuto) y entrenar tus modelos en el **mismo régimen** que usarás en vivo.

# 7) Plan de descarga que te propongo (ya, sin tocar código)

1. **Mantener Week 1** hasta completar 1d/1h para 100% (sigue corriendo).
2. **Ranking por eventos** (nuevo script): cuenta días “extremos” por símbolo (5y) → ordena.
3. **Week 2-3 (1-min)**:

   * **Oleada A**: Top-1000 (3y completos, particionado por fecha).
   * **Oleada B**: +1000 (para llegar a **Top-2000**).
   * **Resto (~3.000)**: **ventanas D-2…D+2** **solo** en días evento (descarga por lotes de 200–300 tickers).
4. (Opcional) **Backfill total 1-min** para 5.000 en segundo plano, en letras/oleadas, si de verdad quieres *todo-todo* por haberlo pagado. No te bloquea el ML.

# 8) Qué toco del pipeline de datos (mínimo)

* En `config.yaml`:
  `ingestion.top_volatile_count: 2000`
* Añadir dos scripts:

  * `scripts/processing/detect_events.py` → genera `processed/events/events_daily.parquet` (gap, RVOL, ATR% con thresholds).
  * `scripts/ingestion/download_event_windows.py` → lee ese parquet y baja 1-min **solo** en las ventanas definidas (D-2..D+2), idempotente y con reintentos.
* Mantener tu `rank_volatility.py` (sirve para priorizar colas y para Top-2000).

---

## TL;DR – Mi punto de vista (crítico y honesto)

* **Sí** a **Top-2000 1-min (3y)** completos: más diversidad → menos overfitting.
* **Sí** a **ventanas de evento** para el resto (~3.000): capturas *todos* los spikes sin desperdiciar GB.
* **Sí** a guardar **D-2..D+2** (estás en swing): cubre el *setup*, el *gatillo* y el *post-move*; el “cola larga” ya la observa el **1h**.
* **Imprescindible**: *active-day masking*, negativos emparejados y validación purgada.
* **Operativa**: entrena tus modelos contra el **universo del screener** (top por RVOL/GAP minuto a minuto) para que lo que aprenda sea lo mismo que verá en vivo.


