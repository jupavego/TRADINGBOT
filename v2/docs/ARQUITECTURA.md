# Arquitectura de EIM v2

Estado a 2026-10-14 (T32). Especificación vinculante: `F0`–`F6` (`F0/MSI-META-001.md` es la constitución).
Contratos de datos: `PLAN/CONTRATOS.md`. Avance por tarea: `PLAN/STATUS.md`.

## Flujo
```
Binance (REST/WS)  ──► data/ (proveedores + almacén parquet/DuckDB)
                          │  build_snapshot()
                          ▼
                    MarketSnapshot ──► agents/* (puros) ──► AgentReport ×14
                                                      │
                     forecast/ (3 escenarios + bandas)│   synthesis/ (tesis)
                                                      ▼
                                   agents/plan ──► plan de operación
                                                      │
                                   risk/ (veto determinista, tamaño, kill-switch)
                                                      │  RiskDecision sellada (HMAC, 60 s)
                                   execution/gateway (única puerta) ──► Broker
                                                      │      SimBroker (SIMULADO) | testnet
                                   execution/reconcile (libro vs exchange)
                                                      │
                                   operation/ (ciclo continuo, alertas, informes, copias)
                                                      │
                     api/ (FastAPI + WS, solo local) ◄┴► web/ (Vite + TS + Lightweight Charts)
```

## Paquetes (`v2/eim/`)
| Paquete | Responsabilidad | Regla clave |
|---|---|---|
| `core` | Contratos pydantic: `MarketSnapshot`, `AgentReport`, velas, overlays | Fuente única de tipos |
| `data` | Proveedores (`providers/`: Binance, liquidaciones, multi-activo, noticias, contexto Claude, calendario oficial Fed/BLS/BEA + FRED), almacén (`store.py`, parquet + DuckDB), `snapshot.py`, `sync.py`, `calendar.py` (calendario point-in-time) + `calendar_sync.py`, `arb_market.py` (fotografía de arbitraje: spot + USDⓈ-M/USDC-M, `providers/binance_arb.py`; `arb_store.py` + `arb_sync.py`: escáner periódico y últimas fotografías, T39; `arb_history_sync.py` + `arb_history.py`: histórico spot/perpetuos/trimestrales/funding y capturas de libros para la simulación, T43), copy trading (T40: `providers/leaders.py` = Hyperliquid `/info` + WS oficiales; `leader_store.py`, `leader_watch.py` vigilante, `leader_discover.py`, `leader_report.py`; T41: `leader_service.py` = vigilante + cotizaciones `bbo`/`allMids` (`leader_quotes.py`, precio del seguidor) + `portfolio` + evaluación periódica (`leader_eval.py`) → tableros JSON (`leader_board.py`), tablas en `leader_score_store.py`), `collectors/`, **`backup.py`** | **Todo el I/O vive aquí** |
| `agents/<id>` | 17 analizadores: structure, ema, vwap, price_action, elliott, seasonality, liquidations, levels, derivatives, microstructure, regime, context, technical, calendar (riesgo de evento, `bias=0`), arbitrage (`bias=0`), smart_money (líderes aprobados, T41; fuera de la síntesis hasta T44), plan. Registro en `agents/registry.py` | Funciones puras sobre el snapshot (sin red/disco/estado) |
| `indicators` | Biblioteca de indicadores técnicos (numpy puro) | Sin I/O |
| `arbitrage` | Oportunidades netas dentro de Binance (T38): carry de funding, base/cash-and-carry, triangular (informativo), USDT-M vs USDC-M; selector; CLI `python -m eim.arbitrage.cli`. `sim/` (T43): reproduce el motor sobre el histórico y simula cada oportunidad (margen, funding, rebalanceo, liquidación, pata incompleta) → `reports/arbitrage_edge.md`; CLI `python -m eim.arbitrage.sim sync|run` | Puro sobre `ArbMarket`; sin desglose de costos no hay oportunidad; sin ejecución (T45) |
| `leaders` | Copy trading (T40): parseo de Hyperliquid, libro esperado por líder (huecos por `startPosition`, reconciliación), descubrimiento; CLI `python -m eim.leaders` | Puro; solo lectura de datos públicos, sin claves ni órdenes (copiar es T42) |
| `copytrading` | Evaluación de líderes (T41): viajes de plano a plano, métricas netas de comisiones y funding, cartera (`portfolio`), Sharpe deflactado e IC con Bonferroni, reglas duras, copiabilidad (precio del seguidor), seguimiento adelante y cohortes, tablero | Puro; lo histórico solo preselecciona, aprueba lo observado adelante |
| `forecast` | Motor de trayectorias (`base_engine`, `kronos_engine` opcional), escenarios, techo/piso, calibración | Siempre probabilístico: 3 escenarios + bandas; velas «simuladas» |
| `synthesis` | Agrega reportes en una tesis con desacuerdo | |
| `backtest` | VRM (migrado del legado) + simulador de perpetuos con costos, `edge.py` (puerta T27) | |
| `calibration` | optuna walk-forward anidado; versiones en `calibration/versions/` | Versiones inmutables |
| `validation` | Puerta de validación por `estrategia@marco@versión` del bróker simulado (T49): criterios inmutables en `validation/versions/`, huella de versión (`paper/versioning.py`), linaje y ventanas de ajuste (`lineage.json`), puerta pura `gate.py`, servicio que recalcula al cierre de cada vela de 4 h, informe `python -m eim.validation` | Solo operaciones sombra cerradas, fuera de muestra y netas; Holm sobre todos los intentos; «ninguna validada» es válido |
| `risk` | Reglas de veto, tamaño, kill-switch global, sello HMAC; config en `risk/versions/` | Determinista, poder de veto; REAL prohibido |
| `execution` | `Broker` (contrato), `SimBroker`, `BinanceTestnetBroker` (solo hosts testnet), `service.py` (SL/TP antes de la entrada), `reconcile.py`, `gateway.py` | Solo se entra por `OrderGateway` con decisión verificada |
| `operation` | Ciclo continuo, supervisor + vigilante, alertas, capital, informe semanal, copia diaria | Corre dentro del proceso de la API |
| `analytics` | Bitácora de trading (exports de Binance) | |
| `api` | FastAPI: `main.py` (fábrica `create_app`), routers por dominio, **`security.py`** | Solo local; POST con `X-EIM-Confirm` |
| `web` | UI (Vite 6 + TypeScript + Lightweight Charts) | Muestra modo Análisis/Simulado/Testnet |
| `observability` | Observatorio (T72): evento normalizado, `trace_for`, emisor a prueba de fallos (JSONL por proceso, sin escribir en la base), catálogo de componentes con textos llanos y umbrales; T73: `store`/`indexer`/`derive` (indexador único JSONL → `obs.duckdb`: eventos, runs, refs, decisiones; idempotente y con reanudación por offset), `bridge` (latidos, alertas y riesgo existentes como eventos, solo lectura) y API `/v2/obs/*` (`api/obs.py`, sin POST) | Observar no es operar; los agentes siguen puros (los instrumenta el corredor, T74) |

