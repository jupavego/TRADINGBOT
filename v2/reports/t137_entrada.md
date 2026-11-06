# T137 — La entrada: SL inicial más amplio y tope de costo, por la puerta de T49

Modo: **SIMULADO** · BTCUSDT · datos hasta 2026-11-03T18:00+00:00 · pre-registro `prereg_t137_v1` (SHA-256 `a5713685b9a67c0d…`, commit `213247f`, anterior a todo cálculo) · criterios `validation_v1` sin cambios · calculado con `f569129` · 520 intentos nuevos, familia de Holm de 832.

## 1. Veredicto (lectura oficial)

**Ninguna versión validada.** Es un resultado válido.

De 520 versiones: 484 EN OBSERVACIÓN · 36 RECHAZADA.

Criterios que más fallan en la lectura oficial:

- V1 Suficiencia de datos: 520 versiones
- V3 Contra el azar: 245 versiones
- V2 Expectativa neta: 170 versiones
- V6 Costos: 16 versiones
- V4 Drawdown: 5 versiones

Llegan al mínimo de V1 (≥ 100 operaciones y ≥ 2 regímenes con ≥ 20): **0** de 520. Ninguna versión puede salir VALIDADA en esta corrida: no hay tramo en vivo, así que V5 queda pendiente, y eso se fijó antes de calcular.

## 2. Las tres lecturas, agregadas por variante

Agregan todas las estrategias: sirven para ver si la geometría cambia algo, no para validar nada. La versión padre es la vigente, con las mismas ventanas.

### Oficial (T49 tal cual, la única que da veredicto)

Da el veredicto. Se sabe antes de calcular que queda muy corta: 2026-10-22T22:36Z → 2026-11-03, unos 11 días. Casi con seguridad ninguna versión llegará a V1, y eso es lo que dice la regla de T49 con los datos que hay.

Veredictos de la puerta: 484 EN OBSERVACIÓN · 36 RECHAZADA. Falla más: V1 (520), V3 (245), V2 (170), V6 (16). Llegan a V1: 0.

| Variante | Marco | n | E[R] | Acierto | PF | Costo R | Bruto R |
|---|---|--:|--:|--:|--:|--:|--:|
| padre (sin cambios) | 15m | 1084 | -0.508 | 33.0 % | 0.467 | 0.392 | -0.116 |
| padre (sin cambios) | 1h | 395 | -0.334 | 46.3 % | 0.476 | 0.191 | -0.143 |
| padre (sin cambios) | 4h | 84 | -0.319 | 46.4 % | 0.430 | 0.097 | -0.222 |
| padre (sin cambios) | todos | 1563 | -0.454 | 37.1 % | 0.468 | 0.325 | -0.128 |
| m8 | 15m | 968 | -0.375 | 38.8 % | 0.527 | 0.304 | -0.071 |
| m8 | 1h | 294 | -0.308 | 40.8 % | 0.502 | 0.140 | -0.168 |
| m8 | 4h | 73 | -0.230 | 46.6 % | 0.548 | 0.081 | -0.150 |
| m8 | todos | 1335 | -0.352 | 39.7 % | 0.523 | 0.255 | -0.097 |
| s1 | 15m | 834 | -0.218 | 48.6 % | 0.597 | 0.177 | -0.041 |
| s1 | 1h | 352 | -0.286 | 45.5 % | 0.536 | 0.168 | -0.118 |
| s1 | 4h | 83 | -0.310 | 47.0 % | 0.439 | 0.096 | -0.215 |
| s1 | todos | 1269 | -0.243 | 47.6 % | 0.568 | 0.169 | -0.074 |
| tope | 15m | 0 | — | — | — | — | — |
| tope | 1h | 3 | -0.212 | 33.3 % | 0.192 | 0.040 | -0.172 |
| tope | 4h | 15 | +0.013 | 73.3 % | 1.067 | 0.047 | +0.060 |
| tope | todos | 18 | -0.024 | 66.7 % | 0.884 | 0.046 | +0.022 |
| m8_tope | 15m | 2 | -0.025 | 50.0 % | 0.945 | 0.035 | +0.010 |
| m8_tope | 1h | 40 | +0.132 | 55.0 % | 1.718 | 0.041 | +0.173 |
| m8_tope | 4h | 34 | -0.003 | 58.8 % | 0.991 | 0.042 | +0.039 |
| m8_tope | todos | 76 | +0.068 | 56.6 % | 1.272 | 0.041 | +0.109 |
| s1_tope | 15m | 0 | — | — | — | — | — |
| s1_tope | 1h | 3 | -0.212 | 33.3 % | 0.192 | 0.040 | -0.172 |
| s1_tope | 4h | 15 | +0.013 | 73.3 % | 1.067 | 0.047 | +0.060 |
| s1_tope | todos | 18 | -0.024 | 66.7 % | 0.884 | 0.046 | +0.022 |

