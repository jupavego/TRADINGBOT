# T87 — Matriz de reutilización multiactivo (auditoría completa)

Fecha: 2026-11-20. Completa la auditoría rápida de `PLAN/notas/T87_universo_multiactivo.md` §2 con
el código leído módulo a módulo y con cifras medidas. **No cambia nada de `eim/`**: el único código
nuevo son dos bancos de medición en `v2/scripts/` (`agents_cost.py`, `agents_portability.py`).

Insumos medidos en este equipo (`juanpablo-cpu`, 4 núcleos, 16 GB), reproducibles:
- `v2/reports/t87_agents_cost.md` (+ `.json`) — costo por agente y del ciclo en 1 h / 4 h / 1 d.
- `v2/reports/t87_portabilidad.md` — los 11 agentes de `candles` sobre oro, S&P 500 y Nasdaq.

Clases: **R** = reutilizable tal cual · **A** = adaptable (hay que generalizar, el contrato aguanta)
· **C** = específico de cripto/perpetuos (hace falta un hermano, no una adaptación).

---

## 1. Contratos y núcleo

| Módulo | Clase | Acoplamiento concreto | Cambio mínimo | Riesgo BTC/ETH |
|---|---|---|---|---|
| `eim/core/market.py` (`MarketSnapshot`, `Candle`) | **R** | Ninguno de símbolo: `symbol` y `timeframe` son `str` y todo lo demás es opcional (`None` → `no_data`). Único roce: `micro`, `funding`, `basis`, `liq_flow`, `arb`, `leaders` son conceptos de perpetuos, pero **opcionales** (`core/market.py:107-139`) | Nada. Los campos nuevos de otras clases (curva, cadena de opciones, dividendos) se añaden opcionales, igual que T34/T35/T183 | **Nulo** si se añade, no se cambia |
| `eim/core/agent.py` (`Agent`, `requires`) | **R** | Ninguno. `requires: set[str]` ya decide elegibilidad por dato disponible | Nada en el contrato. T91 añade **capacidades declaradas** (supuestos de tiempo y de volumen) junto a `requires` | **Nulo** |
| `eim/core/report.py` (`AgentReport`, `Overlay`) | **R** | Ninguno | Nada | **Nulo** |
| `eim/core/fees.py` | **C** | `USDM_MAKER`/`USDM_TAKER` = tarifa VIP 0 USDⓈ-M de Binance (`core/fees.py`, 1 literal `USDT`) | Pasar de constantes a una **tabla de costos por instrumento** (`InstrumentCosts`) resuelta desde el registro de T89 | **Medio**: es la tarifa única del sistema (T143). Toda cifra de BTC/ETH la usa; cambiar su forma obliga a repasar T27/T49/T145 |
| `eim/core/authority.py` (`TradeProposal`, `RiskDecision`) | **R** | Ninguno de símbolo (T114) | Nada | **Nulo** |
| `eim/core/arb_market.py`, `core/arbitrage.py` | **C** | 6 literales; modelo de arbitraje de Binance | Hermano por clase si alguna lo pide; no se generaliza | **Nulo** (no se toca) |

## 2. Agentes (20 registrados, no 17: la nota de octubre precede a `literature`, `intermarket` y `bots`)

Inventario por `requires` leído en `eim/agents/*/agent.py`:

| Grupo | Agentes | Clase |
|---|---|---|
| Solo `candles` (**11**) | `elliott`, `ema`, `levels`, `literature`, `plan`, `price_action`, `regime`, `seasonality`, `structure`, `technical`, `vwap` | **A** (portables por dato, con supuestos que hay que declarar) |
| Genéricos por otra vía (2) | `calendar` (`events`), `context` (`headlines`) | **R** |
| Transversal ya multiactivo (1) | `intermarket` (`intermarket`: oro, S&P 500, Nasdaq en diario, T183) | **R** |
| Específicos de cripto/derivados (6) | `derivatives` (`funding`, `open_interest`), `liquidations` (`liq_flow`, `liquidations`), `microstructure` (`micro`), `arbitrage` (`arb`), `smart_money` (`leaders`), `bots` (`bot_signals`) | **C** |

### 2.1 Lo que la prueba de portabilidad demostró (`reports/t87_portabilidad.md`)

