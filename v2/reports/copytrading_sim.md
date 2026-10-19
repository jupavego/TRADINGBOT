# Copy trading — replicación simulada (T42)

Generado 2026-10-19 00:34 UTC · modo **SIMULADO** (saldo virtual de 10 000 USDC por líder; ninguna orden real ni de testnet) · *El rendimiento pasado no garantiza resultados futuros.*

## Veredicto

- Líderes simulados: 7; aprobados por el scorecard (T41): 0. **7 se simulan solo para medir** (ninguno debería copiarse hoy).
- Rendimiento **aparente** (el del líder × proporción, viajes cerrados): -1 780,17 USD. **Copiable** (subcuentas, mismos viajes): -199,77 USD.
- Por unidad de nocional, en los viajes copiados: líder 3,4, 19,0, 10,3, -14,8, -7,8 pb · seguidor -8,6, -22,3, -3,8, 3,7, -30,5 pb (por líder, mismo orden que la tabla).
- La brecha viene sobre todo de: comisiones (tomador propio vs las del líder) -232,15 USD; diferencial (cruzar el libro: ask/bid vs medio) -27,79 USD; latencia (el precio se movió antes de nuestra orden) -15,63 USD.
- Muestra corta (horas, decenas de viajes): las cifras describen lo ocurrido, no estiman un edge; ninguna prueba de significancia aplica con este n.

## Resultado por líder (reproducción del historial capturado)

| Líder | Estado T41 | Ventana | Viajes líder (cerrados) | Copiados | No copiados | Aparente (USD) | Copiable (USD) | pb líder | pb seguidor | Capital final | Caída máx. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0x7b7f…dee2 | rejected | 74,7 h | 531 | 175 | 356 | +99,20 | -128,34 | 3,4 | -8,6 | 9 862,92 (-1,37 %) | +1,5 % |
| 0xf5d8…ad53 | rejected | 74,7 h | 1719 | 0 | 1719 | -99,56 | +0,00 | — | — | 9 859,04 (-1,41 %) | +1,4 % |
| 0x0fac…7a0a | rejected | 74,6 h | 0 | 0 | 0 | +0,00 | +0,00 | — | — | 10 000,00 (+0,00 %) | +0,0 % |
| 0x2cb2…3f19 | rejected | 74,6 h | 2 | 2 | 0 | +249,54 | -17,84 | 19,0 | -22,3 | 9 982,16 (-0,18 %) | +1,1 % |
| 0x7ca1…9235 | rejected | 74,6 h | 21 | 17 | 4 | +47,37 | -14,00 | 10,3 | -3,8 | 9 978,25 (-0,22 %) | +0,7 % |
| 0x696d…8e28 | rejected | 74,6 h | 9 | 9 | 0 | -1 969,71 | +12,44 | -14,8 | 3,7 | 10 012,44 (+0,12 %) | +1,4 % |
| 0xcf3f…f95f | rejected | 74,6 h | 28 | 6 | 22 | -107,00 | -52,03 | -7,8 | -30,5 | 9 974,62 (-0,25 %) | +0,8 % |

## Copiable vs aparente: causas de la diferencia

Aparente total **-1 780,17 USD** → copiable **-199,77 USD** (diferencia +1 580,40 USD = suma de causas):

| Causa | Aporte (USD) | 0x7b7f…dee2 | 0xf5d8…ad53 | 0x0fac…7a0a | 0x2cb2…3f19 | 0x7ca1…9235 | 0x696d…8e28 | 0xcf3f…f95f |
|---|---|---|---|---|---|---|---|---|
| latencia (el precio se movió antes de nuestra orden) | -15,63 | +2,07 | +0,00 | +0,00 | -15,79 | -0,15 | +2,22 | -3,98 |
| diferencial (cruzar el libro: ask/bid vs medio) | -27,79 | -16,61 | +0,00 | +0,00 | -3,05 | -4,12 | -3,20 | -0,82 |
| comisiones (tomador propio vs las del líder) | -232,15 | -161,05 | +0,00 | +0,00 | -0,47 | -52,28 | -0,18 | -18,17 |
| funding (propio vs el del líder a nuestro tamaño) | +0,93 | -0,34 | +0,00 | +0,00 | +0,82 | +0,36 | +0,13 | -0,03 |
| viajes no copiados | +146,69 | -35,79 | +99,56 | +0,00 | +0,00 | +3,00 | +0,00 | +79,92 |
| tamaño (topes, redondeo, tope de riesgo) | +1 723,73 | -3,31 | +0,00 | +0,00 | -241,84 | -9,38 | +1 964,39 | +13,87 |
| resto (aumentos omitidos, stops, redondeo a mitad) | -15,39 | -12,52 | +0,00 | +0,00 | -7,05 | +1,21 | +18,80 | -15,83 |

Viajes no copiados por motivo (n · aporte):

- `bajo_minimo`: 1414 viajes · +76,44 USD
- `riesgo`: 442 viajes · +144,20 USD
- `redondeo`: 227 viajes · +4,26 USD
- `deslizamiento`: 14 viajes · -73,67 USD
- `flujo_caido`: 4 viajes · -4,54 USD

## Reconciliación de la reproducción

