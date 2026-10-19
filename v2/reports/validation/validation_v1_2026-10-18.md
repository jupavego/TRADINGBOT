# T49 — Puerta de validación por estrategia (`validation_v1`)

Modo: **SIMULADO** · símbolo BTCUSDT · datos hasta 2026-10-18 23:00 UTC · calculado 2026-10-18 23:14 UTC · intentos registrados: 87.
Criterios `validation_v1` (SHA-256 `0a5b19962ded0d12…`), fijados en el commit `18e7283` antes del primer cálculo con datos reales.

## 1. Veredicto

**Ninguna estrategia validada.** Es un resultado válido: ninguna `estrategia@marco@versión` tiene hoy evidencia fuera de muestra suficiente.

De 87 versiones vigentes: 0 VALIDADA · 54 EN OBSERVACIÓN · 33 RECHAZADA.

Criterios que más fallan (insumo del ciclo de mejora):

- V3 Contra el azar: 78 versiones
- V2 Expectativa neta: 74 versiones
- V1 Suficiencia de datos: 62 versiones
- V5 Estabilidad: 40 versiones
- V4 Drawdown: 25 versiones
- V6 Costos: 24 versiones

## 2. Criterios (fijados antes de calcular)

| ID | Criterio | Umbral |
|---|---|---|
| V1 | Suficiencia de datos | ≥ 100 operaciones cerradas fuera de muestra y ≥ 2 regímenes con ≥ 20 cada uno |
| V2 | Expectativa neta | R medio neto > 0 con IC95% bootstrap por bloques de día (5000 remuestreos) que excluye 0 |
| V3 | Contra el azar | Réplica con lado aleatorio (≥ 500 réplicas, 40 × intentos): p unilateral < 0.05 tras Holm sobre todos los intentos registrados (también retirados) |
| V4 | Drawdown | DD máximo ≤ 25% con riesgo fijo de 1% por operación |
| V5 | Estabilidad | R medio > 0 en ≥ 60% de ventanas disjuntas de 30 días (≥ 4 ventanas con ≥ 5 op.) y tramo en vivo con ≥ 20 op. y R medio > 0 |
| V6 | Costos | Costo medio (comisiones + deslizamiento + funding) ≤ 0.3 R por operación |

Claramente negativa (en cualquier momento, con ≥ 20 op.): R medio + 1·EE < 0 → RECHAZADA.

- V2: IC del R medio neto por bootstrap de bloques de día UTC de la decisión (percentiles); cumple si el extremo inferior > 0.
- V3: estadístico = R medio neto. Réplica: cada operación con su lado al azar (p = 1/2); el lado contrario refleja entrada, SL y TP alrededor del precio de referencia de la decisión (misma fecha, misma distancia, mismos costos); si no se llenaría aporta 0 R y si sigue abierta en asof, su R latente. Réplicas = max(min_reps, reps_per_attempt x intentos registrados). p unilateral con corrección +1, ajustado por Holm sobre TODOS los intentos registrados (también los retirados), cada uno con su último p bruto (sin p = 1).
- V4: curva compuesta en orden de cierre, capital x (1 + risk_per_trade x R) por operación; DD = máxima caída desde el pico.
- V5: ventanas disjuntas de window_days días ancladas en la primera decisión fuera de muestra; solo cuentan las ventanas con >= window_min_trades operaciones. Tramo en vivo = origin 'vivo'; con menos de live_min_trades queda pendiente (no falla).
- V6: costo por operación = (comisión de entrada + de salida + deslizamiento + funding pagado) / riesgo, en R.
- Claramente negativa: con >= min_trades, R medio + z x error estándar (desviación muestral / raíz de n) < 0 => RECHAZADA en cualquier momento.
- Veredicto: VALIDADA si V1-V6 se cumplen. EN OBSERVACIÓN si falla V1 o el tramo en vivo está pendiente y nada indica pérdida clara. RECHAZADA si es claramente negativa o si, con V1 cumplido, falla cualquier otro criterio.

## 3. Datos y muestra fuera de muestra

Contextos del bróker simulado:

| Marco | Contextos | Desde | Hasta | Orígenes |
|---|---|---|---|---|
| 15m | 3118 | 2026-09-16 03:00 | 2026-10-18 23:00 | backtest 2955, vivo 163 |
| 1h | 33038 | 2023-01-11 10:00 | 2026-10-18 23:00 | backtest 32988, vivo 50 |
| 4h | 1281 | 2026-03-19 12:00 | 2026-10-18 20:00 | backtest 1266, vivo 15 |

Ventanas de ajuste registradas (se excluyen de la evidencia de la versión y de sus descendientes):

| Origen | Versiones | Ventana de ajuste (UTC) | Símbolos | Nota |
|---|---|---|---|---|
| T48b | 87 | 2026-08-16 00:00 → 2026-10-16 14:00 | todos | Unión conservadora de los 3 marcos, todos los símbolos; fin = cierre de T48c (2026-10-16 13:57 UTC) |

Historial fuera de muestra disponible por marco:

| Marco | Versiones | Op. fuera de muestra | Excluidas por ajuste | Con ≥ 100 | Primera decisión FdM | Último cierre FdM |
|---|---|---|---|---|---|---|
| 15m | 29 | 202 | 2825 | 0 | 2026-10-16 14:00 | 2026-10-18 22:15 |
| 1h | 29 | 37523 | 1791 | 26 | 2023-01-11 10:00 | 2026-10-18 22:45 |
| 4h | 29 | 1269 | 583 | 2 | 2026-03-19 12:00 | 2026-10-18 22:45 |

## 4. Resultados por estrategia@marco@versión