Los 11 agentes de `candles` corrieron **sin modificar nada** sobre XAUUSDT, S&P 500 y Nasdaq
diarios (series reales del almacén, T183) y sobre BTCUSDT diario como referencia:

- **Ninguno falla**: cero excepciones, cero `no_data`. El contrato aguanta el cambio de clase.
- **`structure` degrada** en XAUUSDT y lo avisa: «solo 344 velas (< 400): warmup de EMA-200
  incompleto». Es longitud de historia, no clase de activo.
- **`technical` degrada en las cuatro series, BTCUSDT incluido**: «familias sin datos: flujo
  (requiere `taker_buy_v`); cobertura 4/5» y «sin otros marcos con datos». En cripto es
  transitorio (el almacén sí tiene `taker_buy_v` y marcos vecinos); en acciones e índices es
  **permanente**: Yahoo no entrega taker buy y esas clases solo tienen diario. T91 debe declararlo
  como capacidad ausente, no como degradación.
- **`literature` ya avisa del supuesto de clase**: «reglas planteadas en futuros, no en cripto:
  supuesto 24/7 de cada ficha». Es el precedente de cómo deben declararse los supuestos.
- **`seasonality`** respeta su propio umbral: con 1 observación por mes devuelve sesgo 0 y avisa.

**El riesgo real no es el fallo, es el acierto silencioso.** Medido:

| Síntoma | Evidencia | Por qué |
|---|---|---|
| `vwap` publica `status="ok"`, sesgo −0,13 (S&P 500) y confianza 0,60 **con una de sus cuatro anclas muerta**, y perderla no le cuesta nada | El período `daily` sale `std = 0,0` y `position = "SIN_DATOS"` | El agente ancla por día UTC, lunes, quincena (días 1/16) y mes (`agents/vwap/compute.py:16`). Con velas de 1 d, el ancla diaria tiene **una sola vela**: VWAP = precio típico y σ = 0. El agente hace lo correcto al excluirla del voto y penalizar con `len(votes)/len(PERIODS)` = 3/4 = 0,75 (`agent.py:87`), **pero `max_confidence = 0.6`** (`params.py:49`) recorta antes: la confianza publicada sigue siendo 0,600, exactamente la misma que con las cuatro anclas vivas. Y `status` solo degrada si hay avisos de `partial` (`agent.py:93`), así que sale `ok`. En acciones y FX el ancla correcta es además la **sesión**, no el día UTC |
| Dos de los cuatro votos pueden ser la misma ventana | `weekly` y `quincenal` devolvieron **el mismo número** (7 340,81 en S&P 500; 63 706,99 en BTCUSDT) | **Coincidencia de calendario, no defecto de la clase**: el ancla semanal es el lunes y la quincenal los días 1/16, y el 2026-11-16 de esta corrida **fue lunes**. Pasa ≈ 2 de cada 7 quincenas y **también en cripto**; cuando pasa, esa ventana pesa el doble en el sesgo y en el acuerdo. Anotado para T91, no es un hallazgo multiactivo |
| `regime`, `levels` razonan en velas, sin saber que una vela puede ser un fin de semana | `regime` etiqueta «volatile» en S&P 500 con permanencia media de 24,9 velas; `levels` da ATR en unidades de precio | No hay noción de sesión ni de calendario de mercado. Para una clase 5×8 h, «20 velas» no es «20 días de mercado» igual que en cripto |
| La anualización está fijada a 1 h de cripto | `backtest/params.py:40` → `bars_per_year: float = 8766.0`; la usan `backtest/metrics.py:51,65,86`, `backtest/report.py:64` y `analytics/agents_marginal.py:212-228` | 8766 = horas de un año 24/7. En diario cripto son 365; en renta variable, ~252 sesiones. Un Sharpe calculado con 8766 sobre velas diarias de acciones queda inflado ×√(8766/252) ≈ **5,9** |

**Conclusión de agentes:** los 11 son portables, pero **ninguno es portable sin declarar supuestos**.
Lo que T91 tiene que exigir a cada agente, además de `requires`: ancla temporal (día UTC / sesión),
si necesita volumen y de qué tipo, velas mínimas de calentamiento, y barras por año para anualizar.

### 2.2 Costo medido por agente (`reports/t87_agents_cost.md`)

