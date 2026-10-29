# T119 — Puntuación del escuadrón verificada en la base real (2026-10-25)

Equipo: `laptop-i6pf9ovp-fce8d9` (el del servicio continuo). Todo lo medido es SIMULADO; ningún
bot vota antes ni después de esta tarea.

## 1. ¿Coincidían la API y el informe? No. La causa, antes de tocar nada

Salida de `GET /v2/bots/scorecard` de la API viva (código anterior a T119, recálculo de las
20:01 UTC) frente a `v2/reports/bots_scorecard.json` del 2026-10-20:

```
API: asof 1792958400000 · intentos 18 · {'vota': 0, 'informa': 9, 'rechazado': 0, 'deshabilitado_seguridad': 0}
Informe: asof 1792520100000 · intentos 24 · {'vota': 0, 'informa': 3, 'rechazado': 8, 'deshabilitado_seguridad': 0}
mismos intentos de Holm (id, veredicto, n, p bruto, p Holm, retirado, control): False (18 vs 24)
mismos veredictos y estados por bot: False
```

La API puntuaba bien, pero otra base:
- **El informe se midió en el equipo del otro colaborador** (`git log`: T59/T60 y «bots en datos
  vivos» son de Juan Pablo, 2026-10-20/21), sobre la copia de datos de T58: relleno de 6 meses
  (2026-04-19 → 10-19), FSupertrend con el entorno de Freqtrade (`D:/eim-bots`) y NFI con velas de 5m.
- **La base viva de este equipo nunca recibió ese relleno.** En las copias diarias, `bot_signals`
  aparece por primera vez en la del 2026-10-23 00:00 UTC (72 filas) y empieza el 2026-10-22. Aquí no
  hay entorno de Freqtrade (sin `EIM_BOT_FREQTRADE_*`: ni FSupertrend ni NFI) ni marco 5m.
- Con tres días de posturas cada bot tenía 0–3 operaciones fuera de muestra → V1 insuficiente →
  todos «informa»; 9 estrategias → 18 intentos (el informe: 11 → 24).
- Mecanismo adicional, probado en tests pero **no comprobado en el otro equipo**: el corte (`asof`)
  de toda la medición es el del marco más corto. Si el 5m se queda atrás, el corte se congela, el
  guardado rechaza el mismo `asof` y la API seguía sirviendo la medición anterior con `error` vacío.
  Es la explicación probable de «puede seguir mostrando la medición anterior» en el equipo con NFI.

## 2. Recálculo verificado con la base real

Base: copia diaria `v2/backups/eim_20261025-000020` (`reports` y `paper`, hecha en caliente) + velas
de BTCUSDT de `v2/data/candles` (2026-10-25 22:40 UTC) + `machine_id`. Encima, el relleno de 6
meses con el mismo servicio que `python -m eim.bots.backfill --timeframe 1h --since 2026-04-19`
(modo A, guardado por lotes con `append_many`): **41 031 posturas** (9 estrategias × 4 559 velas de
1h, 2026-04-19 → 2026-10-25), 492 s, pico de 201 MB.

Dos cálculos independientes en procesos distintos: el de la API (mismo cableado que
`eim/api/main.py`: `BotScorer.maybe_run`, luego `GET /v2/bots/scorecard`) y la CLI
(`python -m eim.bots.scorecard_cli`, que escribe el informe). Salida de la comparación:

```
API: asof 1792967400000 · intentos 18 · {'vota': 0, 'informa': 3, 'rechazado': 6, 'deshabilitado_seguridad': 0}
Informe: asof 1792967400000 · intentos 18 · {'vota': 0, 'informa': 3, 'rechazado': 6, 'deshabilitado_seguridad': 0}
freshness: vigente · error: ''
mismos intentos de Holm (id, veredicto, n, p bruto, p Holm, retirado, control): True (18 vs 18)
mismos veredictos y estados por bot: True
mismo resumen: True
```