### Reserva (datos donde no se eligió nada; descriptiva)

Descriptiva. Los datos en los que no se eligió la geometría ni se ajustaron las reglas de T48b. No aplica la ventana automática, así que no puede dar veredicto. T111 y T129 sí vieron de forma agregada parte del segundo tramo.

Veredictos de la puerta: 431 EN OBSERVACIÓN · 89 RECHAZADA. Falla más: V1 (520), V3 (298), V2 (247), V4 (20). Llegan a V1: 0.

| Variante | Marco | n | E[R] | Acierto | PF | Costo R | Bruto R |
|---|---|--:|--:|--:|--:|--:|--:|
| padre (sin cambios) | 15m | 1707 | -0.454 | 34.5 % | 0.507 | 0.387 | -0.067 |
| padre (sin cambios) | 1h | 1654 | -0.310 | 46.1 % | 0.516 | 0.217 | -0.092 |
| padre (sin cambios) | 4h | 458 | -0.278 | 45.6 % | 0.523 | 0.101 | -0.177 |
| padre (sin cambios) | todos | 3819 | -0.371 | 40.9 % | 0.512 | 0.279 | -0.091 |
| m8 | 15m | 1522 | -0.342 | 39.9 % | 0.557 | 0.304 | -0.039 |
| m8 | 1h | 1294 | -0.237 | 44.0 % | 0.582 | 0.144 | -0.093 |
| m8 | 4h | 429 | -0.272 | 45.2 % | 0.523 | 0.092 | -0.180 |
| m8 | todos | 3245 | -0.291 | 42.2 % | 0.562 | 0.212 | -0.079 |
| s1 | 15m | 1333 | -0.218 | 48.0 % | 0.597 | 0.178 | -0.040 |
| s1 | 1h | 1533 | -0.284 | 45.3 % | 0.544 | 0.189 | -0.095 |
| s1 | 4h | 457 | -0.280 | 45.5 % | 0.521 | 0.101 | -0.179 |
| s1 | todos | 3323 | -0.257 | 46.4 % | 0.561 | 0.172 | -0.084 |
| tope | 15m | 0 | — | — | — | — | — |
| tope | 1h | 4 | -0.143 | 50.0 % | 0.273 | 0.040 | -0.102 |
| tope | 4h | 61 | -0.433 | 36.1 % | 0.248 | 0.061 | -0.372 |
| tope | todos | 65 | -0.415 | 36.9 % | 0.248 | 0.060 | -0.355 |
| m8_tope | 15m | 2 | -0.025 | 50.0 % | 0.945 | 0.035 | +0.010 |
| m8_tope | 1h | 108 | -0.046 | 46.3 % | 0.855 | 0.046 | -0.000 |
| m8_tope | 4h | 146 | -0.215 | 44.5 % | 0.555 | 0.051 | -0.164 |
| m8_tope | todos | 256 | -0.143 | 45.3 % | 0.656 | 0.049 | -0.094 |
| s1_tope | 15m | 0 | — | — | — | — | — |
| s1_tope | 1h | 4 | -0.143 | 50.0 % | 0.273 | 0.040 | -0.102 |
| s1_tope | 4h | 61 | -0.433 | 36.1 % | 0.248 | 0.061 | -0.372 |
| s1_tope | todos | 65 | -0.415 | 36.9 % | 0.248 | 0.060 | -0.355 |

### Banco (donde se eligió la geometría: cota optimista, descriptiva)