Snapshot real de BTCUSDT, 500 velas, 7 repeticiones tras calentamiento, 20 agentes:

| Marco | ciclo en serie | `run_agents` en paralelo | agente dominante |
|---|---:|---:|---|
| 1 h | 1 927 ms | 1 986 ms | `plan` = **73 %** del ciclo |
| 4 h | 1 931 ms | 4 123 ms | `plan` |
| 1 d | 1 875 ms | 1 787 ms | `plan` |

Dos hallazgos que cambian el diseño del embudo de T93:

1. **El embudo NO puede definirse por `requires`.** Los agentes «portables por dato» (solo
   `candles`) son el **100 %** del costo del ciclo, porque el más caro —`plan`— solo pide velas.
   Hay que definir la etapa barata **por costo medido**: los 13 agentes que cuestan ≤ 20 ms suman
   **18,7 ms** (1,0 % del ciclo). 10 000 instrumentos: **0,05 h** con la etapa barata frente a
   **5,35 h** con el ciclo completo (un proceso).
2. **`run_agents` en hilos no acelera nada**: 1 986 ms en paralelo frente a 1 927 ms en serie en
   1 h, y 4 123 ms frente a 1 931 ms en 4 h. Son agentes ligados a CPU y el GIL los serializa, con
   el coste añadido de los hilos. El paralelismo del escáner tiene que ser **por procesos** y
   **sobre instrumentos**, no por agentes dentro de un instrumento (y en este equipo, máximo 2
   procesos: `CLAUDE.md`).

El ciclo completo medido (≈ 1,9 s, 20 agentes) es menos de la mitad de los 4,5 s que T72 midió con
13 agentes; la aritmética de la nota §3 se corrige a la baja, pero la conclusión no cambia.

## 3. Datos

| Módulo | Clase | Acoplamiento concreto | Cambio mínimo | Riesgo BTC/ETH |
|---|---|---|---|---|
| `eim/data/timeframes.py` | **A** | `SYMBOLS = ("BTCUSDT","ETHUSDT")` y `FOCUS = ("BTCUSDT",)` (líneas 19-25); `TF_MS` solo 15 m/1 h/4 h (líneas 5-9); `1d` está relegado a `STORE_ONLY_TF_MS` (línea 14). Se importa en **61 módulos** | Registro de instrumentos de T89 como fuente de símbolos; `TF_MS` pasa a catálogo por instrumento con `1d`/`1w` de primera clase | **Alto**: 61 importadores. Hacerlo aditivo (el registro devuelve BTC/ETH por defecto) y contra los golden de T02/T05 |
| `eim/data/snapshot.py` | **A** | **`build_snapshot` no puede construir un snapshot de 1 d**: `_neighbor_candles` (línea 146) hace `ladder.index(timeframe)` sobre `TF_MS` y levanta `ValueError: '1d' is not in list`. Verificado al medir: el banco tuvo que armar el snapshot de 1 d a mano | Escalera de marcos por instrumento, en vez de la global; `1d` dentro de `TF_MS` | **Medio**: la escalera alimenta `candles_tf` (T35), que `technical` usa |
| `eim/data/store.py` | **A** | Genérico por `(kind, symbol, timeframe)`. Pero **`find_gaps` (línea 141) trata todo salto > `step` como hueco**: en acciones un fin de semana o un festivo es un hueco legítimo | `find_gaps` consulta el calendario del instrumento (T89) antes de declarar hueco | **Bajo**: en 24/7 el comportamiento no cambia |
| `eim/data/providers/base.py` | **A** | El `Protocol` `Provider` mezcla `klines` con `funding_rates` y `open_interest`: un proveedor de acciones no puede cumplirlo | Partir en `CandleProvider` (obligatorio) + protocolos opcionales por capacidad | **Bajo**: `BinanceFutures` seguiría cumpliendo los tres |
| `eim/data/providers/multi_asset.py` | **R** | Ya multiactivo y multiclase (`ASSETS`: cripto, oro, S&P 500, Nasdaq; Binance + Yahoo). 2 literales, solo en claves | Nada. Es el patrón a extender en T90 | **Nulo** |
| `eim/data/intermarket.py` | **R** | Ya resuelve point-in-time no cripto (vela diaria solo visible tras cerrar; `seen_at` auditable) y declara que un activo que falla **no se rellena** | Nada. Es el molde de la calidad de dato de T90 | **Nulo** |
| `eim/data/perp_universe.py` | **R** (para el primer universo) | 659 perpetuos USDT, 2,70 M liquidaciones de funding, 641 828 velas diarias (T181), con sesgo de supervivencia declarado | Nada: es el universo de arranque de T93 | **Nulo** |
| `eim/data/calendar.py`, `providers/{fred,calendar}.py` | **R** | Macro FRED/BLS/BEA, ya agnóstico de clase | Nada; sube de importancia fuera de cripto | **Nulo** |
| `eim/data/collectors/` (13 archivos, 20 literales) | **C** | WS de Binance: `binance_ws`, `liq_ws`, `hft_*` | Ninguno. Son recolectores de una bolsa concreta; otra clase trae los suyos | **Nulo** |
| `eim/data/arb_*` (5 archivos) | **C** | Arbitraje de Binance | Ninguno | **Nulo** |

