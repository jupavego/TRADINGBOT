# Contratos de datos (fuente única; T01 los implementa en `eim/core/` con pydantic v2)

Todos: inmutables (`frozen`), con `source: str` donde aplique, tiempos en UTC (ms epoch), precios `float`.

- **Candle**: `t, o, h, l, c, v`.
- **MarketSnapshot**: `symbol, timeframe, candles: list[Candle]` (más antiguo→reciente, última cerrada), `forming: Candle|None` (vela en curso), `funding: list[(t,rate)]|None`, `open_interest: list[(t,v)]|None`, `orderbook: Book|None`, `asof`, `sources: dict[str,str]`, `coverage: dict[str,(t_ini,t_fin)]`.
- **Overlay** (lo que el agente dibuja): `id, agent_id, kind ∈ {zone, level, channel, range, trade_plan, marker}`, `t_from, t_to|None` (None = hasta nuevo aviso), `geometry` (según kind: zone `{p_low,p_high}`; level `{p}`; channel `{upper:(t,p)x2, lower:(t,p)x2}`; trade_plan `{side, entry, sl, tp:[..], rr}`; marker `{t,p,action}`), `label, confidence 0..1, evidence: list[str]`, `valid_until|None`.
- **AgentReport**: `agent_id, version, asof, bias −1..+1, confidence 0..1, horizon_bars, evidence: list[str], metrics: dict, warnings: list[str], overlays: list[Overlay], status ∈ {ok, degraded, no_data}`.
- **Agent** (protocolo): `id: str`, `version: str`, `requires: set[str]` (campos del snapshot), `run(snapshot) -> AgentReport` — puro, sin I/O, determinista.
- **Scenario**: `id ∈ {bull, neutral, bear}`, `probability` (las 3 suman 1), `path: list[(t,p)]` (mediana), `band_low/band_high: list[(t,p)]`, `candles: list[Candle]` (secuencia OHLC representativa, simulada), `invalidation: {level, condition}`, `narrative: str`, `n_paths: int`, `engine: str`.
- **ForecastSet**: `symbol, timeframe, made_at, horizon_bars (20..30), scenarios: list[Scenario]` (exactamente 3), `engine, baseline_engine, warnings`.
- **Synthesis**: `bias, confidence, agreement 0..1, contributions: dict[agent_id, float], thesis: str`.
- **Mode**: `ANALISIS | SIMULADO | TESTNET | REAL` — toda vista de plan/operación lo muestra.