Fuera del paquete: `v2/lab/` (experimentos archivados, p. ej. ESN de T28), `v2/reports/` (informes
de decisión versionados), `legacy/F7/` (código anterior, solo oráculo de regresión).

## Persistencia
- `data/candles/`, `data/funding/`: parquet particionado por símbolo (re-descargable).
- `data/reports.duckdb`: **una sola base** con `reports`, `risk_decisions`, `sim_trades`, `op_alerts`,
  `op_equity`, pronósticos. DuckDB admite **un solo proceso escritor**: la API la abre y todo lo demás
  (informes, copias) se pide a la API en marcha.
- `data/leaders.duckdb` (T40): líderes, ejecuciones, funding, apalancamiento, fotos de posiciones,
  reconciliaciones y huecos; T41: cartera (`portfolio`), precio del seguidor por ejecución y
  historial de veredictos. Base aparte porque el vigilante (`python -m eim.leaders run`) es su
  propio proceso escritor; la API y `build_snapshot` leen los tableros JSON de `data/leaders/`.
- `data/kill_switch.json`: estado persistido del kill-switch.
- `data/operation/`: latido, estado del servicio (libro simulado), registros JSONL por día.
- `backups/`: copias (ver `docs/OPERACION.md`).

## API (prefijo `/v2`)
Lectura: `health`, `snapshot`, `agents`, `reports`, `synthesis`, `overlays`, `forecast`,
`calibration`, `trades`/`journal`/`replay`, `risk` (+`decisions`, `kill-switch`), `execution`,
`operation` (+`report`), `backup`, `more/*`, `paper/*`, `validation` (+`history`). WebSocket: `stream`.

Escritura (todas exigen la cabecera `X-EIM-Confirm: <acción>`; test `test_every_mutating_post_requires_confirm_header`):
| Ruta | Valor de la cabecera |
|---|---|
| `POST /v2/risk/kill-switch/activate` · `/deactivate` | `kill-switch` |
| `POST /v2/risk/execute` | `execute` |
| `POST /v2/execution/reconcile` · `/flatten` | `execution` |
| `POST /v2/operation/report` | `report` |
| `POST /v2/backup` | `backup` |
| `POST /v2/calibration/backfill` | `backfill` |

Excepción: `POST /v2/more/bitacora` (procesa un archivo y responde, sin efecto lateral). Todo cuerpo de petición > 41 MB → 413 (`BodyLimitMiddleware`).

## Modos
`Análisis` (sin ejecución) · `Simulado` (SimBroker, papel) · `Testnet` (`EIM_EXECUTION=testnet`).
`REAL` está prohibido por validación de la configuración de riesgo hasta superar la puerta de edge
(T27: **NO PASA**) y semanas de papel (T31).
