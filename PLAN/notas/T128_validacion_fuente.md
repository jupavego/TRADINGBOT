# T128 — Validación de la fuente nueva del agente de microestructura (◆ resuelta el 2026-11-07)

**Decisión delegada** («toma tu la mejor decision», 2026-11-07). La ◆ pedía «validar unas horas con
el recolector viejo en otra carpeta». No hizo falta volver a encenderlo. El recolector viejo (T23,
`data/micro/`) y la captura HFT (`data/micro_hft/`) corrieron a la vez del 2026-10-28 23:37 al
2026-11-02 23:13 UTC, y los trades de los dos siguen en disco. Se comparan vela por vela, con la
misma reducción que hace `eim/data/micro.py` (compra = agresor comprador, venta = agresor vendedor;
en la captura, un `agg_id` repetido tras reconectar cuenta una vez). Así no se añadió carga al equipo
ni riesgo para la racha de T78.

**Script:** `v2/scripts/t128_validar_fuente.py` (solo lectura, DuckDB con 700 MB y 2 hilos, en
prioridad `batch`). Desde `v2/`:

```
python -m eim.operation.priority run batch -- python -I scripts/t128_validar_fuente.py data 60
python -m eim.operation.priority run batch -- python -I scripts/t128_validar_fuente.py data 15
```

Se excluye toda vela con un hueco en cualquiera de las dos fuentes (los instantes de T23 y los
tramos de la captura que no son «silencio», como en `micro.py`). También se excluyen las que no
tienen datos en una de ellas, por ejemplo el apagado del 31-oct 21:46 al 1-nov 20:34 UTC.

## Resultado (2026-11-07 14:40 UTC)

| Velas | En el tramo común | Con hueco en alguna | Comparables | Compra y venta idénticas | Delta con el mismo signo |
|---|---|---|---|---|---|
| 1 h (29-oct 00:00 → 2-nov 23:00 UTC) | 119 | 43 | 39 | **38 de 39** | 39 de 39 |
| 15 min (28-oct 23:45 → 2-nov 23:00 UTC) | 477 | 81 | 242 | **239 de 242** | 242 de 242 |

Trades sumados en las velas comparables: 1 628 318 en el viejo y 1 628 341 en la captura (1 h);
2 732 387 y 2 738 254 (15 min).

**Donde difieren, siempre tiene más la captura.** El recolector viejo perdió trades sin marcar
hueco:

| Vela (UTC) | Viejo: compra / venta (BTC) | Captura: compra / venta (BTC) |
|---|---|---|
| 2026-10-29 23:30 (15 min) | 1 650,96 / 1 885,64 | 2 007,92 / 2 201,52 |
| 2026-10-31 13:15 (15 min) | 255,26 / 504,78 | 285,40 / 528,88 |
| 2026-10-31 21:45 (15 min) | 11,17 / 4,26 | 11,54 / 4,82 |
| 2026-10-31 21:00 (1 h) | 1 035,52 / 1 109,63 | 1 035,89 / 1 110,19 |

La primera coincide con las desconexiones de Binance del 29-oct a las 23 UTC. La segunda cae en la
saturación del equipo del 31-oct entre las 13 y las 14 UTC. La tercera y la cuarta son los minutos
previos al apagado forzado de las 21:46 UTC.

## Conclusión

La fuente nueva da las mismas cifras que la vieja donde las dos están completas, y es mejor donde
no. Junto con la prueba de regresión del entregable 1 (mismas velas con los mismos mensajes, con y
sin un diff perdido), esto cubre el criterio «el agente `microstructure` da las mismas cifras con la
fuente nueva». El recolector viejo queda retirado.

**No cubre:** las fotos top-10 (OFI e imbalance de profundidad). En el tramo común las escribía solo
el recolector viejo, y desde el 2-nov solo la captura, así que no hay dos fuentes que comparar. Las
cubre la prueba de regresión.

**Lo que sigue abierto en T128:**
- La semana de medición de `leaders.duckdb`, hasta el 2026-11-09 23:13 UTC. Hoy pesa 2 676 MB, frente
  a 1 267 MB tras compactarla el 2-nov.
- Un día completo sin alertas «sin latido» falsas. El 7-nov hay una activa del recolector de
  liquidaciones con el proceso vivo.