| Versión | Veredicto | FdM | Vivo | R medio [IC95 %] | p → Holm | DD | Ventanas + | Costo R | V1–V6 | Motivo |
|---|---|---|---|---|---|---|---|---|---|---|
| `escenario_retroceso@15m@v1` | **EN OBSERVACIÓN** | 1 | 0 | +2.097 [—, —] | 0.4915 → 1.0000 | 0.0% | 0/0 | 0.129 | V1✘ V2… V3✘ V4✔ V5… V6✔ | V1: 1 operaciones fuera de muestra; regímenes: range 1 |
| `ind_macd@15m@v1` | **EN OBSERVACIÓN** | 5 | 3 | +0.247 [-0.396, +0.675] | 0.0307 → 1.0000 | 1.6% | 1/1 | 0.530 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 5 operaciones fuera de muestra; regímenes: range 5 |
| `ind_supertrend@15m@v1` | **EN OBSERVACIÓN** | 3 | 2 | +0.101 [-1.482, +0.892] | 0.5047 → 1.0000 | 1.5% | 0/0 | 0.396 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 3 operaciones fuera de muestra; regímenes: range 3 |
| `contra_sintesis@4h@v1` | **EN OBSERVACIÓN** | 81 | 0 | +0.036 [-0.228, +0.296] | 0.1043 → 1.0000 | 13.5% | 3/5 | 0.109 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 81 operaciones fuera de muestra; regímenes: range 74, volatile 4, trend_down 3 |
| `agente_vwap@4h@v1` | **EN OBSERVACIÓN** | 42 | 0 | +0.022 [-0.309, +0.350] | 0.1319 → 1.0000 | 5.7% | 2/5 | 0.109 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | V1: 42 operaciones fuera de muestra; regímenes: range 38, trend_down 3, volatile 1 |
| `control_aleatorio@15m@v1` | **EN OBSERVACIÓN** | 14 | 11 | +0.012 [-0.776, +0.467] | 0.0164 → 1.0000 | 3.5% | 1/1 | 0.489 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 14 operaciones fuera de muestra; regímenes: range 13, trend_down 1 |
| `ind_macd@4h@v1` | **EN OBSERVACIÓN** | 30 | 0 | -0.004 [-0.439, +0.426] | 0.5228 → 1.0000 | 3.7% | 2/5 | 0.115 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | V1: 30 operaciones fuera de muestra; regímenes: range 30 |
| `sugerencia_1@4h@v1` | **EN OBSERVACIÓN** | 116 | 0 | -0.033 [-0.217, +0.152] | 0.6823 → 1.0000 | 15.5% | 2/5 | 0.061 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | V1: 116 operaciones fuera de muestra; regímenes: range 104, trend_down 6, volatile 6 |
| `sugerencia_3@4h@v1` | **EN OBSERVACIÓN** | 72 | 0 | -0.048 [-0.277, +0.175] | 0.6047 → 1.0000 | 14.8% | 2/5 | 0.070 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | V1: 72 operaciones fuera de muestra; regímenes: range 70, trend_down 2 |
| `escenario_retroceso@1h@v1` | **EN OBSERVACIÓN** | 102 | 0 | -0.076 [-0.301, +0.157] | 0.7791 → 1.0000 | 16.9% | 1/2 | 0.109 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 102 operaciones fuera de muestra; regímenes: range 90, volatile 9, trend_up 3 |
| `ind_bb_ruptura@4h@v1` | **EN OBSERVACIÓN** | 36 | 1 | -0.082 [-0.440, +0.292] | 0.2560 → 1.0000 | 5.4% | 2/5 | 0.113 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | V1: 36 operaciones fuera de muestra; regímenes: range 35, volatile 1 |
| `sugerencia_2@4h@v1` | **EN OBSERVACIÓN** | 100 | 0 | -0.088 [-0.283, +0.111] | 0.8782 → 1.0000 | 14.0% | 2/5 | 0.071 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | V1: 100 operaciones fuera de muestra; regímenes: range 92, volatile 6, trend_down 2 |
| `escenario_rango@4h@v1` | **EN OBSERVACIÓN** | 15 | 0 | -0.094 [-0.669, +0.525] | 0.6357 → 1.0000 | 4.5% | 0/1 | 0.126 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 15 operaciones fuera de muestra; regímenes: range 15 |
| `agente_levels@4h@v1` | **EN OBSERVACIÓN** | 85 | 0 | -0.098 [-0.321, +0.128] | 0.4430 → 1.0000 | 12.6% | 1/5 | 0.108 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | V1: 85 operaciones fuera de muestra; regímenes: range 80, trend_down 3, volatile 2 |
| `escenario_dominante@4h@v1` | **EN OBSERVACIÓN** | 7 | 0 | -0.101 [-0.896, +1.064] | 0.6096 → 1.0000 | 2.4% | 0/0 | 0.207 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 7 operaciones fuera de muestra; regímenes: range 6, volatile 1 |
| `ind_cruce_ema@4h@v1` | **EN OBSERVACIÓN** | 23 | 0 | -0.118 [-0.578, +0.372] | 0.6300 → 1.0000 | 5.4% | 1/2 | 0.120 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 23 operaciones fuera de muestra; regímenes: range 23 |
| `consenso_sintesis@4h@v1` | **EN OBSERVACIÓN** | 77 | 0 | -0.120 [-0.368, +0.130] | 0.6745 → 1.0000 | 15.0% | 1/5 | 0.104 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | V1: 77 operaciones fuera de muestra; regímenes: range 72, trend_down 3, volatile 2 |
| `ind_donchian@4h@v1` | **EN OBSERVACIÓN** | 25 | 0 | -0.169 [-0.592, +0.305] | 0.3174 → 1.0000 | 7.5% | 1/2 | 0.084 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 25 operaciones fuera de muestra; regímenes: range 23, trend_down 2 |
| `ind_rsi@4h@v1` | **EN OBSERVACIÓN** | 19 | 0 | -0.172 [-0.658, +0.355] | 0.4961 → 1.0000 | 5.3% | 0/1 | 0.129 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 19 operaciones fuera de muestra; regímenes: range 18, trend_down 1 |
| `ind_supertrend@4h@v1` | **EN OBSERVACIÓN** | 20 | 0 | -0.184 [-0.576, +0.247] | 0.6648 → 1.0000 | 4.4% | 0/1 | 0.119 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 20 operaciones fuera de muestra; regímenes: range 20 |
| `ind_adx@4h@v1` | **EN OBSERVACIÓN** | 6 | 0 | -0.255 [-0.969, +0.752] | 0.5852 → 1.0000 | 2.3% | 0/0 | 0.141 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 6 operaciones fuera de muestra; regímenes: range 6 |
| `ind_bb_reversion@15m@v1` | **EN OBSERVACIÓN** | 10 | 8 | -0.268 [-0.922, +0.605] | 0.2870 → 1.0000 | 2.8% | 0/1 | 0.464 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 10 operaciones fuera de muestra; regímenes: range 9, volatile 1 |
| `ind_cruce_ema@15m@v1` | **EN OBSERVACIÓN** | 4 | 3 | -0.341 [-1.787, +1.104] | 0.0618 → 1.0000 | 3.5% | 0/0 | 0.622 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 4 operaciones fuera de muestra; regímenes: range 4 |
| `consenso_sintesis@15m@v1` | **EN OBSERVACIÓN** | 17 | 11 | -0.422 [-0.864, +0.116] | 0.1462 → 1.0000 | 8.7% | 0/1 | 0.476 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 17 operaciones fuera de muestra; regímenes: range 16, volatile 1 |
| `plan_tp2@4h@v1` | **EN OBSERVACIÓN** | 6 | 0 | -0.463 [-1.433, +0.870] | 0.5662 → 1.0000 | 3.0% | 0/0 | 0.281 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 6 operaciones fuera de muestra; regímenes: range 6 |
| `agente_price_action@15m@v1` | **EN OBSERVACIÓN** | 19 | 14 | -0.473 [-1.251, +0.204] | 0.2922 → 1.0000 | 11.0% | 0/1 | 0.491 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 19 operaciones fuera de muestra; regímenes: range 17, volatile 2 |
| `sugerencia_alineada@15m@v1` | **EN OBSERVACIÓN** | 1 | 1 | -0.486 [—, —] | 1.0000 → 1.0000 | 0.5% | 0/0 | 0.058 | V1✘ V2… V3✘ V4✔ V5… V6✔ | V1: 1 operaciones fuera de muestra; regímenes: volatile 1 |
| `sugerencia_2@15m@v1` | **EN OBSERVACIÓN** | 5 | 5 | -0.505 [-1.504, +0.161] | 0.5045 → 1.0000 | 4.4% | 0/1 | 0.273 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 5 operaciones fuera de muestra; regímenes: range 4, volatile 1 |
| `ind_rsi@15m@v1` | **EN OBSERVACIÓN** | 9 | 6 | -0.591 [-1.372, -0.147] | 0.5404 → 1.0000 | 6.0% | 0/1 | 0.575 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 9 operaciones fuera de muestra; regímenes: range 8, volatile 1 |
| `agente_ema@15m@v1` | **EN OBSERVACIÓN** | 18 | 13 | -0.707 [-1.259, -0.211] | 0.3694 → 1.0000 | 12.2% | 0/1 | 0.541 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 18 operaciones fuera de muestra; regímenes: range 17, volatile 1 |
| `contra_sintesis@15m@v1` | **EN OBSERVACIÓN** | 17 | 11 | -0.747 [-1.188, -0.399] | 0.6030 → 1.0000 | 12.1% | 0/1 | 0.522 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 17 operaciones fuera de muestra; regímenes: range 16, volatile 1 |
| `ind_bb_ruptura@15m@v1` | **EN OBSERVACIÓN** | 8 | 6 | -0.778 [-1.468, -0.420] | 0.2904 → 1.0000 | 6.1% | 0/1 | 0.600 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 8 operaciones fuera de muestra; regímenes: range 7, trend_down 1 |
| `ind_donchian@15m@v1` | **EN OBSERVACIÓN** | 8 | 6 | -0.808 [-1.393, -0.657] | 0.4737 → 1.0000 | 7.8% | 0/1 | 0.497 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 8 operaciones fuera de muestra; regímenes: range 8 |
| `consenso_fuerte@15m@v1` | **EN OBSERVACIÓN** | 11 | 8 | -0.845 [-1.488, -0.686] | 0.4410 → 1.0000 | 9.0% | 0/1 | 0.643 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 11 operaciones fuera de muestra; regímenes: range 10, volatile 1 |
| `agente_levels@15m@v1` | **EN OBSERVACIÓN** | 18 | 13 | -0.962 [-1.205, -0.748] | 0.9003 → 1.0000 | 16.1% | 0/1 | 0.515 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 18 operaciones fuera de muestra; regímenes: range 16, volatile 2 |
| `agente_technical@15m@v1` | **EN OBSERVACIÓN** | 10 | 6 | -0.985 [-1.705, -0.304] | 0.8115 → 1.0000 | 10.1% | 0/1 | 0.560 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 10 operaciones fuera de muestra; regímenes: range 10 |
| `sugerencia_1@15m@v1` | **EN OBSERVACIÓN** | 3 | 3 | -0.988 [-1.390, -0.184] | 0.8768 → 1.0000 | 2.9% | 0/0 | 0.281 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 3 operaciones fuera de muestra; regímenes: range 2, volatile 1 |
| `sugerencia_3@15m@v1` | **EN OBSERVACIÓN** | 4 | 4 | -1.006 [-1.391, +0.150] | 0.8156 → 1.0000 | 4.1% | 0/0 | 0.324 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 4 operaciones fuera de muestra; regímenes: range 3, volatile 1 |
| `escenario_retroceso@4h@v1` | **EN OBSERVACIÓN** | 2 | 0 | -1.101 [-1.103, -1.100] | 1.0000 → 1.0000 | 2.2% | 0/0 | 0.101 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | V1: 2 operaciones fuera de muestra; regímenes: range 2 |
| `escenario_dominante@15m@v1` | **EN OBSERVACIÓN** | 2 | 1 | -1.215 [-1.215, -1.215] | 0.4904 → 1.0000 | 2.4% | 0/0 | 0.783 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 2 operaciones fuera de muestra; regímenes: range 2 |
| `agente_technical@1h@v1` | **EN OBSERVACIÓN** | 1 | 1 | -1.361 [—, —] | 1.0000 → 1.0000 | 1.4% | 0/0 | 0.361 | V1✘ V2… V3✘ V4✔ V5… V6✘ | V1: 1 operaciones fuera de muestra; regímenes: range 1 |
| `plan_tp1@15m@v1` | **EN OBSERVACIÓN** | 7 | 3 | -1.437 [-1.782, -0.699] | 0.7828 → 1.0000 | 9.7% | 0/1 | 0.661 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 7 operaciones fuera de muestra; regímenes: range 7 |
| `escenario_rango@15m@v1` | **EN OBSERVACIÓN** | 4 | 4 | -1.717 [-1.817, -1.417] | 1.0000 → 1.0000 | 6.7% | 0/0 | 0.717 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 4 operaciones fuera de muestra; regímenes: range 4 |
| `plan_tp2@15m@v1` | **EN OBSERVACIÓN** | 3 | 1 | -1.781 [-1.919, -1.507] | 0.2407 → 1.0000 | 5.2% | 0/0 | 0.781 | V1✘ V2✘ V3✘ V4✔ V5… V6✘ | V1: 3 operaciones fuera de muestra; regímenes: range 3 |
| `ind_adx@15m@v1` | **EN OBSERVACIÓN** | 1 | 0 | -1.890 [—, —] | 1.0000 → 1.0000 | 1.9% | 0/0 | 0.890 | V1✘ V2… V3✘ V4✔ V5… V6✘ | V1: 1 operaciones fuera de muestra; regímenes: range 1 |
| `agente_derivatives@15m@v1` | **EN OBSERVACIÓN** | 0 | 0 | — [—, —] | — → — | 0.0% | 0/0 | — | V1✘ V2… V3… V4… V5… V6… | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| `agente_derivatives@1h@v1` | **EN OBSERVACIÓN** | 0 | 0 | — [—, —] | — → — | 0.0% | 0/0 | — | V1✘ V2… V3… V4… V5… V6… | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| `agente_derivatives@4h@v1` | **EN OBSERVACIÓN** | 0 | 0 | — [—, —] | — → — | 0.0% | 0/0 | — | V1✘ V2… V3… V4… V5… V6… | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| `agente_elliott@15m@v1` | **EN OBSERVACIÓN** | 0 | 0 | — [—, —] | — → — | 0.0% | 0/0 | — | V1✘ V2… V3… V4… V5… V6… | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| `agente_elliott@1h@v1` | **EN OBSERVACIÓN** | 0 | 0 | — [—, —] | — → — | 0.0% | 0/0 | — | V1✘ V2… V3… V4… V5… V6… | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| `agente_elliott@4h@v1` | **EN OBSERVACIÓN** | 0 | 0 | — [—, —] | — → — | 0.0% | 0/0 | — | V1✘ V2… V3… V4… V5… V6… | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| `agente_structure@15m@v1` | **EN OBSERVACIÓN** | 0 | 0 | — [—, —] | — → — | 0.0% | 0/0 | — | V1✘ V2… V3… V4… V5… V6… | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| `agente_technical@4h@v1` | **EN OBSERVACIÓN** | 0 | 0 | — [—, —] | — → — | 0.0% | 0/0 | — | V1✘ V2… V3… V4… V5… V6… | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| `agente_vwap@15m@v1` | **EN OBSERVACIÓN** | 0 | 0 | — [—, —] | — → — | 0.0% | 0/0 | — | V1✘ V2… V3… V4… V5… V6… | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| `sugerencia_1@1h@v1` | **RECHAZADA** | 1851 | 2 | -0.063 [-0.111, -0.015] | 0.9796 → 1.0000 | 75.5% | 13/44 | 0.093 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.063 + 1·EE 0.025 < 0 → ciclo de mejora |
| `sugerencia_2@1h@v1` | **RECHAZADA** | 1632 | 2 | -0.106 [-0.159, -0.051] | 1.0000 → 1.0000 | 85.1% | 13/44 | 0.100 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.106 + 1·EE 0.027 < 0 → ciclo de mejora |
| `sugerencia_3@1h@v1` | **RECHAZADA** | 1645 | 1 | -0.112 [-0.165, -0.056] | 1.0000 → 1.0000 | 86.7% | 14/44 | 0.112 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.112 + 1·EE 0.027 < 0 → ciclo de mejora |
| `sugerencia_alineada@1h@v1` | **RECHAZADA** | 1051 | 1 | -0.112 [-0.174, -0.049] | 1.0000 → 1.0000 | 72.5% | 9/44 | 0.075 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.112 + 1·EE 0.031 < 0 → ciclo de mejora |
| `sugerencia_alineada@4h@v1` | **RECHAZADA** | 59 | 0 | -0.148 [-0.373, +0.090] | 0.8791 → 1.0000 | 10.1% | 1/4 | 0.058 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | claramente negativa: R medio -0.148 + 1·EE 0.124 < 0 → ciclo de mejora |
| `control_aleatorio@4h@v1` | **RECHAZADA** | 68 | 0 | -0.160 [-0.416, +0.106] | 0.5892 → 1.0000 | 21.8% | 2/5 | 0.114 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | claramente negativa: R medio -0.160 + 1·EE 0.141 < 0 → ciclo de mejora |
| `agente_structure@4h@v1` | **RECHAZADA** | 60 | 0 | -0.171 [-0.429, +0.093] | 0.8006 → 1.0000 | 13.8% | 1/4 | 0.109 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | claramente negativa: R medio -0.171 + 1·EE 0.147 < 0 → ciclo de mejora |
| `consenso_fuerte@4h@v1` | **RECHAZADA** | 68 | 0 | -0.176 [-0.467, +0.134] | 0.4576 → 1.0000 | 16.5% | 2/5 | 0.131 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | claramente negativa: R medio -0.176 + 1·EE 0.155 < 0 → ciclo de mejora |
| `ind_bb_reversion@4h@v1` | **RECHAZADA** | 48 | 0 | -0.202 [-0.505, +0.121] | 0.6354 → 1.0000 | 9.5% | 0/5 | 0.154 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | claramente negativa: R medio -0.202 + 1·EE 0.166 < 0 → ciclo de mejora |
| `ind_donchian@1h@v1` | **RECHAZADA** | 1063 | 1 | -0.219 [-0.288, -0.147] | 0.1994 → 1.0000 | 91.2% | 8/44 | 0.182 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.219 + 1·EE 0.035 < 0 → ciclo de mejora |
| `agente_vwap@1h@v1` | **RECHAZADA** | 580 | 0 | -0.220 [-0.304, -0.131] | 0.1560 → 1.0000 | 73.4% | 11/44 | 0.204 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.220 + 1·EE 0.045 < 0 → ciclo de mejora |
| `agente_structure@1h@v1` | **RECHAZADA** | 1630 | 0 | -0.225 [-0.279, -0.171] | 0.2939 → 1.0000 | 97.8% | 3/42 | 0.182 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.225 + 1·EE 0.027 < 0 → ciclo de mejora |
| `escenario_rango@1h@v1` | **RECHAZADA** | 642 | 2 | -0.233 [-0.330, -0.137] | 1.0000 → 1.0000 | 79.5% | 9/44 | 0.251 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.233 + 1·EE 0.050 < 0 → ciclo de mejora |
| `agente_ema@1h@v1` | **RECHAZADA** | 3017 | 5 | -0.244 [-0.283, -0.204] | 0.0899 → 1.0000 | 100.0% | 1/45 | 0.212 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.244 + 1·EE 0.020 < 0 → ciclo de mejora |
| `agente_price_action@4h@v1` | **RECHAZADA** | 93 | 0 | -0.245 [-0.475, -0.006] | 0.8555 → 1.0000 | 21.6% | 1/5 | 0.111 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | claramente negativa: R medio -0.245 + 1·EE 0.114 < 0 → ciclo de mejora |
| `agente_price_action@1h@v1` | **RECHAZADA** | 3218 | 5 | -0.250 [-0.290, -0.211] | 0.1916 → 1.0000 | 100.0% | 2/45 | 0.212 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.250 + 1·EE 0.019 < 0 → ciclo de mejora |
| `agente_ema@4h@v1` | **RECHAZADA** | 90 | 0 | -0.252 [-0.477, -0.024] | 0.8880 → 1.0000 | 21.4% | 1/5 | 0.118 | V1✘ V2✘ V3✘ V4✔ V5✘ V6✔ | claramente negativa: R medio -0.252 + 1·EE 0.114 < 0 → ciclo de mejora |
| `consenso_sintesis@1h@v1` | **RECHAZADA** | 2671 | 5 | -0.256 [-0.298, -0.214] | 0.2735 → 1.0000 | 99.9% | 3/45 | 0.211 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.256 + 1·EE 0.021 < 0 → ciclo de mejora |
| `ind_bb_ruptura@1h@v1` | **RECHAZADA** | 1458 | 2 | -0.258 [-0.316, -0.199] | 0.0069 → 0.5998 | 97.9% | 7/44 | 0.236 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.258 + 1·EE 0.029 < 0 → ciclo de mejora |
| `control_aleatorio@1h@v1` | **RECHAZADA** | 2241 | 6 | -0.259 [-0.304, -0.215] | 0.3488 → 1.0000 | 99.8% | 2/45 | 0.207 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.259 + 1·EE 0.023 < 0 → ciclo de mejora |
| `agente_levels@1h@v1` | **RECHAZADA** | 2987 | 4 | -0.263 [-0.303, -0.224] | 0.4887 → 1.0000 | 100.0% | 2/45 | 0.212 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.263 + 1·EE 0.020 < 0 → ciclo de mejora |
| `ind_cruce_ema@1h@v1` | **RECHAZADA** | 720 | 2 | -0.265 [-0.349, -0.180] | 0.1727 → 1.0000 | 86.2% | 8/44 | 0.237 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.265 + 1·EE 0.043 < 0 → ciclo de mejora |
| `contra_sintesis@1h@v1` | **RECHAZADA** | 2757 | 5 | -0.277 [-0.321, -0.232] | 0.6625 → 1.0000 | 100.0% | 2/45 | 0.217 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.277 + 1·EE 0.021 < 0 → ciclo de mejora |
| `plan_tp1@4h@v1` | **RECHAZADA** | 21 | 0 | -0.294 [-0.790, +0.238] | 0.7475 → 1.0000 | 6.2% | 1/3 | 0.153 | V1✘ V2✘ V3✘ V4✔ V5… V6✔ | claramente negativa: R medio -0.294 + 1·EE 0.275 < 0 → ciclo de mejora |
| `ind_macd@1h@v1` | **RECHAZADA** | 982 | 1 | -0.306 [-0.374, -0.238] | 0.6507 → 1.0000 | 95.6% | 1/44 | 0.231 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.307 + 1·EE 0.035 < 0 → ciclo de mejora |
| `ind_supertrend@1h@v1` | **RECHAZADA** | 632 | 1 | -0.312 [-0.401, -0.223] | 0.4927 → 1.0000 | 86.7% | 9/44 | 0.215 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.312 + 1·EE 0.045 < 0 → ciclo de mejora |
| `consenso_fuerte@1h@v1` | **RECHAZADA** | 2325 | 3 | -0.330 [-0.381, -0.278] | 0.4901 → 1.0000 | 100.0% | 1/44 | 0.258 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.329 + 1·EE 0.025 < 0 → ciclo de mejora |
| `ind_bb_reversion@1h@v1` | **RECHAZADA** | 1738 | 5 | -0.374 [-0.423, -0.326] | 0.9805 → 1.0000 | 99.9% | 1/45 | 0.256 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.374 + 1·EE 0.025 < 0 → ciclo de mejora |
| `ind_rsi@1h@v1` | **RECHAZADA** | 821 | 0 | -0.376 [-0.452, -0.296] | 0.9957 → 1.0000 | 95.7% | 1/44 | 0.223 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.376 + 1·EE 0.038 < 0 → ciclo de mejora |
| `plan_tp1@1h@v1` | **RECHAZADA** | 782 | 3 | -0.382 [-0.460, -0.300] | 0.7578 → 1.0000 | 95.4% | 3/44 | 0.278 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.382 + 1·EE 0.041 < 0 → ciclo de mejora |
| `ind_adx@1h@v1` | **RECHAZADA** | 209 | 0 | -0.421 [-0.567, -0.274] | 0.8684 → 1.0000 | 60.8% | 0/24 | 0.216 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✔ | claramente negativa: R medio -0.421 + 1·EE 0.072 < 0 → ciclo de mejora |
| `escenario_dominante@1h@v1` | **RECHAZADA** | 351 | 0 | -0.474 [-0.603, -0.338] | 0.8538 → 1.0000 | 81.7% | 4/36 | 0.340 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✘ | claramente negativa: R medio -0.474 + 1·EE 0.067 < 0 → ciclo de mejora |
| `plan_tp2@1h@v1` | **RECHAZADA** | 417 | 2 | -0.505 [-0.623, -0.382] | 0.9744 → 1.0000 | 88.3% | 4/42 | 0.316 | V1✔ V2✘ V3✘ V4✘ V5✘ V6✘ | claramente negativa: R medio -0.505 + 1·EE 0.060 < 0 → ciclo de mejora |

