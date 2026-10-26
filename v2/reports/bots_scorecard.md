# Escuadrón de bots — puntuación y puerta de edge (T59)

Modo: **SIMULADO** · símbolo BTCUSDT · corte (asof) 2026-10-25 22:30 UTC · criterios `validation_v1` (sha 0a5b19962ded) · intentos en la familia de Holm: 18 (cada versión de cada bot, también las retiradas, más un control aleatorio por cada una).

Medido en la máquina `laptop-i6pf9ovp-fce8d9` sobre la base `C:\Users\user\AppData\Local\Temp\claude\C--Users-user-Desktop-SANTIVEGO-17-0---TRADING-Trading-Bot-TRADINGBOT\8e54b3dc-9915-43b2-842d-9c3fdcd77d5a\scratchpad\real\data`: solo vale para la API que lea esa misma base.

## Respuesta corta

- **Votan**: ninguno
- **Solo informan**: hummingbot-directional:macd_bb_v1@1h@v1, jesse-example-strategies:MACD_EMA@1h@v1, trendrider-strategy:TrendRiderStrategy@1h@v1
- **Publicables** (VALIDADOS por T49): ninguno
- **Modulan la confianza**: ninguno
- Estados: {'vota': 0, 'informa': 3, 'rechazado': 6, 'deshabilitado_seguridad': 0}

> Parámetros de terceros fijados por SHA: EIM no los ajustó con ningún dato, así que no hay ventanas de ajuste; toda la historia posterior al alta del bot es fuera de muestra.

## Marcos leídos

| Marco | Posturas | Desde | Hasta | Velas del camino | Velas hasta | Fija el corte |
|---|---|---|---|---|---|---|
| 1h | 41031 | 2026-04-19 00:00 | 2026-10-25 22:00 | 15m | 2026-10-25 22:30 | sí |

## Concepto por bot (cuatro dimensiones, sin nota global)

| Bot@estrategia@marco@versión | Estado | Rendimiento | Evidencia | Seguridad | Operativa | R medio | n OOS | p Holm | Control (R medio) | Peso inicial |
|---|---|---|---|---|---|---|---|---|---|---|
| hummingbot-directional:bollinger_v1@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.214 | 86 | +1.0000 | -0.386 | 0.0 |
| hummingbot-directional:macd_bb_v1@1h@v1 | **informa** | no cumple | no cumple | cumple | cumple | -1.059 | 5 | +1.0000 | -1.028 | 0.0 |
| jesse-example-strategies:Donchian@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.331 | 38 | +1.0000 | -0.152 | 0.0 |
| jesse-example-strategies:MACD_EMA@1h@v1 | **informa** | no cumple | no cumple | cumple | cumple | -0.097 | 64 | +1.0000 | -0.322 | 0.0 |
| jesse-example-strategies:RSI2@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.174 | 154 | +1.0000 | -0.284 | 0.0 |
| jesse-example-strategies:SMACrossover@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.363 | 26 | +1.0000 | -0.212 | 0.0 |
| jesse-example-strategies:TradingView_RSI@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.363 | 112 | +1.0000 | -0.124 | 0.0 |
| jesse-example-strategies:TurtleRules@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.108 | 179 | +0.3994 | -0.361 | 0.0 |
| trendrider-strategy:TrendRiderStrategy@1h@v1 | **informa** | no cumple | no cumple | cumple | cumple | -0.523 | 12 | +1.0000 | -0.097 | 0.0 |

