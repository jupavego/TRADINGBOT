# T91 — Portabilidad de los agentes, con capacidades y elegibilidad

Generado: 2026-11-25 23:52 UTC · reproducible con `python scripts/agents_eligibility.py` · mismas series que `reports/t87_portabilidad.md`, ahora con los 20 agentes por `run_eligible`.

Cada celda: estado en T87 (el agente tal cual) → estado con T91. «no elegible» = no corre y sale `no_data` con el motivo escrito.

| Agente | `XAUUSDT` (commodity.binance.usdm.XAUUSDT) | `SP500` (index.yahoo.^GSPC) | `NASDAQ` (index.yahoo.^IXIC) | `BTCUSDT` (crypto.binance.usdm.BTCUSDT) |
|---|---|---|---|---|
| `arbitrage` | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** |
| `bots` | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** |
| `calendar` | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** |
| `context` | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** |
| `derivatives` | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** |
| `elliott` | ok → ok | ok → ok | ok → ok | ok → ok |
| `ema` | ok → ok | ok → ok | ok → ok | ok → ok |
| `intermarket` | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** |
| `levels` | ok → ok | ok → ok | ok → ok | ok → ok |
| `liquidations` | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** |
| `literature` | ok → ok | ok → ok | ok → ok | ok → ok |
| `microstructure` | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** |
| `plan` | ok → ok | ok → **no elegible** | ok → **no elegible** | ok → ok |
| `price_action` | ok → ok | ok → ok | ok → ok | ok → ok |
| `regime` | ok → ok | ok → ok | ok → ok | ok → ok |
| `seasonality` | ok → ok | ok → ok | ok → ok | ok → ok |
| `smart_money` | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** | no_data → **no elegible** |
| `structure` | degraded → degraded | ok → **no elegible** | ok → **no elegible** | ok → ok |
| `technical` | degraded → degraded | degraded → degraded | degraded → degraded | degraded → degraded |
| `vwap` | ok → ok | ok → **no elegible** | ok → **no elegible** | ok → ok |

## Resumen en las series no cripto

- degradado con aviso: **4**
- elegible: **23**
- no elegible con motivo: **33**

- `vwap` en los índices (acierto silencioso de T87: `ok` con un ancla muerta): **corregido**, ya no publica `ok`

## Motivos y avisos de T91, literales

### `XAUUSDT`
- `arbitrage`: clase no soportada: commodity (el agente aplica a crypto)
- `bots`: clase no soportada: commodity (el agente aplica a crypto)
- `calendar`: no hay calendario económico
- `context`: no hay titulares
- `derivatives`: no hay funding (no es un perpetuo o no se sincronizó); no hay interés abierto
- `intermarket`: no hay series de intermercado
- `liquidations`: clase no soportada: commodity (el agente aplica a crypto)
- `microstructure`: marco no soportado: 1d (admite 15m, 1h, 1m, 4h, 5m)
- `smart_money`: clase no soportada: commodity (el agente aplica a crypto)

### `SP500`
- `arbitrage`: clase no soportada: index (el agente aplica a crypto)
- `bots`: clase no soportada: index (el agente aplica a crypto)
- `calendar`: no hay calendario económico
- `context`: no hay titulares
- `derivatives`: modelo de sesión no soportado: exchange_hours (el agente pide 24/7)
- `intermarket`: no hay series de intermercado
- `liquidations`: clase no soportada: index (el agente aplica a crypto)
- `microstructure`: clase no soportada: index (el agente aplica a commodity, crypto, equity, etf, future)
- `plan`: necesita volumen y el instrumento no tiene volumen negociado
- `smart_money`: clase no soportada: index (el agente aplica a crypto)
- `structure`: necesita volumen y el instrumento no tiene volumen negociado
- `technical`: elegible, degradado con aviso: sin volumen negociado: pierde la parte que lo usa
- `vwap`: necesita volumen y el instrumento no tiene volumen negociado

### `NASDAQ`
- `arbitrage`: clase no soportada: index (el agente aplica a crypto)
- `bots`: clase no soportada: index (el agente aplica a crypto)
- `calendar`: no hay calendario económico
- `context`: no hay titulares
- `derivatives`: modelo de sesión no soportado: exchange_hours (el agente pide 24/7)
- `intermarket`: no hay series de intermercado
- `liquidations`: clase no soportada: index (el agente aplica a crypto)
- `microstructure`: clase no soportada: index (el agente aplica a commodity, crypto, equity, etf, future)
- `plan`: necesita volumen y el instrumento no tiene volumen negociado
- `smart_money`: clase no soportada: index (el agente aplica a crypto)
- `structure`: necesita volumen y el instrumento no tiene volumen negociado
- `technical`: elegible, degradado con aviso: sin volumen negociado: pierde la parte que lo usa
- `vwap`: necesita volumen y el instrumento no tiene volumen negociado

### `BTCUSDT`
- `arbitrage`: no hay escáner de arbitraje
- `bots`: no hay posturas del escuadrón de bots
- `calendar`: no hay calendario económico
- `context`: no hay titulares
- `derivatives`: no hay funding (no es un perpetuo o no se sincronizó); no hay interés abierto
- `intermarket`: no hay series de intermercado
- `liquidations`: no hay flujo de liquidaciones en vivo; no hay liquidaciones históricas
- `microstructure`: marco no soportado: 1d (admite 15m, 1h, 1m, 4h, 5m)
- `smart_money`: no hay tablero de líderes (copy trading)

asof de la corrida: 2026-11-25 23:51 UTC
