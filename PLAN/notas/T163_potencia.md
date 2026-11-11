# T163 — Puerta de potencia, antes del pre-registro y antes de cualquier cifra

Fijado el 2026-11-11, **antes de calcular ningún resultado**, en un commit propio y **anterior al
pre-registro**. Nada de lo que sigue se cambia después de mirar cifras; si un defecto del código
obliga a repetir, se declara en el informe.

T163 es una ◆: gasta un intento de la familia de trading de Holm (hoy 841). El usuario la abre el
2026-11-11 **con una condición**: primero el MinTRL. Si la historia disponible no alcanza para
detectar la ventaja mínima que la hipótesis se propone probar, la tarea **se cierra con ese
veredicto**, sin pre-registro, sin medir y **sin gastar el intento**. Es el procedimiento que
BACKLOG T161 (3) dejó obligatorio y el que cerró T166 el mismo día.

**Modo: SIMULADO (solo análisis).** No toca riesgo, ejecución, los perfiles del bróker simulado ni
la corrida de papel T31. Aunque la hipótesis llegara a pasar, **no se adopta antes del cierre de
T31 (2026-11-27)**: la adopción sería otra entrega.

## Hipótesis

Una **cartera continua de BTCUSDT perpetuo**, siempre posicionada, con la señal de tendencia lenta
promediada en tres lookbacks, **dimensionada por volatilidad objetivo** y rebalanceada
semanalmente, tiene un **Sharpe neto anualizado > 0** en el tramo de evaluación.

Es la forma en que la estudia la literatura y la que T139 **no** probó: T139 midió
`momento_1d@1d` como entradas con stop en R (n = 121, +0,048 R netos). Aquí no hay stop, no hay
entradas: hay una posición que siempre existe y cuyo tamaño cambia.

**Alcance: solo BTCUSDT.** La ficha `PLAN/T163.md` y la nota de T161 escriben «BTC + ETH»; el
alcance del proyecto está fijado en BTC y no se amplía por iniciativa propia. Esto **reduce** el
Sharpe esperado (una sola pata, sin diversificación transversal) y se tiene en cuenta abajo.

## Datos

- **Banco `v2/backups/t139_banco`**, BTCUSDT `binance-futures`: velas de 1 min del
  2019-09-08T17:57Z al 2026-11-06T03:36Z (3 766 179 filas, cobertura 99,70 %, 1 vela que el
  proveedor no devolvió) y **funding** de 7 842 puntos desde 2019-09-10T08:00Z
  (`backups/t139_banco/cobertura.md`). Copia estática: no se lee nada del almacén vivo, que el
  colector HFT está compactando.
- **Día UTC** válido si tiene ≥ 90 % de sus 1 440 velas de 1 min (misma regla que T162 y T166).
  Cierre del día = último cierre de 1 min del día; retorno diario = log del cociente de cierres.
- La historia de BTCUSDT perpetuo **empieza en 2019-09-08**: ese es el techo duro de esta tarea.
  No existe más historia del instrumento, y el contado antes de 2019 no tiene ni el funding ni el
  libro del perpetuo, así que no se sustituye.

## Especificación única (declarada aquí, no se ajusta nada)

Una sola, sin rejilla y sin elección posterior. Al cierre del día `d` (todo conocido a las 00:00
del día `d+1`):

1. **Señal:** `s_d = (1/3)·Σ_{L ∈ {20, 60, 120}} signo(ln(C_d / C_{d−L}))`, con `s_d ∈ {−1, −⅓,
   +⅓, +1}`. Los tres lookbacks son los que la nota de T161 propuso como ejemplo.
2. **Volatilidad:** `σ̂_d` = desviación de los 60 últimos retornos diarios, anualizada por √365,
   solo con días `≤ d`.
3. **Peso objetivo:** `w_d = recorte(s_d · σ_objetivo / σ̂_d, −3, +3)` con **σ_objetivo = 0,30
   anual** y tope de apalancamiento **3×**.
4. **Rebalanceo semanal:** cada lunes a las 00:00 UTC se lleva la posición a `w` del cierre del
   domingo. Entre lunes la **cantidad** en BTC se mantiene fija (la exposición deriva con el
   precio): es la forma de rotación baja de la literatura, no un reajuste diario.
5. **Costos (los de T25, `backtest/params.CostParams` por defecto, tarifa única de T143):**
   comisión **taker 5 pb** sobre el nocional negociado en cada rebalanceo más el deslizamiento de
   `backtest/perp.slippage_frac` evaluado en la **vela de 1 h de la hora de ejecución**, y
   **funding cada 8 h** del banco sobre el nocional mantenido, con el signo del motor de T25
   (`side·qty·precio·tasa`, + = pagado).

   > **Corrección del 2026-11-11, antes de ejecutar nada** (ninguna cifra calculada todavía; se
   > declara igual que T134 y T166 declararon las suyas): la primera versión de este punto escribió
   > «base 0,1 pb de entrada» entre paréntesis. Eso son los parámetros del bróker simulado
   > (`slip_entry_base_bps`), que `slippage_frac` **no** usa. Lo que se usa es `slippage_frac` con
   > los valores por defecto de `CostParams`, tal como los usa el motor de T25 tanto al entrar como
   > al salir: **1 pb de base + 0,10 × rango relativo de la vela de 1 h + impacto por tamaño**, con
   > tope de 100 pb. Es el modelo más caro de los dos y no se cambia después.