## 4. Costos, margen y simulación — el bloque más específico de cripto

| Módulo | Clase | Acoplamiento concreto | Cambio mínimo | Riesgo BTC/ETH |
|---|---|---|---|---|
| `eim/backtest/params.py` | **C→A** | `CostParams` **es** un perpetuo lineal: `funding_interval_ms = 8 h` (línea 38), `mmr = 0.005` (línea 39), comisión maker/taker de `core/fees`. `BacktestParams.leverage = 5.0` margen aislado (línea 38) y `bars_per_year = 8766.0` (línea 40) | `CostParams` pasa a ser una **implementación** de un protocolo de costos por clase: perpetuo (funding), acción (dividendo, split, préstamo del corto), futuro (multiplicador, roll, vencimiento), FX (swap), bono (cupón, accrued). `bars_per_year` se deriva del calendario del instrumento, no se fija | **Alto**: T27, T49 y T145 se midieron con estos números. Ninguna cifra publicada puede moverse; T92 tiene que probar que el camino de perpetuos da **bit a bit** lo mismo |
| `eim/backtest/perp.py` | **C** | Mecánica de perpetuos: `liquidation_price` (margen aislado), `slippage_frac` con impacto por volumen de la vela, `exit_in_bar` | Hermano por clase. Para acciones, el hueco de apertura entre sesiones es la regla, no la excepción (`exit_in_bar` ya ejecuta a la apertura si hay hueco: eso sí se reutiliza) | **Nulo** si no se toca |
| `eim/risk/sizing.py` | **C→A** | `max_safe_leverage` asume margen aislado con `mmr` y apalancamiento **entero** ≤ 3× (`cfg.max_leverage`); `size_position` llama a `liquidation_price` de perpetuos | El tamaño por riesgo fijo (`notional = equity · risk / sl_frac`) es **reutilizable tal cual**; lo que cambia es el tope: liquidación en perpetuos, margen inicial Reg-T/SPAN en acciones y futuros | **Alto**: es la puerta de riesgo. Cualquier cambio se prueba contra las suites de T29/T114 |
| `eim/paper/{engine,desk}.py` | **C→A** | `FUNDING_MS = 8 h` fijado en los dos (`engine.py:32`, `desk.py:48`); `engine.py:178` cuenta cobros de funding por división entera | El bróker simulado toma los **eventos de costo de tenencia** del modelo de la clase (funding, dividendo, cupón, swap), no de una constante | **Medio**: T31 lleva semanas de papel con estos números; no se toca hasta cerrar sus semanas |
| `eim/calibration/` (5 literales) | **C** | Deslizamiento calibrado con el libro real de BTCUSDT (2026-10-20) | Calibración por instrumento, con su propia cobertura declarada | **Nulo** |

## 5. Ejecución, API, interfaz y Observatorio

