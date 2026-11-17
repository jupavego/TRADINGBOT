# T177 — Examen físico de los prospectos en la historia

**Modo: SIMULADO.** Sin rendimiento: este informe no calcula ni muestra R neto, acierto ni PF (regla 5 de la nota de T167 §3). La historia no asciende a nadie; solo descarta por razones mecánicas, con los umbrales fijados en `PLAN/T169.md` antes de correr.

**15 prospectos con historia examinados** de 15: **1 descartados** por razones mecánicas y 14 siguen, de los que 8 quedan «sin opción a primer equipo» (no llegan a ≈ 100 operaciones, o a 120 días con posición, en 6 meses). 6 cambian de banda por su tenencia.

- **0 descartes dependen de la reasignación de banda**: con la banda declarada seguirían (ninguno).
- **0 reglas no se cumplen nunca** en la muestra (ninguno): la causa de cada una está en `PLAN/notas/T177_bibliografia_prospectos.md`.
- **Gemelos físicos** (mismas ideas y operaciones): ninguno.

Muestra: 4h 7876 contextos de 7876 en 1 tramo (1312,7 días); 1h 10752 contextos de 10752 en 16 tramos (448,0 días).

Costo de generación (un proceso, en IDLE, por la cola): 4h 7876 contextos a 0,189 s; 1h 7328 contextos a 0,552 s → **1,5 h de cálculo** (0,06 días de máquina) en 2 pasadas; RAM máxima 135 MB. Los otros 3424 contextos salieron de pasadas de prueba anteriores al registro de costo.

## Prospectos con historia

«Operaciones» son órdenes llenadas (una a la vez); «No llenadas», las límite que vencieron sin llenarse; «Por bloque», la cadencia mínima · mediana · máxima de los bloques de 28 días; «En posición», la fracción de días con posición abierta.

| Prospecto | Marco | Banda | Ideas | Operaciones | No llenadas | Al mes | Por bloque | Costo medio (R) | Tenencia mediana (h) | En posición (días) | Rotación (× capital/mes) | Estado |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| `elliott_oscilacion` | 4h | intradia (declarada tres_dias) | 1175 | 650 | 4 | 14,9 | 5,4 · 12,9 · 35,4 | 0,070 | 8,0 | 69% | 12,1 | sin opción a primer equipo |
| `elliott_dow` | 4h | intradia (declarada tres_dias) | 875 | 589 | 5 | 13,5 | 4,3 · 12,9 · 32,1 | 0,069 | 9,2 | 68% | 11,0 | sin opción a primer equipo |
| `elliott_tendencia_dow` | 4h | tres_dias | 300 | 207 | 0 | 4,7 | 0,0 · 4,3 · 10,7 | 0,065 | 48,0 | 36% | 3,8 | **descartado** |
| `ema_precio_200` | 4h | tres_dias | 7876 | 221 | 0 | 5,1 | 0,0 · 5,4 · 15,0 | 0,111 | 24,0 | 100% | 5,2 | sin opción a primer equipo |
| `ema_cruce_21_55` | 1h | intradia (declarada tres_dias) | 201 | 158 | 1 | 10,6 | 4,3 · 10,7 · 17,1 | 0,157 | 9,2 | 63% | 20,1 | sin opción a primer equipo |
| `ema_retroceso_12h` | 1h | intradia | 195 | 142 | 2 | 9,5 | 5,4 · 9,6 · 15,0 | 0,175 | 11,8 | 34% | 20,1 | sin opción a primer equipo |
| `niveles_redondos` | 1h | intradia | 1013 | 262 | 4 | 17,5 | 2,1 · 18,2 · 28,9 | 0,139 | 11,4 | 57% | 29,8 | sigue |
| `lit_consenso_4h` | 4h | tres_dias | 840 | 429 | 0 | 9,8 | 4,3 · 9,6 · 15,0 | 0,081 | 48,0 | 69% | 9,7 | sin opción a primer equipo |
| `estructura_ruptura_sc02` | 1h | intradia | 505 | 261 | 4 | 17,5 | 2,1 · 19,3 · 28,9 | 0,167 | 10,5 | 49% | 38,2 | sigue |
| `estructura_cambio_sc04` | 1h | intradia | 1114 | 540 | 13 | 36,2 | 27,9 · 36,4 · 47,1 | 0,163 | 12,0 | 86% | 79,7 | sigue |
| `tec_acuerdo_tres_marcos` | 1h | scalping (declarada intradia) | 1496 | 533 | 7 | 35,7 | 27,9 · 35,4 · 45,0 | 0,128 | 2,0 | 61% | 65,3 | sigue |
| `tec_rsi_giro` | 1h | intradia | 680 | 496 | 8 | 33,2 | 26,8 · 33,2 · 38,6 | 0,153 | 12,0 | 90% | 63,2 | sigue |
| `tec_compresion_bb_12h` | 1h | intradia | 221 | 206 | 2 | 13,8 | 9,6 · 12,9 · 19,3 | 0,187 | 8,6 | 53% | 32,6 | sin opción a primer equipo |
| `vwap_reversion_1h` | 1h | scalping (declarada intradia) | 2087 | 1007 | 17 | 67,4 | 54,6 · 67,5 · 80,4 | 0,105 | 2,0 | 100% | 137,2 | sigue |
| `vwap_quincenal` | 4h | intradia (declarada tres_dias) | 7525 | 663 | 3 | 15,2 | 6,4 · 15,0 · 24,6 | 0,079 | 16,9 | 100% | 15,8 | sin opción a primer equipo |