✔ cumple · ✘ falla · … pendiente (sin datos para juzgarlo).

## 5. Informativo (no son criterios)

| Versión | Acierto | PF | MFE / MAE (R) | DSR (intentos) | Retorno al 1 % | Comprar y mantener (mismo tramo) |
|---|---|---|---|---|---|---|
| `escenario_retroceso@15m@v1` | 100.0% | — | 2.23 / 0.59 | — | +2.1% | -0.2% |
| `ind_macd@15m@v1` | 80.0% | 1.76 | 1.16 / 0.60 | 0.042 | +1.2% | -0.6% |
| `ind_supertrend@15m@v1` | 66.7% | 1.20 | 1.23 / 0.42 | 0.010 | +0.3% | -0.5% |
| `contra_sintesis@4h@v1` | 51.8% | 1.07 | 0.92 / 0.69 | 0.013 | +2.4% | -7.6% |
| `agente_vwap@4h@v1` | 61.9% | 1.05 | 1.02 / 0.59 | 0.009 | +0.7% | -8.8% |
| `control_aleatorio@15m@v1` | 57.1% | 1.02 | 1.09 / 0.74 | 0.007 | +0.1% | +0.1% |
| `ind_macd@4h@v1` | 50.0% | 0.99 | 0.93 / 0.71 | 0.006 | -0.4% | -9.0% |
| `sugerencia_1@4h@v1` | 50.0% | 0.93 | 0.79 / 0.62 | 0.002 | -4.3% | -9.6% |
| `sugerencia_3@4h@v1` | 51.4% | 0.89 | 0.81 / 0.62 | 0.002 | -3.7% | -6.7% |
| `escenario_retroceso@1h@v1` | 46.1% | 0.86 | 0.97 / 0.66 | 0.001 | -8.1% | +243.8% |
| `ind_bb_ruptura@4h@v1` | 52.8% | 0.85 | 0.91 / 0.70 | 0.002 | -3.1% | +19.1% |
| `sugerencia_2@4h@v1` | 52.0% | 0.81 | 0.77 / 0.67 | 0.000 | -8.8% | +17.2% |
| `escenario_rango@4h@v1` | 53.3% | 0.82 | 1.12 / 0.57 | 0.004 | -1.5% | -17.2% |
| `agente_levels@4h@v1` | 51.8% | 0.82 | 0.94 / 0.70 | 0.001 | -8.5% | -8.9% |
| `escenario_dominante@4h@v1` | 42.9% | 0.81 | 1.22 / 0.72 | 0.006 | -0.8% | -17.3% |
| `ind_cruce_ema@4h@v1` | 52.2% | 0.78 | 1.03 / 0.61 | 0.002 | -2.8% | -9.5% |
| `consenso_sintesis@4h@v1` | 46.8% | 0.79 | 0.94 / 0.69 | 0.001 | -9.3% | -8.3% |
| `ind_donchian@4h@v1` | 48.0% | 0.70 | 0.95 / 0.70 | 0.001 | -4.3% | -8.3% |
| `ind_rsi@4h@v1` | 47.4% | 0.72 | 0.91 / 0.64 | 0.001 | -3.3% | -7.3% |
| `ind_supertrend@4h@v1` | 55.0% | 0.64 | 0.93 / 0.69 | 0.001 | -3.7% | -9.1% |
| `ind_adx@4h@v1` | 33.3% | 0.56 | 0.87 / 0.77 | 0.004 | -1.6% | -8.7% |
| `ind_bb_reversion@15m@v1` | 60.0% | 0.57 | 0.74 / 0.68 | 0.001 | -2.7% | -0.2% |
| `ind_cruce_ema@15m@v1` | 50.0% | 0.62 | 1.37 / 0.69 | 0.002 | -1.4% | -0.6% |
| `consenso_sintesis@15m@v1` | 47.1% | 0.47 | 0.82 / 0.68 | 0.000 | -7.0% | -1.6% |
| `plan_tp2@4h@v1` | 33.3% | 0.49 | 1.09 / 0.77 | 0.004 | -2.8% | -4.4% |
| `agente_price_action@15m@v1` | 42.1% | 0.46 | 0.87 / 0.73 | 0.000 | -8.7% | -0.9% |
| `sugerencia_alineada@15m@v1` | 0.0% | 0.00 | 0.62 / 0.81 | — | -0.5% | +0.5% |
| `sugerencia_2@15m@v1` | 20.0% | 0.44 | 1.30 / 0.78 | 0.004 | -2.5% | -0.9% |
| `ind_rsi@15m@v1` | 44.4% | 0.36 | 0.60 / 0.81 | 0.000 | -5.3% | +0.5% |
| `agente_ema@15m@v1` | 33.3% | 0.29 | 0.80 / 0.72 | 0.000 | -12.1% | -1.0% |
| `contra_sintesis@15m@v1` | 35.3% | 0.29 | 0.68 / 0.84 | 0.000 | -12.1% | -1.6% |
| `ind_bb_ruptura@15m@v1` | 37.5% | 0.26 | 0.79 / 0.82 | 0.000 | -6.1% | -1.0% |
| `ind_donchian@15m@v1` | 25.0% | 0.30 | 0.82 / 0.89 | 0.001 | -6.3% | -0.9% |
| `consenso_fuerte@15m@v1` | 27.3% | 0.30 | 1.22 / 0.90 | 0.000 | -9.0% | +0.3% |
| `agente_levels@15m@v1` | 22.2% | 0.18 | 0.55 / 0.85 | 0.000 | -16.1% | -0.1% |
| `agente_technical@15m@v1` | 20.0% | 0.18 | 0.78 / 0.89 | 0.001 | -9.5% | -0.5% |
| `sugerencia_1@15m@v1` | 0.0% | 0.00 | 1.16 / 0.83 | 0.001 | -2.9% | +0.5% |
| `sugerencia_3@15m@v1` | 25.0% | 0.04 | 0.53 / 0.97 | 0.003 | -4.0% | +0.4% |
| `escenario_retroceso@4h@v1` | 0.0% | 0.00 | 0.37 / 1.00 | — | -2.2% | -18.5% |
| `escenario_dominante@15m@v1` | 0.0% | 0.00 | 1.20 / 0.78 | — | -2.4% | -0.1% |
| `agente_technical@1h@v1` | 0.0% | 0.00 | 0.42 / 1.00 | — | -1.4% | +0.9% |
| `plan_tp1@15m@v1` | 14.3% | 0.01 | 0.63 / 0.89 | 0.004 | -9.7% | +0.1% |
| `escenario_rango@15m@v1` | 0.0% | 0.00 | 1.14 / 1.00 | 0.000 | -6.7% | -0.2% |
| `plan_tp2@15m@v1` | 0.0% | 0.00 | 0.45 / 1.00 | 0.000 | -5.2% | -0.0% |
| `ind_adx@15m@v1` | 0.0% | 0.00 | 1.09 / 1.00 | — | -1.9% | -0.5% |
| `sugerencia_1@1h@v1` | 50.5% | 0.88 | 0.84 / 0.66 | 0.000 | -72.0% | +364.6% |
| `sugerencia_2@1h@v1` | 48.2% | 0.81 | 0.84 / 0.68 | 0.000 | -83.8% | +367.1% |
| `sugerencia_3@1h@v1` | 49.8% | 0.80 | 0.85 / 0.68 | 0.000 | -85.5% | +346.7% |
| `sugerencia_alineada@1h@v1` | 47.2% | 0.78 | 0.82 / 0.67 | 0.000 | -70.8% | +367.0% |
| `sugerencia_alineada@4h@v1` | 42.4% | 0.70 | 0.72 / 0.64 | 0.000 | -8.6% | -8.7% |
| `control_aleatorio@4h@v1` | 42.6% | 0.74 | 0.80 / 0.73 | 0.000 | -10.7% | -8.7% |
| `agente_structure@4h@v1` | 46.7% | 0.71 | 0.84 / 0.66 | 0.000 | -10.1% | -10.6% |
| `consenso_fuerte@4h@v1` | 45.6% | 0.71 | 1.09 / 0.72 | 0.000 | -11.8% | -8.4% |
| `ind_bb_reversion@4h@v1` | 47.9% | 0.67 | 0.85 / 0.73 | 0.000 | -9.5% | -10.8% |
| `ind_donchian@1h@v1` | 45.0% | 0.64 | 0.94 / 0.72 | 0.000 | -90.9% | +370.1% |
| `agente_vwap@1h@v1` | 46.2% | 0.63 | 0.86 / 0.70 | 0.000 | -73.0% | +196.7% |
| `agente_structure@1h@v1` | 45.4% | 0.62 | 0.83 / 0.71 | 0.000 | -97.7% | +210.7% |
| `escenario_rango@1h@v1` | 48.4% | 0.65 | 1.30 / 0.72 | 0.000 | -78.7% | +365.6% |
| `agente_ema@1h@v1` | 45.1% | 0.60 | 0.84 / 0.71 | 0.000 | -100.0% | +367.4% |
| `agente_price_action@4h@v1` | 40.9% | 0.61 | 0.85 / 0.73 | 0.000 | -20.9% | -8.9% |
| `agente_price_action@1h@v1` | 45.3% | 0.60 | 0.84 / 0.71 | 0.000 | -100.0% | +367.4% |
| `agente_ema@4h@v1` | 43.3% | 0.59 | 0.85 / 0.71 | 0.000 | -20.8% | -9.1% |
| `consenso_sintesis@1h@v1` | 45.4% | 0.58 | 0.84 / 0.71 | 0.000 | -99.9% | +367.8% |
| `ind_bb_ruptura@1h@v1` | 45.1% | 0.59 | 0.84 / 0.72 | 0.000 | -97.9% | +370.1% |
| `control_aleatorio@1h@v1` | 44.8% | 0.59 | 0.83 / 0.71 | 0.000 | -99.7% | +369.3% |
| `agente_levels@1h@v1` | 44.2% | 0.58 | 0.83 / 0.72 | 0.000 | -100.0% | +367.1% |
| `ind_cruce_ema@1h@v1` | 44.9% | 0.59 | 0.93 / 0.73 | 0.000 | -85.9% | +366.0% |
| `contra_sintesis@1h@v1` | 44.1% | 0.58 | 0.82 / 0.73 | 0.000 | -100.0% | +363.7% |
| `plan_tp1@4h@v1` | 38.1% | 0.60 | 0.83 / 0.76 | 0.001 | -6.2% | -6.0% |
| `ind_macd@1h@v1` | 43.7% | 0.53 | 0.83 / 0.73 | 0.000 | -95.4% | +365.4% |
| `ind_supertrend@1h@v1` | 41.3% | 0.53 | 0.89 / 0.73 | 0.000 | -86.7% | +284.6% |
| `consenso_fuerte@1h@v1` | 39.1% | 0.51 | 0.99 / 0.74 | 0.000 | -100.0% | +363.7% |
| `ind_bb_reversion@1h@v1` | 45.3% | 0.42 | 0.65 / 0.69 | 0.000 | -99.9% | +361.6% |
| `ind_rsi@1h@v1` | 40.2% | 0.48 | 0.74 / 0.76 | 0.000 | -95.7% | +248.5% |
| `plan_tp1@1h@v1` | 43.1% | 0.45 | 0.93 / 0.72 | 0.000 | -95.2% | +366.1% |
| `ind_adx@1h@v1` | 40.2% | 0.38 | 0.85 / 0.76 | 0.000 | -59.1% | +180.5% |
| `escenario_dominante@1h@v1` | 37.0% | 0.37 | 0.98 / 0.74 | 0.000 | -81.7% | +348.2% |
| `plan_tp2@1h@v1` | 36.4% | 0.34 | 1.03 / 0.74 | 0.000 | -88.3% | +370.1% |

