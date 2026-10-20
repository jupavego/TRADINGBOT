# Escuadrón de bots — puntuación y puerta de edge (T59)

Modo: **SIMULADO** · símbolo BTCUSDT · corte (asof) 2026-10-19 16:00 UTC · criterios `validation_v1` (sha 0a5b19962ded) · intentos en la familia de Holm: 6 (cada versión de cada bot, también las retiradas, más un control aleatorio por cada una).

## Respuesta corta

- **Votan**: ninguno
- **Solo informan**: hummingbot-directional:macd_bb_v1@1h@v1
- **Publicables** (VALIDADOS por T49): ninguno
- **Modulan la confianza**: ninguno
- Estados: {'vota': 0, 'informa': 1, 'rechazado': 2, 'deshabilitado_seguridad': 0}

> Parámetros de terceros fijados por SHA: EIM no los ajustó con ningún dato, así que no hay ventanas de ajuste; toda la historia posterior al alta del bot es fuera de muestra.

## Concepto por bot (cuatro dimensiones, sin nota global)

| Bot@estrategia@marco@versión | Estado | Rendimiento | Evidencia | Seguridad | Operativa | R medio | n OOS | p Holm | Control (R medio) | Peso inicial |
|---|---|---|---|---|---|---|---|---|---|---|
| freqtrade-strategies:FSupertrendStrategy@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.192 | 48 | +0.6587 | -0.198 | 0.0 |
| hummingbot-directional:bollinger_v1@1h@v1 | **rechazado** | no cumple | no cumple | cumple | cumple | -0.325 | 81 | +1.0000 | -0.451 | 0.0 |
| hummingbot-directional:macd_bb_v1@1h@v1 | **informa** | no cumple | no cumple | cumple | cumple | -1.101 | 5 | +1.0000 | -1.073 | 0.0 |

