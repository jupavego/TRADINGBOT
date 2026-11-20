# T87 — Portabilidad de los agentes de `candles` a series sin cripto

Generado: 2026-11-20 11:32 UTC · reproducible con `python scripts/agents_portability.py` · **ningún agente fue modificado**.

## Series usadas (reales, ya en el almacén por T183)

| Serie | clase | velas diarias | desde | hasta |
|---|---|---:|---|---|
| `XAUUSDT` | materia prima (perpetuo TradFi de Binance, 24/5 con pausas) | 344 | 2025-12-11 | 2026-11-19 |
| `SP500` | índice de renta variable (^GSPC, sesión de Nueva York) | 400 | 2025-04-21 | 2026-11-19 |
| `NASDAQ` | índice de renta variable (^IXIC, sesión de Nueva York) | 400 | 2025-04-21 | 2026-11-19 |
| `BTCUSDT` | cripto, referencia (perpetuo 24/7) | 400 | 2025-10-16 | 2026-11-19 |

## Resultado por agente y serie

`estado` del `AgentReport`: `ok`, `degraded`, `no_data` o `EXCEPCIÓN` (el agente levantó un error). Entre paréntesis, el nº de avisos.

| Agente | `XAUUSDT` | `SP500` | `NASDAQ` | `BTCUSDT` | veredicto |
|---|---|---|---|---|---|
| `elliott` | ok (2) | ok (3) | ok (3) | ok (1) | ok |
| `ema` | ok | ok | ok | ok | ok |
| `levels` | ok | ok | ok | ok | ok |
| `literature` | ok (2) | ok (2) | ok (2) | ok (1) | ok |
| `plan` | ok (1) | ok (1) | ok (1) | ok (1) | ok |
| `price_action` | ok | ok | ok | ok | ok |
| `regime` | ok | ok | ok | ok | ok |
| `seasonality` | ok (2) | ok (2) | ok (2) | ok (2) | ok |
| `structure` | degraded (1) | ok | ok | ok | degrada |
| `technical` | degraded (3) | degraded (3) | degraded (3) | degraded (3) | degrada |
| `vwap` | ok | ok | ok | ok | ok |

## Avisos y errores, literales

### `XAUUSDT`
- `elliott`: Conteo de Elliott = heurística sujeta a re-conteo; tratar como hipótesis, no como hecho
- `elliott`: Onda 2 retrocedió más allá del inicio de la Onda 1 (regla dura violada)
- `literature`: reglas planteadas en futuros, no en cripto: supuesto 24/7 de cada ficha
- `literature`: Apoyo bibliográfico · no es una señal validada; confianza con techo 0.5 hasta medirla (T54)
- `plan`: Propuesta analítica, no es una orden; el tamaño lo decide el motor de riesgo
- `seasonality`: cobertura real 2025-12 → 2026-10; los años sin datos no se rellenan
- `seasonality`: solo 0 observaciones de Nov (< 3): sin sesgo
- `structure`: solo 344 velas (< 400): warmup de EMA-200 incompleto
- `technical`: marco 4h: 0 velas (< 120), no se evalúa
- `technical`: familias sin datos: flujo (p. ej. flujo requiere taker_buy_v); cobertura 4/5
- `technical`: sin otros marcos con datos: acuerdo multi-marco no medido

### `SP500`
- `elliott`: Conteo de Elliott = heurística sujeta a re-conteo; tratar como hipótesis, no como hecho
- `elliott`: Onda 2 retrocedió más allá del inicio de la Onda 1 (regla dura violada)
- `elliott`: Onda 4 se solapó con el territorio de precio de la Onda 1 (regla dura violada)
- `literature`: reglas planteadas en futuros, no en cripto: supuesto 24/7 de cada ficha
- `literature`: Apoyo bibliográfico · no es una señal validada; confianza con techo 0.5 hasta medirla (T54)
- `plan`: Propuesta analítica, no es una orden; el tamaño lo decide el motor de riesgo
- `seasonality`: cobertura real 2025-04 → 2026-10; los años sin datos no se rellenan
- `seasonality`: solo 1 observaciones de Nov (< 3): sin sesgo
- `technical`: marco 4h: 0 velas (< 120), no se evalúa
- `technical`: familias sin datos: flujo (p. ej. flujo requiere taker_buy_v); cobertura 4/5
- `technical`: sin otros marcos con datos: acuerdo multi-marco no medido

### `NASDAQ`
- `elliott`: Conteo de Elliott = heurística sujeta a re-conteo; tratar como hipótesis, no como hecho
- `elliott`: Onda 2 retrocedió más allá del inicio de la Onda 1 (regla dura violada)
- `elliott`: Onda 4 se solapó con el territorio de precio de la Onda 1 (regla dura violada)
- `literature`: reglas planteadas en futuros, no en cripto: supuesto 24/7 de cada ficha
- `literature`: Apoyo bibliográfico · no es una señal validada; confianza con techo 0.5 hasta medirla (T54)
- `plan`: Propuesta analítica, no es una orden; el tamaño lo decide el motor de riesgo
- `seasonality`: cobertura real 2025-04 → 2026-10; los años sin datos no se rellenan
- `seasonality`: solo 1 observaciones de Nov (< 3): sin sesgo
- `technical`: marco 4h: 0 velas (< 120), no se evalúa
- `technical`: familias sin datos: flujo (p. ej. flujo requiere taker_buy_v); cobertura 4/5
- `technical`: sin otros marcos con datos: acuerdo multi-marco no medido

### `BTCUSDT`
- `elliott`: Conteo de Elliott = heurística sujeta a re-conteo; tratar como hipótesis, no como hecho
- `literature`: Apoyo bibliográfico · no es una señal validada; confianza con techo 0.5 hasta medirla (T54)
- `plan`: Propuesta analítica, no es una orden; el tamaño lo decide el motor de riesgo
- `seasonality`: cobertura real 2025-10 → 2026-10; los años sin datos no se rellenan
- `seasonality`: solo 1 observaciones de Nov (< 3): sin sesgo
- `technical`: marco 4h: 0 velas (< 120), no se evalúa
- `technical`: familias sin datos: flujo (p. ej. flujo requiere taker_buy_v); cobertura 4/5
- `technical`: sin otros marcos con datos: acuerdo multi-marco no medido

asof de la corrida: 2026-11-20 11:32 UTC