| Módulo | Clase | Acoplamiento concreto | Cambio mínimo | Riesgo BTC/ETH |
|---|---|---|---|---|
| `eim/execution/broker.py` | **A** | El `Protocol` `Broker` es genérico; lo que ata es el vocabulario de Binance: `close_position`, prefijos `eim-`/`eia-`/`eih-`, estados `NEW/PARTIALLY_FILLED/...`, `GTX` post-only | Nada mientras la ejecución siga **solo simulada**. Con otro intermediario (T103), un adaptador nuevo que cumpla el mismo `Protocol` | **Nulo** |
| `eim/execution/binance_*` (11 archivos, 15 literales) | **C** | Futuros USDⓈ-M y spot de Binance | Ninguno | **Nulo** |
| `eim/api/` (11 archivos, **34 literales**, el segundo bloque más denso) | **A** | `main.py` (6), `paper.py` (6), `trades.py` (4), `more.py` (4), `risk.py` (3): símbolo por defecto y validación contra `SYMBOLS` | El símbolo se valida contra el registro de T89; el valor por defecto sigue siendo `FOCUS` | **Bajo** si es aditivo; la UI no pide otros símbolos |
| `eim/web/src/` (**33 archivos** con `USDT`) | **A** | Etiquetas, formato de precio y de cantidad, y el par fijo en las vistas de operación y de papel | Formato por instrumento (decimales, moneda de cotización) desde el registro; T94 añade el panel del escáner | **Bajo**: visual |
| `eim/observability/` | **R** | **Cero literales de cripto.** El catálogo, los interruptores (T174) y las trazas son agnósticos | Nada. El Observatorio sirve al escáner sin cambios | **Nulo** |
| `eim/validation/`, `eim/nursery/` | **A** | `validation/__main__.py:116` (`choices=SYMBOLS`) y, sobre todo, **`nursery/prereg.py:125`: `symbol: Literal["BTCUSDT"]`** — acoplamiento a nivel de tipo, no de literal | El pre-registro acepta el instrumento del registro. **T95 es más importante que el escáner**: multiplicar instrumentos multiplica hipótesis, y Holm ya lleva 841 en la familia (T164) | **Alto conceptual**: sin control de multiplicidad el escáner produce falsos hallazgos por diseño |
| `eim/analytics/` (14), `eim/bots/` (17), `eim/arbitrage/` (21), `eim/literature/` (8), `eim/forecast/` (6), `eim/operation/` (8) | **A** / **C** | Informes, escuadrón de bots, arbitraje, fichas y pronóstico, todos con el par por defecto | Se migran cuando su clase entre; ninguno bloquea el escáner | **Nulo** |

## 6. Inventario completo de literales de cripto

**117 archivos** de `eim/` contienen `BTCUSDT`, `ETHUSDT`, `"USDT"` o `USDⓈ` (la nota de octubre
estimaba «unos 80»), en **240 líneas** y con **269 apariciones**. Reproducible desde `v2/`:

```
grep -rc "BTCUSDT\|ETHUSDT\|\"USDT\"\|'USDT'\|USDⓈ" --include="*.py" eim | grep -v ":0$"
```

Añadiendo `eim/web/src/`, son **33 archivos más** (TypeScript). La columna «líneas» de la tabla
cuenta líneas con al menos una aparición (lo que devuelve `grep -c`), no apariciones.