6. **Capital:** 10 000 USDT (`BacktestParams.initial_equity`), margen aislado como el motor de
   T25. Retorno diario de la cartera = variación relativa del capital **neta** de comisión,
   deslizamiento y funding.

## Métrica principal

**Sharpe neto anualizado** de los retornos diarios de la cartera, `media/desviación · √365`. Es
la métrica de la condición de aceptación de la ficha. Tasa libre de riesgo = 0 (el colateral del
perpetuo no la devenga en el bróker simulado).

## Tramos (fijados aquí)

| Tramo | Fechas | Para qué |
|---|---|---|
| Calentamiento | 2019-09-08 → 2020-01-05 | 120 días de lookback + 60 de σ; no se puntúa |
| **Potencia** | **2020-01-06 → 2020-12-31** | estimar **solo** dispersión, asimetría, curtosis y dependencia serie de los retornos diarios, **antes** de evaluar |
| **Evaluación** | **2021-01-01 → último día completo del banco** | el único tramo que decide |
| Subtramo | 2024-01-01 → último día completo | se informa **por separado** (es el tramo que la nota de T161 escribió en la hipótesis) |

Del tramo de potencia **no se calcula ni se informa la media ni el Sharpe**: solo los momentos de
segundo orden en adelante y el bloque del bootstrap. Queda fuera del tramo de evaluación.

## Ventaja mínima que esta hipótesis se propone probar

`S_min = **0,70** de Sharpe neto anualizado`, declarada aquí por tres razones, todas anteriores a
cualquier cifra propia:

1. El **único** número fuera de muestra publicado para esta forma de estrategia es **1,41 neto de
   25 pb** en *majors* ([SSRN 7115459](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7115459)),
   y sus autores **admiten sesgo de supervivencia y que no superan un umbral de pruebas
   múltiples**. El recorte habitual por sesgo de publicación y pruebas múltiples es de **la mitad**
   del Sharpe informado (Harvey y Liu, *Backtesting*, JPM 2015): 1,41 / 2 ≈ 0,70.
2. Las cifras publicadas (1,41 en *majors*; 2,41 con señales de 6 h sobre más de 150 pares,
   [arXiv 2602.11708](https://arxiv.org/abs/2602.11708)) son de **carteras multiactivo**. Esta es
   **una sola pata**: sin diversificación transversal el Sharpe esperado es menor todavía, no
   mayor.
3. Un tercer trabajo sostiene que es **una ventaja envejecida**, con el bruto dependiente de un
   único dato atípico ([SSRN 7405060](https://papers.ssrn.com/sol3/Delivery.cfm/7405060.pdf?abstractid=7405060&mirid=1)).

Fijar `S_min` en el 1,41 publicado sería diseñar una prueba con potencia **solo** para el mejor
caso posible: exactamente lo que T161 prohibió. El informe publicará además la curva completa
«Sharpe detectable ↔ años de historia», que es aritmética a priori y no depende de ningún
resultado, para que se vea qué habría pasado con otros `S_min`.

## Puerta de potencia (se aplica tal cual)

Con `n_eval` = días válidos del tramo de evaluación y `S_d = S_min/√365` el Sharpe **por día**:

- **MinTRL** (Bailey y López de Prado 2012, `validation/power.min_track_record`): observaciones
  para rechazar «Sharpe ≤ 0» con confianza 1 − α, α = 0,05, con la asimetría y la curtosis del
  tramo de potencia.
- **n a priori** (`validation/power.n_needed`, α = 0,05 unilateral, potencia 0,80):
  `n = ((z_0,05 + z_0,20)/S_d)² = (2,4865/S_d)²`.
- **Inflación por dependencia serie** `κ`: los retornos de una cartera que mantiene el signo
  semanas no son independientes, y `power.py` los supone independientes. `κ = max(1, 1 +
  2·Σ_{k=1..B} (1 − k/(B+1))·ρ̂_k)` (Newey-West con ventana `B`), con `B` el bloque medio de
  Politis-White (`validation/spa.block_length`) estimado en el **tramo de potencia**. `κ` es una
  adición declarada sobre `power.py`, no una corrección posterior.

> **La hipótesis se abre solo si `n_eval ≥ κ · n_apriori(S_min)`**, es decir si el tramo de
> evaluación tiene potencia 0,80 para detectar `S_min = 0,70`. Se informa también el MinTRL
> (significación sin potencia) y la misma cuenta para el subtramo 2024–2026.

Si la puerta **falla**: se cierra T163 con el veredicto SIN POTENCIA, **no se escribe el
pre-registro**, **no se calcula ningún Sharpe del tramo de evaluación**, **no se gasta el intento
de Holm** (la familia sigue en 841) y el informe lo dice así, con la cuenta delante. Forzar un
resultado sin potencia es lo que T161 dejó prohibido y lo que T166 acató el mismo día.

Si la puerta **pasa**: se escribe `PLAN/notas/T163_preregistro.md` en un commit propio, anterior a
cualquier cifra del tramo de evaluación, con familia declarada, métrica, benchmarks (comprar y
mantener; la misma cartera sin volatilidad objetivo), MCS y p ajustada por Holm en la familia, y
solo entonces se mide.

## Lo que esta tarea no hace

- No amplía a ETH ni a ningún otro símbolo (alcance BTC).
- No toca riesgo, ejecución, los perfiles del bróker simulado ni la corrida de papel T31.
- No prueba momentum transversal (T164, bloqueada por T93) ni rejillas de lookbacks: una sola
  especificación.
- No instala dependencias nuevas: numpy, duckdb y el extra `stats` (`arch`), ya en uso desde T161.