## Descartes mecánicos

Manda la banda medida por la tenencia (`PLAN/T169.md`). «Con la banda declarada» dice si el prospecto seguiría sin esa reasignación, para que se vea de qué depende cada descarte.

| Prospecto | Motivo | Al borde | Con la banda declarada |
|---|---|---|---|
| `elliott_tendencia_dow` | tres_dias: 4,7 operaciones al mes (< 5) | cadencia | — |

## Días hasta el veredicto (supervivientes)

σ = 1 R por operación **supuesta**; μ en R por operación; z = 1,645 (α 0,05) y z ≈ 3,09 (α 0,05/50, la familia). Operaciones necesarias: μ +0,10 R con z 1,65 → 273; μ +0,10 R con z 3,09 → 961; μ +0,25 R con z 1,65 → 46; μ +0,25 R con z 3,09 → 159.

| Prospecto | Banda | Esperadas en 6 meses | +0,10 R | +0,10 R familia | +0,25 R | +0,25 R familia | Al borde |
|---|---|--:|--:|--:|--:|--:|---|
| `elliott_oscilacion` | intradia (declarada tres_dias) | 90 | 551 | 1 940 | 92 | 320 | — |
| `elliott_dow` | intradia (declarada tres_dias) | 82 | 608 | 2 141 | 102 | 353 | — |
| `ema_precio_200` | tres_dias | 31 | 1 621 | 5 706 | 271 | 942 | cadencia |
| `ema_cruce_21_55` | intradia (declarada tres_dias) | 64 | 774 | 2 724 | 129 | 450 | — |
| `ema_retroceso_12h` | intradia | 58 | 861 | 3 031 | 144 | 500 | — |
| `niveles_redondos` | intradia | 106 | 467 | 1 643 | 78 | 271 | — |
| `lit_consenso_4h` | tres_dias | 60 | 835 | 2 940 | 140 | 485 | — |
| `estructura_ruptura_sc02` | intradia | 106 | 468 | 1 649 | 78 | 272 | — |
| `estructura_cambio_sc04` | intradia | 219 | 226 | 797 | 38 | 132 | — |
| `tec_acuerdo_tres_marcos` | scalping (declarada intradia) | 216 | 229 | 808 | 38 | 133 | — |
| `tec_rsi_giro` | intradia | 202 | 246 | 868 | 41 | 143 | — |
| `tec_compresion_bb_12h` | intradia | 84 | 594 | 2 089 | 99 | 345 | — |
| `vwap_reversion_1h` | scalping (declarada intradia) | 409 | 121 | 427 | 20 | 70 | — |
| `vwap_quincenal` | intradia (declarada tres_dias) | 92 | 540 | 1 902 | 90 | 314 | — |

