# Copy trading — replicación simulada (T42)

Generado 2026-10-16 20:09 UTC · modo **SIMULADO** (saldo virtual de 10 000 USDC por líder; ninguna orden real ni de testnet) · *El rendimiento pasado no garantiza resultados futuros.*

## Veredicto

- Líderes simulados: 7; aprobados por el scorecard (T41): 0. **7 se simulan solo para medir** (ninguno debería copiarse hoy).
- Rendimiento **aparente** (el del líder × proporción, viajes cerrados): +777,98 USD. **Copiable** (subcuentas, mismos viajes): -53,21 USD.
- Por unidad de nocional, en los viajes copiados: líder 7,6, 19,0, 19,4, 19,9, -7,8 pb · seguidor -5,8, -22,3, 6,1, 49,8, -30,5 pb (por líder, mismo orden que la tabla).
- La brecha viene sobre todo de: tamaño (topes, redondeo, tope de riesgo) -579,97 USD; comisiones (tomador propio vs las del líder) -135,16 USD; viajes no copiados -68,03 USD.
- Muestra corta (horas, decenas de viajes): las cifras describen lo ocurrido, no estiman un edge; ninguna prueba de significancia aplica con este n.

## Resultado por líder (reproducción del historial capturado)

| Líder | Estado T41 | Ventana | Viajes líder (cerrados) | Copiados | No copiados | Aparente (USD) | Copiable (USD) | pb líder | pb seguidor | Capital final | Caída máx. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0x7b7f…dee2 | rejected | 22,5 h | 151 | 94 | 57 | +164,42 | -49,08 | 7,6 | -5,8 | 9 953,87 (-0,46 %) | +1,2 % |
| 0xf5d8…ad53 | rejected | 22,4 h | 1128 | 0 | 1128 | +70,17 | +0,00 | — | — | 9 944,46 (-0,56 %) | +0,7 % |
| 0x0fac…7a0a | rejected | 22,4 h | 0 | 0 | 0 | +0,00 | +0,00 | — | — | 10 000,00 (+0,00 %) | +0,0 % |
| 0x2cb2…3f19 | rejected | 22,4 h | 2 | 2 | 0 | +249,54 | -17,84 | 19,0 | -22,3 | 9 982,16 (-0,18 %) | +1,1 % |
| 0x7ca1…9235 | rejected | 22,4 h | 9 | 9 | 0 | +29,37 | +8,76 | 19,4 | 6,1 | 10 009,04 (+0,09 %) | +0,3 % |
| 0x696d…8e28 | rejected | 22,4 h | 3 | 3 | 0 | +371,55 | +56,95 | 19,9 | 49,8 | 10 057,21 (+0,57 %) | +1,3 % |
| 0xcf3f…f95f | rejected | 22,4 h | 28 | 6 | 22 | -107,07 | -52,00 | -7,8 | -30,5 | 9 962,65 (-0,37 %) | +0,8 % |

## Copiable vs aparente: causas de la diferencia

Aparente total **+777,98 USD** → copiable **-53,21 USD** (diferencia -831,19 USD = suma de causas):

| Causa | Aporte (USD) | 0x7b7f…dee2 | 0xf5d8…ad53 | 0x0fac…7a0a | 0x2cb2…3f19 | 0x7ca1…9235 | 0x696d…8e28 | 0xcf3f…f95f |
|---|---|---|---|---|---|---|---|---|
| latencia (el precio se movió antes de nuestra orden) | -12,69 | +3,00 | +0,00 | +0,00 | -15,79 | +3,35 | +0,72 | -3,97 |
| diferencial (cruzar el libro: ask/bid vs medio) | -20,88 | -12,03 | +0,00 | +0,00 | -3,05 | -1,95 | -3,04 | -0,82 |
| comisiones (tomador propio vs las del líder) | -135,16 | -97,38 | +0,00 | +0,00 | -0,47 | -19,21 | +0,03 | -18,12 |
| funding (propio vs el del líder a nuestro tamaño) | +0,52 | -0,27 | +0,00 | +0,00 | +0,82 | +0,00 | -0,00 | -0,03 |
| viajes no copiados | -68,03 | -77,78 | -70,17 | +0,00 | +0,00 | +0,00 | +0,00 | +79,92 |
| tamaño (topes, redondeo, tope de riesgo) | -579,97 | -10,89 | +0,00 | +0,00 | -241,84 | -3,61 | -337,58 | +13,95 |
| resto (aumentos omitidos, stops, redondeo a mitad) | -14,98 | -18,15 | +0,00 | +0,00 | -7,05 | +0,81 | +25,27 | -15,86 |

Viajes no copiados por motivo (n · aporte):

- `bajo_minimo`: 848 viajes · -4,10 USD
- `riesgo`: 215 viajes · -0,57 USD
- `redondeo`: 137 viajes · +5,53 USD
- `deslizamiento`: 6 viajes · -70,56 USD
- `flujo_caido`: 1 viajes · +1,67 USD

## Reconciliación de la reproducción

