# T169 — Examen físico de los prospectos en la historia

**Modo: SIMULADO.** Sin rendimiento: este informe no calcula ni muestra R neto, acierto ni PF (regla 5 de la nota de T167 §3). La historia no asciende a nadie; solo descarta por razones mecánicas, con los umbrales fijados en `PLAN/T169.md` antes de correr.

**32 prospectos con historia examinados** de 43: **16 descartados** por razones mecánicas y 16 siguen, de los que 4 quedan «sin opción a primer equipo» (no llegan a ≈ 100 operaciones, o a 120 días con posición, en 6 meses). 19 cambian de banda por su tenencia.

- **5 descartes dependen de la reasignación de banda**: con la banda declarada seguirían (`ema_pila`, `ema_retroceso`, `lit_regla_4_semanas`, `tec_compresion_bb`, `vwap_anclado`).
- **4 reglas no se cumplen nunca** en la muestra (`elliott_onda3`, `elliott_onda5_giro`, `estructura_ruptura`, `tec_acuerdo_marcos`): la causa de cada una está en `PLAN/notas/T169_examen_fisico.md`.
- **Gemelos físicos** (mismas ideas y operaciones): `regimen_tramo` = `regimen_tramo_estable`.

Muestra: 4h 7876 contextos de 7876 en 1 tramo (1312,7 días); 15m 21504 contextos de 21504 en 16 tramos (224,0 días); 1h 10752 contextos de 10752 en 16 tramos (448,0 días).

Costo de generación (un proceso, en IDLE, por la cola): 4h 7752 contextos a 0,355 s; 15m 21444 contextos a 0,161 s; 1h 10692 contextos a 0,615 s → **3,5 h de cálculo** (0,15 días de máquina) en 3 pasadas; RAM máxima 135 MB. Los otros 244 contextos salieron de pasadas de prueba anteriores al registro de costo.

## Prospectos con historia

«Operaciones» son órdenes llenadas (una a la vez); «No llenadas», las límite que vencieron sin llenarse; «Por bloque», la cadencia mínima · mediana · máxima de los bloques de 28 días; «En posición», la fracción de días con posición abierta.