| Intento | Veredicto | n OOS | p Holm | API = informe |
|---|---|---|---|---|
| hummingbot-directional:bollinger_v1@1h#control@v1 | RECHAZADA | 86 | 1.0 | sí |
| hummingbot-directional:bollinger_v1@1h@v1 | RECHAZADA | 86 | 1.0 | sí |
| hummingbot-directional:macd_bb_v1@1h#control@v1 | EN OBSERVACIÓN | 5 | 1.0 | sí |
| hummingbot-directional:macd_bb_v1@1h@v1 | EN OBSERVACIÓN | 5 | 1.0 | sí |
| jesse-example-strategies:Donchian@1h#control@v1 | EN OBSERVACIÓN | 38 | 1.0 | sí |
| jesse-example-strategies:Donchian@1h@v1 | RECHAZADA | 38 | 1.0 | sí |
| jesse-example-strategies:MACD_EMA@1h#control@v1 | RECHAZADA | 63 | 1.0 | sí |
| jesse-example-strategies:MACD_EMA@1h@v1 | EN OBSERVACIÓN | 64 | 1.0 | sí |
| jesse-example-strategies:RSI2@1h#control@v1 | RECHAZADA | 154 | 1.0 | sí |
| jesse-example-strategies:RSI2@1h@v1 | RECHAZADA | 154 | 1.0 | sí |
| jesse-example-strategies:SMACrossover@1h#control@v1 | EN OBSERVACIÓN | 26 | 1.0 | sí |
| jesse-example-strategies:SMACrossover@1h@v1 | RECHAZADA | 26 | 1.0 | sí |
| jesse-example-strategies:TradingView_RSI@1h#control@v1 | RECHAZADA | 110 | 1.0 | sí |
| jesse-example-strategies:TradingView_RSI@1h@v1 | RECHAZADA | 112 | 1.0 | sí |
| jesse-example-strategies:TurtleRules@1h#control@v1 | RECHAZADA | 177 | 1.0 | sí |
| jesse-example-strategies:TurtleRules@1h@v1 | RECHAZADA | 179 | 0.399445 | sí |
| trendrider-strategy:TrendRiderStrategy@1h#control@v1 | EN OBSERVACIÓN | 12 | 1.0 | sí |
| trendrider-strategy:TrendRiderStrategy@1h@v1 | EN OBSERVACIÓN | 12 | 1.0 | sí |

`v2/reports/bots_scorecard.{md,json}` es ahora este informe (dice en qué máquina y sobre qué base se
midió). Frente al del otro equipo: faltan FSupertrend y NFI (sin modo B aquí); las 9 estrategias
comunes salen igual salvo **MACD_EMA, que pasa de RECHAZADA a EN OBSERVACIÓN** (R medio −0,190 →
−0,097 con 6 días más y las velas de este equipo: deja de ser «claramente negativa»). Las demás
cambian pocas operaciones (p. ej. bollinger 81 → 86). Las condiciones por régimen tienen ahora
régimen (en el otro equipo salían «sin dato»). No se volvió a medir el aporte marginal
(`--marginal`): no cambia ningún estado porque ningún bot pasa la puerta. Criterios (`validation_v1`,
sha `0a5b19962ded`) y regla marginal intactos.

## 3. Pico de memoria del recálculo (41 031 posturas, proceso aparte)

| | Pico working set | Sobre el proceso | Tiempo | DuckDB |
|---|---|---|---|---|
| Antes (código de T59) | 690 MB | +555 MB | 3,8 s | 12 MB |
| CLI, antes | 680 MB | — | 6,1 s | — |
| Después (`PaperStore.regimes`) | 253 MB | +127 MB | ~2 s | 12 MB |

El pico no estaba en DuckDB ni en las posturas (`query_lean`: +50 MB) sino en `regime_lookup`, que
parseaba los 33 183 contextos de 1h del bróker (65 MB de JSON) para leer solo `t` y `regime`
(+525 MB, 2,7 s). Ahora lee `(asof_ms, régimen)` con una consulta. Comprobado igual: mismos 33 183
regímenes y misma tabla que el informe.

