# T87 — Costo por agente y del ciclo (medido)

Generado: 2026-11-20 11:41 UTC · reproducible con `python scripts/agents_cost.py` · 7 repeticiones por agente tras una de calentamiento (mediana, p90 y máximo).

`context` se mide **sin analizador LLM** (el banco no llama a ninguna API): su costo real es la llamada al modelo. Los agentes que salen `no_data` cuestan lo que cuesta comprobar que les falta el dato — ese es justo el costo que paga el escáner cuando el instrumento no tiene funding, libro o líderes.

## Marco 1h · BTCUSDT

Almacén `C:/Users/jo/Desktop/JP/TRADINGBOT/v2/data` · 500 velas cerradas · asof 2026-11-20 11:39 UTC · 20 agentes (11 solo `candles`).

| Agente | versión | requiere | estado | mediana (ms) | p90 (ms) | máx (ms) | pico mem (KiB) |
|---|---|---|---|---:|---:|---:|---:|
| `plan` · | 1.0.0 | candles | ok | 1414.23 | 2591.94 | 2591.94 | 1,714 |
| `regime` · | 1.0.0 | candles | ok | 113.08 | 117.64 | 117.64 | 70 |
| `price_action` · | 1.0.0 | candles | ok | 106.46 | 139.26 | 139.26 | 142 |
| `structure` · | 1.0.0 | candles | ok | 87.07 | 239.34 | 239.34 | 1,658 |
| `technical` · | 0.1.0 | candles | ok | 85.00 | 227.15 | 227.15 | 925 |
| `ema` · | 1.0.0 | candles | ok | 54.78 | 63.36 | 63.36 | 382 |
| `vwap` · | 1.0.0 | candles | ok | 48.03 | 218.62 | 218.62 | 389 |
| `literature` · | 0.1.0 | candles | degraded | 6.82 | 37.45 | 37.45 | 67 |
| `derivatives` | 1.0.0 | candles, funding, open_interest | ok | 2.25 | 2.82 | 2.82 | 28 |
| `levels` · | 1.0.0 | candles | ok | 2.06 | 5.55 | 5.55 | 40 |
| `arbitrage` | 1.0.0 | arb | degraded | 2.03 | 2.45 | 2.45 | 144 |
| `intermarket` | 0.1.0 | intermarket | ok | 1.93 | 6.65 | 6.65 | 56 |
| `microstructure` | 1.0.0 | candles, micro | ok | 1.62 | 2.68 | 2.68 | 10 |
| `seasonality` · | 1.0.0 | candles | no_data | 0.88 | 1.42 | 1.42 | 26 |
| `liquidations` | 2.0.0 | liq_flow, liquidations | degraded | 0.82 | 1.25 | 1.25 | 22 |
| `elliott` · | 1.0.0 | candles | ok | 0.23 | 0.28 | 0.28 | 18 |
| `calendar` | 1.1.0 | events | ok | 0.06 | 0.09 | 0.09 | 8 |
| `context` | 1.0.0 | headlines | no_data | 0.01 | 0.03 | 0.03 | 3 |
| `bots` | 0.1.0 | bot_signals | no_data | 0.01 | 0.02 | 0.02 | 2 |
| `smart_money` | 0.1.0 | leaders | no_data | 0.01 | 0.01 | 0.01 | 2 |

`·` = portable por dato (solo pide `candles`).

- **Ciclo completo, suma en serie**: 1927.4 ms por instrumento.
- **Ciclo completo, `run_agents` en paralelo** (hilos, con el GIL): 1986.1 ms.
- **Portables por dato** (11 agentes de `candles`): 1918.6 ms (100% del ciclo) — **no** es la etapa barata: `plan` solo pide `candles` y se lleva 73% del ciclo.
- **Baratos por costo** (≤ 20 ms: `smart_money`, `bots`, `context`, `calendar`, `elliott`, `liquidations`, `seasonality`, `microstructure`, `intermarket`, `arbitrage`, `levels`, `derivatives`, `literature`): 18.7 ms (1.0% del ciclo).

## Marco 4h · BTCUSDT

Almacén `C:/Users/jo/Desktop/JP/TRADINGBOT/v2/data` · 500 velas cerradas · asof 2026-11-20 11:40 UTC · 20 agentes (11 solo `candles`).