| Prospecto | Marco | Banda | Ideas | Operaciones | No llenadas | Al mes | Por bloque | Costo medio (R) | Tenencia mediana (h) | En posición (días) | Rotación (× capital/mes) | Estado |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| `elliott_onda3` | 4h | semanal | 0 | 0 | 0 | 0,0 | 0,0 · 0,0 · 0,0 | — | — | 0% | 0,0 | **descartado** |
| `elliott_onda5_giro` | 4h | semanal | 0 | 0 | 0 | 0,0 | 0,0 · 0,0 · 0,0 | — | — | 0% | 0,0 | **descartado** |
| `ema_pila` | 4h | tres_dias (declarada semanal) | 3866 | 214 | 0 | 4,9 | 1,1 · 4,3 · 10,7 | 0,104 | 36,0 | 60% | 5,0 | **descartado** |
| `ema_resorte` | 1h | scalping (declarada intradia) | 80 | 80 | 0 | 5,4 | 2,1 · 5,4 · 8,6 | 0,125 | 1,6 | 19% | 9,4 | **descartado** |
| `ema_retroceso` | 1h | scalping (declarada intradia) | 195 | 166 | 2 | 11,1 | 6,4 · 10,7 · 17,1 | 0,149 | 1,5 | 32% | 23,0 | **descartado** |
| `ema_elastico` | 1h | intradia | 1201 | 222 | 5 | 14,9 | 0,0 · 9,6 · 65,4 | 0,077 | 3,2 | 23% | 21,3 | sin opción a primer equipo |
| `niveles_rebote` | 1h | scalping (declarada intradia) | 3075 | 1335 | 29 | 89,4 | 68,6 · 91,1 · 103,9 | 0,142 | 1,5 | 94% | 175,9 | sigue |
| `niveles_ruptura` | 1h | intradia (declarada tres_dias) | 286 | 254 | 9 | 17,0 | 11,8 · 18,2 · 21,4 | 0,153 | 6,5 | 67% | 32,2 | sigue |
| `niveles_canal_extremos` | 1h | intradia | 1740 | 391 | 7 | 26,2 | 21,4 · 26,8 · 32,1 | 0,176 | 10,9 | 83% | 52,2 | sigue |
| `niveles_canal_tendencia` | 4h | intradia (declarada semanal) | 1518 | 148 | 2 | 3,4 | 0,0 · 3,2 · 10,7 | 0,095 | 20,9 | 29% | 3,5 | **descartado** |
| `lit_consenso` | 1h | intradia | 804 | 513 | 8 | 34,4 | 23,6 · 35,4 · 40,7 | 0,150 | 12,0 | 91% | 64,4 | sigue |
| `lit_regla_4_semanas` | 4h | tres_dias (declarada semanal) | 185 | 44 | 0 | 1,0 | 0,0 · 1,1 · 3,2 | 0,261 | 62,4 | 61% | 1,0 | **descartado** |
| `lit_nison_giro` | 1h | intradia | 581 | 413 | 4 | 27,7 | 19,3 · 27,9 · 35,4 | 0,149 | 12,0 | 83% | 52,1 | sigue |
| `lit_murphy_rsi` | 1h | intradia | 288 | 233 | 5 | 15,6 | 8,6 · 16,1 · 20,4 | 0,140 | 11,2 | 52% | 26,6 | sin opción a primer equipo |
| `pa_bos` | 1h | intradia (declarada tres_dias) | 461 | 294 | 4 | 19,7 | 13,9 · 19,3 · 26,8 | 0,186 | 9,0 | 81% | 41,7 | sigue |
| `pa_choch` | 1h | intradia (declarada tres_dias) | 498 | 308 | 8 | 20,6 | 15,0 · 21,4 · 25,7 | 0,179 | 9,8 | 85% | 44,7 | sigue |
| `pa_patron_zona` | 1h | intradia | 5909 | 968 | 13 | 64,8 | 60,0 · 64,3 · 71,8 | 0,165 | 11,8 | 100% | 134,7 | sigue |
| `pa_bos_patron` | 1h | intradia (declarada tres_dias) | 385 | 260 | 3 | 17,4 | 10,7 · 18,2 · 22,5 | 0,188 | 9,0 | 73% | 37,1 | sigue |
| `regimen_tramo` | 1h | scalping (declarada tres_dias) | 256 | 68 | 0 | 4,6 | 1,1 · 5,4 · 7,5 | 0,136 | 2,0 | 11% | 8,2 | **descartado** |
| `regimen_tramo_estable` | 1h | scalping (declarada tres_dias) | 256 | 68 | 0 | 4,6 | 1,1 · 5,4 · 7,5 | 0,136 | 2,0 | 11% | 8,2 | **descartado** |
| `estructura_continuacion` | 4h | intradia (declarada semanal) | 699 | 695 | 4 | 15,9 | 0,0 · 15,0 · 36,4 | 0,070 | 4,0 | 41% | 16,7 | sin opción a primer equipo |
| `estructura_ruptura` | 1h | intradia | 0 | 0 | 0 | 0,0 | 0,0 · 0,0 · 0,0 | — | — | 0% | 0,0 | **descartado** |
| `estructura_cambio` | 1h | scalping (declarada intradia) | 110 | 102 | 1 | 6,8 | 0,0 · 7,5 · 16,1 | 0,136 | 1,5 | 19% | 12,7 | **descartado** |
| `estructura_retroceso` | 1h | scalping (declarada intradia) | 440 | 357 | 7 | 23,9 | 2,1 · 20,4 · 56,8 | 0,125 | 1,5 | 38% | 40,5 | sigue |
| `tec_acuerdo_marcos` | 1h | tres_dias | 0 | 0 | 0 | 0,0 | 0,0 · 0,0 · 0,0 | — | — | 0% | 0,0 | **descartado** |
| `tec_rsi_rango` | 1h | intradia | 116 | 98 | 1 | 6,6 | 0,0 · 6,4 · 10,7 | 0,166 | 12,0 | 27% | 14,2 | **descartado** |
| `tec_ruptura_volumen` | 1h | scalping (declarada intradia) | 3528 | 1210 | 20 | 81,0 | 56,8 · 83,6 · 98,6 | 0,132 | 1,2 | 84% | 144,8 | sigue |
| `tec_compresion_bb` | 1h | scalping (declarada intradia) | 221 | 208 | 2 | 13,9 | 10,7 · 12,9 · 20,4 | 0,179 | 1,2 | 44% | 33,0 | **descartado** |
| `vwap_reversion` | 15m | scalping | 2253 | 1113 | 0 | 149,1 | 120,0 · 150,0 · 192,9 | 0,337 | 0,8 | 100% | 533,0 | **descartado** |
| `vwap_tendencia` | 1h | intradia | 9573 | 1607 | 30 | 107,6 | 92,1 · 108,2 · 117,9 | 0,148 | 3,0 | 100% | 223,8 | sigue |
| `vwap_semanal` | 4h | intradia (declarada semanal) | 591 | 586 | 5 | 13,4 | 6,4 · 13,9 · 21,4 | 0,076 | 20,0 | 94% | 13,8 | sin opción a primer equipo |
| `vwap_anclado` | 4h | tres_dias (declarada semanal) | 7869 | 114 | 0 | 2,6 | 0,0 · 1,1 · 17,1 | 0,166 | 32,0 | 100% | 2,7 | **descartado** |

