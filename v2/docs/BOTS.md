# Escuadrón de bots: operación (T57)

Bots de terceros aprobados en T56 (`eim/bots/registry/*.json`, `PLAN/notas/T56_auditoria.md`) que dan una **postura** (−1…+1) por estrategia. No operan: el agente `bots` solo informa (peso 0, `excluded`) hasta que T59/T60 los habiliten. Contrato y reglas: `PLAN/CONTRATOS.md` (Fase 12), seguridad: `docs/SEGURIDAD.md` (Bots de terceros).

## Qué corre solo
Modo A (`hummingbot-directional`: `bollinger_v1`, `macd_bb_v1`) siempre: código propio, sin instalación. Cada cierre de vela el servicio (`eim/bots/service.py`) calcula las posturas, las guarda en `bot_signals` (`reports.duckdb`, solo se añade) y las pone en `snapshot.bot_signals` para el agente. Ver: `GET /v2/bots/signals`, `GET /v2/bots/catalog`, `GET /v2/agents`.

## Modo B (Freqtrade): preparación manual, una vez
El entorno y el checkout se preparan **fuera** de la ejecución (el ejecutor no descarga nada):
```bash
# Python 3.12 aparte, sin tocar el de EIM
uv venv data/bots/ft-env --python 3.12
uv pip install --python data/bots/ft-env/bin/python freqtrade==2026.9 ta-lib technical
# estrategias, en el SHA fijado de la ficha (eim/bots/registry/freqtrade-strategies.json)
git init data/bots/freqtrade-strategies && cd data/bots/freqtrade-strategies
git remote add origin https://github.com/freqtrade/freqtrade-strategies.git
git fetch --depth 1 origin f3340ce11f5bdf62f598522e64d1f5638eaa13f5 && git checkout FETCH_HEAD
```
Después, en el entorno de la API: `EIM_BOT_FREQTRADE_PY=<ruta al python de ft-env>` y `EIM_BOT_FREQTRADE_ENGINE=2026.9` (versión fijada del motor; si el instalado difiere, la salida se rechaza). En Windows el intérprete está en `Scripts\python.exe`. Sin esas variables el modo B no se activa (y el catálogo marca `adapter_active: false`).

## Cambiar de versión
Subir el SHA de la ficha (otra tarea, con auditoría) o los parámetros crea una **versión nueva**: las señales viejas se conservan con la suya y la primera señal nueva lleva la nota `version_changed` (el agente avisa). Nunca se reescribe una fila.

## Paridad con el bot nativo
`tests/fixtures/bots/hummingbot_parity.json` guarda las posturas y los indicadores que da el bot **nativo** (líneas de `update_processed_data` con `pandas-ta` real) sobre las mismas 1000 velas; `tests/bots/test_hb_directional.py` exige que el adaptador coincida (1e-9). Regenerar: `tests/fixtures/bots/make_hummingbot_parity.py` (cabecera).

## Passivbot (clase L): carril de simulación (T58)
Passivbot gestiona órdenes e inventario (entradas con trailing, reentradas, grid): no da una postura direccional, así que **no vota ni produce `BotSignal`**. Su backtester (el mismo motor Rust de producción) corre sobre velas de 1 min locales en un proceso aislado y devuelve una `SimRun` (fills y capital **simulados**, solo largos, comisión de T25). Estrategias: `trailing_martingale` (por defecto) y `ema_anchor`; `trailing_grid_v7` está obsoleta y no se expone.