## 6. Notas y riesgos conocidos

- Criterios fijados en el commit 18e7283 (2026-10-18 14:30 UTC); el primer cálculo con datos reales fue a las 15:16 UTC. Este informe usa el cálculo de las 23:14 UTC (datos hasta 23:00 UTC), con toda la historia reconstruida.
- Ventana de ajuste T48b excluida en las 87 versiones v1: 2026-08-16 00:00 → 2026-10-16 14:00 UTC, todos los símbolos (lo que se miró para elegir reglas en T47 y mecánica en T48b).
- Historia: 1 h reconstruida walk-forward desde 2023-01-11 (33 038 contextos, 28 945 nuevos en esta tarea); 4 h solo desde 2026-03-19 (el almacén empieza el 2026-02-05 y hacen falta 250 velas previas); 15 m sin reconstrucción (2026-09-16 → hoy, casi todo dentro de la ventana de ajuste): las 29 versiones @15m suman 202 operaciones fuera de muestra y quedan EN OBSERVACIÓN.
- Tramo en vivo solo desde el 2026-10-16 (50 contextos vivos de 1 h, 15 de 4 h, 163 de 15 m): V5 queda pendiente en todas; ninguna versión puede ser VALIDADA hasta reunir ≥ 20 operaciones en vivo (semanas en 1 h, meses en 4 h).
- 1 h: las 26 versiones con ≥ 100 operaciones fuera de muestra tienen R medio neto negativo y 25 son claramente negativas (R medio + 1·EE < 0) → RECHAZADA, al ciclo de mejora. La mejor, sugerencia_1@1h@v1 (n = 1 851), da −0,063 R con IC95 % [−0,111, −0,015]; las únicas cercanas a 0 (sugerencia_1/2@4h, escenario_retroceso@1h) no llegan a V1 en regímenes o tramo en vivo.
- V3 (réplica de lado aleatorio): en las familias con órdenes límite (sugerencias, retroceso y rango de escenarios) el p bruto ≈ 1, es decir, el lado reflejado rindió más que el elegido. Puede ser una elección de lado peor que el azar o una asimetría de la aproximación (la entrada límite se refleja alrededor de la apertura de 15 m de la decisión y cambia la probabilidad de llenado). No cambia ningún veredicto (esas versiones ya son claramente negativas); queda en BACKLOG revisarlo.
- Los contextos reconstruidos usan el código actual de los agentes sobre datos pasados (sin anticipación). Faltan context (LLM, sin titulares), OI histórico (derivatives) y microestructura: esas estrategias tienen pocas o ninguna señal. T26/T27 ya miraron 2023–2026 de 1 h con el agente plan (sin adoptar la calibración): riesgo menor de contaminación en las estrategias del plan.
- Holm sobre 87 intentos (3 480 réplicas por versión). Cada versión nueva suma un intento para siempre: el ciclo de mejora debe probar pocas versiones con razón económica previa.