## Descartes mecánicos

Manda la banda medida por la tenencia (`PLAN/T169.md`). «Con la banda declarada» dice si el prospecto seguiría sin esa reasignación, para que se vea de qué depende cada descarte.

| Prospecto | Motivo | Al borde | Con la banda declarada |
|---|---|---|---|
| `elliott_onda3` | ninguna idea en toda la muestra: la regla no se cumple nunca; semanal en posición el 0 % de los días (< 30 %) | — | — |
| `elliott_onda5_giro` | ninguna idea en toda la muestra: la regla no se cumple nunca; semanal en posición el 0 % de los días (< 30 %) | — | — |
| `ema_pila` | tres_dias: 4,9 operaciones al mes (< 5) | cadencia | seguiría (semanal) |
| `ema_resorte` | scalping: 5,4 operaciones al mes (< 20) | — | también cae (intradia) |
| `ema_retroceso` | scalping: 11,1 operaciones al mes (< 20) | — | seguiría (intradia) |
| `niveles_canal_tendencia` | intradia: 3,4 operaciones al mes (< 8) | — | también cae (semanal) |
| `lit_regla_4_semanas` | tres_dias: 1,0 operaciones al mes (< 5) | costo | seguiría (semanal) |
| `regimen_tramo` | scalping: 4,6 operaciones al mes (< 20) | — | también cae (tres_dias) |
| `regimen_tramo_estable` | scalping: 4,6 operaciones al mes (< 20) | — | también cae (tres_dias) |
| `estructura_ruptura` | ninguna idea en toda la muestra: la regla no se cumple nunca; intradia: 0,0 operaciones al mes (< 8) | — | — |
| `estructura_cambio` | scalping: 6,8 operaciones al mes (< 20) | — | también cae (intradia) |
| `tec_acuerdo_marcos` | ninguna idea en toda la muestra: la regla no se cumple nunca; tres_dias: 0,0 operaciones al mes (< 5) | — | — |
| `tec_rsi_rango` | intradia: 6,6 operaciones al mes (< 8) | — | — |
| `tec_compresion_bb` | scalping: 13,9 operaciones al mes (< 20) | — | seguiría (intradia) |
| `vwap_reversion` | costo medio 0,337 R (> 0,3 R, V6 de T49) | — | — |
| `vwap_anclado` | tres_dias: 2,6 operaciones al mes (< 5) | — | seguiría (semanal) |