Preparación manual, una vez (Windows sin MSVC: Rust con toolchain GNU y MinGW-w64; todo fuera del repo):
```bash
# Rust (toolchain GNU) y MinGW-w64 (WinLibs, GCC 16.2, ZIP con SHA-256 verificado) en un disco NTFS
RUSTUP_HOME=<dir>/rustup CARGO_HOME=<dir>/cargo rustup-init -y --no-modify-path --profile minimal --default-host x86_64-pc-windows-gnu
# Python 3.12 aparte + motor Rust como rueda (sin tocar el checkout) + dependencias del bot
py -3.12 -m venv <dir>/pb-env
<dir>/pb-env/Scripts/python -m pip install maturin==1.5.1
# PATH con cargo y mingw64/bin; RUSTUP_TOOLCHAIN=stable-x86_64-pc-windows-gnu; CARGO_TARGET_DIR fuera del checkout; CARGO_BUILD_JOBS=1 si hay poca RAM
cd <passivbot>/passivbot-rust && <dir>/pb-env/Scripts/python -m maturin build --release -o <dir>/wheels -i <dir>/pb-env/Scripts/python
<dir>/pb-env/Scripts/python -m pip install <dir>/wheels/*.whl -r <passivbot>/requirements-live.txt -r <passivbot>/requirements-full.txt
# checkout en el SHA de la ficha (eim/bots/registry/passivbot.json), sin autocrlf
git init <passivbot> && cd <passivbot> && git config core.autocrlf false && git remote add origin https://github.com/enarjord/passivbot.git
git fetch --depth 1 origin 772abadc10a5bbf258a84aa8209a9084699fa1bd && git checkout FETCH_HEAD
```
Después: `EIM_BOT_PASSIVBOT_PY=<pb-env python>` y `EIM_BOT_PASSIVBOT_DIR=<passivbot>`; velas de 1 min en el almacén (`sync_candles(store, BinanceFutures(), "BTCUSDT", "1m", inicio)`); y `python -m eim.bots.sim_lane run --symbol BTCUSDT --since 2026-03-01`. El bot necesita ~17 días de historia propia antes de operar (EMA de 1690 h por defecto): pide siempre algo más que la ventana que quieres ver. Paridad: `tests/fixtures/bots/passivbot_parity.json` (fills del bot **nativo** sobre velas sintéticas con semilla; regenerar con `make_passivbot_parity.py`); `tests/bots/test_pb_adapter.py` la exige exacta con el bot real si hay entorno (si no, se salta).

Límites conocidos: solo largos y un símbolo; la comisión es la de EIM pero el bot aplica su propio deslizamiento a mercado (`market_order_slippage_pct` 0,05 %) y fills de límite por cruce de vela de 1 min; los resultados son del bot, no evidencia de edge (T59 los vuelve a costear y puntúa).

## Relleno histórico y ventanas de 6 meses
`python -m eim.bots.backfill --symbol BTCUSDT --timeframe 1h --since 2026-04-19` rellena `bot_signals` con una postura por cierre de vela (Hummingbot vela a vela por el servicio; Freqtrade con una sola corrida, ver `FreqtradeAdapter.history`). Necesita 1000 velas previas en el almacén. En Windows, el checkout de las estrategias de Freqtrade se prepara con `git config core.autocrlf false` (el ejecutor igualmente trata CRLF como limpio) y, si está en un disco FAT32/exFAT, funciona porque el ejecutor pasa `safe.directory` a su git aislado.

## Puntuación y puerta de edge (T59)

Cada `bot@estrategia@marco@vN` (la versión = SHA del bot + hash de parámetros, numerada por su primera aparición en `bot_signals`) pasa por **la misma puerta de T49** (`eim/validation/gate.py`), no por otra vara. Código en `eim/bots/`:

- `shadow.py`: postura → idea del bróker simulado (regla fija: abre al cambiar de lado, SL 1,5 ATR, TP 2 R, salida por tiempo al horizonte del bot o 24 velas). Costos de perpetuos de T25 (`ExecParams`); los `costs_assumed` del bot se ignoran. **Control aleatorio** de la misma familia (mismos instantes y geometría, lado sorteado con semilla fija): es un intento más de Holm y nunca vota.
- `scorecard.py`: veredicto por versión (V1–V6), familia de Holm con TODAS las versiones de TODOS los bots (también retiradas) + un control por cada una; condiciones por régimen (solo informe) e informe aparte de la clase L (`bot_sim_runs`).
- `concept.py`: cuatro dimensiones sin nota global (rendimiento V2/V4/V6, evidencia V1/V3/V5, seguridad de la ficha T56, operativa) y estado `vota | informa | rechazado | deshabilitado_seguridad`. Sin seguridad habilitada el bot no entra aunque rinda. `publicable` (VALIDADA) es una marca aparte: solo alimenta «Operaciones sugeridas» (T50).
- `marginal.py`: aporte al núcleo con el método de T44 (`agents_marginal`, el bot como un agente más): ΔSharpe, ΔE[R], ΔIC24 fuera de muestra, correlación con `ema/structure/technical` y efecto moderador. Peso inicial **medido** = `MODERATE_WEIGHT·(1 − ρ⁺ máx)` si aporta, 0 si no o si repite al núcleo (|ρ| ≥ 0,9).
- `health.py`: degradación (rendimiento vivo bajo el IC fuera de muestra, deriva entre versiones, fallos del ejecutor, latencia) → baja a `informa` con alerta (`Condition` del `AlertCenter` de T31).
- Persistencia `bot_scorecard` (solo añadir) y `GET /v2/bots/scorecard` (solo lectura). El bróker recalcula al cierre de cada vela de 4 h (`BotScorer.maybe_run`), reutilizando la última medición marginal mientras la versión no cambie.

