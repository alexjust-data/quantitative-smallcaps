El **límite en 0,50 $** no es dogma; es un **corte práctico** que suele mejorar la calidad del dataset y la ejecutabilidad. Por qué suele ponerse ahí:

1. **Riesgo de delisting y reverse splits**

* Por debajo de **1 $** las listadas (NASDAQ/NYSE) entran en incumplimiento; muchas pasan **meses** sub-1 $ y luego hacen **reverse splits**.
* Sub-0,50 $ la probabilidad de reverse/dilución se dispara → tu histórico queda lleno de **saltos artificiales** y cambios de símbolo/ratio que complican features y labels.

2. **Micro-ticks y “ruido de libro”**

* Sub-1 $ el **tick mínimo** puede ser **$0.0001**: el NBBO “parpadea” y el libro se **hiperfragmenta**.
* Eso hincha los quotes, genera spreads raros, y muchos *prints* de tamaño ínfimo → **features de microestructura** se vuelven más ruidosas y menos transferibles.

3. **Costes efectivos y slippage**

* En precio ultrabajo el **spread en bps** y el **impacto** son enormes aunque el spread absoluto sea pequeño.
* Con comisiones/fees y fills parciales, el **edge neto** se evapora; tu label “éxito” se contamina por costes.

4. **Liquidez y calidad de data**

* Más **gaps de datos**, **halt/ resume** frecuentes y prints anómalos.
* Peor **borrow/SSR** para cortos; operativa real menos replicable al backtest.

5. **Menos relevancia para tu edge**

* Tu idea (momentum/ignition en small caps listadas) funciona mejor en **0,50–20 $** con **dólar-volumen decente** y cobertura de datos estable.

---

## ¿Bajarlo de 0,50 $? Posible, pero con reglas

Si quieres incluir sub-0,50 $, hazlo **condicional** a calidad de mercado, no solo a precio. Por ejemplo:

* **Liquidez mínima**:

  * *median dollar volume* ≥ **$300k** (o $500k) / día
  * *trades/day* ≥ **1000**
* **Coste razonable**:

  * *median effective spread* ≤ **60–80 bps**
  * *% time spread > 1%* ≤ **20%**
* **Calidad de datos**:

  * *% barras vacías* ≤ **5%** en sesión regular
  * *dupes* (symbol,timestamp) = 0
* **Estabilidad**:

  * *days_since_reverse_split* ≥ **30** días

En YAML (idea):

```yaml
universe:
  price_min: 0.50           # default
  allow_below_min: true
  min_price_floor: 0.10     # límite duro
  sub_min_overrides:
    min_dollar_volume: 300000
    min_trades_per_day: 1000
    max_median_effective_spread_bps: 80
    max_empty_bar_ratio: 0.05
    min_days_since_reverse_split: 30
```

Implementación: si `price < 0.50` y `price ≥ 0.10`, **incluye** solo si pasa todos los filtros de override.

---

## Reglas alternativas (más data-driven)

* En vez de un precio fijo, usa **cuantiles por “coste de transacción”** (p. ej., excluye el 20 % con *effective spread* y *impact* más altos).
* O define el universo por **dólar-volumen y spread**, y luego capea por precio solo para evitar los ultra-penny.

---

## Conclusión

* **0,50 $** es un **corte sanitario** para empezar con datos más limpios y un backtest más creíble.
* Si tu *edge* vive en los “ultra-pennies”, inclúyelos, pero **bajo filtros estrictos de liquidez/coste/calidad**.
* Mi recomendación: arranca con **≥ 0,50 $**, valida el pipeline y el modelo; luego activa el **override** para casos que cumplan las métricas anteriores.
