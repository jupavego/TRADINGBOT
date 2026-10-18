# Contribución marginal de los agentes nuevos en la síntesis (T44)

Generado 2026-10-17 02:41 UTC con `python -m eim.analytics.agents_marginal_report`. Análisis histórico: **no es una promesa de resultados**.

## Decisión

| Agente | ¿Aporta fuera de muestra? | Peso inicial vigente | Motivo por activo |
|---|---|---|---|
| `technical` | **no** | 0 | BTCUSDT: ΔSharpe -0.00, ΔE[R] +0.000, ΔIC24 0.0004, gana 29% de ventanas; ETHUSDT: ΔSharpe +0.12, ΔE[R] +0.011, ΔIC24 0.0011, gana 57% de ventanas |
| `smart_money` | **no** | 0 | BTCUSDT: sin datos en todo el histórico (100 % `no_data`): no medible; ETHUSDT: sin datos en todo el histórico (100 % `no_data`): no medible |

Regla fijada antes de mirar la prueba: aporta ⇔ en la mitad de prueba de CADA activo, con el agente a peso moderado: Sharpe agregado, expectativa por operación (R) e IC a 24 velas mejoran a la vez frente a la síntesis sin él, y el Sharpe mejora en ≥ 60 % de las ventanas de 90 días.

### Lectura

- BTCUSDT: la síntesis base pierde en la prueba (Sharpe -2.39, E[R] -0.261): no hay ventaja que mejorar (T27). `technical` a peso moderado: ΔSharpe -0.00 (p 0.499); a peso 1 sin penalización: ΔSharpe -0.07 — mismo signo. `technical` sale degradado en el 99.8% del panel (histórico sin `taker_buy_v`).
- ETHUSDT: la síntesis base pierde en la prueba (Sharpe -1.05, E[R] -0.099): no hay ventaja que mejorar (T27). `technical` a peso moderado: ΔSharpe +0.12 (p 0.026); a peso 1 sin penalización: ΔSharpe -0.41 — el signo cambia con el peso: no es robusto. `technical` sale degradado en el 99.8% del panel (histórico sin `taker_buy_v`).

## Método

- Panel: reportes reales de todos los agentes (salvo `plan`, `context`, `arbitrage`) cada 4 velas de 1 h, con snapshots idénticos a `build_snapshot` (recorte en memoria; probado) — `eim/analytics/agent_panel.py`.
- Partición: primera 50% = descubrimiento (correlaciones y umbral), resto = prueba (todo lo que decide).
- Variantes: síntesis base (pesos de `technical` y `smart_money` = 0) frente a la síntesis con el agente a peso moderado 0.5 y penalización por correlación (peso × (1 − ρ⁺ máx. con `ema`/`structure` cuando votan)); sensibilidad con peso 1 sin penalización.
- Backtest T25 (`walk_forward`, costos de perpetuo, ventanas disjuntas de 2160 velas = 90 días, capital nuevo por ventana): señal = signo de sesgo × confianza de la síntesis si |s| ≥ cuantil 80% de esa variante en descubrimiento; SL 1.5 ATR, TP 2 R, salida por tiempo 48 velas, riesgo 1% por operación.
- IC: Spearman de s contra el log-retorno a 4, 24 velas (muestras sin solape); diferencia con la base por bootstrap pareado (IC 95 %).

## BTCUSDT

8186 instantes de 2023-01-21 a 2026-10-17; prueba desde 2024-12-04.

### Cobertura del panel (fracción de instantes)

| Agente | ok | degradado | sin datos |
|---|---|---|---|
| calendar | 0% | 0% | 100% |
| derivatives | 0% | 0% | 100% |
| elliott | 100% | 0% | 0% |
| ema | 100% | 0% | 0% |
| levels | 100% | 0% | 0% |
| liquidations | 0% | 0% | 100% |
| microstructure | 0% | 0% | 100% |
| price_action | 100% | 0% | 0% |
| regime | 100% | 0% | 0% |
| seasonality | 0% | 0% | 100% |
| smart_money | 0% | 0% | 100% |
| structure | 100% | 0% | 0% |
| technical | 0% | 100% | 0% |
| vwap | 68% | 32% | 0% |

### Correlación entre reportes (sesgo; velas con datos en ambos)

Descubrimiento (fija la penalización):

