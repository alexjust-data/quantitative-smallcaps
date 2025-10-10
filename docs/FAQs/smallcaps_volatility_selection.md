

## 🧩 Por qué seleccionamos small caps por volatilidad

### 🎯 1. Qué estamos buscando

El objetivo de tu proyecto es modelar y detectar **eventos explosivos de corto plazo** — los “pum/dump” o “short squeezes” — que caracterizan a las *small caps* especulativas.
Por tanto, la información más valiosa no es la media del comportamiento, sino **los episodios extremos de expansión de rango y volumen**.

---

### ⚙️ 2. Tipos de small caps que existen

Podemos distinguir tres tipos de small caps en tu universo inicial (~1 300):

| Tipo de small cap             | Comportamiento típico                                                              | Valor para el modelo                                             |
| ----------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| **A. Volátiles persistentes** | Alta variabilidad diaria constante (biotech, clean-tech, meme stocks)              | Núcleo del entrenamiento (ejemplos claros de “ignition”)         |
| **B. Volatilidad episódica**  | Normalmente inactiva, pero con “erucciones” de 1-3 semanas tras noticias u ofertas | **Muy valiosa**: enseña al modelo *cuándo* se enciende una llama |
| **C. Estables o muertas**     | Sin volumen ni rango significativos durante meses                                  | Ruido — se usan solo para *negativos* (ejemplos sin evento)      |

---

### 📈 3. Qué significa “seleccionar por volatilidad”

No se trata de excluir las B (episódicas).
Seleccionar *por volatilidad* significa **ponderar la priorización de descarga y entrenamiento**, no excluir:

* En **Week 2-3 (1-min)** descargamos solo *Top 500 volátiles* porque son las que justifican el peso intradía (orden flow, microestructura).
  Las *quietas* no aportan señal intradía y encarecen la base.

* Pero en **Week 1 (1d + 1h)** descargamos **todas las small caps** (volátiles o no), porque incluso las tranquilas sirven como *negativo estructural* y para medir *base rates* (frecuencia de eventos).

👉 **Resumen práctico:**

* Daily/hourly → **todas** (para contexto, volatilidad episodica y base rates)
* Minute → **solo las más volátiles** (para detalles del evento)

---

### 🧠 4. Por qué las B (volátiles a ratos) son cruciales

Las empresas que “despiertan” puntualmente enseñan al modelo:

* Cómo cambian volumen, spread, y volatilidad *antes* del estallido.
* Cuánto dura el “modo encendido”.
* Cuándo se apaga la tendencia.

Por eso **sí entran en el entrenamiento**, aunque no estén siempre activas.
De hecho, muchas features (RVOL, z-score de rango, gap %) capturan precisamente esa transición de *modo dormido → modo explosivo*.

---

### 🧩 5. Cómo formalizamos la selección

1. **Week 1**: universo completo filtrado por *precio 0.5–20 USD* y *market cap < 2 B*.
2. **Rank volatilidad (para 1-min)**:

   * `ATR%` = mean((high – low)/close) × 100
   * `Gap%` = |open – prev_close| / prev_close
   * `RVOL` = volumen / sma(volumen, 20)
   * Ranking combinado → top N.
3. **Actualización mensual del ranking**, para capturar nuevas “dormidas → despiertas”.

Así, ninguna small cap queda excluida del análisis global; simplemente priorizamos el nivel de detalle descargado.

---

