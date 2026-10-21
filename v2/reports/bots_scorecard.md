# Escuadrón de bots — puntuación y puerta de edge (T59)

Modo: **SIMULADO** · símbolo BTCUSDT · corte (asof) 2026-10-20 18:15 UTC · criterios `validation_v1` (sha 0a5b19962ded) · intentos en la familia de Holm: 24 (cada versión de cada bot, también las retiradas, más un control aleatorio por cada una).

## Respuesta corta

- **Votan**: ninguno
- **Solo informan**: hummingbot-directional:macd_bb_v1@1h@v1, nostalgia-for-infinity:NostalgiaForInfinityX7@5m@v1, trendrider-strategy:TrendRiderStrategy@1h@v1
- **Publicables** (VALIDADOS por T49): ninguno
- **Modulan la confianza**: ninguno
- Estados: {'vota': 0, 'informa': 3, 'rechazado': 8, 'deshabilitado_seguridad': 0}

> Parámetros de terceros fijados por SHA: EIM no los ajustó con ningún dato, así que no hay ventanas de ajuste; toda la historia posterior al alta del bot es fuera de muestra.

## Concepto por bot (cuatro dimensiones, sin nota global)

| Bot@estrategia@marco@versión | Estado | Rendimiento | Evidencia | Seguridad | Operativa | R medio | n OOS | p Holm | Control (R medio) | Peso inicial |
|---|---|---|---|---|---|---|---|---|---|---|
| freqtrade-strategies:FSupertrendStrategy@1h@v2 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.401 | 38 | +1.0000 | -0.339 | 0.0 |
| hummingbot-directional:bollinger_v1@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.326 | 81 | +1.0000 | -0.463 | 0.0 |
| hummingbot-directional:macd_bb_v1@1h@v1 | **informa** | no cumple | no cumple | cumple | cumple | -1.101 | 5 | +1.0000 | -1.073 | 0.0 |
| jesse-example-strategies:Donchian@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.367 | 38 | +1.0000 | -0.295 | 0.0 |
| jesse-example-strategies:MACD_EMA@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.190 | 64 | +1.0000 | -0.420 | 0.0 |
| jesse-example-strategies:RSI2@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.223 | 149 | +1.0000 | -0.319 | 0.0 |
| jesse-example-strategies:SMACrossover@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.502 | 24 | +1.0000 | -0.251 | 0.0 |
| jesse-example-strategies:TradingView_RSI@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.437 | 110 | +1.0000 | -0.231 | 0.0 |
| jesse-example-strategies:TurtleRules@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.204 | 174 | +0.5494 | -0.445 | 0.0 |
| nostalgia-for-infinity:NostalgiaForInfinityX7@5m@v1 | **informa** | no cumple | no cumple | cumple | cumple | -2.130 | 1 | +1.0000 | -2.132 | 0.0 |
| trendrider-strategy:TrendRiderStrategy@1h@v1 | **informa** | no cumple | no cumple | cumple | cumple | -0.821 | 12 | +1.0000 | -0.445 | 0.0 |

### freqtrade-strategies:FSupertrendStrategy@1h@v2

- puerta T49: RECHAZADA — claramente negativa: R medio -0.401 + 1·EE 0.171 < 0 → ciclo de mejora
- aporte marginal: no aporta: ΔSharpe -0.07, ΔE[R] -0.024, ΔIC24 0.011, gana 0% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.401 + 1·EE 0.171 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 38 operaciones fuera de muestra; regímenes: sin dato 38
  - V2 Expectativa neta ✘: R medio -0.401, IC [-0.721, -0.064]
  - V3 Contra el azar ✘: p bruto 0.5713 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 14.3%
  - V5 Estabilidad ✘: 1/5 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.278 R