Descriptiva y contaminada a favor: es la ventana donde se eligió la geometría. Sirve de cota optimista, porque lo que falla aquí no pasaría en datos limpios; lo que pasa aquí no demuestra nada.

Veredictos de la puerta: 223 EN OBSERVACIÓN · 142 RECHAZADA. Falla más: V3 (310), V2 (296), V1 (263), V5 (148). Llegan a V1: 102.

| Variante | Marco | n | E[R] | Acierto | PF | Costo R | Bruto R |
|---|---|--:|--:|--:|--:|--:|--:|
| padre (sin cambios) | 1h | 28689 | -0.156 | 49.1 % | 0.727 | 0.155 | -0.001 |
| padre (sin cambios) | 4h | 1139 | -0.076 | 50.7 % | 0.851 | 0.083 | +0.007 |
| padre (sin cambios) | todos | 29828 | -0.152 | 49.2 % | 0.731 | 0.152 | -0.000 |
| m8 | 1h | 22250 | -0.093 | 50.0 % | 0.809 | 0.098 | +0.004 |
| m8 | 4h | 1139 | -0.076 | 50.7 % | 0.851 | 0.083 | +0.007 |
| m8 | todos | 23389 | -0.093 | 50.0 % | 0.811 | 0.097 | +0.005 |
| s1 | 1h | 26469 | -0.123 | 49.6 % | 0.775 | 0.132 | +0.009 |
| s1 | 4h | 1141 | -0.071 | 50.7 % | 0.860 | 0.082 | +0.010 |
| s1 | todos | 27610 | -0.121 | 49.7 % | 0.778 | 0.130 | +0.009 |
| tope | 1h | 3602 | -0.119 | 47.4 % | 0.765 | 0.071 | -0.048 |
| tope | 4h | 573 | -0.105 | 48.5 % | 0.789 | 0.064 | -0.041 |
| tope | todos | 4175 | -0.117 | 47.6 % | 0.768 | 0.070 | -0.047 |
| m8_tope | 1h | 8431 | -0.057 | 50.1 % | 0.865 | 0.054 | -0.003 |
| m8_tope | 4h | 573 | -0.105 | 48.5 % | 0.789 | 0.064 | -0.041 |
| m8_tope | todos | 9004 | -0.060 | 50.0 % | 0.859 | 0.054 | -0.005 |
| s1_tope | 1h | 4388 | -0.080 | 49.7 % | 0.836 | 0.067 | -0.013 |
| s1_tope | 4h | 576 | -0.112 | 48.1 % | 0.776 | 0.064 | -0.048 |
| s1_tope | todos | 4964 | -0.083 | 49.5 % | 0.829 | 0.066 | -0.017 |

## 3. Lo que deja fuera el tope de 0,08 R

El tope se mide sobre el SL de la versión. «Ideas» son las candidatas desde 2024-01-11; «operaciones» compara lo que cerró cada versión con su gemela sin tope, en el banco (1 h y 4 h) y en todo el tramo de 15 m.

| Variante | Marco | Ideas | SL movido | Vetadas | Costo ex ante R |
|---|---|--:|--:|--:|--:|
| padre | 15m | 43634 | 0.0 % | 0.0 % | 0.490 |
| padre | 1h | 262718 | 0.0 % | 0.0 % | 0.183 |
| padre | 4h | 15455 | 0.0 % | 0.0 % | 0.102 |
| m8 | 15m | 43634 | 18.8 % | 0.0 % | 0.459 |
| m8 | 1h | 262718 | 87.4 % | 0.0 % | 0.133 |
| m8 | 4h | 15455 | 13.7 % | 0.0 % | 0.098 |
| s1 | 15m | 43634 | 98.8 % | 0.0 % | 0.260 |
| s1 | 1h | 262718 | 30.7 % | 0.0 % | 0.159 |
| s1 | 4h | 15455 | 4.1 % | 0.0 % | 0.101 |
| tope | 15m | 43634 | 0.0 % | 100.0 % | 0.490 |
| tope | 1h | 262718 | 0.0 % | 89.9 % | 0.183 |
| tope | 4h | 15455 | 0.0 % | 68.1 % | 0.102 |
| m8_tope | 15m | 43634 | 18.8 % | 100.0 % | 0.459 |
| m8_tope | 1h | 262718 | 87.4 % | 74.6 % | 0.133 |
| m8_tope | 4h | 15455 | 13.7 % | 62.3 % | 0.098 |
| s1_tope | 15m | 43634 | 98.8 % | 100.0 % | 0.260 |
| s1_tope | 1h | 262718 | 30.7 % | 88.2 % | 0.159 |
| s1_tope | 4h | 15455 | 4.1 % | 67.6 % | 0.101 |

