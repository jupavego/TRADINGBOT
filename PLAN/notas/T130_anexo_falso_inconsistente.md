# Anexo de T130 — Diagnóstico del «estado inconsistente» falso del 31-oct

> Escrito el 2026-11-03 por otra sesión como «T129» (fase 18), en el worktree `t129-proteccion-falso-positivo` y sin confirmar. Se conserva aquí como anexo de T130, que ya arregla el fallo (`ladder_floor.early`, `floor_superseded`). Aporta la causa de raíz con el registro de observabilidad. Esa «T129» y su registro en STATUS se descartan: el número T129 es la auditoría del stop dinámico (fase 22).

2026-11-03, desde `juanpablo-cpu`. Solo lectura sobre los datos vivos. Lo único que se escribió fue la reconciliación que aprobó el usuario (al final).

## La operación
`agresivo|BTCUSDT|BTCUSDT:1h:1793412000000:agente_levels`: corto con entrada a 77 357,23, 0,106 BTC y stop inicial en 78 154,70. El escalón 1 son 6,34 USD netos y cada paso suma 3,17 USD.

| seq | Evento | Stop | `updated_t` (UTC) | Grabada (UTC) |
|---|---|---|---|---|
| 1 | alta | 78 154,7 | 31-oct 02:00:00 | 02:22:25 |
| 2 | escalón 2 | 77 164,5 | 31-oct **03:45:00** | 03:45:53 |
| 3 | inconsistente | 77 164,5 | 31-oct 03:45:00 | 03:46:38 |

Motivo de la fila 3: el recálculo la cerraba a las 03:41 UTC, antes del estado guardado de las 03:45 UTC.

## Lo que pasó en el mercado
Hay dos fuentes independientes y coinciden:

- **Velas de 1 m** (`data/candles/…/timeframe=1m`): mínimo de 77 146,4 en la vela de 03:39 y máximo de 77 169,3 en la de 03:40.
- **Trades de la captura HFT** (`data/micro_hft/trades/…/hour=03`): mínimo de 77 146,4 a las 03:39:41 y primer trade ≥ 77 164,5 a las **03:40:03**. Entre 03:45:00 y 03:45:53 el precio estuvo entre 77 180 y 77 200, **por encima del stop** que se acababa de guardar.

El estado guardado como «viva a las 03:45» ya era imposible cuando se escribió.

## Por qué (registro de observabilidad `data/obs/spool/api.20261031.35880.jsonl`)

| UTC | Evento |
|---|---|
| 03:44:55 | El bróker sincroniza el 1 m: +1 vela (hasta la de 03:43) |
| 03:45:08 | Otro ciclo trae la vela de 15 m de 03:30, ya cerrada |
| 03:45:53 | Pasada de protección: le faltaba la vela de 1 m de 03:44 para la de 15 m de 03:30 (14 de 15) |
| 03:45:57 | El bróker sincroniza el 1 m: +1 vela (la de 03:44) |
| 03:46:38 | Pasada siguiente: el 1 m ya cubre la vela, cierra a las 03:41 → `early()` → «inconsistente» |

Cómo se llega a ese resultado:

- `ladder._fine_covers` exige las 15 velas de 1 m para resolver una vela de 15 m ambigua. Sin ellas aplica la regla conservadora: sube el escalón **al final** de la vela de 15 m (03:45:00) y la da por viva.
- Las velas de 1 m solo las sincroniza `PaperService._sync`, en el tick del bróker (cada ~62 s). La de 15 m puede llegar antes por otro ciclo.
- Con el 1 m completo, el cierre real cae **dentro** de la vela que produjo el suelo y antes de su `t`. `ladder_floor.early` no distingue este caso (refinar con 1 m) de un cierre inventado.

**Caso de control, en la misma pasada:** `moderado|…:4h:1793390400000:base_retroceso` guardó también un escalón con `t` 03:45:00 (stop 77 216,3). Su stop se tocó después de las 03:45 (cierre SLD a las 04:15), así que no hubo aviso. El fallo solo aparece si el stop se toca entre el escalón real y el cierre de la vela de 15 m.

## Efecto
- La operación quedó **abierta en el libro del perfil agresivo** del 31-oct al 03-nov, como posición fantasma.
- En ese tiempo el perfil agresivo rechazó 16 cortos por «tope de riesgo abierto por dirección (3 %)». No se ha medido cuántos se deben a ella.
- El aviso «Protección en estado inconsistente: agresivo BTCUSDT» salió en cada arranque de la API.

## Resolución manual (2026-11-03 05:18 UTC, con permiso del usuario)
`python -m eim.paper proteccion reconciliar … --decision recalculo` con la nota del falso positivo. Resultado de la pasada siguiente:

- Escalón 1 a las 03:39 (stop 77 194,3) y escalón 2 a las 03:40 (stop 77 164,5).
- Cierre **SLD a las 03:41 UTC en 77 164,5**: +9,51 USD netos (+0,11 R).
- Diario: 0 inconsistentes.
