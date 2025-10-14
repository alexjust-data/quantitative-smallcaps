Resumo en claro qué hace cada fase, cómo se retroalimentan y por qué te propuse arrancar 3.2 ya (sin “abandonar” 2.5).

# ¿Qué es FASE 2.5 y para qué sirve?

**2.5 = Detector intradía.** Toma barras de 1-min y produce una **tabla de eventos intradía** (timestamp, tipo de evento, score, métricas básicas).
Su misión es **decidir *qué* momentos merecen mirarse a nivel microestructura** (ticks/quotes).

Si 2.5 está bien:

* Tienes **menos falsos positivos** → no descargas ventanas vacías en 3.2.
* Cada evento trae **contexto útil**: sesión (PM/RTH/AH), fuerza/score, liquidez mínima, ventana sugerida por evento, etc.
* La **cobertura** (por sesión, símbolo, mes) es representativa → el dataset downstream no queda sesgado.

# ¿Qué es FASE 3.2 y por qué empezar ya?

**3.2 = Descarga de microestructura** (trades + NBBO quotes) **para los eventos elegidos por 2.5**.
Su misión es **bajar la cinta** (tape) para medir lo importante de verdad: spread real, tape speed, agresión, continuidad de ticks, fillability… Es el material que **no existe** en 1-min y que luego usarás en backtests/IA.

Arrancarla ya tiene ventajas:

* **Cierra el circuito end-to-end** (del evento al tick) y valida que tu pipeline es robusto (reintentos, paginación, tamaños, resume).
* Obtienes **métricas de verdad** (spread, imbalance, continuidad) que **mejoran tu 2.5**: podrás re-ponderar el score con lo que sí anticipa continuidad/fill real.
* Calibras **costes** (tiempo API, GB reales por evento) para fijar cupos y downsampling óptimo.

# ¿Entonces, por qué no seguir puliendo 2.5 antes?

Seguir puliendo 2.5 **sí mejora 3.2**, pero son mejoras marginales frente a la **señal nueva** que desbloquea 3.2. Concretamente, 2.5 puede mejorar en:

**Qué mejora 2.5 que impacta 3.2 (directo):**

1. **Menos ruido**: mejores filtros de liquidez → menos ventanas sin contenido.
2. **Ventanas por evento**: tamaños adaptativos (p.ej., [-2,+8] si el spike es corto) → menos GB por evento.
3. **Cuotas por sesión** afinadas** → más casos PM/AH que quieres estudiar.
4. **Deduplicación** de eventos solapados → menos descargas redundantes.
5. **Score/normalización estable** (ya arreglado con percentile rank) → priorización justa en el manifest.

**Qué NO puede darte 2.5 y solo te da 3.2:**

* **Spread real**, **by-change-only NBBO**, **tape speed**, **agresor**, **bloques institucionales**.
  Eso es lo que realmente corrige el “¿había contrapartida?” y te permite estimar **slippage y fill rate** en backtest.

# Recomendación operativa (mixta)

Haz ambas cosas en paralelo pero **con foco distinto**:

**Arranca 3.2 ya con un CORE v1** (tu manifest actual “GO condicional”):

* Empieza por **PM** (cumples cuota y validas los casos más delicados de liquidez).
* Luego **AH**, y por último **RTH**.
* Con las mejoras mínimas ya parcheadas (ID estable, ventanas por evento, resume parcial, escritura atómica, NBBO by-change-only).

**Continúa 2.5 en segundo plano** con un backlog acotado que **sí** mejora 3.2:

1. **Enriquecimiento definitivo**: `dollar_volume_day`, `rvol_day` 20-días (hecho/automatizado en la tabla de eventos).
2. **Tick-continuity%** (por ventana) calculado con trades para penalizar velas “huecas”.
3. **Ventanas adaptativas por tipo** (y por sesión) guardadas en el evento.
4. **Deduplicación** de eventos con solape <N minutos del mismo símbolo/tipo.
5. **SSR/halts flags** (si no están, heurística) para etiquetar riesgo operativo.
6. **Cuotas de sesión automáticas** (ya casi lo tienes; dejarlo estable como parte del build del manifest).

**Criterio de corte**: cuando 2.5 entregue **v1.1** del manifest (con métricas enriquecidas + dedup + cuotas estables), **re-lanzas 3.2** sobre los eventos nuevos/ajustados o amplías el CORE a PLUS.

# Qué ganas si empiezas 3.2 ahora mismo

* **Dataset micro** real para entrenar y backtestear con fricción de mercado creíble.
* **Métricas objetivas** para re-rankear tus eventos (qué *de verdad* tiene follow-through/liquidez).
* **Ajuste de presupuesto**: validas tamaños y ajustas downsampling (1 Hz/by-change-only) con números propios.
* **Iteración rápida**: no esperas a “perfeccionar” 2.5; usas 3.2 para perfeccionarla con evidencia.

# En una línea