## Días hasta el veredicto (supervivientes)

σ = 1 R por operación **supuesta**; μ en R por operación; z = 1,645 (α 0,05) y z ≈ 3,09 (α 0,05/50, la familia). Operaciones necesarias: μ +0,10 R con z 1,65 → 273; μ +0,10 R con z 3,09 → 961; μ +0,25 R con z 1,65 → 46; μ +0,25 R con z 3,09 → 159.

| Prospecto | Banda | Esperadas en 6 meses | +0,10 R | +0,10 R familia | +0,25 R | +0,25 R familia | Al borde |
|---|---|--:|--:|--:|--:|--:|---|
| `ema_elastico` | intradia | 90 | 551 | 1 939 | 92 | 320 | — |
| `niveles_rebote` | scalping (declarada intradia) | 542 | 92 | 322 | 15 | 53 | — |
| `niveles_ruptura` | intradia (declarada tres_dias) | 103 | 481 | 1 694 | 80 | 280 | — |
| `niveles_canal_extremos` | intradia | 159 | 313 | 1 101 | 52 | 182 | — |
| `lit_consenso` | intradia | 208 | 238 | 839 | 40 | 138 | — |
| `lit_nison_giro` | intradia | 168 | 296 | 1 042 | 50 | 172 | — |
| `lit_murphy_rsi` | intradia | 95 | 525 | 1 847 | 88 | 305 | — |
| `pa_bos` | intradia (declarada tres_dias) | 119 | 416 | 1 464 | 70 | 242 | — |
| `pa_choch` | intradia (declarada tres_dias) | 125 | 397 | 1 397 | 66 | 231 | — |
| `pa_patron_zona` | intradia | 393 | 126 | 445 | 21 | 73 | — |
| `pa_bos_patron` | intradia (declarada tres_dias) | 106 | 470 | 1 655 | 79 | 273 | — |
| `estructura_continuacion` | intradia (declarada semanal) | 96 | 515 | 1 815 | 86 | 300 | — |
| `estructura_retroceso` | scalping (declarada intradia) | 145 | 342 | 1 206 | 57 | 199 | — |
| `tec_ruptura_volumen` | scalping (declarada intradia) | 492 | 101 | 356 | 17 | 59 | — |
| `vwap_tendencia` | intradia | 653 | 76 | 268 | 13 | 44 | — |
| `vwap_semanal` | intradia (declarada semanal) | 81 | 611 | 2 152 | 102 | 355 | — |

## Cobertura de las variables declaradas

«Agente con datos»: contextos en que el agente no salió `no_data`. «Con valor»: contextos con la variable presente; en las variables de lista (`[]`), con al menos un elemento, así que una lista vacía (p. ej., ningún acierto de `literature` en esa vela) cuenta como sin valor aunque no sea un dato perdido.