| Paquete | líneas | archivos |
|---|---:|---|
| `eim/data/` | 52 | `arb_history.py` (4), `arb_history_sync.py` (1), `arb_market.py` (3), `arb_sim_data.py` (1), `backfill.py` (1), `bots/scripts/freqtrade_signal.py` (1), `bots/scripts/nfi_signal.py` (3), `calendar.py` (1), `collectors/binance_ws.py` (1), `collectors/health.py` (2), `collectors/hft_capture.py` (1), `collectors/hft_events.py` (1), `collectors/hft_ops.py` (2), `collectors/hft_supervise.py` (2), `collectors/hft_verify.py` (2), `collectors/hft_ws.py` (2), `collectors/liq_ws.py` (2), `collectors/supervise.py` (2), `import_history.py` (2), `intermarket.py` (2), `perp_universe.py` (2), `providers/binance.py` (1), `providers/binance_arb.py` (2), `providers/liquidations.py` (4), `providers/multi_asset.py` (2), `store.py` (1), `timeframes.py` (4) |
| `eim/api/` | 34 | `bots.py` (3), `calibration.py` (2), `forecast.py` (1), `main.py` (6), `more.py` (4), `paper.py` (6), `paper_variant.py` (1), `risk.py` (3), `setups.py` (2), `trades.py` (4), `validation.py` (2) |
| `eim/paper/` | 22 | `__main__.py` (5), `arb_tests.py` (4), `desk.py` (1), `exit_cli.py` (2), `ladder_params.py` (4), `params.py` (3), `protection_cli.py` (2), `snapshot.py` (1) |
| `eim/arbitrage/` | 21 | `basis.py` (5), `funding_carry.py` (2), `live/plan.py` (2), `related_perps.py` (3), `sim/depth.py` (1), `sim/frame.py` (2), `sim/replay.py` (4), `sim/triangular.py` (1), `triangular.py` (1) |
| `eim/bots/` | 17 | `backfill.py` (3), `ft_adapter.py` (2), `pb_adapter.py` (2), `scorecard_cli.py` (2), `scorer.py` (1), `sim_lane.py` (2), `squad_runtime.py` (1), `trendrider.py` (4) |
| `eim/execution/` | 15 | `arb_book.py` (1), `arb_executor.py` (1), `arb_legs.py` (1), `arb_runner.py` (1), `arb_sim.py` (2), `arb_smoke.py` (2), `binance_spot_testnet.py` (1), `binance_testnet.py` (1), `binance_ws_api.py` (1), `smoke.py` (2), `user_stream.py` (2) |
| `eim/analytics/` | 14 | `agents_marginal_report.py` (2), `audit/__main__.py` (2), `audit/render.py` (1), `audit/sources.py` (2), `event_report.py` (2), `technical_ic.py` (2), `transversal.py` (1), `why_no_data.py` (2) |
| `eim/agents/` | 9 | `arbitrage/agent.py` (1), `arbitrage/rows.py` (5), `intermarket/agent.py` (2), `smart_money/params.py` (1) |
| `eim/core/` | 8 | `arb_market.py` (5), `arbitrage.py` (1), `fees.py` (1), `market.py` (1) |
| `eim/literature/` | 8 | `__main__.py` (3), `report.py` (3), `tilt_eval.py` (2) |
| `eim/operation/` | 8 | `alerts.py` (1), `cycle.py` (1), `fleet_cause.py` (2), `usage.py` (1), `usage_summary.py` (3) |
| `eim/forecast/` | 6 | `backfill.py` (2), `eval.py` (2), `sr_eval.py` (2) |
| `eim/backtest/` | 5 | `cli.py` (2), `engine.py` (1), `params.py` (2) |
| `eim/calibration/` | 5 | `cli.py` (3), `gate_cli.py` (2) |
| `eim/library/` | 4 | `digital/consensus.py` (2), `digital/diagnose.py` (1), `digital/profiles.py` (1) |
| `eim/validation/` | 3 | `__main__.py` (2), `entry_control.py` (1) |
| `eim/repro/` | 3 | `cli.py` (3) |
| `eim/nursery/` | 2 | `prereg.py` (1), `report/feedback.py` (1) |
| `eim/synthesis/` | 2 | `params.py` (2) |
| `eim/risk/` | 1 | `hft_config.py` (1) |
| `eim/hft/` | 1 | `latency_report.py` (1) |
| `eim/observability/` | **0** | — |

**Los 117 archivos no son 117 trabajos.** Sólo 4 son acoplamientos de arquitectura
(`data/timeframes.py`, `data/snapshot.py`, `data/providers/base.py`, `backtest/params.py` con
`core/fees.py` y `risk/sizing.py` detrás); el resto son valores por defecto, CLI y etiquetas que
siguen al registro de T89 en cuanto exista, o módulos de cripto que no se tocan nunca.

## 7. Cobertura de datos por clase, hoy (lo que T88 completa)

Lo que **ya** está en este equipo, gratis y con la licencia clara, frente a lo que falta. Las
licencias de proveedores externos quedan **sin verificar en la fuente**: eso es T88 con el
formato de T04.