Versiones **inertes**, en las que la geometría no movió ni un SL y son su padre con otro nombre (cuentan como intentos, pero no ponen a prueba nada): m8 57, s1 18, m8_tope 57, s1_tope 18. M8 lo es cuando la estrategia@marco no llega a 30 ganadoras en el tramo de ajuste, y S1 cuando su stop ya estaba más lejos de 3 ATR de 15 m.

| Con tope | Sin tope | Operaciones con tope | Sin tope | Quedan fuera |
|---|---|--:|--:|--:|
| tope (1 h y 4 h, banco) | base | 4175 | 29828 | 86.0 % |
| tope (15 m, todo) | base | 0 | 4712 | 100.0 % |
| m8_tope (1 h y 4 h, banco) | m8 | 9004 | 23389 | 61.5 % |
| m8_tope (15 m, todo) | m8 | 2 | 4527 | 100.0 % |
| s1_tope (1 h y 4 h, banco) | s1 | 4964 | 27610 | 82.0 % |
| s1_tope (15 m, todo) | s1 | 0 | 3654 | 100.0 % |

## 4. Control con entradas al azar

Sobre `control_aleatorio@1h`. El cuantil de M8 sale de `consenso_sintesis@1h`, que tiene sus mismas salidas (`control_aleatorio` no llega a la muestra mínima). Si el bruto destacara sobre las series sustitutas habría anticipación o un error.

| Variante | n real | SL movido (real / sustitutas) | Bruto real | Nulo: media | p95 | p | ¿La pone a prueba? | ¿Pasa? |
|---|--:|--:|--:|--:|--:|--:|---|---|
| padre | 1810 | 0 % / 0 % | -0.010 | +0.004 | +0.096 | 0.524 | sí | ✓ |
| m8 | 1440 | 92 % / 76 % | +0.012 | -0.010 | +0.079 | 0.381 | sí | ✓ |
| s1 | 1690 | 41 % / 48 % | +0.001 | +0.001 | +0.108 | 0.476 | sí | ✓ |
| tope | 110 | 0 % / 0 % | -0.150 | +0.033 | +0.220 | 0.857 | sí | ✓ |
| m8_tope | 339 | 92 % / 76 % | -0.037 | +0.031 | +0.221 | 0.714 | sí | ✓ |
| s1_tope | 151 | 41 % / 48 % | -0.160 | +0.033 | +0.220 | 0.857 | sí | ✓ |

## 5. 15 m

Hay contextos desde 2026-09-16, aunque el banco de T131 no los lleve. Además de contar en las lecturas oficial y de reserva, se informa de todo el tramo con contextos, de forma descriptiva: costo en R ex ante y realizado, cuánto deja fuera el tope y E[R] por variante. M8 solo aparta el stop desde 2026-10-16T14:00Z.

| Variante | Tramo | n | E[R] | Acierto | PF | Costo R | Bruto R |
|---|---|--:|--:|--:|--:|--:|--:|
| padre | todo | 4712 | -0.401 | 36.4 % | 0.548 | 0.379 | -0.022 |
| padre | desde 2026-10-16 | 1707 | -0.454 | 34.5 % | 0.507 | 0.387 | -0.067 |
| m8 | todo | 4527 | -0.361 | 38.3 % | 0.568 | 0.351 | -0.010 |
| m8 | desde 2026-10-16 | 1522 | -0.342 | 39.9 % | 0.557 | 0.304 | -0.039 |
| s1 | todo | 3654 | -0.172 | 49.3 % | 0.659 | 0.175 | +0.003 |
| s1 | desde 2026-10-16 | 1333 | -0.218 | 48.0 % | 0.597 | 0.178 | -0.040 |
| tope | todo | 0 | — | — | — | — | — |
| tope | desde 2026-10-16 | 0 | — | — | — | — | — |
| m8_tope | todo | 2 | -0.025 | 50.0 % | 0.945 | 0.035 | +0.010 |
| m8_tope | desde 2026-10-16 | 2 | -0.025 | 50.0 % | 0.945 | 0.035 | +0.010 |
| s1_tope | todo | 0 | — | — | — | — | — |
| s1_tope | desde 2026-10-16 | 0 | — | — | — | — | — |