| Prospecto | Agente con datos | Variable | Con valor |
|---|--:|---|--:|
| `elliott_onda3` | 100% | `metrics.pivots[-1].wave_label` | 100% |
| `elliott_onda3` | 100% | `metrics.valid_count` | 100% |
| `elliott_onda3` | 100% | `metrics.pivots[-1].type` | 100% |
| `elliott_onda5_giro` | 100% | `metrics.pivots[-1].wave_label` | 100% |
| `elliott_onda5_giro` | 100% | `metrics.valid_count` | 100% |
| `elliott_onda5_giro` | 100% | `metrics.pivots[-1].type` | 100% |
| `ema_pila` | 100% | `metrics.variables.STACK_ORDER` | 100% |
| `ema_pila` | 100% | `metrics.variables.PRICE_VS_STACK` | 100% |
| `ema_resorte` | 100% | `metrics.variables.COMPRESSION_INDEX` | 100% |
| `ema_resorte` | 100% | `metrics.variables.COMPRESSION_DURATION` | 100% |
| `ema_resorte` | 100% | `metrics.variables.SLOPE_DIRECTION` | 100% |
| `ema_retroceso` | 100% | `metrics.variables.STACK_ORDER` | 100% |
| `ema_retroceso` | 100% | `metrics.variables.EMA_21` | 100% |
| `ema_retroceso` | 100% | `metrics.variables.BOUNCE_COUNT_21` | 100% |
| `ema_elastico` | 100% | `metrics.variables.ELASTICITY` | 100% |
| `ema_elastico` | 100% | `metrics.variables.EMA_21` | 100% |
| `niveles_rebote` | 100% | `metrics.dist_support` | 88% |
| `niveles_rebote` | 100% | `metrics.dist_resistance` | 85% |
| `niveles_rebote` | 100% | `metrics.atr` | 100% |
| `niveles_rebote` | 100% | `metrics.zones[].touches` | 100% |
| `niveles_rebote` | 100% | `metrics.zones[].p_low` | 100% |
| `niveles_rebote` | 100% | `metrics.zones[].p_high` | 100% |
| `niveles_ruptura` | 100% | `metrics.channel.state` | 90% |
| `niveles_ruptura` | 100% | `metrics.channel.kind` | 90% |
| `niveles_canal_extremos` | 100% | `metrics.channel.state` | 90% |
| `niveles_canal_extremos` | 100% | `metrics.channel_pos` | 90% |
| `niveles_canal_tendencia` | 100% | `metrics.channel.state` | 92% |
| `niveles_canal_tendencia` | 100% | `metrics.channel.r2` | 92% |
| `niveles_canal_tendencia` | 100% | `metrics.channel.slope_per_bar` | 92% |
| `lit_consenso` | 100% | `metrics.hits[].direction` | 7% |
| `lit_consenso` | 100% | `metrics.hits[].strength` | 7% |
| `lit_regla_4_semanas` | 100% | `metrics.hits[].card_id` | 11% |
| `lit_regla_4_semanas` | 100% | `metrics.hits[].direction` | 11% |
| `lit_nison_giro` | 100% | `metrics.hits[].card_id` | 7% |
| `lit_nison_giro` | 100% | `metrics.hits[].direction` | 7% |
| `lit_nison_giro` | 100% | `metrics.hits[].strength` | 7% |
| `lit_murphy_rsi` | 100% | `metrics.hits[].card_id` | 7% |
| `lit_murphy_rsi` | 100% | `metrics.hits[].direction` | 7% |
| `pa_bos` | 100% | `metrics.last_event` | 100% |
| `pa_bos` | 100% | `metrics.last_event_age` | 100% |
| `pa_choch` | 100% | `metrics.last_event` | 100% |
| `pa_choch` | 100% | `metrics.last_event_age` | 100% |
| `pa_patron_zona` | 100% | `metrics.bullish_patterns` | 100% |
| `pa_patron_zona` | 100% | `metrics.bearish_patterns` | 100% |
| `pa_patron_zona` | 100% | `metrics.sr_zones` | 100% |
| `pa_bos_patron` | 100% | `metrics.last_event` | 100% |
| `pa_bos_patron` | 100% | `metrics.last_event_age` | 100% |
| `pa_bos_patron` | 100% | `metrics.bullish_patterns` | 100% |
| `pa_bos_patron` | 100% | `metrics.bearish_patterns` | 100% |
| `regimen_tramo` | 100% | `metrics.regime` | 100% |
| `regimen_tramo_estable` | 100% | `metrics.regime` | 100% |
| `regimen_tramo_estable` | 100% | `metrics.unstable` | 100% |
| `estructura_continuacion` | 100% | `metrics.scenario` | 100% |
| `estructura_continuacion` | 100% | `metrics.conviction` | 100% |
| `estructura_continuacion` | 100% | `bias` | 100% |
| `estructura_ruptura` | 100% | `metrics.scenario` | 100% |
| `estructura_ruptura` | 100% | `metrics.conviction` | 100% |
| `estructura_ruptura` | 100% | `bias` | 100% |
| `estructura_cambio` | 100% | `metrics.scenario` | 100% |
| `estructura_cambio` | 100% | `metrics.conviction` | 100% |
| `estructura_cambio` | 100% | `bias` | 100% |
| `estructura_retroceso` | 100% | `metrics.scenario` | 100% |
| `estructura_retroceso` | 100% | `metrics.conviction` | 100% |
| `estructura_retroceso` | 100% | `bias` | 100% |
| `tec_acuerdo_marcos` | 100% | `metrics.frames.1h.bias` | 100% |
| `tec_acuerdo_marcos` | 100% | `metrics.frames.4h.bias` | 100% |
| `tec_acuerdo_marcos` | 100% | `metrics.frames.1d.bias` | 0% |
| `tec_rsi_rango` | 100% | `metrics.regime.adx` | 100% |
| `tec_rsi_rango` | 100% | `metrics.votes.RSI` | 100% |
| `tec_ruptura_volumen` | 100% | `metrics.regime.adx` | 100% |
| `tec_ruptura_volumen` | 100% | `metrics.families.tendencia` | 100% |
| `tec_ruptura_volumen` | 100% | `metrics.families.volumen` | 100% |
| `tec_compresion_bb` | 100% | `metrics.regime.width_pct` | 100% |
| `tec_compresion_bb` | 100% | `metrics.families.tendencia` | 100% |
| `vwap_reversion` | 100% | `metrics.periods.daily.position` | 100% |
| `vwap_reversion` | 100% | `metrics.periods.daily.vwap` | 100% |
| `vwap_tendencia` | 100% | `metrics.periods.daily.position` | 100% |
| `vwap_tendencia` | 100% | `metrics.periods.daily.slope_pct` | 100% |
| `vwap_semanal` | 100% | `metrics.periods.weekly.position` | 100% |
| `vwap_semanal` | 100% | `metrics.periods.weekly.vwap` | 100% |
| `vwap_semanal` | 100% | `metrics.close` | 100% |
| `vwap_anclado` | 100% | `metrics.anchored_vwap` | 100% |
| `vwap_anclado` | 100% | `metrics.close` | 100% |