| Nuevo | Existente | n | Pearson | Spearman |
|---|---|---|---|---|
| technical | ema | 4093 | +0.68 | +0.67 |
| technical | structure | 4093 | +0.58 | +0.55 |
| technical | vwap | 4090 | +0.40 | +0.41 |
| technical | price_action | 4093 | +0.55 | +0.52 |
| technical | levels | 4093 | +0.46 | +0.44 |
| smart_money | ema | 0 | — | — |
| smart_money | structure | 0 | — | — |
| smart_money | vwap | 0 | — | — |
| smart_money | price_action | 0 | — | — |
| smart_money | levels | 0 | — | — |

Prueba (control de estabilidad):

| Nuevo | Existente | n | Pearson | Spearman |
|---|---|---|---|---|
| technical | ema | 4093 | +0.69 | +0.67 |
| technical | structure | 4093 | +0.57 | +0.51 |
| smart_money | ema | 0 | — | — |
| smart_money | structure | 0 | — | — |

### Resultados en la mitad de prueba

| Variante | Ops | Retorno | Sharpe [IC95] | E[R] | Acierto | Caída máx. | IC 4 v | IC 24 v | ΔIC 24 v [IC95] | Δ Sharpe p | Gana ventanas |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 326 | -58.8 % | -2.39 [-4.03, -0.86] | -0.261 | 34% | 61.3% | -0.0543 | -0.0208 | — | — | — |
| +technical | 326 | -58.7 % | -2.39 [-4.03, -0.83] | -0.260 | 34% | 61.3% | -0.0546 | -0.0204 | +0.0004 [-0.002, +0.003] | 0.499 | 29% |
| +technical (peso 1, sin penalización) | 332 | -60.1 % | -2.46 [-4.11, -0.96] | -0.265 | 34% | 62.6% | -0.0544 | -0.0210 | -0.0003 [-0.004, +0.004] | 0.570 | 57% |
| +smart_money | 326 | -58.8 % | -2.39 [-4.03, -0.86] | -0.261 | 34% | 61.3% | -0.0543 | -0.0208 | +0.0000 [+0.000, +0.000] | 1.000 | 0% |
| +smart_money (peso 1, sin penalización) | 326 | -58.8 % | -2.39 [-4.03, -0.86] | -0.261 | 34% | 61.3% | -0.0543 | -0.0208 | +0.0000 [+0.000, +0.000] | 1.000 | 0% |
| +ambos | 326 | -58.7 % | -2.39 [-4.03, -0.83] | -0.260 | 34% | 61.3% | -0.0546 | -0.0204 | +0.0004 [-0.002, +0.003] | 0.499 | 29% |

Sharpe por ventana de 90 días (base → con el agente):

- `technical`: 2024-12-04 -3.76→-3.76, 2025-03-04 -2.31→-2.29, 2025-06-02 -3.00→-3.00, 2025-08-31 -2.31→-2.31, 2025-11-29 -2.74→-3.15, 2026-02-27 -0.63→-0.09, 2026-05-28 -1.83→-2.06
- `smart_money`: 2024-12-04 -3.76→-3.76, 2025-03-04 -2.31→-2.31, 2025-06-02 -3.00→-3.00, 2025-08-31 -2.31→-2.31, 2025-11-29 -2.74→-2.74, 2026-02-27 -0.63→-0.63, 2026-05-28 -1.83→-1.83

## ETHUSDT

8185 instantes de 2023-01-21 a 2026-10-16; prueba desde 2024-12-03.

### Cobertura del panel (fracción de instantes)

| Agente | ok | degradado | sin datos |
|---|---|---|---|
| calendar | 0% | 0% | 100% |
| derivatives | 0% | 0% | 100% |
| elliott | 100% | 0% | 0% |
| ema | 100% | 0% | 0% |
| levels | 100% | 0% | 0% |
| liquidations | 0% | 0% | 100% |
| microstructure | 0% | 0% | 100% |
| price_action | 100% | 0% | 0% |
| regime | 100% | 0% | 0% |
| seasonality | 0% | 0% | 100% |
| smart_money | 0% | 0% | 100% |
| structure | 100% | 0% | 0% |
| technical | 0% | 100% | 0% |
| vwap | 68% | 32% | 0% |

### Correlación entre reportes (sesgo; velas con datos en ambos)