### hummingbot-directional:bollinger_v1@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.214 + 1·EE 0.128 < 0 → ciclo de mejora
- aporte marginal: sin medir (sin panel de agentes en el periodo)
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.214 + 1·EE 0.128 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 86 operaciones fuera de muestra; regímenes: range 73, volatile 10, trend_down 2, trend_up 1
  - V2 Expectativa neta ✘: R medio -0.214, IC [-0.455, +0.047]
  - V3 Contra el azar ✘: p bruto 0.5853 → Holm 1.0000 (720 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 23.3%
  - V5 Estabilidad ✘: 2/6 ventanas positivas; en vivo 1 op., R medio +1.878 (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.193 R
- Comparación homogénea: buy&hold del mismo tramo +0.042 · control aleatorio R medio -0.386 · retorno con 1 % de riesgo -0.173.

### hummingbot-directional:macd_bb_v1@1h@v1

- puerta T49: EN OBSERVACIÓN — V1: 5 operaciones fuera de muestra; regímenes: range 4, volatile 1
- aporte marginal: sin medir (sin panel de agentes en el periodo)
- Puerta: **EN OBSERVACIÓN** — V1: 5 operaciones fuera de muestra; regímenes: range 4, volatile 1
  - V1 Suficiencia de datos ✘: 5 operaciones fuera de muestra; regímenes: range 4, volatile 1
  - V2 Expectativa neta ✘: R medio -1.059, IC [-1.381, -0.541]
  - V3 Contra el azar ✘: p bruto 0.9834 → Holm 1.0000 (720 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 5.2%
  - V5 Estabilidad …: 0/0 ventanas positivas (pendiente: < 4 ventanas); en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✘: costo medio 0.315 R
- Comparación homogénea: buy&hold del mismo tramo +0.254 · control aleatorio R medio -1.028 · retorno con 1 % de riesgo -0.052.

### jesse-example-strategies:Donchian@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.331 + 1·EE 0.182 < 0 → ciclo de mejora
- aporte marginal: sin medir (sin panel de agentes en el periodo)
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.331 + 1·EE 0.182 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 38 operaciones fuera de muestra; regímenes: range 36, volatile 2
  - V2 Expectativa neta ✘: R medio -0.331, IC [-0.666, +0.029]
  - V3 Contra el azar ✘: p bruto 0.5520 → Holm 1.0000 (720 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 12.3%
  - V5 Estabilidad ✘: 1/5 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.247 R
- Comparación homogénea: buy&hold del mismo tramo +0.081 · control aleatorio R medio -0.152 · retorno con 1 % de riesgo -0.120.

### jesse-example-strategies:MACD_EMA@1h@v1

- puerta T49: EN OBSERVACIÓN — V1: 64 operaciones fuera de muestra; regímenes: range 64
- aporte marginal: sin medir (sin panel de agentes en el periodo)
- Puerta: **EN OBSERVACIÓN** — V1: 64 operaciones fuera de muestra; regímenes: range 64
  - V1 Suficiencia de datos ✘: 64 operaciones fuera de muestra; regímenes: range 64
  - V2 Expectativa neta ✘: R medio -0.097, IC [-0.356, +0.177]
  - V3 Contra el azar ✘: p bruto 0.1262 → Holm 1.0000 (720 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 14.8%
  - V5 Estabilidad ✘: 2/6 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.210 R
- Comparación homogénea: buy&hold del mismo tramo +0.097 · control aleatorio R medio -0.322 · retorno con 1 % de riesgo -0.064.

### jesse-example-strategies:RSI2@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.174 + 1·EE 0.091 < 0 → ciclo de mejora
- aporte marginal: sin medir (sin panel de agentes en el periodo)
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.174 + 1·EE 0.091 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 154 operaciones fuera de muestra; regímenes: range 144, volatile 9, trend_down 1
  - V2 Expectativa neta ✘: R medio -0.174, IC [-0.350, -0.000]
  - V3 Contra el azar ✘: p bruto 0.1775 → Holm 1.0000 (720 réplicas de lado al azar)
  - V4 Drawdown ✘: DD máximo 25.4%
  - V5 Estabilidad ✘: 1/7 ventanas positivas; en vivo 2 op., R medio +0.114 (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.223 R
- Comparación homogénea: buy&hold del mismo tramo +0.066 · control aleatorio R medio -0.284 · retorno con 1 % de riesgo -0.243.

### jesse-example-strategies:SMACrossover@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.363 + 1·EE 0.226 < 0 → ciclo de mejora
- aporte marginal: sin medir (sin panel de agentes en el periodo)
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.363 + 1·EE 0.226 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 26 operaciones fuera de muestra; regímenes: range 25, volatile 1
  - V2 Expectativa neta ✘: R medio -0.363, IC [-0.780, +0.105]
  - V3 Contra el azar ✘: p bruto 0.7781 → Holm 1.0000 (720 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 11.1%
  - V5 Estabilidad …: 0/1 ventanas positivas (pendiente: < 4 ventanas); en vivo 1 op., R medio +1.908 (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.216 R
- Comparación homogénea: buy&hold del mismo tramo +0.047 · control aleatorio R medio -0.212 · retorno con 1 % de riesgo -0.092.

### jesse-example-strategies:TradingView_RSI@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.363 + 1·EE 0.111 < 0 → ciclo de mejora
- aporte marginal: sin medir (sin panel de agentes en el periodo)
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.363 + 1·EE 0.111 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 112 operaciones fuera de muestra; regímenes: range 102, volatile 8, trend_down 2
  - V2 Expectativa neta ✘: R medio -0.363, IC [-0.577, -0.140]
  - V3 Contra el azar ✘: p bruto 0.9626 → Holm 1.0000 (720 réplicas de lado al azar)
  - V4 Drawdown ✘: DD máximo 34.5%
  - V5 Estabilidad ✘: 0/6 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.209 R
- Comparación homogénea: buy&hold del mismo tramo +0.074 · control aleatorio R medio -0.124 · retorno con 1 % de riesgo -0.339.

### jesse-example-strategies:TurtleRules@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.108 + 1·EE 0.087 < 0 → ciclo de mejora
- aporte marginal: sin medir (sin panel de agentes en el periodo)
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.108 + 1·EE 0.087 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 179 operaciones fuera de muestra; regímenes: range 168, volatile 10, trend_down 1
  - V2 Expectativa neta ✘: R medio -0.108, IC [-0.273, +0.057]
  - V3 Contra el azar ✘: p bruto 0.0222 → Holm 0.3994 (720 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 21.9%
  - V5 Estabilidad ✘: 1/7 ventanas positivas; en vivo 2 op., R medio +0.322 (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.224 R
- Comparación homogénea: buy&hold del mismo tramo +0.058 · control aleatorio R medio -0.361 · retorno con 1 % de riesgo -0.185.

### trendrider-strategy:TrendRiderStrategy@1h@v1

- puerta T49: EN OBSERVACIÓN — V1: 12 operaciones fuera de muestra; regímenes: range 11, volatile 1
- aporte marginal: sin medir (sin panel de agentes en el periodo)
- Puerta: **EN OBSERVACIÓN** — V1: 12 operaciones fuera de muestra; regímenes: range 11, volatile 1
  - V1 Suficiencia de datos ✘: 12 operaciones fuera de muestra; regímenes: range 11, volatile 1
  - V2 Expectativa neta ✘: R medio -0.523, IC [-1.073, +0.120]
  - V3 Contra el azar ✘: p bruto 0.6588 → Holm 1.0000 (720 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 6.2%
  - V5 Estabilidad …: 0/0 ventanas positivas (pendiente: < 4 ventanas); en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.261 R
- Comparación homogénea: buy&hold del mismo tramo +0.130 · control aleatorio R medio -0.097 · retorno con 1 % de riesgo -0.062.

## Condiciones por régimen (solo informe)

ningún bot supera la puerta dentro de un régimen: no se activa selección por régimen (BACKLOG). Celdas bot×régimen evaluadas: 3.

| Bot | Régimen | n OOS | Evaluada | Supera | R medio | p Holm |
|---|---|---|---|---|---|---|
| hummingbot-directional:bollinger_v1@1h@v1 | range | 73 | False | False | — | — |
| hummingbot-directional:bollinger_v1@1h@v1 | trend_down | 2 | False | False | — | — |
| hummingbot-directional:bollinger_v1@1h@v1 | trend_up | 1 | False | False | — | — |
| hummingbot-directional:bollinger_v1@1h@v1 | volatile | 10 | False | False | — | — |
| hummingbot-directional:macd_bb_v1@1h@v1 | range | 4 | False | False | — | — |
| hummingbot-directional:macd_bb_v1@1h@v1 | volatile | 1 | False | False | — | — |
| jesse-example-strategies:Donchian@1h@v1 | range | 36 | False | False | — | — |
| jesse-example-strategies:Donchian@1h@v1 | volatile | 2 | False | False | — | — |
| jesse-example-strategies:MACD_EMA@1h@v1 | range | 64 | False | False | — | — |
| jesse-example-strategies:RSI2@1h@v1 | range | 144 | True | False | -0.169 | +0.3353 |
| jesse-example-strategies:RSI2@1h@v1 | trend_down | 1 | False | False | — | — |
| jesse-example-strategies:RSI2@1h@v1 | volatile | 9 | False | False | — | — |
| jesse-example-strategies:SMACrossover@1h@v1 | range | 25 | False | False | — | — |
| jesse-example-strategies:SMACrossover@1h@v1 | volatile | 1 | False | False | — | — |
| jesse-example-strategies:TradingView_RSI@1h@v1 | range | 102 | True | False | -0.316 | +0.9062 |
| jesse-example-strategies:TradingView_RSI@1h@v1 | trend_down | 2 | False | False | — | — |
| jesse-example-strategies:TradingView_RSI@1h@v1 | volatile | 8 | False | False | — | — |
| jesse-example-strategies:TurtleRules@1h@v1 | range | 168 | True | False | -0.107 | +0.0719 |
| jesse-example-strategies:TurtleRules@1h@v1 | trend_down | 1 | False | False | — | — |
| jesse-example-strategies:TurtleRules@1h@v1 | volatile | 10 | False | False | — | — |
| trendrider-strategy:TrendRiderStrategy@1h@v1 | range | 11 | False | False | — | — |
| trendrider-strategy:TrendRiderStrategy@1h@v1 | volatile | 1 | False | False | — | — |

## Clase L (simulación aparte; no vota ni pasa por la puerta direccional)

Sin corridas guardadas.

## Todos los intentos (Holm)

| Intento | Veredicto | n OOS | p bruto | p Holm | Retirado | Control |
|---|---|---|---|---|---|---|
| hummingbot-directional:bollinger_v1@1h@v1 | RECHAZADA | 86 | +0.5853 | +1.0000 | False | False |
| hummingbot-directional:bollinger_v1@1h#control@v1 | RECHAZADA | 86 | +0.9501 | +1.0000 | False | True |
| hummingbot-directional:macd_bb_v1@1h@v1 | EN OBSERVACIÓN | 5 | +0.9834 | +1.0000 | False | False |
| hummingbot-directional:macd_bb_v1@1h#control@v1 | EN OBSERVACIÓN | 5 | +0.9445 | +1.0000 | False | True |
| jesse-example-strategies:Donchian@1h@v1 | RECHAZADA | 38 | +0.5520 | +1.0000 | False | False |
| jesse-example-strategies:Donchian@1h#control@v1 | EN OBSERVACIÓN | 38 | +0.1872 | +1.0000 | False | True |
| jesse-example-strategies:MACD_EMA@1h@v1 | EN OBSERVACIÓN | 64 | +0.1262 | +1.0000 | False | False |
| jesse-example-strategies:MACD_EMA@1h#control@v1 | RECHAZADA | 63 | +0.7046 | +1.0000 | False | True |
| jesse-example-strategies:RSI2@1h@v1 | RECHAZADA | 154 | +0.1775 | +1.0000 | False | False |
| jesse-example-strategies:RSI2@1h#control@v1 | RECHAZADA | 154 | +0.6560 | +1.0000 | False | True |
| jesse-example-strategies:SMACrossover@1h@v1 | RECHAZADA | 26 | +0.7781 | +1.0000 | False | False |
| jesse-example-strategies:SMACrossover@1h#control@v1 | EN OBSERVACIÓN | 26 | +0.5478 | +1.0000 | False | True |
| jesse-example-strategies:TradingView_RSI@1h@v1 | RECHAZADA | 112 | +0.9626 | +1.0000 | False | False |
| jesse-example-strategies:TradingView_RSI@1h#control@v1 | RECHAZADA | 110 | +0.3564 | +1.0000 | False | True |
| jesse-example-strategies:TurtleRules@1h@v1 | RECHAZADA | 179 | +0.0222 | +0.3994 | False | False |
| jesse-example-strategies:TurtleRules@1h#control@v1 | RECHAZADA | 177 | +0.8447 | +1.0000 | False | True |
| trendrider-strategy:TrendRiderStrategy@1h@v1 | EN OBSERVACIÓN | 12 | +0.6588 | +1.0000 | False | False |
| trendrider-strategy:TrendRiderStrategy@1h#control@v1 | EN OBSERVACIÓN | 12 | +0.1331 | +1.0000 | False | True |