## Comprobaciones

- **No anticipación:** 18 cortes (6 por marco), 162 contextos recalculados con el banco truncado: 0 distintos; prospectos cuyas ideas cambian: ninguno.
- **Identidad del subconjunto:** 9 de 9 contextos con `nat` idéntico al de la mesa con todos los agentes (los agentes sin historia no aportan nada en el banco).

## Sin historia (se examinan hacia adelante)

| Prospecto | Por qué |
|---|---|
| `bots_mayoria` | pide las señales del servicio de bots, que no se guardan |
| `bots_unanimidad` | pide las señales del servicio de bots, que no se guardan |
| `deriv_funding_contrario` | el agente exige interés abierto y el banco solo tiene funding |
| `deriv_largos_cortos` | el agente exige interés abierto y el banco solo tiene funding |
| `deriv_oi_tendencia` | el agente exige interés abierto y el banco solo tiene funding |
| `deriv_saturacion` | el agente exige interés abierto y el banco solo tiene funding |
| `liq_agotamiento` | pide liquidaciones en vivo, que el banco no tiene |
| `liq_cascada` | pide liquidaciones en vivo, que el banco no tiene |
| `liq_cascada_multibolsa` | pide liquidaciones en vivo, que el banco no tiene |
| `micro_absorcion` | pide la captura HFT, que el banco no tiene |
| `micro_ofi` | pide la captura HFT, que el banco no tiene |
