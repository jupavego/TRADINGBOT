# Copy trading — replicación simulada (T42)

Generado 2026-10-16 20:43 UTC · modo **SIMULADO** (saldo virtual de 10 000 USDC por líder; ninguna orden real ni de testnet) · *El rendimiento pasado no garantiza resultados futuros.*

## Veredicto

- Líderes simulados: 7; aprobados por el scorecard (T41): 0. **7 se simulan solo para medir** (ninguno debería copiarse hoy).
- Rendimiento **aparente** (el del líder × proporción, viajes cerrados): +783,65 USD. **Copiable** (subcuentas, mismos viajes): -55,49 USD.
- Por unidad de nocional, en los viajes copiados: líder 7,6, 19,0, 19,4, 19,9, -7,8 pb · seguidor -5,8, -22,3, 6,1, 49,8, -30,5 pb (por líder, mismo orden que la tabla).
- La brecha viene sobre todo de: tamaño (topes, redondeo, tope de riesgo) -579,97 USD; comisiones (tomador propio vs las del líder) -139,54 USD; viajes no copiados -71,05 USD.
- Muestra corta (horas, decenas de viajes): las cifras describen lo ocurrido, no estiman un edge; ninguna prueba de significancia aplica con este n.

## Resultado por líder (reproducción del historial capturado)

| Líder | Estado T41 | Ventana | Viajes líder (cerrados) | Copiados | No copiados | Aparente (USD) | Copiable (USD) | pb líder | pb seguidor | Capital final | Caída máx. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0x7b7f…dee2 | rejected | 23,1 h | 157 | 100 | 57 | +167,06 | -51,36 | 7,6 | -5,8 | 9 955,30 (-0,45 %) | +1,2 % |
| 0xf5d8…ad53 | rejected | 23,1 h | 1228 | 0 | 1228 | +73,19 | +0,00 | — | — | 9 944,46 (-0,56 %) | +0,7 % |
| 0x0fac…7a0a | rejected | 23,0 h | 0 | 0 | 0 | +0,00 | +0,00 | — | — | 10 000,00 (+0,00 %) | +0,0 % |
| 0x2cb2…3f19 | rejected | 23,0 h | 2 | 2 | 0 | +249,54 | -17,84 | 19,0 | -22,3 | 9 982,16 (-0,18 %) | +1,1 % |
| 0x7ca1…9235 | rejected | 23,0 h | 9 | 9 | 0 | +29,37 | +8,76 | 19,4 | 6,1 | 10 006,79 (+0,07 %) | +0,3 % |
| 0x696d…8e28 | rejected | 23,0 h | 3 | 3 | 0 | +371,55 | +56,95 | 19,9 | 49,8 | 10 052,30 (+0,52 %) | +1,3 % |
| 0xcf3f…f95f | rejected | 23,0 h | 28 | 6 | 22 | -107,07 | -52,00 | -7,8 | -30,5 | 9 969,18 (-0,31 %) | +0,8 % |

## Copiable vs aparente: causas de la diferencia

Aparente total **+783,65 USD** → copiable **-55,49 USD** (diferencia -839,13 USD = suma de causas):

| Causa | Aporte (USD) | 0x7b7f…dee2 | 0xf5d8…ad53 | 0x0fac…7a0a | 0x2cb2…3f19 | 0x7ca1…9235 | 0x696d…8e28 | 0xcf3f…f95f |
|---|---|---|---|---|---|---|---|---|
| latencia (el precio se movió antes de nuestra orden) | -13,12 | +2,57 | +0,00 | +0,00 | -15,79 | +3,35 | +0,72 | -3,97 |
| diferencial (cruzar el libro: ask/bid vs medio) | -21,01 | -12,16 | +0,00 | +0,00 | -3,05 | -1,95 | -3,04 | -0,82 |
| comisiones (tomador propio vs las del líder) | -139,54 | -101,76 | +0,00 | +0,00 | -0,47 | -19,21 | +0,03 | -18,12 |
| funding (propio vs el del líder a nuestro tamaño) | +0,52 | -0,26 | +0,00 | +0,00 | +0,82 | +0,00 | -0,00 | -0,03 |
| viajes no copiados | -71,05 | -77,78 | -73,19 | +0,00 | +0,00 | +0,00 | +0,00 | +79,92 |
| tamaño (topes, redondeo, tope de riesgo) | -579,97 | -10,89 | +0,00 | +0,00 | -241,84 | -3,61 | -337,58 | +13,95 |
| resto (aumentos omitidos, stops, redondeo a mitad) | -14,97 | -18,14 | +0,00 | +0,00 | -7,05 | +0,81 | +25,27 | -15,86 |

Viajes no copiados por motivo (n · aporte):

- `bajo_minimo`: 910 viajes · -5,35 USD
- `riesgo`: 230 viajes · -1,44 USD
- `redondeo`: 160 viajes · +4,63 USD
- `deslizamiento`: 6 viajes · -70,56 USD
- `flujo_caido`: 1 viajes · +1,67 USD

## Reconciliación de la reproducción