| Agente | versión | requiere | estado | mediana (ms) | p90 (ms) | máx (ms) | pico mem (KiB) |
|---|---|---|---|---:|---:|---:|---:|
| `plan` · | 1.0.0 | candles | ok | 1418.15 | 2304.64 | 2304.64 | 1,774 |
| `regime` · | 1.0.0 | candles | ok | 108.82 | 119.57 | 119.57 | 70 |
| `price_action` · | 1.0.0 | candles | ok | 98.73 | 161.83 | 161.83 | 142 |
| `structure` · | 1.0.0 | candles | ok | 88.15 | 94.44 | 94.44 | 1,657 |
| `ema` · | 1.0.0 | candles | ok | 81.84 | 190.48 | 190.48 | 377 |
| `technical` · | 0.1.0 | candles | ok | 65.09 | 120.93 | 120.93 | 922 |
| `vwap` · | 1.0.0 | candles | ok | 40.91 | 50.58 | 50.58 | 389 |
| `seasonality` · | 1.0.0 | candles | ok | 17.80 | 25.92 | 25.92 | 51 |
| `literature` · | 0.1.0 | candles | ok | 2.37 | 2.80 | 2.80 | 67 |
| `arbitrage` | 1.0.0 | arb | degraded | 2.06 | 3.48 | 3.48 | 144 |
| `levels` · | 1.0.0 | candles | ok | 1.92 | 2.27 | 2.27 | 40 |
| `derivatives` | 1.0.0 | candles, funding, open_interest | ok | 1.79 | 1.92 | 1.92 | 20 |
| `intermarket` | 0.1.0 | intermarket | ok | 1.35 | 1.48 | 1.48 | 56 |
| `microstructure` | 1.0.0 | candles, micro | degraded | 0.77 | 0.79 | 0.79 | 8 |
| `liquidations` | 2.0.0 | liq_flow, liquidations | degraded | 0.37 | 0.57 | 0.57 | 12 |
| `elliott` · | 1.0.0 | candles | ok | 0.25 | 0.26 | 0.26 | 20 |
| `calendar` | 1.1.0 | events | ok | 0.06 | 0.08 | 0.08 | 8 |
| `context` | 1.0.0 | headlines | no_data | 0.01 | 0.02 | 0.02 | 3 |
| `bots` | 0.1.0 | bot_signals | no_data | 0.01 | 0.02 | 0.02 | 2 |
| `smart_money` | 0.1.0 | leaders | no_data | 0.01 | 0.01 | 0.01 | 2 |

`·` = portable por dato (solo pide `candles`).

- **Ciclo completo, suma en serie**: 1930.5 ms por instrumento.
- **Ciclo completo, `run_agents` en paralelo** (hilos, con el GIL): 4123.5 ms.
- **Portables por dato** (11 agentes de `candles`): 1924.0 ms (100% del ciclo) — **no** es la etapa barata: `plan` solo pide `candles` y se lleva 73% del ciclo.
- **Baratos por costo** (≤ 20 ms: `smart_money`, `bots`, `context`, `calendar`, `elliott`, `liquidations`, `microstructure`, `intermarket`, `derivatives`, `levels`, `arbitrage`, `literature`, `seasonality`): 28.8 ms (1.5% del ciclo).

## Marco 1d · BTCUSDT

Almacén `C:/Users/jo/Desktop/JP/TRADINGBOT/v2/data/universe_perps` · 500 velas cerradas · asof 2026-11-17 00:00 UTC · 20 agentes (11 solo `candles`).