## 4. La interfaz nunca presenta una medición vieja como actual

`freshness` en `GET /v2/bots/scorecard` y `GET /v2/bots` (`state`: `vigente`, `fallida` con el
motivo, `vieja` si el corte tiene más de 8 h, `sin_medicion`), con `asof`, `computed`,
`last_attempt` y `last_ok`; `frames` dice qué leyó de cada marco y cuál fija el corte. La pestaña
«Escuadrón» muestra de cuándo es la puntuación y, si no es la actual, un aviso con el motivo.

## 5. Marco 5m al día

10 días de 1m reales de BTCUSDT (2026-10-15 → 10-25) repetidos en ciclos horarios del bróker
(`DeskService._keep_5m`, con el último grupo de 5 min a medias) con un reinicio y dos caídas:

```
1m reales: 14399 de 14400 minutos posibles
202 ciclos en 159 s · reinicio en 10-18 00:02; caída de 30 h desde 10-20 00:00; caída de 6 h desde 10-23 02:00
5m incremental: 2879 velas · de una vez: 2879 · idénticas: True
huecos de 5m en la ventana: 1 (de ellos con 1m incompleto en la fuente: 1) ['2026-10-24T23:55:00+00:00']
```

El único «hueco» es el corte de la ventana de la prueba (no leyó el minuto 23:59, que sí está en la
fuente): ningún hueco real. En este equipo el 5m no existe porque nadie lo usa (no hay NFI); se crea
una vez con `eim.bots.backfill --timeframe 5m` y desde ahí se mantiene solo.

## 6. NFI declarado fuera del ciclo

`GET /v2/bots` → `out_of_cycle`: aquí `freqtrade-strategies` (modo B sin entorno),
`nostalgia-for-infinity` (solo histórico: un ciclo de 5 min pediría 1–6 GB por corrida) y `passivbot`
(carril de simulación). La pestaña «Escuadrón» los lista en «Fuera del ciclo en este equipo», y un bot
cuya última postura tiene más de 3 velas sale «sin señal reciente» y no cuenta en la discrepancia ni
en el apoyo.

## 7. Cuarentena con un bot real

Hallazgo: la API guardaba la cuarentena en memoria, así que la reactivación por CLI del RUNBOOK no
surtía efecto sin reiniciar y un disparo posterior la deshacía. Ahora la API relee
`quarantine.json` (`Quarantine.sync`) y hay CLI (`python -m eim.bots.quarantine list|release`).
Corrida con el adaptador real de Hummingbot sobre las últimas 1 000 velas reales de 1h de BTCUSDT
(fallo inyectado; la reactivación, desde otro proceso):

```
1. vota: ['hummingbot-directional@bollinger_v1']
2. ciclo sano: [('bollinger_v1', 0.0, 'ok'), ('macd_bb_v1', 0.0, 'ok')] · cuarentena: {}
3. ciclo con fallo: [('*', 'degraded', 'error del adaptador: TimeoutError: el ejecutor no respondió ')]
   cuarentena: {'hummingbot-directional@bollinger_v1': {...}} · votan: []
4. CLI release hummingbot-directional@bollinger_v1 --by T119 (otro proceso) → 0: reactivado
   antes del siguiente ciclo (memoria del servicio): ['hummingbot-directional@bollinger_v1']
5. siguiente ciclo: cuarentena {} · votan: ['hummingbot-directional@bollinger_v1']
6. bitácora: trip (TimeoutError…) → release (T119)
```

## 8. Lo que falta en vivo

Para que la API viva diga lo mismo que el informe hay que (a) llevar el relleno a la base viva con
`eim.bots.merge_signals` (solo añade; exige la operación parada uno o dos minutos, `docs/BOTS.md`
§Llevar un relleno a los datos vivos) y (b) desplegar este código. Después: el primer recálculo de
la API (al primer ciclo del bróker) contra la CLI sobre una copia en caliente tomada en la misma
ventana de 15 min.
