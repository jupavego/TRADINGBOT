# Calibración T26 — BTCUSDT 1h (modo SIMULADO)

Datos: binance-futures · 33166 velas 2023-01-01→2026-10-13 · hash `8a285b8e29c6b89e` · control cruzado: ETHUSDT

Objetivo por pliegue: mediana de Sharpe por subventana − 2.0·peor DD − 0.05·nº de parámetros movidos >10 %; < 20 operaciones → -5.0

**Decisión: SE MANTIENEN LOS VALORES PREVIOS** (gana en 1 de 5 pliegues de prueba).
- la calibración gana solo en 1 de 5 pliegues de prueba
- en el último pliegue ningún candidato superó de forma estable al vigente

## Dentro vs fuera de muestra por pliegue (mediana de Sharpe por ventana)

| Prueba | Vigente train | Calib. train | Vigente test | Calib. test | Degradación calib. (test−train) | Control vigente | Control calib. |
|---|---|---|---|---|---|---|---|
| 2024-01-21→2024-07-21 | -2.26 | -0.04 | -2.96 | -1.83 | -1.79 | -2.25 | -1.39 |
| 2024-07-22→2025-01-20 | -3.14 | -3.14 | -3.02 | -3.02 | +0.12 | -2.13 | -2.13 |
| 2025-01-20→2025-07-21 | -2.60 | -2.60 | -2.40 | -2.40 | +0.21 | -2.96 | -2.96 |
| 2025-07-22→2026-01-20 | -2.09 | -2.09 | -1.91 | -1.91 | +0.17 | -4.59 | -4.59 |
| 2026-01-20→2026-07-21 | -2.28 | -2.28 | -2.45 | -2.45 | -0.18 | -1.11 | -1.11 |

## Agregado fuera de muestra (ventanas de prueba encadenadas)

| Métrica | Vigente | Calibrado | Diferencia |
|---|---|---|---|
| median_window_sharpe | -2.45 | -2.40 | +0.05 |
| sharpe | -2.54 | -2.34 | +0.20 |
| total_return | -0.59 | -0.56 | +0.03 |
| max_drawdown | +0.60 | +0.57 | -0.02 |
| expectancy_r | -0.48 | -0.47 | +0.01 |
| win_rate | +0.29 | +0.28 | -0.00 |
| n_trades | 182 | 172 | -10 |
| median_window_sharpe (control) | -2.25 | -2.13 | +0.12 |
| sharpe (control) | -2.59 | -2.37 | +0.21 |
| total_return (control) | -0.56 | -0.55 | +0.02 |
| max_drawdown (control) | +0.59 | +0.59 | +0.00 |
| expectancy_r (control) | -0.46 | -0.45 | +0.01 |
| win_rate (control) | +0.28 | +0.26 | -0.02 |
| n_trades (control) | 176 | 172 | -4 |

## Parámetros (último pliegue) y estabilidad ±10 %

| Parámetro | Vigente | Último pliegue | Rango | Justificación |
|---|---|---|---|---|
| `plan.min_abs_bias` | 0.15 | 0.15 | [0.05, 0.4] | θ: sesgo combinado mínimo (0.15 vigente) |
| `plan.min_confidence` | 0.3 | 0.3 | [0.15, 0.5] | θ: confianza mínima (0.30 vigente) |
| `plan.min_rr` | 1.5 | 1.5 | [1.0, 3.0] | θ: R:R mínimo a TP1; <1 contradice el plan |
| `plan.sl_buffer_atr` | 0.5 | 0.5 | [0.2, 1.0] | colchón del SL tras el nivel (0.5 ATR vigente) |
| `plan.max_sl_atr` | 5.0 | 5.0 | [2.5, 8.0] | SL más lejano admitido (5 ATR vigente) |
| `plan.expiry_bars` | 48 | 48 | [24, 96] | vigencia del plan: 1–4 días en 1h |
| `synth.w_structure` | 1.0 | 1.0 | [0.5, 2.0] | W: peso structure/levels (1 vigente; ≥0.05 VRM) |
| `synth.disagree_penalty` | 0.5 | 0.5 | [0.3, 0.8] | factor de confianza ante desacuerdo (0.5) |
| `strategy.tp_index` | 0 | 0 | [0, 1] | salida en TP1 o TP2 |

Último pliegue: ningún candidato superó al vigente en su peor caso ±10 %.

## Fidelidad del caché de insumos

Ventana de 720 velas: 7 operaciones con caché vs 7 con el agente completo (7 entradas idénticas); retorno +0.0188 vs +0.0188.

## Notas

- Optimización SOLO con ventanas de entrenamiento; cada prueba es posterior y nunca vista por la búsqueda.
- Los insumos structure/levels se memoizan con ventana móvil (ver fidelidad).
- Costos de perpetuo de T25 (comisiones, deslizamiento, funding real).
- Resultado de simulación: no garantiza edge futuro (decide T27).
