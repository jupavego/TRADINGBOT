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