| Agente | versión | requiere | estado | mediana (ms) | p90 (ms) | máx (ms) | pico mem (KiB) |
|---|---|---|---|---:|---:|---:|---:|
| `plan` · | 1.0.0 | candles | ok | 1299.85 | 2096.73 | 2096.73 | 1,690 |
| `regime` · | 1.0.0 | candles | ok | 166.86 | 202.28 | 202.28 | 70 |
| `structure` · | 1.0.0 | candles | ok | 142.51 | 313.64 | 313.64 | 1,666 |
| `price_action` · | 1.0.0 | candles | ok | 95.62 | 129.92 | 129.92 | 143 |
| `ema` · | 1.0.0 | candles | ok | 83.57 | 96.09 | 96.09 | 377 |
| `vwap` · | 1.0.0 | candles | ok | 40.55 | 50.27 | 50.27 | 389 |
| `technical` · | 0.1.0 | candles | ok | 25.35 | 26.76 | 26.76 | 556 |
| `seasonality` · | 1.0.0 | candles | ok | 13.72 | 17.94 | 17.94 | 53 |
| `literature` · | 0.1.0 | candles | ok | 3.83 | 4.99 | 4.99 | 67 |
| `levels` · | 1.0.0 | candles | ok | 2.54 | 4.09 | 4.09 | 40 |
| `elliott` · | 1.0.0 | candles | ok | 0.43 | 0.47 | 0.47 | 68 |
| `microstructure` | 1.0.0 | candles, micro | no_data | 0.03 | 0.06 | 0.06 | 2 |
| `liquidations` | 2.0.0 | liq_flow, liquidations | no_data | 0.01 | 0.06 | 0.06 | 2 |
| `context` | 1.0.0 | headlines | no_data | 0.01 | 0.02 | 0.02 | 3 |
| `bots` | 0.1.0 | bot_signals | no_data | 0.01 | 0.02 | 0.02 | 2 |
| `arbitrage` | 1.0.0 | arb | no_data | 0.01 | 0.01 | 0.01 | 2 |
| `intermarket` | 0.1.0 | intermarket | no_data | 0.01 | 0.02 | 0.02 | 2 |
| `smart_money` | 0.1.0 | leaders | no_data | 0.01 | 0.01 | 0.01 | 2 |
| `derivatives` | 1.0.0 | candles, funding, open_interest | no_data | 0.01 | 0.01 | 0.01 | 2 |
| `calendar` | 1.1.0 | events | no_data | 0.01 | 0.01 | 0.01 | 2 |

`·` = portable por dato (solo pide `candles`).

- **Ciclo completo, suma en serie**: 1874.9 ms por instrumento.
- **Ciclo completo, `run_agents` en paralelo** (hilos, con el GIL): 1786.7 ms.
- **Portables por dato** (11 agentes de `candles`): 1874.8 ms (100% del ciclo) — **no** es la etapa barata: `plan` solo pide `candles` y se lleva 69% del ciclo.
- **Baratos por costo** (≤ 20 ms: `calendar`, `derivatives`, `smart_money`, `intermarket`, `arbitrage`, `bots`, `context`, `liquidations`, `microstructure`, `elliott`, `levels`, `literature`, `seasonality`): 20.6 ms (1.1% del ciclo).

## Extrapolación al universo

Un marco por instrumento y una pasada; el tiempo de OBTENER los datos no está incluido (lo mide T90). `proc` = procesos del equipo (4 núcleos; este proyecto no pasa de 2 por la cola, ver `CLAUDE.md`).

| Marco | etapa | ms/instr. | 1 000 (1 proc) | 1 000 (4 proc) | 10 000 (1 proc) | 10 000 (4 proc) |
|---|---|---:|---:|---:|---:|---:|
| 1h | ciclo completo | 1927.4 | 0.54 h | 0.13 h | 5.35 h | 1.34 h |
| 1h | portables por dato | 1918.6 | 0.53 h | 0.13 h | 5.33 h | 1.33 h |
| 1h | baratos por costo (≤ 20 ms) | 18.7 | 0.01 h | 0.00 h | 0.05 h | 0.01 h |
| 4h | ciclo completo | 1930.5 | 0.54 h | 0.13 h | 5.36 h | 1.34 h |
| 4h | portables por dato | 1924.0 | 0.53 h | 0.13 h | 5.34 h | 1.34 h |
| 4h | baratos por costo (≤ 20 ms) | 28.8 | 0.01 h | 0.00 h | 0.08 h | 0.02 h |
| 1d | ciclo completo | 1874.9 | 0.52 h | 0.13 h | 5.21 h | 1.30 h |
| 1d | portables por dato | 1874.8 | 0.52 h | 0.13 h | 5.21 h | 1.30 h |
| 1d | baratos por costo (≤ 20 ms) | 20.6 | 0.01 h | 0.00 h | 0.06 h | 0.01 h |

Lectura para T93: **el embudo no puede definirse por `requires`**, porque los agentes más caros son justo los portables (solo `candles`). Hay que definirlo por costo medido: con los baratos por costo el universo entero cabe en minutos; con el ciclo completo, no cabe. Y la caché por `(instrumento, marco, hash de datos, versión del agente)` evita repetir incluso esa etapa cuando no hay vela nueva.