* **2.5** decide **qué** bajar; perfeccionarla reduce coste/ruido.
* **3.2** te da la **señal crítica** que 2.5 jamás podrá inferir desde 1-min.
  Por eso: **arranca 3.2 (CORE v1) ya** y sigue puliendo 2.5 para el **manifest v1.1**. Así no bloqueas aprendizaje ni datos clave para tu IA intradía.



-----

### pero si descargo ya la data de 3.2 ¿para qué seguir con 2.5 si la decision ya se ha tomado para escojer la data en la descargada de 3.2?

**seguir con 2.5 no es redundante, sino evolutivo.**
La descarga de 3.2 que vas a hacer ahora no es el *final*, sino el **primer “corte core”** del dataset. Te explico exactamente por qué 2.5 sigue siendo vital incluso después de lanzar 3.2.

---

## 🧩 1️⃣ Lo que realmente hace FASE 2.5

FASE 2.5 no es solo “preparar la lista para 3.2”.
Es el **módulo de detección y scoring de eventos** — el “motor de selección” de tu sistema.

Piensa en ella como un **modelo de *event detection*** que convierte datos agregados (velas 1m, 5m, diarios) en hipótesis de oportunidad:

> “Aquí puede haber un pump, un flush, un ORB, un VWAP break…”

Y el **manifest** que generas para 3.2 (10.000 eventos) no es un punto final, sino **una muestra de entrenamiento**.
Te servirá para refinar la propia 2.5.

---

## 🔁 2️⃣ 3.2 alimenta de vuelta a 2.5

Cuando descargues los *trades+quotes* en 3.2, tendrás por primera vez **datos de verdad de ejecución y tape**, cosas que 2.5 no puede inferir:

* **Continuidad de ticks (fillability)**
* **Spread real / profundidad / aggressor flow**
* **Duración efectiva del evento (volatilidad real)**
* **Imbalance** entre agresores y pasivos
* **Reacciones post-evento (follow-through)**

Con eso, puedes **volver a entrenar 2.5** para que aprenda qué patrones *sí* tuvieron microestructura sana (real pump con liquidez) y cuáles fueron *falsos positivos* (movimiento sin contrapartida).

👉 En otras palabras: **3.2 te da las etiquetas de verdad** (“valid event”, “fake event”).
Así conviertes la 2.5 en un **modelo supervisado**, no sólo un detector de umbrales.

---

## 🧠 3️⃣ Qué mejoras podrás hacer en 2.5 gracias a 3.2

Cuando tengas las ventanas de ticks, podrás:

1. **Redefinir el “score” de evento:** incluir métricas reales de *impacto microestructural* (e.g., ratio aggressor/bid-volume, spread compression, continuation %).
2. **Ajustar los thresholds dinámicamente:** 2.5 hoy usa umbrales fijos (p.ej., +25% en 60 min, 3× volumen). Con feedback real puedes calibrarlos por *tipo* y *sesión*.
3. **Reducir falsos positivos:** verás qué condiciones generan eventos sin trades (vacíos).
4. **Etiquetar patrones raros:** halts, fake gaps, reanudaciones.
5. **Probar aprendizaje no supervisado** sobre los perfiles de 3.2 y retroalimentar clusters a 2.5.

Eso es exactamente lo que se hace en *datasets iterativos*:
FASE 2.5 produce candidatos → 3.2 observa microestructura → los resultados se reintegran → 2.5 v2 aprende con feedback real.

---

## 🚀 4️⃣ Qué pasa si paras 2.5 aquí

Si detienes 2.5 ahora:

* Tu **sistema de detección** quedará “congelado” en su versión inicial (basado en datos 1m).
* Cada nueva descarga de 3.2 tendría que hacerse con los mismos criterios, sin aprendizaje.
* No podrás priorizar mejor los próximos 10 000 eventos (p. ej., evitar los *quiet flushes* sin volumen).

En cambio, mantener 2.5 vivo significa que el *detector* evoluciona con evidencia, y tus próximas rondas de 3.2 serán más eficientes y ricas en señal.

---

## 🧭 5️⃣ En síntesis

| Fase                  | Propósito actual                           | Qué aporta al futuro                         |
| --------------------- | ------------------------------------------ | -------------------------------------------- |
| **2.5**               | Detecta y califica eventos en data 1m      | Aprende patrones y prioriza nuevas descargas |
| **3.2**               | Descarga microestructura para esos eventos | Provee etiquetas reales de calidad/liquidez  |
| **→ Ciclo siguiente** | Reentrenas 2.5 con feedback de 3.2         | Selección cada vez más inteligente           |

---

✅ **Por eso:**

* Lanza **3.2 CORE v1** ya — te da datos duros y valiosos.
* Mantén **2.5 activo** — irá evolucionando con esos datos para decidir mejor *qué vale la pena descargar después*.

Piensa en 2.5 como el “cerebro” que aprende, y 3.2 como los “ojos” que lo alimentan.
Si paras el cerebro, verás… pero no aprenderás.