Descubrimiento (fija la penalización):

| Nuevo | Existente | n | Pearson | Spearman |
|---|---|---|---|---|
| technical | ema | 4092 | +0.69 | +0.68 |
| technical | structure | 4092 | +0.60 | +0.56 |
| technical | vwap | 4089 | +0.39 | +0.39 |
| technical | price_action | 4092 | +0.57 | +0.54 |
| technical | levels | 4092 | +0.48 | +0.47 |
| smart_money | ema | 0 | — | — |
| smart_money | structure | 0 | — | — |
| smart_money | vwap | 0 | — | — |
| smart_money | price_action | 0 | — | — |
| smart_money | levels | 0 | — | — |

Prueba (control de estabilidad):

| Nuevo | Existente | n | Pearson | Spearman |
|---|---|---|---|---|
| technical | ema | 4093 | +0.69 | +0.67 |
| technical | structure | 4093 | +0.65 | +0.61 |
| smart_money | ema | 0 | — | — |
| smart_money | structure | 0 | — | — |

### Resultados en la mitad de prueba

| Variante | Ops | Retorno | Sharpe [IC95] | E[R] | Acierto | Caída máx. | IC 4 v | IC 24 v | ΔIC 24 v [IC95] | Δ Sharpe p | Gana ventanas |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 386 | -34.6 % | -1.05 [-2.55, +0.50] | -0.099 | 38% | 42.8% | -0.0576 | -0.0880 | — | — | — |
| +technical | 386 | -31.6 % | -0.93 [-2.44, +0.63] | -0.087 | 39% | 41.0% | -0.0572 | -0.0868 | +0.0011 [-0.000, +0.003] | 0.026 | 57% |
| +technical (peso 1, sin penalización) | 381 | -43.5 % | -1.46 [-2.84, +0.23] | -0.139 | 37% | 51.9% | -0.0564 | -0.0842 | +0.0038 [+0.001, +0.007] | 0.936 | 43% |
| +smart_money | 386 | -34.6 % | -1.05 [-2.55, +0.50] | -0.099 | 38% | 42.8% | -0.0576 | -0.0880 | +0.0000 [+0.000, +0.000] | 1.000 | 0% |
| +smart_money (peso 1, sin penalización) | 386 | -34.6 % | -1.05 [-2.55, +0.50] | -0.099 | 38% | 42.8% | -0.0576 | -0.0880 | +0.0000 [+0.000, +0.000] | 1.000 | 0% |
| +ambos | 386 | -31.6 % | -0.93 [-2.44, +0.63] | -0.087 | 39% | 41.0% | -0.0572 | -0.0868 | +0.0011 [-0.000, +0.003] | 0.026 | 57% |

Sharpe por ventana de 90 días (base → con el agente):

- `technical`: 2024-12-03 -1.56→-1.56, 2025-03-03 -1.77→-1.55, 2025-06-01 -1.92→-1.92, 2025-08-30 -2.70→-2.30, 2025-11-28 +0.32→+0.33, 2026-02-26 -0.25→-0.25, 2026-05-27 +0.58→+0.84
- `smart_money`: 2024-12-03 -1.56→-1.56, 2025-03-03 -1.77→-1.77, 2025-06-01 -1.92→-1.92, 2025-08-30 -2.70→-2.70, 2025-11-28 +0.32→+0.32, 2026-02-26 -0.25→-0.25, 2026-05-27 +0.58→+0.58

## Limitaciones

- `smart_money`: el tablero de líderes existe desde 2026-10-16 y no hay ningún líder aprobado → en todo el histórico da `no_data`; su aporte no es medible y su peso inicial queda en 0 hasta tener semanas de veredictos adelante (T41/T42).
- `calendar`: no vota (bias = 0). Su efecto (confianza × 0,75 en ventana, × 0,5 con blackout; tamaño × 0,5 en ventana sin blackout con `risk_v2`; veto con blackout) es defensivo y no se evalúa aquí: no hay calendario point-in-time antes de 2026-10-14.
- `derivatives`, `microstructure`, `liquidations` y `context` tampoco tienen historia completa: la síntesis histórica usa menos agentes que la de vivo.
- Una sola regla de operación fija (sin optimizar); otro umbral o salida puede dar otro resultado. Las ventanas incompletas al final de la serie se descartan.