## Cobertura de las variables declaradas

«Agente con datos»: contextos en que el agente no salió `no_data`. «Con valor»: contextos con la variable presente; en las variables de lista (`[]`), con al menos un elemento, así que una lista vacía (p. ej., ningún acierto de `literature` en esa vela) cuenta como sin valor aunque no sea un dato perdido.

| Prospecto | Agente con datos | Variable | Con valor |
|---|--:|---|--:|
| `elliott_oscilacion` | 100% | `metrics.pivots[-1].type` | 100% |
| `elliott_dow` | 100% | `metrics.pivots[-1].type` | 100% |
| `elliott_dow` | 100% | `metrics.pivots[-1].price` | 100% |
| `elliott_dow` | 100% | `metrics.pivots[-3].price` | 100% |
| `elliott_tendencia_dow` | 100% | `metrics.pivots[-1].type` | 100% |
| `elliott_tendencia_dow` | 100% | `metrics.pivots[-1].price` | 100% |
| `elliott_tendencia_dow` | 100% | `metrics.pivots[-3].price` | 100% |
| `ema_precio_200` | 100% | `metrics.variables.EMA_200` | 100% |
| `ema_cruce_21_55` | 100% | `metrics.variables.SPREAD_21_55` | 100% |
| `ema_retroceso_12h` | 100% | `metrics.variables.STACK_ORDER` | 100% |
| `ema_retroceso_12h` | 100% | `metrics.variables.BOUNCE_COUNT_21` | 100% |
| `ema_retroceso_12h` | 100% | `metrics.variables.EMA_21` | 100% |
| `niveles_redondos` | 100% | `metrics.dist_support` | 88% |
| `niveles_redondos` | 100% | `metrics.dist_resistance` | 85% |
| `niveles_redondos` | 100% | `metrics.atr` | 100% |
| `niveles_redondos` | 100% | `metrics.zones[].touches` | 100% |
| `niveles_redondos` | 100% | `metrics.zones[].p_low` | 100% |
| `niveles_redondos` | 100% | `metrics.zones[].p_high` | 100% |
| `lit_consenso_4h` | 100% | `metrics.hits[].direction` | 11% |
| `lit_consenso_4h` | 100% | `metrics.hits[].strength` | 11% |
| `estructura_ruptura_sc02` | 100% | `metrics.scenario` | 100% |
| `estructura_ruptura_sc02` | 100% | `bias` | 100% |
| `estructura_cambio_sc04` | 100% | `metrics.scenario` | 100% |
| `estructura_cambio_sc04` | 100% | `bias` | 100% |
| `tec_acuerdo_tres_marcos` | 100% | `metrics.frames.15m.bias` | 100% |
| `tec_acuerdo_tres_marcos` | 100% | `metrics.frames.1h.bias` | 100% |
| `tec_acuerdo_tres_marcos` | 100% | `metrics.frames.4h.bias` | 100% |
| `tec_rsi_giro` | 100% | `metrics.votes.RSI` | 100% |
| `tec_compresion_bb_12h` | 100% | `metrics.regime.width_pct` | 100% |
| `tec_compresion_bb_12h` | 100% | `metrics.families.tendencia` | 100% |
| `vwap_reversion_1h` | 100% | `metrics.periods.daily.position` | 100% |
| `vwap_reversion_1h` | 100% | `metrics.periods.daily.vwap` | 100% |
| `vwap_quincenal` | 100% | `metrics.close` | 100% |
| `vwap_quincenal` | 100% | `metrics.periods.quincenal.vwap` | 100% |
| `vwap_quincenal` | 100% | `metrics.periods.quincenal.slope_pct` | 100% |

## Comprobaciones

- **No anticipación:** 12 cortes (6 por marco), 108 contextos recalculados con el banco truncado: 0 distintos; prospectos cuyas ideas cambian: ninguno.
- **Identidad del subconjunto:** 6 de 6 contextos con `nat` idéntico al de la mesa con todos los agentes (los agentes sin historia no aportan nada en el banco).

## Sin historia (se examinan hacia adelante)

| Prospecto | Por qué |
|---|---|