- Reconciliaciones con la foto real del líder: 1878; con alguna diferencia explicada (topes, mínimos, vetos, señales en camino): 1165; con diferencia **no explicada**: 4 (aisladas: ninguna se repitió en la foto siguiente) → pausas: **0**.
- Resincronizaciones por hueco de captura conocido (> 5 min sin confirmar el flujo: equipo apagado, reinicios del servicio): 14. Ejecuciones llegadas tarde y anteriores a lo ya procesado (reenvío del WS antes que el relleno REST): 368, tratadas como historial.

## Ejecución simulada

Precio del seguidor por señal:

- bid/ask grabado (WS `bbo`): 47722 (94%)
- cierre de vela 1 min + deslizamiento T25 (supuesto): 3003 (6%)
- precio del líder + deslizamiento base (supuesto): 10 (0%)
- precio medio `allMids` + medio diferencial supuesto: 8 (0%)

| Líder | Señales | Órdenes | Latencia señal p50 / p90 (ms) | Rechazos por motivo | Funding (USD) | Comisiones (USD) | Horas sin tasa |
|---|---|---|---|---|---|---|---|
| 0x7b7f…dee2 | 2798 | 1204 | 208 / 494 | bajo_minimo 873, excluido 130, riesgo 93, redondeo 42, deslizamiento 26, tope 18, flujo_caido 5 | -0,23 | -104,06 | 0 |
| 0xf5d8…ad53 | 46220 | 972 | 198 / 449 | riesgo 16225, bajo_minimo 6384, excluido 1915, redondeo 489, deslizamiento 216, tope 56 | -0,05 | -27,23 | 0 |
| 0x0fac…7a0a | 0 | 0 | — / — | — | +0,00 | -0,00 | 0 |
| 0x2cb2…3f19 | 30 | 8 | 203 / 285 | tope 12, bajo_minimo 5 | +0,83 | -7,20 | 0 |
| 0x7ca1…9235 | 293 | 146 | 229 / 558 | excluido 135, bajo_minimo 13, redondeo 2 | -0,03 | -20,61 | 0 |
| 0x696d…8e28 | 43 | 10 | 171 / 465 | tope 24, bajo_minimo 6, deslizamiento 3 | +0,28 | -12,11 | 0 |
| 0xcf3f…f95f | 991 | 250 | 230 / 547 | tope 195, bajo_minimo 176, excluido 22, riesgo 22, redondeo 7 | -0,25 | -28,39 | 0 |

## Simulación en vivo (servicio de líderes)

Modo **SIMULADO** (Simulación: saldo virtual, sin órdenes reales ni de testnet); resumen de 2026-10-16 20:09 UTC (hace 3 s). Subcuentas: 7; seguimiento desde 2026-10-16 19:16 UTC (**0,9 h**). Reconciliaciones: 623; con diferencia no explicada: 33 (acumulado); las acumuladas no tienen hora registrada (estado anterior al registro); en pausa ahora: 0.

| Líder | Capital | Resultado | Órdenes | Rechazos | Posiciones | Pausa |
|---|---|---|---|---|---|---|
| 0x7ca165f3 | 10 002,35 | +2,35 | 13 | 16 | 1 | — |
| 0x0facac3b | 10 000,00 | +0,00 | 0 | 0 | 0 | — |
| 0x2cb21297 | 10 000,00 | +0,00 | 0 | 0 | 0 | — |
| 0xcf3f419d | 10 000,00 | +0,00 | 0 | 95 | 0 | — |
| 0xf5d81a13 | 9 999,79 | -0,21 | 15 | 3660 | 0 | — |
| 0x7b7f72a2 | 9 997,69 | -2,31 | 38 | 184 | 3 | — |
| 0x696d1265 | 9 996,87 | -3,13 | 2 | 20 | 1 | — |

## Método y supuestos

- Mismo motor en vivo y en la reproducción (`eim/copytrading/copy_engine.py`): objetivo = posición del líder × capital asignado / cuenta del líder (fijada al abrir cada viaje; cuenta de `portfolio`). Topes: 40% del capital por moneda y 150% por líder; deslizamiento máximo 0.5% frente a la entrada media del líder; mínimos del exchange de `meta` (hyperliquid:info.meta (copia hl_meta.json)); lo abierto antes de seguirlo no se copia.
- Riesgo: cada orden que aumenta riesgo pasa por el motor T29 con `risk_copy_v1` (stop de protección 5%, señal ≤ 30 s, flujo confirmado ≤ 2 min, pérdida diaria/semanal, enfriamiento, kill-switch propio por caída). Reducir o cerrar nunca se veta.
- La orden llega 300 ms después de ver la ejecución del líder; comisión de tomador 0.045% (Hyperliquid, nivel base); funding horario con la tasa real pagada por los líderes capturados; marcas y stops con velas de 1 min de Hyperliquid.
- Reconciliación con cada foto del líder: una diferencia sin motivo registrado en 2 comprobaciones seguidas pausa la subcuenta y avisa (nunca se opera para «cuadrar»).
- Limitaciones: sin impacto del tamaño propio en el libro (subcuenta pequeña); stops evaluados al cierre de cada minuto; sin cotización grabada, el precio es un supuesto declarado arriba; una subcuenta por líder (sin compensar posiciones entre líderes: eso es el asignador de T46).