- Comparación homogénea: buy&hold del mismo tramo +0.063 · control aleatorio R medio -0.339 · retorno con 1 % de riesgo -0.143.
- Aporte marginal: no aporta: ΔSharpe -0.07, ΔE[R] -0.024, ΔIC24 0.011, gana 0% de ventanas · deltas {'sharpe': -0.07316126307693338, 'expectancy_r': -0.024257754198858228, 'ic24': 0.011019835704267705} · moderador {'h': 24, 'n_agree': 23, 'n_disagree': 1, 'hit_agree': 0.43478260869565216, 'hit_disagree': 0.0, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### hummingbot-directional:bollinger_v1@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.326 + 1·EE 0.126 < 0 → ciclo de mejora
- aporte marginal: no aporta: ΔSharpe -3.23, ΔE[R] -0.238, ΔIC24 0.0085, gana 0% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.326 + 1·EE 0.126 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 81 operaciones fuera de muestra; regímenes: sin dato 81
  - V2 Expectativa neta ✘: R medio -0.326, IC [-0.560, -0.063]
  - V3 Contra el azar ✘: p bruto 0.6379 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✘: DD máximo 25.3%
  - V5 Estabilidad ✘: 1/6 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.234 R
- Comparación homogénea: buy&hold del mismo tramo +0.060 · control aleatorio R medio -0.463 · retorno con 1 % de riesgo -0.236.
- Aporte marginal: no aporta: ΔSharpe -3.23, ΔE[R] -0.238, ΔIC24 0.0085, gana 0% de ventanas · deltas {'sharpe': -3.2322546807617085, 'expectancy_r': -0.23809419920020575, 'ic24': 0.008507621410847238} · moderador {'h': 24, 'n_agree': 0, 'n_disagree': 6, 'hit_agree': None, 'hit_disagree': 0.3333333333333333, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### hummingbot-directional:macd_bb_v1@1h@v1

- puerta T49: EN OBSERVACIÓN — V1: 5 operaciones fuera de muestra; regímenes: sin dato 5
- aporte marginal: no aporta: ΔSharpe +0.00, ΔE[R] +0.000, ΔIC24 0.0, gana 0% de ventanas
- Puerta: **EN OBSERVACIÓN** — V1: 5 operaciones fuera de muestra; regímenes: sin dato 5
  - V1 Suficiencia de datos ✘: 5 operaciones fuera de muestra; regímenes: sin dato 5
  - V2 Expectativa neta ✘: R medio -1.101, IC [-1.411, -0.578]
  - V3 Contra el azar ✘: p bruto 0.9792 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 5.4%
  - V5 Estabilidad …: 0/0 ventanas positivas (pendiente: < 4 ventanas); en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✘: costo medio 0.356 R
- Comparación homogénea: buy&hold del mismo tramo +0.254 · control aleatorio R medio -1.073 · retorno con 1 % de riesgo -0.054.
- Aporte marginal: no aporta: ΔSharpe +0.00, ΔE[R] +0.000, ΔIC24 0.0, gana 0% de ventanas · deltas {'sharpe': 0.0, 'expectancy_r': 0.0, 'ic24': 0.0} · moderador {'h': 24, 'n_agree': 0, 'n_disagree': 0, 'hit_agree': None, 'hit_disagree': None, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### jesse-example-strategies:Donchian@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.367 + 1·EE 0.182 < 0 → ciclo de mejora
- aporte marginal: no aporta: ΔSharpe -0.63, ΔE[R] -0.078, ΔIC24 0.0092, gana 0% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.367 + 1·EE 0.182 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 38 operaciones fuera de muestra; regímenes: sin dato 38
  - V2 Expectativa neta ✘: R medio -0.367, IC [-0.701, -0.016]
  - V3 Contra el azar ✘: p bruto 0.4568 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 13.4%
  - V5 Estabilidad ✘: 1/5 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.293 R
- Comparación homogénea: buy&hold del mismo tramo +0.081 · control aleatorio R medio -0.295 · retorno con 1 % de riesgo -0.132.
- Aporte marginal: no aporta: ΔSharpe -0.63, ΔE[R] -0.078, ΔIC24 0.0092, gana 0% de ventanas · deltas {'sharpe': -0.6279232032036495, 'expectancy_r': -0.0781743845054465, 'ic24': 0.009170352788866132} · moderador {'h': 24, 'n_agree': 30, 'n_disagree': 5, 'hit_agree': 0.43333333333333335, 'hit_disagree': 0.6, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### jesse-example-strategies:MACD_EMA@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.190 + 1·EE 0.135 < 0 → ciclo de mejora
- aporte marginal: no aporta: ΔSharpe -0.23, ΔE[R] -0.028, ΔIC24 0.005, gana 0% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.190 + 1·EE 0.135 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 64 operaciones fuera de muestra; regímenes: sin dato 64
  - V2 Expectativa neta ✘: R medio -0.190, IC [-0.436, +0.072]
  - V3 Contra el azar ✘: p bruto 0.1259 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 16.9%
  - V5 Estabilidad ✘: 2/6 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.258 R
- Comparación homogénea: buy&hold del mismo tramo +0.097 · control aleatorio R medio -0.420 · retorno con 1 % de riesgo -0.118.
- Aporte marginal: no aporta: ΔSharpe -0.23, ΔE[R] -0.028, ΔIC24 0.005, gana 0% de ventanas · deltas {'sharpe': -0.2286636798310151, 'expectancy_r': -0.02846270419579977, 'ic24': 0.005024428586840962} · moderador {'h': 24, 'n_agree': 42, 'n_disagree': 6, 'hit_agree': 0.38095238095238093, 'hit_disagree': 0.16666666666666666, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### jesse-example-strategies:RSI2@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.223 + 1·EE 0.093 < 0 → ciclo de mejora
- aporte marginal: no aporta: ΔSharpe +0.00, ΔE[R] -0.001, ΔIC24 0.0109, gana 100% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.223 + 1·EE 0.093 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 149 operaciones fuera de muestra; regímenes: sin dato 149
  - V2 Expectativa neta ✘: R medio -0.223, IC [-0.408, -0.028]
  - V3 Contra el azar ✘: p bruto 0.2040 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✘: DD máximo 29.2%
  - V5 Estabilidad ✘: 1/7 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.254 R
- Comparación homogénea: buy&hold del mismo tramo +0.101 · control aleatorio R medio -0.319 · retorno con 1 % de riesgo -0.290.
- Aporte marginal: no aporta: ΔSharpe +0.00, ΔE[R] -0.001, ΔIC24 0.0109, gana 100% de ventanas · deltas {'sharpe': 0.003885939433482033, 'expectancy_r': -0.0013155372639394591, 'ic24': 0.010865712127984234} · moderador {'h': 24, 'n_agree': 6, 'n_disagree': 16, 'hit_agree': 0.3333333333333333, 'hit_disagree': 0.375, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### jesse-example-strategies:SMACrossover@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.503 + 1·EE 0.237 < 0 → ciclo de mejora
- aporte marginal: no aporta: ΔSharpe -0.01, ΔE[R] -0.012, ΔIC24 0.0095, gana 0% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.503 + 1·EE 0.237 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 24 operaciones fuera de muestra; regímenes: sin dato 24
  - V2 Expectativa neta ✘: R medio -0.503, IC [-0.922, -0.035]
  - V3 Contra el azar ✘: p bruto 0.8803 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 11.5%
  - V5 Estabilidad …: 0/1 ventanas positivas (pendiente: < 4 ventanas); en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.250 R
- Comparación homogénea: buy&hold del mismo tramo +0.091 · control aleatorio R medio -0.251 · retorno con 1 % de riesgo -0.115.
- Aporte marginal: no aporta: ΔSharpe -0.01, ΔE[R] -0.012, ΔIC24 0.0095, gana 0% de ventanas · deltas {'sharpe': -0.011650707425313378, 'expectancy_r': -0.012227041553819429, 'ic24': 0.009478599941433047} · moderador {'h': 24, 'n_agree': 51, 'n_disagree': 41, 'hit_agree': 0.37254901960784315, 'hit_disagree': 0.3902439024390244, 'diff': -0.017694882831181258, 'ci95': [-0.2138809182209469, 0.1774390243902439], 'modulates': False}

### jesse-example-strategies:TradingView_RSI@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.437 + 1·EE 0.108 < 0 → ciclo de mejora
- aporte marginal: no aporta: ΔSharpe -0.38, ΔE[R] -0.030, ΔIC24 0.0588, gana 0% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.437 + 1·EE 0.108 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 110 operaciones fuera de muestra; regímenes: sin dato 110
  - V2 Expectativa neta ✘: R medio -0.437, IC [-0.645, -0.221]
  - V3 Contra el azar ✘: p bruto 0.9636 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✘: DD máximo 39.1%
  - V5 Estabilidad ✘: 0/6 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.252 R
- Comparación homogénea: buy&hold del mismo tramo +0.078 · control aleatorio R medio -0.231 · retorno con 1 % de riesgo -0.387.
- Aporte marginal: no aporta: ΔSharpe -0.38, ΔE[R] -0.030, ΔIC24 0.0588, gana 0% de ventanas · deltas {'sharpe': -0.3801432978330457, 'expectancy_r': -0.030169599208188125, 'ic24': 0.058782731994513227} · moderador {'h': 24, 'n_agree': 23, 'n_disagree': 34, 'hit_agree': 0.5217391304347826, 'hit_disagree': 0.29411764705882354, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### jesse-example-strategies:TurtleRules@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.204 + 1·EE 0.086 < 0 → ciclo de mejora
- aporte marginal: no medible: solo 1 ventana(s) de prueba (< 2); regla T44 sola: ΔSharpe +0.45, ΔE[R] +0.038, ΔIC24 0.0083, gana 100% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.204 + 1·EE 0.086 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 174 operaciones fuera de muestra; regímenes: sin dato 174
  - V2 Expectativa neta ✘: R medio -0.204, IC [-0.366, -0.038]
  - V3 Contra el azar ✘: p bruto 0.0229 → Holm 0.5494 (960 réplicas de lado al azar)
  - V4 Drawdown ✘: DD máximo 31.5%
  - V5 Estabilidad ✘: 0/6 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.266 R
- Comparación homogénea: buy&hold del mismo tramo +0.095 · control aleatorio R medio -0.445 · retorno con 1 % de riesgo -0.307.
- Aporte marginal: no medible: solo 1 ventana(s) de prueba (< 2); regla T44 sola: ΔSharpe +0.45, ΔE[R] +0.038, ΔIC24 0.0083, gana 100% de ventanas · deltas {'sharpe': 0.44804124820290037, 'expectancy_r': 0.037529340727117666, 'ic24': 0.00833808547693543} · moderador {'h': 24, 'n_agree': 56, 'n_disagree': 7, 'hit_agree': 0.39285714285714285, 'hit_disagree': 0.5714285714285714, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### nostalgia-for-infinity:NostalgiaForInfinityX7@5m@v1

- puerta T49: EN OBSERVACIÓN — V1: 1 operaciones fuera de muestra; regímenes: sin dato 1
- aporte marginal: no aporta: ΔSharpe +0.00, ΔE[R] +0.000, ΔIC24 0.0076, gana 0% de ventanas
- Puerta: **EN OBSERVACIÓN** — V1: 1 operaciones fuera de muestra; regímenes: sin dato 1
  - V1 Suficiencia de datos ✘: 1 operaciones fuera de muestra; regímenes: sin dato 1
  - V2 Expectativa neta …: muestra insuficiente
  - V3 Contra el azar ✘: p bruto 0.5068 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 2.1%
  - V5 Estabilidad …: 0/0 ventanas positivas (pendiente: < 4 ventanas); en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✘: costo medio 1.130 R
- Comparación homogénea: buy&hold del mismo tramo — · control aleatorio R medio -2.132 · retorno con 1 % de riesgo -0.021.
- Aporte marginal: no aporta: ΔSharpe +0.00, ΔE[R] +0.000, ΔIC24 0.0076, gana 0% de ventanas · deltas {'sharpe': 0.0, 'expectancy_r': 0.0, 'ic24': 0.007644529383659809} · moderador {'h': 24, 'n_agree': 0, 'n_disagree': 1, 'hit_agree': None, 'hit_disagree': 0.0, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### trendrider-strategy:TrendRiderStrategy@1h@v1

- puerta T49: EN OBSERVACIÓN — V1: 12 operaciones fuera de muestra; regímenes: sin dato 12
- aporte marginal: no medible: solo 1 ventana(s) de prueba (< 2); regla T44 sola: ΔSharpe +0.21, ΔE[R] +0.015, ΔIC24 0.0257, gana 100% de ventanas
- Puerta: **EN OBSERVACIÓN** — V1: 12 operaciones fuera de muestra; regímenes: sin dato 12
  - V1 Suficiencia de datos ✘: 12 operaciones fuera de muestra; regímenes: sin dato 12
  - V2 Expectativa neta ✘: R medio -0.821, IC [-1.314, -0.212]
  - V3 Contra el azar ✘: p bruto 0.7045 → Holm 1.0000 (960 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 9.5%
  - V5 Estabilidad …: 0/0 ventanas positivas (pendiente: < 4 ventanas); en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✘: costo medio 0.316 R
- Comparación homogénea: buy&hold del mismo tramo +0.130 · control aleatorio R medio -0.445 · retorno con 1 % de riesgo -0.095.
- Aporte marginal: no medible: solo 1 ventana(s) de prueba (< 2); regla T44 sola: ΔSharpe +0.21, ΔE[R] +0.015, ΔIC24 0.0257, gana 100% de ventanas · deltas {'sharpe': 0.21034378286026234, 'expectancy_r': 0.015284593421448722, 'ic24': 0.02567698780882513} · moderador {'h': 24, 'n_agree': 44, 'n_disagree': 35, 'hit_agree': 0.45454545454545453, 'hit_disagree': 0.3142857142857143, 'diff': 0.14025974025974025, 'ci95': [-0.08766233766233766, 0.3457305194805192], 'modulates': False}

## Condiciones por régimen (solo informe)

ningún bot supera la puerta dentro de un régimen: no se activa selección por régimen (BACKLOG). Celdas bot×régimen evaluadas: 3.

| Bot | Régimen | n OOS | Evaluada | Supera | R medio | p Holm |
|---|---|---|---|---|---|---|
| freqtrade-strategies:FSupertrendStrategy@1h@v1 | sin dato | 48 | False | False | — | — |
| freqtrade-strategies:FSupertrendStrategy@1h@v2 | sin dato | 38 | False | False | — | — |
| hummingbot-directional:bollinger_v1@1h@v1 | sin dato | 81 | False | False | — | — |
| hummingbot-directional:macd_bb_v1@1h@v1 | sin dato | 5 | False | False | — | — |
| jesse-example-strategies:Donchian@1h@v1 | sin dato | 38 | False | False | — | — |
| jesse-example-strategies:MACD_EMA@1h@v1 | sin dato | 64 | False | False | — | — |
| jesse-example-strategies:RSI2@1h@v1 | sin dato | 149 | True | False | -0.223 | +0.3473 |
| jesse-example-strategies:SMACrossover@1h@v1 | sin dato | 24 | False | False | — | — |
| jesse-example-strategies:TradingView_RSI@1h@v1 | sin dato | 110 | True | False | -0.437 | +0.9721 |
| jesse-example-strategies:TurtleRules@1h@v1 | sin dato | 174 | True | False | -0.204 | +0.0479 |
| nostalgia-for-infinity:NostalgiaForInfinityX7@5m@v1 | sin dato | 1 | False | False | — | — |
| trendrider-strategy:TrendRiderStrategy@1h@v1 | sin dato | 12 | False | False | — | — |

## Clase L (simulación aparte; no vota ni pasa por la puerta direccional)

- passivbot:ema_anchor@1m (772abadc10a5): 50 fills · PnL de inventario +197.68 · costos pagados +14.65 · DD máx +0.005 · riesgo de inventario {'max_wallet_exposure': 0.31616703189584394, 'max_position': 0.054} — fuera de la puerta direccional; sin deslizamiento modelado; no vota
- passivbot:trailing_martingale@1m (772abadc10a5): 868 fills · PnL de inventario -1762.59 · costos pagados +77.41 · DD máx +0.685 · riesgo de inventario {'max_wallet_exposure': 4.444189611109403, 'max_position': 0.593} — fuera de la puerta direccional; sin deslizamiento modelado; no vota

## Todos los intentos (Holm)

| Intento | Veredicto | n OOS | p bruto | p Holm | Retirado | Control |
|---|---|---|---|---|---|---|
| freqtrade-strategies:FSupertrendStrategy@1h@v1 | RECHAZADA | 48 | +0.1051 | +1.0000 | True | False |
| freqtrade-strategies:FSupertrendStrategy@1h#control@v1 | RECHAZADA | 48 | +0.1207 | +1.0000 | True | True |
| freqtrade-strategies:FSupertrendStrategy@1h@v2 | RECHAZADA | 38 | +0.5713 | +1.0000 | False | False |
| freqtrade-strategies:FSupertrendStrategy@1h#control@v2 | RECHAZADA | 38 | +0.4100 | +1.0000 | False | True |
| hummingbot-directional:bollinger_v1@1h@v1 | RECHAZADA | 81 | +0.6379 | +1.0000 | False | False |
| hummingbot-directional:bollinger_v1@1h#control@v1 | RECHAZADA | 82 | +0.9448 | +1.0000 | False | True |
| hummingbot-directional:macd_bb_v1@1h@v1 | EN OBSERVACIÓN | 5 | +0.9792 | +1.0000 | False | False |
| hummingbot-directional:macd_bb_v1@1h#control@v1 | EN OBSERVACIÓN | 5 | +0.9438 | +1.0000 | False | True |
| jesse-example-strategies:Donchian@1h@v1 | RECHAZADA | 38 | +0.4568 | +1.0000 | False | False |
| jesse-example-strategies:Donchian@1h#control@v1 | RECHAZADA | 38 | +0.3091 | +1.0000 | False | True |
| jesse-example-strategies:MACD_EMA@1h@v1 | RECHAZADA | 64 | +0.1259 | +1.0000 | False | False |
| jesse-example-strategies:MACD_EMA@1h#control@v1 | RECHAZADA | 63 | +0.7503 | +1.0000 | False | True |
| jesse-example-strategies:RSI2@1h@v1 | RECHAZADA | 149 | +0.2040 | +1.0000 | False | False |
| jesse-example-strategies:RSI2@1h#control@v1 | RECHAZADA | 148 | +0.5827 | +1.0000 | False | True |
| jesse-example-strategies:SMACrossover@1h@v1 | RECHAZADA | 24 | +0.8803 | +1.0000 | False | False |
| jesse-example-strategies:SMACrossover@1h#control@v1 | EN OBSERVACIÓN | 24 | +0.5203 | +1.0000 | False | True |
| jesse-example-strategies:TradingView_RSI@1h@v1 | RECHAZADA | 110 | +0.9636 | +1.0000 | False | False |
| jesse-example-strategies:TradingView_RSI@1h#control@v1 | RECHAZADA | 109 | +0.4724 | +1.0000 | False | True |
| jesse-example-strategies:TurtleRules@1h@v1 | RECHAZADA | 174 | +0.0229 | +0.5494 | False | False |
| jesse-example-strategies:TurtleRules@1h#control@v1 | RECHAZADA | 169 | +0.8460 | +1.0000 | False | True |
| nostalgia-for-infinity:NostalgiaForInfinityX7@5m@v1 | EN OBSERVACIÓN | 1 | +0.5068 | +1.0000 | False | False |
| nostalgia-for-infinity:NostalgiaForInfinityX7@5m#control@v1 | EN OBSERVACIÓN | 1 | +1.0000 | +1.0000 | False | True |
| trendrider-strategy:TrendRiderStrategy@1h@v1 | EN OBSERVACIÓN | 12 | +0.7045 | +1.0000 | False | False |
| trendrider-strategy:TrendRiderStrategy@1h#control@v1 | EN OBSERVACIÓN | 12 | +0.1821 | +1.0000 | False | True |