## 6. Regresión contra T134 y T136

Con M0 y el mismo código de geometría, sobre los tramos de prueba de T134. Si no coincidiera, lo medido aquí no sería la geometría que dio la señal.

| Caso | n | E[R] | Publicado n | Publicado E[R] | ¿Coincide? |
|---|--:|--:|--:|--:|---|
| `M0 first_r=0.1` | 29828 | -0.153823 | 29828 | -0.153823 | ✓ |
| `M8 q=0.95` | 29841 | -0.104489 | 29841 | -0.104489 | ✓ |
| `S1 d_min_sigma=3 sigma=atr14` | 29841 | -0.134444 | 29841 | -0.134444 | ✓ |
| `tope 0.08` | 3216 | -0.055692 | 3216 | -0.055692 | ✓ |
| `padre con su propia sombra (M1)` | 29828 | -0.152490 | 29828 | -0.152490 | ✓ |

**Las unidades de M8 no coinciden, y se conserva así a propósito.** T134 estima el cuantil en σ de Parkinson y lo aplica sobre σ ATR14, con una mediana de ATR14/Parkinson de 1.377: el stop queda más lejos de lo que dice `q`. Es la geometría que dio la señal, así que es la que se evalúa; corregirla sería otra variante y otros intentos (BACKLOG).

## 7. Por versión

Cada criterio de las 520 versiones en las tres lecturas está en `reports/t137_entrada.csv`. Aquí, las de mayor R medio con ≥ 100 operaciones.

### Oficial (T49 tal cual, la única que da veredicto)

Ninguna versión llega a 100 operaciones.

### Reserva (datos donde no se eligió nada; descriptiva)

| Versión | Variante | Veredicto | n | R medio | IC95 % | p Holm | DD | Costo R | V1 | V2 | V3 | V4 | V5 | V6 |
|---|---|---|--:|--:|---|--:|--:|--:|---|---|---|---|---|---|
| `agente_price_action@15m@v1372` | s1 | RECHAZADA | 107 | -0.154 | [-0.36, +0.04] | 1.000 | 16 % | 0.175 | ✗ | ✗ | ✗ | ✓ | · | ✓ |
| `consenso_sintesis@15m@v1371` | m8 | RECHAZADA | 100 | -0.213 | [-0.44, +0.03] | 1.000 | 25 % | 0.251 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `agente_levels@15m@v1371` | m8 | RECHAZADA | 109 | -0.263 | [-0.45, -0.08] | 1.000 | 27 % | 0.259 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `base_tendencia@1h@v1372` | s1 | RECHAZADA | 108 | -0.266 | [-0.44, -0.08] | 1.000 | 26 % | 0.177 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `agente_price_action@15m@v1371` | m8 | RECHAZADA | 141 | -0.299 | [-0.56, -0.05] | 1.000 | 35 % | 0.320 | ✗ | ✗ | ✗ | ✗ | · | ✗ |
| `agente_levels@1h@v1372` | s1 | RECHAZADA | 123 | -0.306 | [-0.48, -0.13] | 1.000 | 33 % | 0.209 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `agente_ema@15m@v1372` | s1 | RECHAZADA | 100 | -0.310 | [-0.45, -0.16] | 1.000 | 28 % | 0.192 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `base_tendencia@15m@v1371` | m8 | RECHAZADA | 107 | -0.320 | [-0.50, -0.14] | 1.000 | 30 % | 0.220 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `base_tendencia@15m@v1372` | s1 | RECHAZADA | 101 | -0.321 | [-0.50, -0.14] | 1.000 | 28 % | 0.191 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `agente_ema@1h@v1372` | s1 | RECHAZADA | 112 | -0.321 | [-0.49, -0.16] | 1.000 | 31 % | 0.205 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `agente_price_action@1h@v1372` | s1 | RECHAZADA | 124 | -0.328 | [-0.52, -0.14] | 1.000 | 36 % | 0.219 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `contra_sintesis@15m@v1371` | m8 | RECHAZADA | 105 | -0.336 | [-0.59, -0.07] | 1.000 | 30 % | 0.306 | ✗ | ✗ | ✗ | ✗ | · | ✗ |
| `agente_ema@15m@v1371` | m8 | RECHAZADA | 116 | -0.338 | [-0.54, -0.15] | 1.000 | 34 % | 0.248 | ✗ | ✗ | ✗ | ✗ | · | ✓ |