### freqtrade-strategies:FSupertrendStrategy@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.192 + 1·EE 0.165 < 0 → ciclo de mejora
- aporte marginal: no medible: solo 1 ventana(s) de prueba (< 2); regla T44 sola: ΔSharpe +0.21, ΔE[R] +0.022, ΔIC24 0.0162, gana 100% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.192 + 1·EE 0.165 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 48 operaciones fuera de muestra; regímenes: range 46, volatile 2
  - V2 Expectativa neta ✘: R medio -0.192, IC [-0.507, +0.125]
  - V3 Contra el azar ✘: p bruto 0.1158 → Holm 0.6587 (500 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 11.7%
  - V5 Estabilidad ✘: 2/6 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.283 R
- Comparación homogénea: buy&hold del mismo tramo +0.084 · control aleatorio R medio -0.198 · retorno con 1 % de riesgo -0.091.
- Aporte marginal: no medible: solo 1 ventana(s) de prueba (< 2); regla T44 sola: ΔSharpe +0.21, ΔE[R] +0.022, ΔIC24 0.0162, gana 100% de ventanas · deltas {'sharpe': 0.21321054578642062, 'expectancy_r': 0.021695282685959605, 'ic24': 0.01622869883739449} · moderador {'h': 24, 'n_agree': 35, 'n_disagree': 5, 'hit_agree': 0.5714285714285714, 'hit_disagree': 0.4, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### hummingbot-directional:bollinger_v1@1h@v1

- puerta T49: RECHAZADA — claramente negativa: R medio -0.325 + 1·EE 0.126 < 0 → ciclo de mejora
- aporte marginal: no aporta: ΔSharpe -2.81, ΔE[R] -0.188, ΔIC24 -0.0035, gana 0% de ventanas
- Puerta: **RECHAZADA** — claramente negativa: R medio -0.325 + 1·EE 0.126 < 0 → ciclo de mejora
  - V1 Suficiencia de datos ✘: 81 operaciones fuera de muestra; regímenes: range 73, volatile 6, trend_up 1, trend_down 1
  - V2 Expectativa neta ✘: R medio -0.325, IC [-0.559, -0.063]
  - V3 Contra el azar ✘: p bruto 0.6228 → Holm 1.0000 (500 réplicas de lado al azar)
  - V4 Drawdown ✘: DD máximo 25.3%
  - V5 Estabilidad ✘: 1/6 ventanas positivas; en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✔: costo medio 0.233 R
- Comparación homogénea: buy&hold del mismo tramo +0.060 · control aleatorio R medio -0.451 · retorno con 1 % de riesgo -0.236.
- Aporte marginal: no aporta: ΔSharpe -2.81, ΔE[R] -0.188, ΔIC24 -0.0035, gana 0% de ventanas · deltas {'sharpe': -2.8063617042725646, 'expectancy_r': -0.1875067594180077, 'ic24': -0.003535594839942667} · moderador {'h': 24, 'n_agree': 0, 'n_disagree': 18, 'hit_agree': None, 'hit_disagree': 0.5, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

### hummingbot-directional:macd_bb_v1@1h@v1

- puerta T49: EN OBSERVACIÓN — V1: 5 operaciones fuera de muestra; regímenes: range 4, volatile 1
- aporte marginal: no aporta: ΔSharpe +0.00, ΔE[R] +0.000, ΔIC24 -0.005, gana 0% de ventanas
- Puerta: **EN OBSERVACIÓN** — V1: 5 operaciones fuera de muestra; regímenes: range 4, volatile 1
  - V1 Suficiencia de datos ✘: 5 operaciones fuera de muestra; regímenes: range 4, volatile 1
  - V2 Expectativa neta ✘: R medio -1.101, IC [-1.411, -0.578]
  - V3 Contra el azar ✘: p bruto 0.9880 → Holm 1.0000 (500 réplicas de lado al azar)
  - V4 Drawdown ✔: DD máximo 5.4%
  - V5 Estabilidad …: 0/0 ventanas positivas (pendiente: < 4 ventanas); en vivo 0 op. (pendiente: < 20)
  - V6 Costos ✘: costo medio 0.356 R
- Comparación homogénea: buy&hold del mismo tramo +0.254 · control aleatorio R medio -1.073 · retorno con 1 % de riesgo -0.054.
- Aporte marginal: no aporta: ΔSharpe +0.00, ΔE[R] +0.000, ΔIC24 -0.005, gana 0% de ventanas · deltas {'sharpe': 0.0, 'expectancy_r': 0.0, 'ic24': -0.0050167224080267525} · moderador {'h': 24, 'n_agree': 0, 'n_disagree': 1, 'hit_agree': None, 'hit_disagree': 1.0, 'diff': None, 'ci95': None, 'modulates': False, 'note': 'muestra insuficiente (< 30 por grupo)'}

## Condiciones por régimen (solo informe)

ningún bot supera la puerta dentro de un régimen: no se activa selección por régimen (BACKLOG). Celdas bot×régimen evaluadas: 0.

| Bot | Régimen | n OOS | Evaluada | Supera | R medio | p Holm |
|---|---|---|---|---|---|---|
| freqtrade-strategies:FSupertrendStrategy@1h@v1 | range | 46 | False | False | — | — |
| freqtrade-strategies:FSupertrendStrategy@1h@v1 | volatile | 2 | False | False | — | — |
| hummingbot-directional:bollinger_v1@1h@v1 | range | 73 | False | False | — | — |
| hummingbot-directional:bollinger_v1@1h@v1 | trend_down | 1 | False | False | — | — |
| hummingbot-directional:bollinger_v1@1h@v1 | trend_up | 1 | False | False | — | — |
| hummingbot-directional:bollinger_v1@1h@v1 | volatile | 6 | False | False | — | — |
| hummingbot-directional:macd_bb_v1@1h@v1 | range | 4 | False | False | — | — |
| hummingbot-directional:macd_bb_v1@1h@v1 | volatile | 1 | False | False | — | — |

## Clase L (simulación aparte; no vota ni pasa por la puerta direccional)

- passivbot:ema_anchor@1m (772abadc10a5): 50 fills · PnL de inventario +197.68 · costos pagados +14.65 · DD máx +0.005 · riesgo de inventario {'max_wallet_exposure': 0.31616703189584394, 'max_position': 0.054} — fuera de la puerta direccional; sin deslizamiento modelado; no vota
- passivbot:trailing_martingale@1m (772abadc10a5): 868 fills · PnL de inventario -1762.59 · costos pagados +77.41 · DD máx +0.685 · riesgo de inventario {'max_wallet_exposure': 4.444189611109403, 'max_position': 0.593} — fuera de la puerta direccional; sin deslizamiento modelado; no vota

## Todos los intentos (Holm)

| Intento | Veredicto | n OOS | p bruto | p Holm | Retirado | Control |
|---|---|---|---|---|---|---|
| freqtrade-strategies:FSupertrendStrategy@1h@v1 | RECHAZADA | 48 | +0.1158 | +0.6587 | False | False |
| freqtrade-strategies:FSupertrendStrategy@1h#control@v1 | RECHAZADA | 48 | +0.1098 | +0.6587 | False | True |
| hummingbot-directional:bollinger_v1@1h@v1 | RECHAZADA | 81 | +0.6228 | +1.0000 | False | False |
| hummingbot-directional:bollinger_v1@1h#control@v1 | RECHAZADA | 81 | +0.9521 | +1.0000 | False | True |
| hummingbot-directional:macd_bb_v1@1h@v1 | EN OBSERVACIÓN | 5 | +0.9880 | +1.0000 | False | False |
| hummingbot-directional:macd_bb_v1@1h#control@v1 | EN OBSERVACIÓN | 5 | +0.9541 | +1.0000 | False | True |
