Perfecto — te explico con precisión dónde estáis, qué está haciendo el sistema ahora mismo, por qué se escogieron esos datos y hacia dónde apunta todo el proceso 👇

---

## 🧩 Dónde estamos en el timeline

### 🔹 FASE 2.5 → **Detección Intradía**

* Está corriendo (o recién ha terminado) la **detección de eventos intradía** sobre las barras de **1 minuto** descargadas previamente desde **Polygon.io**.
* Esas barras 1m son históricas, no en streaming. Cubren unos **dos años** por ~2.000 small caps.
* El resultado de esa fase es un gran fichero:
  `processed/events/events_intraday_YYYYMMDD.parquet`
  con ~370.000 eventos detectados (volume_spike, vwap_break, etc.).

👉 En términos conceptuales, esta fase **no descarga más datos**; solo analiza los 1m ya bajados y **marca los momentos importantes** dentro de cada día/símbolo.

---

### 🔹 FASE 3.2 → **Descarga Micro (Trades + Quotes)**

* Es la **fase siguiente**, que estás preparando ahora mismo.
* No usa toda la data, sino un subconjunto de los eventos detectados en 2.5 (los mejores ~10 000 según calidad, liquidez, diversidad, etc.).
  Esa selección se llama **CORE manifest**.
* A partir del manifest, el sistema irá a Polygon y descargará, para cada evento, una **ventana de microestructura**:

  ```
  [-3, +7] minutos alrededor del timestamp del evento
  ```

  obteniendo:

  * Trades (todas las ejecuciones reales)
  * Quotes (NBBO filtrado 5 Hz by-change-only)

**Objetivo:** disponer de datos “tick-by-tick” alrededor de los momentos más informativos, para análisis de order-flow, spread, desequilibrio, tape speed, etc.

---

## 🧮 Por qué se escogieron estos datos

1. **Base temporal:**
   Polygon ofrece barras 1m históricas para miles de small caps → es la granularidad mínima que puedes cubrir a escala multianual sin petabytes.

2. **Micro-descarga selectiva:**
   Descargar ticks de todos los días sería inviable (≈ 2.6 TB).
   Por eso se detectan eventos 1m y solo se bajan los **segmentos relevantes** (ventanas de 10 min) para unos pocos miles de ellos.

3. **Small Caps:**
   Porque ahí se producen patrones de *pump & dump*, *gap & flush* y microestructuras explotables que son difíciles de modelar en large caps.

4. **Fuente Polygon.io:**
   Es adecuada para prototipado: ofrece trades, quotes (NBBO), aggregates y corporativos, con API REST consistente.
   En tiempo real también puede emitir streaming WebSocket, así que en el futuro podrás conectar tu pipeline científico a datos en vivo sin cambiar la estructura.

---

## 🔭 Hacia dónde va el proceso

### 1️⃣ Corto plazo — terminar FASE 2.5

* Esperar que acabe la detección intradía completa (todos los símbolos).
* Validar cuántos eventos y qué tipos predominan.

### 2️⃣ Inmediato — construir el **CORE manifest**

* Aplicar filtros de calidad, liquidez y diversidad.
* Dejar el archivo `manifest_core_YYYYMMDD.parquet` como lista maestra de eventos para descarga micro.

### 3️⃣ Próximo — ejecutar FASE 3.2 (descarga micro)

* Descargar trades + quotes para los eventos del manifest.
* Validar cobertura y tamaños (~30 GB estimados).

### 4️⃣ Medio plazo — análisis y modelos

* Calcular features microestructurales (spread, imbalance, tape speed…).
* Etiquetar con *triple barrier* o secuencias futuras.
* Entrenar modelos IA para predicción / screening de patrones.

### 5️⃣ Largo plazo — streaming en tiempo real

* Conectar la arquitectura a Polygon WebSocket (u otro feed) para replicar la detección y el scoring **en vivo**.
* La IA monitorizará tick-by-tick y lanzará alertas o ejecutará estrategias.

---

## 🚦 Posibles fallos críticos antes de continuar

| Categoría                  | Riesgo                                                                                              | Solución                                                                    |
| -------------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| **Proceso Windows**        | Si la detección 2.5 se ejecuta en background (&) puede cerrarse sola (~60 s).                       | Ejecutar **en primer plano con tee** o dentro de **WSL/Linux**.             |
| **Memoria**                | `detect_events_intraday.py` acumula todo en `all_events` antes de guardar → puede agotar RAM.       | Procesar **por batches** (guardar cada 100 símbolos).                       |
| **Integridad de datos 1m** | Algunos símbolos no tienen datos 1m completos → “No bars file”.                                     | Confirmar `symbols_with_1m.parquet` actualizado y limitar a los válidos.    |
| **Manifest sin dry-run**   | Si generas el manifest sin calibrar filtros (score/liquidez) puedes acabar con 0 o 100 000 eventos. | Ejecutar **`generate_core_manifest_dryrun.py`** primero y ajustar umbrales. |
| **Espacio disco**          | Si descargas trades+quotes para todo el universo → >2 TB.                                           | Empezar con **perfil CORE** (10 K eventos, ~30 GB).                         |

---

## 🧭 En resumen

| Etapa        | Qué hace                                                           | Estado           |
| ------------ | ------------------------------------------------------------------ | ---------------- |
| **FASE 1**   | Descarga barras diarias, horarias y 1 m desde Polygon              | ✅ completada     |
| **FASE 2**   | Detección de eventos diarios                                       | ✅ completada     |
| **FASE 2.5** | Detección de eventos intradía sobre barras 1 m                     | ⚙️ en curso      |
| **FASE 3.1** | Análisis y dry-run del manifest CORE                               | ✅ en preparación |
| **FASE 3.2** | Descarga trades + quotes tick-by-tick de los eventos seleccionados | ⏳ siguiente paso |
| **FASE 4**   | Feature engineering, labeling, modelado IA                         | 🔜 futura fase   |

---

✅ **Conclusión:**
Estás justo en la **transición entre 2.5 y 3.2** — detectando los eventos intradía dentro de los datos 1 min descargados, y preparando el manifest para decidir **qué eventos merecen bajarse a nivel micro**.

No hay fallos críticos que impidan continuar, siempre que:

* ejecutes la detección 2.5 en primer plano o en WSL, y
* generes el manifest CORE con el dry-run validado antes de lanzar descargas micro.