Medición completa a mano (lenta; abre `reports.duckdb`, así que con la API parada o sobre una copia de `data/`):

```bash
python -m eim.bots.scorecard_cli --data-dir data --symbol BTCUSDT --marginal
```

Escribe `reports/bots_scorecard.{md,json}`. No hay ventanas de ajuste: los parámetros son de terceros fijados por SHA y EIM no los ajusta; cambiarlos es una versión nueva (ciclo T49/T51).

## Ampliación del escuadrón: Jesse, TrendRider y NFI (2026-10-20)
El usuario aprobó por escrito los tres opcionales que T56 dejó fuera (nota `PLAN/notas/T56_auditoria.md`, decisión del 2026-10-20). Aprobar no es validar: pasan por la misma puerta de T49/T59, sin cambiar la regla marginal ni los criterios.

| Bot | Modo | Marco | Qué se adapta | Qué NO cabe en una postura |
|---|---|---|---|---|
| `jesse-example-strategies` (MIT) | A | 1 h | 6 de 11: Donchian, RSI2, SMACrossover, MACD_EMA, TradingView_RSI, TurtleRules (`eim/bots/jesse_examples.py`) | stop-loss, take-profit, tamaño y pirámide. No portadas: IFR2, SimpleBollinger (Ichimoku), KDJstrategy (regla accidental `J > (K and D)`), MAGen (tipo de media por índice), DUAL_THRUST (vela ancla abierta) |
| `trendrider-strategy` (MIT) | A | 1 h, solo BTCUSDT | `TrendRiderStrategy` entera con sus `buy_params` (`eim/bots/trendrider.py`, `trendrider_ind.py`) | ROI, stoploss −6 %, trailing, `custom_exit` por tiempo. FNG y funding fijados en neutro (versión pública). Pide 5400 velas de 1 h (EMA200 diaria) |
| `nostalgia-for-infinity` (GPL-3.0) | B | 5 min | `NostalgiaForInfinityX7` en el entorno Python 3.12 de Freqtrade (`eim/bots/nfi_adapter.py`, `scripts/nfi_signal.py`) | **Promediado a la baja (rebuy/grind)**, ROI/stoploss/«derisk» y el límite de operaciones abiertas. La postura es el sentido de las banderas de entrada y salida |

- **Estado de la postura (Jesse):** posición tras cada vela con la mecánica de Jesse (entra solo plano, largo antes que corto, sale por `update_position`); ventana de 1000 velas y 210 de arranque, para que el estado no dependa de dónde empiece la historia.
- **Paridad:** Jesse contra las reglas calculadas vela a vela con TA-Lib (`tests/fixtures/bots/make_jesse_parity.py`; no se ejecutó el framework de Jesse: su motor de indicadores es Rust y necesita base de datos); TrendRider contra la estrategia real de Freqtrade con un `DataProvider` de mentira (`make_trendrider_parity.py`, 30 ventanas, postura y banderas idénticas). Ambas se regeneran a mano en `D:/eim-bots/ft-env`.
- **Marco 5 min:** `5m` es un marco **solo de almacén** (agregado desde 1 m con `eim.bots.backfill.aggregate`, DuckDB; nunca se pide a la API). Los adaptadores declaran `timeframes`; el servicio no los llama en otro marco. NFI **no está cableado en vivo** (no hay ciclo de 5 min): solo relleno histórico.
- **NFI por tramos:** 6 meses de 5 min no caben en una corrida; `NfiAdapter._run_all` corre tramos de 6000 velas con 800 de arranque y concatena banderas (causal ⇒ igual que una corrida; probado con un ejecutor falso en `tests/bots/test_nfi_adapter.py` y con el bot real sobre 3300 velas). Los informativos 15m/1h/4h/1d se arman con 56 días de historia propia (el diario de NFI usa periodo 50).
- **Entorno:** el mismo Python 3.12 de Freqtrade (`EIM_BOT_FREQTRADE_PY`/`_ENGINE`) y el checkout en el SHA de la ficha (`EIM_BOT_NFI_DIR` o `data/bots/nostalgia-for-infinity`). Relleno: `python -m eim.bots.backfill --timeframe 5m --since 2026-04-19`.
- **Puntuación:** `BotScorer` lee los marcos `1h` y `5m`; cada operación sombra se resuelve con velas del mismo marco (1 h → camino de 15 m; 5 m → camino de 5 m).