| Clase | Qué hay hoy en el almacén | Marco | Fuente | Qué falta para la lista de aceptación |
|---|---|---|---|---|
| Cripto perpetuos (USDⓈ-M Binance) | 659 instrumentos, 641 828 velas diarias, 2,70 M de funding (T181); BTC/ETH en 1 m–4 h con `taker_buy_v`, libro, microestructura y liquidaciones | 1 m – 1 d | Binance (API pública, sin clave) | Nada: es el primer universo de T93 |
| Materia prima (oro) | XAUUSDT, 344 velas diarias | 1 d | Binance perpetuo «TradFi» | Historia (< 1 año: `structure` ya degrada), y verificar en T88 qué otros TradFi lista |
| Renta variable — índices | S&P 500 (^GSPC) y Nasdaq (^IXIC), 400 velas diarias cada uno | 1 d / 1 wk / 1 mo | Yahoo Finance vía `yfinance` | **Licencia y condiciones de uso de Yahoo sin verificar** (T88, alerta de T04). Sin `taker_buy_v`, sin intradía, sin calendario de sesiones ni de festivos |
| Renta variable — acciones y ETF | Nada | — | — | Universo, calendario, **dividendos y splits** (point-in-time), préstamo del corto, y un proveedor con licencia |
| Macro | Calendario económico (FRED/BLS/BEA) ya en el ciclo | eventos | `providers/{fred,calendar}.py` | Nada para empezar; sube de importancia fuera de cripto |
| FX | Nada | — | — | Es OTC y fragmentado: hay que declarar `market_structure`. Volumen de ticks o inexistente → `technical` pierde la familia de flujo |
| Futuros tradicionales | Nada | — | — | Multiplicador, roll, vencimiento, y series continuas con su método de empalme declarado |
| Renta fija, derivados, opciones | Nada | — | — | Curva, cupón/accrued, cadena de opciones. T100 solo mide viabilidad |

## 8. Lo que esta auditoría cambia respecto de la nota de octubre

1. Los agentes son **20**, no 17; los de solo `candles` son **11**, no 10.
2. Los archivos con literales de cripto son **117** (269 apariciones), no «unos 80», más 33 de la
   interfaz; y sólo **4** son acoplamientos de arquitectura.
3. El ciclo completo cuesta **≈ 1,9 s** por instrumento y marco (20 agentes), no 4,5 s.
4. **El embudo no se puede definir por `requires`**: el agente más caro (`plan`, 73 % del ciclo)
   es de los portables. Se define por costo medido (≤ 20 ms ⇒ 1 % del ciclo).
5. **`run_agents` en hilos no acelera**: el escáner paraleliza por procesos sobre instrumentos.
6. **`build_snapshot` no admite 1 d**: es un bloqueo duro para toda clase que solo opera en diario,
   y no estaba anotado.
7. El riesgo dominante de los agentes no es que fallen, es el **acierto silencioso**: `vwap`
   publica `ok` con una de sus cuatro anclas muerta y **sin que la confianza se mueva** (el tope
   de 0,6 recorta antes que la penalización de 3/4), y `bars_per_year = 8766` infla el Sharpe de
   una serie diaria de acciones ×5,9.

## 9. Estándar para T89–T100 (lista de aceptación por clase)

Una clase de activo **no entra** hasta cumplir los 8 puntos. Es el molde que T97–T100 usan tal cual:

1. **Registro**: cada instrumento declara `market_structure`, calendario de sesiones y festivos,
   moneda de cotización, multiplicador y vencimiento (si los tiene), y los datos que existen.
2. **Datos**: proveedor con licencia y condiciones de uso **verificadas en la fuente** (T04);
   cada cifra con su `source` y su cobertura real; point-in-time auditable (`seen_at`).
3. **Calidad**: huecos juzgados contra el calendario del instrumento, no contra 24/7; revisiones y
   ajustes (dividendos, splits) declarados; sesgo de supervivencia explícito.
4. **Agentes elegibles**: lista de los que corren en la clase, con sus capacidades declaradas
   (ancla temporal, volumen, calentamiento, barras por año). Un agente sin ese dato no corre:
   `no_data` con motivo, nunca un número silencioso.
5. **Costos y margen**: modelo de la clase con sus parámetros medidos o citados, y el umbral de
   costo que una ventaja debe superar (la aritmética de T145).
6. **Simulación**: bróker simulado con los eventos de tenencia de la clase; sin dinero real.
7. **Validación**: pre-registro antes de mirar retornos, con la familia de hipótesis y el control
   de multiplicidad (Holm/FDR, Sharpe deflactado, PBO, control placebo) **ampliados al nuevo
   universo**, no reiniciados.
8. **No regresión**: los golden de T02/T05 y las suites existentes de BTC/ETH pasan sin cambiar un
   solo número.
