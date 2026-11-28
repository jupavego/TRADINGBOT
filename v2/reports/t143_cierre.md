# T143 — Cierre: la corrida aparte `t143` frente a T31

**Modo: SIMULADO.** Generado 2026-11-28 01:32 UTC desde los libros fijos que exporta la API viva (`GET /v2/paper/ledger.csv` y `GET /v2/paper/variant/t143/ledger.csv`, solo lectura). Ventana: operaciones abiertas entre 2026-11-10 04:17 UTC (despliegue de la corrida aparte, PR #243) y 2026-11-28 00:00 UTC (cierre de T31), y cerradas antes de esa hora. Universo oficial de T144 (`libro_perfiles`): perfiles, vivas, con peso y sin `retro`. Método en `eim/paper/run_compare.py`.

## 1. La cifra oficial

| Cifra | T31 (mesa principal) | t143 (corrida aparte) | t143 − T31 |
|---|--:|--:|--:|
| Operaciones que cuentan | 522 | 385 | -137 |
| Acierto | 84.1% | 79.7% | -4.4% |
| E[R] neto por operación | -0.033 | -0.082 | -0.050 |
| IC95 % de E[R] neto | [-0.071, +0.006] | [-0.131, -0.033] | |
| R total | -16.98 | -31.72 | -14.74 |
| Costo medio en R | +0.126 | +0.114 | -0.012 |
| E[R] bruto (neto + costo) | +0.093 | +0.031 | -0.062 |
| Salidas por SL inicial | 12.8% | 16.6% | 3.8% |
| PnL (USDT) | -973.5 | -1647.0 | -673.5 |
| Comisiones (USDT) | 1682.2 | 929.2 | -753.0 |
| Deslizamiento (USDT) | 1622.4 | 1022.4 | -600.1 |
| Funding (USDT) | -11.4 | -10.2 | +1.3 |
| Máximo descenso (USDT) | 1281.8 | 1969.8 | 688.1 |
| Huella de lo contado | `5c9188a14237` | `a76cf68a743e` | |

## 2. Por marco

| Marco | T31 n | T31 neto ± EE | T31 costo | T31 PnL | t143 n | t143 neto ± EE | t143 costo | t143 PnL |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 15m | 230 | -0.098 ± 0.035 | 0.155 | -1398.4 | 153 | -0.193 ± 0.045 | 0.157 | -1272.3 |
| 1h | 182 | -0.000 ± 0.031 | 0.122 | +169.7 | 144 | -0.024 ± 0.040 | 0.101 | -318.8 |
| 4h | 110 | +0.052 ± 0.027 | 0.070 | +255.1 | 88 | +0.015 ± 0.036 | 0.060 | -56.0 |

## 3. Por perfil

| Perfil | T31 n | T31 neto ± EE | T31 costo | T31 PnL | t143 n | t143 neto ± EE | t143 costo | t143 PnL |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| agresivo | 163 | -0.053 ± 0.033 | 0.138 | -882.4 | 118 | -0.111 ± 0.043 | 0.122 | -988.7 |
| moderado | 244 | -0.036 ± 0.028 | 0.120 | -105.0 | 204 | -0.095 ± 0.034 | 0.110 | -693.4 |
| ppp_btcusdt | 115 | +0.004 ± 0.047 | 0.120 | +13.9 | 63 | +0.013 ± 0.070 | 0.109 | +35.0 |

## 4. Por tipo de entrada

| Entrada | T31 n | T31 neto ± EE | T31 costo | T31 PnL | t143 n | t143 neto ± EE | t143 costo | t143 PnL |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| limit | 130 | +0.058 ± 0.032 | 0.096 | +535.5 | 271 | -0.016 ± 0.026 | 0.090 | -451.1 |
| market | 392 | -0.062 ± 0.024 | 0.135 | -1509.1 | 114 | -0.241 ± 0.054 | 0.170 | -1195.9 |

## 5. La misma operación en los dos libros

Clave: el mismo perfil y la misma idea (`idea_id`). Δ = t143 − T31 por operación.

| Marco | Pares | Δ neto ± EE | Δ costo ± EE | Δ bruto ± EE | Mismo motivo de salida | Tipo de entrada (T31→t143) |
|---|--:|--:|--:|--:|--:|---|
| 15m | 119 | -0.000 ± 0.002 | +0.000 ± 0.000 | -0.000 ± 0.002 | 119 | limit→limit 33, market→market 86 |
| 1h | 103 | -0.044 ± 0.029 | -0.016 ± 0.002 | -0.059 ± 0.030 | 97 | limit→limit 22, market→limit 81 |
| 4h | 66 | +0.003 ± 0.005 | -0.011 ± 0.001 | -0.008 ± 0.006 | 66 | limit→limit 12, market→limit 54 |
| todos | 288 | -0.015 ± 0.011 | -0.008 ± 0.001 | -0.023 ± 0.011 | 282 | limit→limit 67, market→limit 135, market→market 86 |

De los pares, **135 entraron a mercado en T31 y en límite en t143** (la conversión maker de 1 h y 4 h). Lo que cambió en ellos:

| Concepto | T31 | t143 |
|---|--:|--:|
| Comisiones (pb del nocional) | 9.99 | 6.99 |
| Deslizamiento (pb del nocional) | 9.40 | 9.05 |
| Precio de entrada mejor en t143 (pb) | | +0.08 |
| Retraso del llenado en t143 (min) | | +0.0 |

- **Misma salida (129 pares):** Δ neto +0.022 ± 0.007 R por operación.
- **Otra salida (6 pares):**
  - agresivo 1h: T31 «SLD» +0.00 R, t143 «SL» -1.09 R; cantidad 0.077 → 0.076; cierre 2026-11-17 17:06 UTC → 2026-11-17 21:45 UTC
  - agresivo 1h: T31 «SLD» +0.05 R, t143 «SL» -1.21 R; cantidad 0.236 → 0.11; cierre 2026-11-18 17:15 UTC → 2026-11-18 17:30 UTC
  - agresivo 1h: T31 «SLD» +0.14 R, t143 «SL» -1.11 R; cantidad 0.074 → 0.074; cierre 2026-11-27 15:02 UTC → 2026-11-27 15:45 UTC
  - moderado 1h: T31 «SLD» +0.14 R, t143 «SL» -1.11 R; cantidad 0.026 → 0.022; cierre 2026-11-27 15:02 UTC → 2026-11-27 15:45 UTC
  - moderado 1h: T31 «SLD» +0.14 R, t143 «SL» -1.11 R; cantidad 0.026 → 0.022; cierre 2026-11-27 15:02 UTC → 2026-11-27 15:45 UTC
  - ppp_btcusdt 1h: T31 «SLD» -0.03 R, t143 «SL» -1.11 R; cantidad 0.055 → 0.05; cierre 2026-11-27 15:03 UTC → 2026-11-27 15:45 UTC

## 6. Lo que tomó un libro y el otro no

| Solo en | Marco | n | E[R] neto ± EE | Salidas por SL | PnL (USDT) |
|---|---|--:|--:|--:|--:|
| T31 | 15m | 111 | -0.078 ± 0.051 | 18% | -620.3 |
| T31 | 1h | 79 | -0.037 ± 0.053 | 14% | -93.9 |
| T31 | 4h | 44 | +0.014 ± 0.054 | 9% | +94.8 |
| T31 | todos | 234 | -0.047 ± 0.032 | 15% | -619.4 |
| t143 | 15m | 34 | -0.460 ± 0.106 | 41% | -592.8 |
| t143 | 1h | 41 | -0.045 ± 0.083 | 17% | -330.6 |
| t143 | 4h | 22 | -0.178 ± 0.109 | 23% | -237.9 |
| t143 | todos | 97 | -0.220 ± 0.059 | 27% | -1161.2 |

## 7. Lectura

- **Cifra oficial: t143 -0.082 R por operación frente a -0.033 R de T31** (385 y 522 operaciones; PnL -1647.0 frente a -973.5 USDT). La corrida aparte no mejora el resultado oficial.
- **Sobre las mismas operaciones (288 pares), el costo baja 0.0082 R** (1 h -0.0156, 4 h -0.0113), lejos de los 0.0432 R que esperaba el banco y del criterio de 0.04 R. El neto emparejado cambia -0.015 ± 0.011 R y su IC95 % incluye el 0: en las operaciones comunes la ejecución no se distingue.
- **La entrada maker hace lo que debía, pero ahorra menos de lo previsto.** En las 135 convertidas la comisión baja de 10.0 a 7.0 pb y el deslizamiento casi no cambia (9.4 → 9.0 pb): casi todo el deslizamiento es de la salida, no de la entrada. Con la misma salida ganan +0.022 ± 0.007 R por operación. **6 pares cambiaron de salida y restan -7.19 R en total**: entraron al mismo precio y en el mismo minuto, así que no es la entrada lo que los separa (§5).
- **La diferencia está en la composición:** t143 tomó 97 operaciones que T31 no tomó, con -0.220 R de media y 27% de salidas por SL, y dejó de tomar 234 que T31 sí tomó (-0.047 R).
- **Puerta de marcos (umbral 0.15 R):** 1 celda operó con un costo vivido igual o mayor al umbral: agresivo·15m 0.185 R (n = 42). La puerta decide con la sombra calibrada, no con lo vivido.

## 8. Lo que esta comparación no cubre

- **El R no ve el riesgo con costo de forma directa.** `r` es PnL entre el riesgo de precio al SL en los dos libros, y `risk_includes_costs` solo reduce la cantidad (×0,85). Pero la cantidad sí puede cambiar la salida cuando la protección se mide en USDT (escalones de PPP, BE+ con costo): es uno de los candidatos de los pares que cambiaron de salida, sin confirmar aquí.
- **Los dos libros divergen por su propia historia**: pesos de realimentación, posiciones ocupadas y límites sin llenar hacen que cada uno tome operaciones distintas. Por eso la §5 (lo común) y la §6 (lo distinto) van aparte.
- **La corrida aparte cambió dos veces durante la ventana**: la puerta pasó a medir solo lo tomable el 2026-11-10 (PR #246) y a decidir por perfil y marco el 2026-11-17 (T179).
- **Muestra corta**: unas tres semanas y unos cientos de operaciones; los EE están en cada tabla.
