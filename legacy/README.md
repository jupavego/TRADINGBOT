# legacy/ — código archivado

`legacy/F7/` es el sistema EIM anterior (FastAPI + `web/index.html`, motor FRM→BRM→IRM, VWAP,
Elliott, price action, estacionalidad, liquidaciones, bitácora). Se archivó aquí en **T32** (2026-10-14),
cuando todo su comportamiento ya estaba migrado al paquete `v2/eim/`.

## Estado
- **Congelado.** No se edita, no se importa desde `v2/eim/` y no se despliega.
- Único uso vigente: **oráculo de regresión**. `v2/tests/legacy/_runner.py` lo añade a `sys.path`
  y `tests/legacy/test_golden.py` comprueba que su salida sigue coincidiendo con
  `v2/tests/fixtures/golden/*.json`; los tests de agentes (`tests/agents/*`) y la bitácora
  (`tests/api/test_more.py`) se comparan contra esos goldens / contra el legado.
- Ruta alternativa: `EIM_LEGACY_DIR=<carpeta>` (p. ej. para la comprobación de sensibilidad del golden).

## Qué módulo se migró a dónde
| Legado (`legacy/F7/`) | v2 |
|---|---|
| `eim_frm.py`, `eim_brm_irm.py` | `eim/agents/structure/` (frm, brm, irm) |
| `eim_engine.py` (VRM / backtest) | `eim/backtest/vrm.py` |
| `eim_vwap.py` | `eim/agents/vwap/` |
| `eim_elliott.py` | `eim/agents/elliott/` |
| `eim_price_action.py` | `eim/agents/price_action/` |
| `eim_seasonality.py` | `eim/agents/seasonality/` |
| `eim_liquidations.py` | `eim/data/providers/liquidations.py` |
| `eim_market_data.py`, `eim_data.py` | `eim/data/providers/` (binance, multi_asset) |
| `eim_bitacora.py` | `eim/analytics/bitacora*.py` + `POST /v2/more/bitacora` |
| `eim_web.py`, `web/index.html` | `eim/api/` + `eim/web/` (pestañas en «Más análisis») |

## Cuándo borrarlo
Cuando los goldens de `v2/tests/fixtures/golden/` se consideren la única referencia (ya lo son para
los agentes): borrar `tests/legacy/test_golden.py`, la comparación directa de la bitácora en
`tests/api/test_more.py` y esta carpeta, en el mismo PR. La historia queda en git.

Arranque (solo consulta histórica): configuración `eim-web` de `.claude/launch.json`
(`uvicorn eim_web:app --app-dir legacy/F7`); necesita `legacy/F7/requirements.txt`.
