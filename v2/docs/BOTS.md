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