- Reconciliaciones con la foto real del líder: 2074; con alguna diferencia explicada (topes, mínimos, vetos, señales en camino): 1296; con diferencia **no explicada**: 3 (aisladas: ninguna se repitió en la foto siguiente) → pausas: **0**.
- Resincronizaciones por hueco de captura conocido (> 5 min sin confirmar el flujo: equipo apagado, reinicios del servicio): 14. Ejecuciones llegadas tarde y anteriores a lo ya procesado (reenvío del WS antes que el relleno REST): 374, tratadas como historial.

## Ejecución simulada

Precio del seguidor por señal:

- bid/ask grabado (WS `bbo`): 50578 (94%)
- cierre de vela 1 min + deslizamiento T25 (supuesto): 3005 (6%)
- precio del líder + deslizamiento base (supuesto): 10 (0%)
- precio medio `allMids` + medio diferencial supuesto: 9 (0%)

| Líder | Señales | Órdenes | Latencia señal p50 / p90 (ms) | Rechazos por motivo | Funding (USD) | Comisiones (USD) | Horas sin tasa |
|---|---|---|---|---|---|---|---|
| 0x7b7f…dee2 | 2939 | 1283 | 205 / 487 | bajo_minimo 923, excluido 130, riesgo 93, redondeo 44, deslizamiento 26, tope 18, flujo_caido 5 | -0,23 | -109,11 | 0 |
| 0xf5d8…ad53 | 48855 | 972 | 196 / 444 | riesgo 17103, bajo_minimo 6640, excluido 2373, redondeo 513, deslizamiento 216, tope 56 | -0,05 | -27,23 | 0 |
| 0x0fac…7a0a | 0 | 0 | — / — | — | +0,00 | -0,00 | 0 |
| 0x2cb2…3f19 | 30 | 8 | 203 / 285 | tope 12, bajo_minimo 5 | +0,83 | -7,20 | 0 |
| 0x7ca1…9235 | 298 | 151 | 228 / 556 | excluido 135, bajo_minimo 13, redondeo 2 | -0,03 | -21,14 | 0 |
| 0x696d…8e28 | 52 | 10 | 160 / 469 | tope 33, bajo_minimo 6, deslizamiento 3 | +0,28 | -12,11 | 0 |
| 0xcf3f…f95f | 1054 | 250 | 228 / 546 | tope 233, bajo_minimo 179, excluido 22, riesgo 22, redondeo 7 | -0,25 | -28,39 | 0 |

## Simulación en vivo (servicio de líderes)

Modo **SIMULADO** (Simulación: saldo virtual, sin órdenes reales ni de testnet); resumen de 2026-10-16 20:43 UTC (hace 10 s). Subcuentas: 7; seguimiento desde 2026-10-16 19:16 UTC (**1,4 h**). Reconciliaciones: 1078; con diferencia no explicada: 34 (acumulado); sin diferencias no explicadas desde 2026-10-16 20:25 UTC (**0,3 h**); en pausa ahora: 0.

| Líder | Capital | Resultado | Órdenes | Rechazos | Posiciones | Pausa |
|---|---|---|---|---|---|---|
| 0x7ca165f3 | 10 002,14 | +2,14 | 17 | 16 | 1 | — |
| 0x0facac3b | 10 000,00 | +0,00 | 0 | 0 | 0 | — |
| 0x2cb21297 | 10 000,00 | +0,00 | 0 | 0 | 0 | — |
| 0xcf3f419d | 10 000,00 | +0,00 | 0 | 148 | 0 | — |
| 0xf5d81a13 | 9 999,79 | -0,21 | 15 | 4827 | 0 | — |
| 0x696d1265 | 9 996,18 | -3,82 | 2 | 26 | 1 | — |
| 0x7b7f72a2 | 9 995,65 | -4,35 | 72 | 261 | 3 | — |

## Método y supuestos

- Mismo motor en vivo y en la reproducción (`eim/copytrading/copy_engine.py`): objetivo = posición del líder × capital asignado / cuenta del líder (fijada al abrir cada viaje; cuenta de `portfolio`). Topes: 40% del capital por moneda y 150% por líder; deslizamiento máximo 0.5% frente a la entrada media del líder; mínimos del exchange de `meta` (hyperliquid:info.meta); lo abierto antes de seguirlo no se copia.
- Riesgo: cada orden que aumenta riesgo pasa por el motor T29 con `risk_copy_v1` (stop de protección 5%, señal ≤ 30 s, flujo confirmado ≤ 2 min, pérdida diaria/semanal, enfriamiento, kill-switch propio por caída). Reducir o cerrar nunca se veta.
- La orden llega 300 ms después de ver la ejecución del líder; comisión de tomador 0.045% (Hyperliquid, nivel base); funding horario con la tasa real pagada por los líderes capturados; marcas y stops con velas de 1 min de Hyperliquid.
- Reconciliación con cada foto del líder: una diferencia sin motivo registrado en 2 comprobaciones seguidas pausa la subcuenta y avisa (nunca se opera para «cuadrar»).
- Limitaciones: sin impacto del tamaño propio en el libro (subcuenta pequeña); stops evaluados al cierre de cada minuto; sin cotización grabada, el precio es un supuesto declarado arriba; una subcuenta por líder (sin compensar posiciones entre líderes: eso es el asignador de T46).