### Banco (donde se eligió la geometría: cota optimista, descriptiva)

| Versión | Variante | Veredicto | n | R medio | IC95 % | p Holm | DD | Costo R | V1 | V2 | V3 | V4 | V5 | V6 |
|---|---|---|--:|--:|---|--:|--:|--:|---|---|---|---|---|---|
| `contra_sintesis@1h@v1373` | tope | RECHAZADA | 146 | +0.059 | [-0.13, +0.25] | 1.000 | 10 % | 0.082 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `ppp_tendencia@1h@v1371` | m8 | EN OBSERVACIÓN | 237 | +0.005 | [-0.12, +0.13] | 1.000 | 10 % | 0.099 | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `sugerencia_2@1h@v1374` | m8_tope | RECHAZADA | 607 | -0.008 | [-0.07, +0.06] | 1.000 | 15 % | 0.038 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `sugerencia_1@1h@v1371` | m8 | RECHAZADA | 988 | -0.011 | [-0.07, +0.05] | 1.000 | 31 % | 0.055 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `base_tendencia@1h@v1375` | s1_tope | RECHAZADA | 365 | -0.012 | [-0.11, +0.09] | 1.000 | 19 % | 0.073 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `base_tendencia@1h@v1373` | tope | RECHAZADA | 361 | -0.013 | [-0.11, +0.09] | 1.000 | 21 % | 0.074 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `sugerencia_2@1h@v1375` | s1_tope | RECHAZADA | 324 | -0.014 | [-0.12, +0.09] | 1.000 | 18 % | 0.056 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `sugerencia_1@1h@v1374` | m8_tope | RECHAZADA | 645 | -0.016 | [-0.08, +0.05] | 1.000 | 27 % | 0.039 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `sugerencia_3@1h@v1373` | tope | RECHAZADA | 262 | -0.018 | [-0.13, +0.10] | 1.000 | 20 % | 0.059 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `ppp_tendencia@1h@v1372` | s1 | EN OBSERVACIÓN | 258 | -0.021 | [-0.16, +0.11] | 1.000 | 16 % | 0.124 | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `ind_bb_ruptura@1h@v1374` | m8_tope | RECHAZADA | 203 | -0.027 | [-0.15, +0.10] | 1.000 | 13 % | 0.055 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `agente_price_action@1h@v1374` | m8_tope | RECHAZADA | 511 | -0.032 | [-0.11, +0.05] | 1.000 | 25 % | 0.059 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `ind_bb_reversion@1h@v1374` | m8_tope | RECHAZADA | 222 | -0.037 | [-0.15, +0.08] | 1.000 | 11 % | 0.059 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `sugerencia_alineada@1h@v1374` | m8_tope | RECHAZADA | 526 | -0.040 | [-0.11, +0.03] | 1.000 | 26 % | 0.038 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `base_tendencia@1h@v1371` | m8 | RECHAZADA | 1361 | -0.041 | [-0.09, +0.01] | 1.000 | 56 % | 0.078 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `agente_structure@1h@v1374` | m8_tope | RECHAZADA | 405 | -0.045 | [-0.14, +0.04] | 1.000 | 26 % | 0.057 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `sugerencia_1@1h@v1372` | s1 | RECHAZADA | 1240 | -0.046 | [-0.11, +0.01] | 1.000 | 53 % | 0.083 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `consenso_sintesis@1h@v1374` | m8_tope | RECHAZADA | 446 | -0.046 | [-0.13, +0.04] | 1.000 | 28 % | 0.058 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `sugerencia_alineada@1h@v1371` | m8 | RECHAZADA | 649 | -0.047 | [-0.12, +0.02] | 1.000 | 31 % | 0.045 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `ind_bb_reversion@1h@v1375` | s1_tope | RECHAZADA | 124 | -0.049 | [-0.21, +0.11] | 1.000 | 12 % | 0.066 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `sugerencia_1@1h@v1373` | tope | RECHAZADA | 444 | -0.050 | [-0.15, +0.05] | 1.000 | 28 % | 0.058 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `base_retroceso@1h@v1371` | m8 | RECHAZADA | 1186 | -0.050 | [-0.10, +0.00] | 1.000 | 56 % | 0.071 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `agente_levels@1h@v1375` | s1_tope | RECHAZADA | 212 | -0.050 | [-0.18, +0.08] | 1.000 | 19 % | 0.073 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `ind_supertrend@1h@v1374` | m8_tope | RECHAZADA | 148 | -0.051 | [-0.20, +0.11] | 1.000 | 15 % | 0.058 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `agente_structure@1h@v1371` | m8 | RECHAZADA | 951 | -0.051 | [-0.12, +0.01] | 1.000 | 55 % | 0.087 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `base_retroceso@1h@v1374` | m8_tope | RECHAZADA | 594 | -0.051 | [-0.12, +0.02] | 1.000 | 35 % | 0.049 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `agente_price_action@1h@v1375` | s1_tope | RECHAZADA | 230 | -0.051 | [-0.18, +0.08] | 1.000 | 16 % | 0.071 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `sugerencia_3@1h@v1375` | s1_tope | RECHAZADA | 294 | -0.052 | [-0.16, +0.06] | 1.000 | 19 % | 0.058 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `ind_donchian@1h@v1373` | tope | RECHAZADA | 140 | -0.052 | [-0.24, +0.13] | 1.000 | 22 % | 0.077 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `sugerencia_1@1h@v1375` | s1_tope | RECHAZADA | 444 | -0.053 | [-0.15, +0.04] | 1.000 | 30 % | 0.056 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `agente_ema@1h@v1374` | m8_tope | RECHAZADA | 511 | -0.053 | [-0.13, +0.03] | 1.000 | 33 % | 0.058 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `contra_sintesis@1h@v1375` | s1_tope | RECHAZADA | 208 | -0.055 | [-0.20, +0.09] | 1.000 | 19 % | 0.079 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `agente_levels@1h@v1374` | m8_tope | RECHAZADA | 510 | -0.059 | [-0.14, +0.02] | 1.000 | 36 % | 0.059 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `agente_vwap@1h@v1371` | m8 | RECHAZADA | 345 | -0.063 | [-0.17, +0.04] | 1.000 | 24 % | 0.095 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `agente_ema@1h@v1371` | m8 | RECHAZADA | 1552 | -0.064 | [-0.11, -0.01] | 1.000 | 70 % | 0.100 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `sugerencia_3@1h@v1374` | m8_tope | RECHAZADA | 530 | -0.065 | [-0.14, +0.01] | 1.000 | 39 % | 0.044 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `base_retroceso@1h@v1372` | s1 | RECHAZADA | 1395 | -0.066 | [-0.13, -0.01] | 1.000 | 70 % | 0.099 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `base_retroceso@1h@v1375` | s1_tope | RECHAZADA | 270 | -0.067 | [-0.18, +0.05] | 1.000 | 28 % | 0.064 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `sugerencia_2@1h@v1373` | tope | RECHAZADA | 318 | -0.072 | [-0.19, +0.04] | 1.000 | 29 % | 0.061 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `base_retroceso@1h@v1373` | tope | RECHAZADA | 268 | -0.073 | [-0.19, +0.04] | 1.000 | 25 % | 0.064 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |

## 8. Regla de lectura para la ◆

Ninguna versión cumple la regla fijada en el pre-registro para proponer seguimiento prospectivo.