- Reconciliaciones con la foto real del líder: 9602; con alguna diferencia explicada (topes, mínimos, vetos, señales en camino): 7117; con diferencia **no explicada**: 3 (aisladas: ninguna se repitió en la foto siguiente) → pausas: **0**.
- Resincronizaciones por hueco de captura conocido (> 5 min sin confirmar el flujo: equipo apagado, reinicios del servicio): 77. Ejecuciones llegadas tarde y anteriores a lo ya procesado (reenvío del WS antes que el relleno REST): 1029, tratadas como historial.

## Ejecución simulada

Precio del seguidor por señal:

- bid/ask grabado (WS `bbo`): 189567 (97%)
- cierre de vela 1 min + deslizamiento T25 (supuesto): 5575 (3%)
- precio medio `allMids` + medio diferencial supuesto: 120 (0%)
- precio del líder + deslizamiento base (supuesto): 10 (0%)

| Líder | Señales | Órdenes | Latencia señal p50 / p90 (ms) | Rechazos por motivo | Funding (USD) | Comisiones (USD) | Horas sin tasa |
|---|---|---|---|---|---|---|---|
| 0x7b7f…dee2 | 9125 | 2191 | 192 / 573 | riesgo 1854, bajo_minimo 1495, excluido 391, redondeo 103, deslizamiento 46, tope 20, flujo_caido 12 | -0,16 | -176,09 | 0 |
| 0xf5d8…ad53 | 181555 | 4921 | 183 / 499 | riesgo 61304, bajo_minimo 29616, excluido 4793, redondeo 2148, deslizamiento 697, tope 348, flujo_caido 32 | +0,01 | -147,79 | 0 |
| 0x0fac…7a0a | 4 | 0 | 387 / 810 | excluido 4 | +0,00 | -0,00 | 0 |
| 0x2cb2…3f19 | 30 | 8 | 203 / 285 | tope 12, bajo_minimo 5 | +0,83 | -7,20 | 0 |
| 0x7ca1…9235 | 861 | 487 | 223 / 657 | excluido 135, tope 102, bajo_minimo 69, redondeo 13, riesgo 10, flujo_caido 1, deslizamiento 1 | +1,15 | -58,16 | 0 |
| 0x696d…8e28 | 172 | 27 | 155 / 431 | tope 102, bajo_minimo 35, deslizamiento 3, flujo_caido 1 | +1,57 | -31,38 | 0 |
| 0xcf3f…f95f | 2496 | 339 | 219 / 557 | tope 611, bajo_minimo 332, riesgo 24, excluido 22, redondeo 14 | -1,86 | -37,85 | 0 |

## Simulación en vivo (servicio de líderes)

Modo **SIMULADO** (Simulación: saldo virtual, sin órdenes reales ni de testnet); resumen de 2026-10-19 00:34 UTC (hace 7 s). Subcuentas: 7; seguimiento desde 2026-10-16 19:16 UTC (**53,3 h**). Reconciliaciones: 23667; con diferencia no explicada: 34 (acumulado); sin diferencias no explicadas desde 2026-10-16 20:25 UTC (**52,2 h**); en pausa ahora: 0.

| Líder | Capital | Resultado | Órdenes | Rechazos | Posiciones | Pausa |
|---|---|---|---|---|---|---|
| 0x0facac3b | 10 000,00 | +0,00 | 0 | 4 | 0 | — |
| 0x2cb21297 | 10 000,00 | +0,00 | 0 | 0 | 0 | — |
| 0xcf3f419d | 10 000,00 | +0,00 | 0 | 1634 | 0 | — |
| 0x7ca165f3 | 9 965,80 | -34,20 | 357 | 210 | 1 | — |
| 0x7b7f72a2 | 9 960,88 | -39,12 | 592 | 3005 | 2 | — |
| 0x696d1265 | 9 954,62 | -45,38 | 14 | 128 | 0 | — |
| 0xf5d81a13 | 9 858,87 | -141,13 | 3902 | 79819 | 0 | — |

## Método y supuestos

- Mismo motor en vivo y en la reproducción (`eim/copytrading/copy_engine.py`): objetivo = posición del líder × capital asignado / cuenta del líder (fijada al abrir cada viaje; cuenta de `portfolio`). Topes: 40% del capital por moneda y 150% por líder; deslizamiento máximo 0.5% frente a la entrada media del líder; mínimos del exchange de `meta` (hyperliquid:info.meta); lo abierto antes de seguirlo no se copia.
- Riesgo: cada orden que aumenta riesgo pasa por el motor T29 con `risk_copy_v1` (stop de protección 5%, señal ≤ 30 s, flujo confirmado ≤ 2 min, pérdida diaria/semanal, enfriamiento, kill-switch propio por caída). Reducir o cerrar nunca se veta.
- La orden llega 300 ms después de ver la ejecución del líder; comisión de tomador 0.045% (Hyperliquid, nivel base); funding horario con la tasa real pagada por los líderes capturados; marcas y stops con velas de 1 min de Hyperliquid.
- Reconciliación con cada foto del líder: una diferencia sin motivo registrado en 2 comprobaciones seguidas pausa la subcuenta y avisa (nunca se opera para «cuadrar»).
- Limitaciones: sin impacto del tamaño propio en el libro (subcuenta pequeña); stops evaluados al cierre de cada minuto; sin cotización grabada, el precio es un supuesto declarado arriba; una subcuenta por líder (sin compensar posiciones entre líderes: eso es el asignador de T46).
