window.EIM_STATUS = {
 "generated": "2026-10-23T20:19:26",
 "tasks": [
  {
   "id": "T01",
   "title": "Cimientos: paquete, contratos, git, gate",
   "deps": [],
   "state": "done",
   "notes": "v2/eim/core (contratos pydantic) + v2/tests/core; pyproject, .gitignore, skill eim-new-agent. Gate OK (12 tests).",
   "effort": "medio",
   "phase": 0,
   "goal": "Crear el esqueleto del paquete `eim/` con los contratos de datos y un gate de calidad, sin tocar `F7/`."
  },
  {
   "id": "T02",
   "title": "Red de seguridad: regresión del legado",
   "deps": [
    "T01"
   ],
   "state": "done",
   "notes": "v2/tests/legacy (_runner, generate_golden, test_golden) + golden JSON en v2/tests/fixtures/golden (no parquet: sin pyarrow y *.parquet está en .gitignore) + fixture ethusdt_1h_1000.csv. Cubiertos: FRM, BRM, IRM, VWAP (día/semana/quincena/mes + anclado), price action (+zonas S/R), Elliott, estacionalidad (con cierres mensuales sintéticos: el CSV cubre ~6 semanas). NO cubiertos: eim_engine (orquesta feed de red; su pipeline FRM→BRM→IRM sí), eim_liquidations/market_data/data/web/bitacora (requieren red/estado). Tolerancia rtol/atol 1e-9; umbral θ-001 alterado en copia (EIM_LEGACY_DIR) hace fallar el test. Gate OK (19 tests).",
   "effort": "medio",
   "phase": 0,
   "goal": "Congelar el comportamiento actual de F7 (ya corregido en sesiones previas) con \"golden outputs\", para migrar sin regresiones."
  },
  {
   "id": "T03",
   "title": "Capa de datos y almacén",
   "deps": [
    "T01"
   ],
   "state": "done",
   "notes": "v2/eim/data: `providers/` (Provider, BinanceFutures con reintentos/tasa), `store.py` (Parquet+DuckDB, huecos), `sync.py` (relleno incremental), `snapshot.py` (`build_snapshot`). Manual real: 6000 velas 1h BTCUSDT, 0 huecos. Evaluación OpenBB en PLAN/notas/T03_openbb.md. Gate OK (19 tests).",
   "effort": "medio",
   "phase": 0,
   "goal": "Proveedores de datos con interfaz común y un almacén local (DuckDB/Parquet) que alimente `MarketSnapshot` sin que los agentes toquen red ni disco."
  },
  {
   "id": "T04",
   "title": "Auditoría de repos (licencia/seguridad)",
   "deps": [],
   "state": "done",
   "notes": "PLAN/notas/T04_auditoria.md: 13 repos con veredicto. Rojas: market-regime y limit-order-book sin licencia real, Freqtrade GPL, OpenBB redirige a org nueva, circuit-framework descartado. Usar: Optuna, Kronos oficial.",
   "effort": "medio",
   "phase": 0,
   "goal": "Decidir qué se puede reciclar y cómo, sin riesgo legal ni de seguridad."
  },
  {
   "id": "T05",
   "title": "Runner de agentes + agente structure",
   "deps": [
    "T01",
    "T02",
    "T03"
   ],
   "state": "done",
   "notes": "v2/eim/agents: `base.py` (reportes degraded/no_data), `registry.py` (id+versión, `default_registry`), `runner.py` (paralelo, timeout, excepción→degraded). `structure/` (frm/brm/irm/params/agent, sin I/O): salida idéntica al golden de T02 (RTOL 1e-9); sesgo=(convicción−50)/50, confianza=score IRM/100, evidencia con reglas SR/M disparadas. Tests en tests/agents. Gate OK.",
   "effort": "alto",
   "phase": 1,
   "goal": "Registro y ejecutor de agentes, y migrar el motor EIM (FRM→BRM→IRM) como agente `structure` sin cambiar su comportamiento."
  },
  {
   "id": "T06",
   "title": "Agentes VWAP + price action",
   "deps": [
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/agents: `vwap/` (diario/semanal/quincenal/mensual+anclado, bandas ±1σ/±2σ, overlays `level` por período, avisa período parcial), `price_action/` (swings, patrones, BOS/CHOCH, zonas S/R como `zone`), y `ema/` (extra pedido: las 44 variables FRM en `metrics.variables`/`groups`, overlays EMA y cruces). Los 3 en `default_registry` y corren en el runner. Regresión contra golden RTOL 1e-9. Gate OK.",
   "effort": "bajo-medio",
   "phase": 1,
   "goal": "Migrar `eim_vwap.py` y `eim_price_action.py` a agentes puros con la interfaz común."
  },
  {
   "id": "T07",
   "title": "Agentes Elliott + estacionalidad + liquidaciones",
   "deps": [
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/agents: `elliott/` (zigzag+conteo 0-C, overlays `marker` por pivote y `level` de invalidación/solape, avisa heurística), `seasonality/` (cierres mensuales desde velas, matriz Año×Mes, sesgo del mes en curso; `strict_gaps` corrige el hueco que el legado interpolaba), `liquidations/` (consume `snapshot.liquidations`; obsoleto→`degraded` sin sesgo, expone `stale`/`most_recent_date`/`liquidation_symbol` vs `requested_symbol`). I/O en `eim/data/providers/liquidations.py`; contrato nuevo `Liquidations` en `core/market.py`. Equivalencia con golden T02. Gate OK.",
   "effort": "medio",
   "phase": 1,
   "goal": "Migrar `eim_elliott.py`, `eim_seasonality.py` y `eim_liquidations.py` a la interfaz de agentes/datos."
  },
  {
   "id": "T08",
   "title": "API v2 (REST + WebSocket + persistencia)",
   "deps": [
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/api: `main.py` (`create_app`; REST `/v2/health|snapshot|agents|reports|overlays`, `WS /v2/stream` con latido y estado de fuente), `live.py` (hub por símbolo/marco; al cierre de vela corre agentes y difunde reportes+overlays), `sources.py` (kline WS de Binance con reconexión exponencial; fuente inyectable), `reports_db.py` (tabla `reports` en DuckDB, consulta por rango), `config.py` (env `EIM_*`, CORS). Verificado en 127.0.0.1 con fuente simulada: ticks→reportes persistidos. Gate OK.",
   "effort": "medio",
   "phase": 2,
   "goal": "Servidor FastAPI que expone snapshots, reportes de agentes y un canal en vivo, y persiste cada reporte."
  },
  {
   "id": "T09",
   "title": "Frontend base + gráfico de velas en vivo",
   "deps": [
    "T08"
   ],
   "state": "done",
   "notes": "v2/eim/web (Vite 5 + TS + Lightweight Charts 5): `api.ts` (REST snapshot + WS con reconexión exponencial), `chart.ts`, `theme.ts` (claro por defecto/oscuro), `main.ts`, tipos a mano en `types.ts`. Layout UI_SPEC con barra superior (activo, marco, precio, En vivo/Sin conexión, modo), columna derecha y pestañas vacías. Verificado con API real: 500 velas BTCUSDT, última vela y precio cambian por tick; claro/oscuro/tablet por screenshot; banner \"Sin conexión\" y reconexión; ETH/15m. Gate OK.",
   "effort": "medio",
   "phase": 2,
   "goal": "Proyecto Vite + TypeScript con la \"Mesa de trading\" base: layout, tema claro/oscuro y gráfico de velas en tiempo real."
  },
  {
   "id": "T10",
   "title": "Panel de agentes + síntesis (UI)",
   "deps": [
    "T09"
   ],
   "state": "done",
   "notes": "v2/eim/web/src: `panels.ts` (tarjetas por agente: barra de sesgo −1..+1, confianza, estado, 3 líneas de evidencia, expandible a métricas/advertencias; bitácora de `/v2/reports`), `synth.ts` (síntesis SIMULADA en el navegador hasta T20, acuerdo, contribuciones, alerta de desacuerdo). Se actualiza con el mensaje WS `reports`. Verificado con API sobre fixture, claro y oscuro; falta ver el cambio al cerrar vela en vivo (sin red). Pendiente: visto bueno del usuario a la interfaz antes de Fase 3.",
   "effort": "medio",
   "phase": 2,
   "goal": "Columna derecha con una tarjeta por agente y un panel de síntesis, actualizados en vivo. **Punto de decisión humana al cerrar:** ¿la interfaz sirve?"
  },
  {
   "id": "T11",
   "title": "Portar pestañas legadas",
   "deps": [
    "T10"
   ],
   "state": "done",
   "notes": "Vista «Más análisis» (botón en la barra): `web/src/more*.ts` + API `eim/api/more.py` (`/v2/more/*`). Portado: `backtest/vrm.py` (idéntico al legado, test de regresión), `analytics/bitacora*.py` (ledger>historial>estimado, apalancamiento obligatorio), `providers/multi_asset.py` (Binance/Yahoo); liquidaciones (`stale` visible), estacionalidad (cobertura real) y VWAP por periodos reutilizan los agentes v2. Verificado con navegador y contra el legado. Bug heredado corregido: el proveedor de liquidaciones duplicaba importes (faltaba `drop_duplicates`). Diferencia consciente: estacionalidad excluye el mes en curso. F7/web intacto.",
   "effort": "medio",
   "phase": 2,
   "goal": "Llevar a la UI nueva lo que aún solo existe en `F7/web/index.html`: Backtest/VRM, Bitácora de trading, Multi-activo, Liquidaciones, Estacionalidad, VWAP por periodos."
  },
  {
   "id": "T12",
   "title": "Agente de niveles (S/R, canal, rango)",
   "deps": [
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/agents/levels: `pivots.py` (ATR, fractales, clustering 1D → zonas con toques/recencia/volumen, 2 arriba y 2 abajo), `channel.py` (Theil–Sen sobre pivotes, rango si deriva/ancho<0.35, canal roto tras 3 cierres fuera, extendido adelante), `agent.py` (sesgo por posición en canal + cercanía a zonas; overlays `zone`/`channel`/`range`), registrado en `default_registry`. Tests sintéticos + fixture en tests/agents/levels.",
   "effort": "alto",
   "phase": 3,
   "goal": "Agente puro que detecta zonas de soporte/resistencia y el canal o rango vigente, y los emite como overlays."
  },
  {
   "id": "T13",
   "title": "Agente de plan (entrada/SL/TP/R:R)",
   "deps": [
    "T12"
   ],
   "state": "done",
   "notes": "v2/eim/agents/plan: `plan.py` (propose: SL tras soporte/resistencia estructural + colchón ATR, TP1/TP2 en zonas opuestas, R:R≥1.5; advance: invalidado por cierre más allá del SL, cumplido, expirado; improve: solo acerca el SL), `agent.py` (sesgo combinado structure+levels hasta T20; reproduce las últimas 96 velas cada 6 para mantener el plan estable; overlay `trade_plan`, siempre `mode=ANALISIS`, sin tamaño de posición). Registrado en `default_registry`. Tests en tests/agents/plan. Test API relajado (range 6→40) por el coste extra del pipeline.",
   "effort": "alto",
   "phase": 3,
   "goal": "Agente que, a partir de los niveles y la síntesis disponible, propone un plan de operación analítico: dirección, entrada, SL, TP1/TP2 y relación riesgo/beneficio."
  },
  {
   "id": "T14",
   "title": "Capas sobre el gráfico + hover de evidencia",
   "deps": [
    "T09",
    "T12",
    "T13"
   ],
   "state": "done",
   "notes": "v2/eim/web/src: `layers.ts` (LayerEngine: overlays por id, reemplazo por agente, primitiva de Lightweight Charts que dibuja zonas como bandas, canal como 2 líneas + relleno, plan con etiquetas y R:R; extrapola tiempo futuro), `layers_ui.ts` (fila de capas con estado en localStorage; tarjeta de evidencia al hover), `api.fetchOverlays`; etiqueta \"Propuesta · Análisis\" en el plan. Verificado con datos reales BTCUSDT 1h: coordenadas de capas = priceToCoordinate de los precios del overlay; claro y oscuro. Plan probado con overlay sintético (el agente no emitió plan con esos datos). Niveles = solo agente `levels`.",
   "effort": "medio-alto",
   "phase": 3,
   "goal": "Dibujar en el gráfico en tiempo real lo que marca el agente: canal/rango, zonas de soporte y resistencia, y el plan (entrada, SL, TP1, TP2)."
  },
  {
   "id": "T15",
   "title": "Marcas de operaciones + bitácora + reproducción",
   "deps": [
    "T14"
   ],
   "state": "done",
   "notes": "v2/eim/execution/sim_ledger.py (libro SIMULADO reconstruido desde los planes persistidos: entrada al cierre del plan, SL vigente/TP1/TP2/invalidez, comisión+funding supuestos, R neto; DuckDB `sim_trades`). API `eim/api/trades.py`: /v2/trades, /v2/journal, /v2/replay, /v2/replay/asofs (+ `ReportStore.at/asofs`). Web: `trades_ui.ts` (marcadores + pestaña Bitácora) y deslizador en main.ts. Test: replay devuelve el plan emitido en ese instante (tests/api/test_trades.py). Sin llamadas a exchange.",
   "effort": "medio",
   "phase": 3,
   "goal": "Ver cómo \"opera\" el agente en el gráfico (en modo simulado) y poder reproducir sus decisiones pasadas."
  },
  {
   "id": "T16",
   "title": "Proyección: trayectorias OHLC (base + Kronos opc.)",
   "deps": [
    "T03",
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/forecast: `engine.py` (interfaz `Engine.sample -> (n,h,4)`, horizonte 20–30, `valid_candles`), `base_engine.py` (GARCH(1,1) + bootstrap conjunto de formas de vela en unidades de σ, deriva y semilla), `kronos_engine.py` (opcional, extra `[kronos]`, se omite sin deps; predictor inyectable), `eval.py` (pinball + cobertura 50/80 walk-forward). ETH 1h fixture: cob50 56.8 %, cob80 83.2 %. Kronos sin evaluar (no instalado; PINNED_REVISION pendiente). Tests en tests/forecast.",
   "effort": "alto",
   "phase": 4,
   "goal": "Generar muchas trayectorias futuras de velas OHLC (20–30 velas) desde el precio actual, con un motor base estadístico y, opcionalmente, Kronos."
  },
  {
   "id": "T17",
   "title": "Escenarios (3, probabilidad, invalidación) + API",
   "deps": [
    "T16",
    "T08"
   ],
   "state": "done",
   "notes": "v2/eim/forecast/scenarios.py (`build_forecast`: clasifica por retorno terminal con umbral `neutral_atr`·ATR, prob. = proporción, mediana/banda 10–90/medoide, invalidación por ATR o SL del plan, deriva externa para T20, grupo vacío → prob. 0 + aviso). v2/eim/api: `forecast.py` (`GET /v2/forecast?symbol&tf&h`, `Forecaster`), `forecast_db.py` (tabla `forecasts`), Hub emite `forecast` por WS al cierre. Tests en tests/forecast/test_scenarios.py. Gate OK.",
   "effort": "medio-alto",
   "phase": 4,
   "goal": "Convertir las trayectorias en exactamente tres escenarios (alcista, neutral, bajista) con probabilidad, banda, secuencia de velas representativa y condición de invalidación; exponerlos por API."
  },
  {
   "id": "T18",
   "title": "Escenarios sobre el gráfico (+ toggle velas)",
   "deps": [
    "T09",
    "T17"
   ],
   "state": "done",
   "notes": "v2/eim/web/src/scenarios.ts (primitiva: 3 trayectorias + banda + etiqueta de prob., desde el último cierre; modo velas simuladas, cuerpo lleno=sube/hueco=baja) y scenarios_ui.ts (pestaña Escenarios: tarjetas con prob./narrativa/invalidación/motor/n_paths, resaltado, selector 20/25/30, toggle velas, avisos de línea base y cobertura). Capa «Escenarios» en el motor de capas; se refresca por WS `forecast` al cerrar vela. Verificado con datos reales de Binance (BTCUSDT 1h): prob. suman 1, origen = último cierre, claro y oscuro. Pendiente T19: aviso de línea base usa `engine==baseline_engine`, no métrica evaluada.",
   "effort": "medio-alto",
   "phase": 4,
   "goal": "Dibujar los tres escenarios desde el punto actual y permitir ver cada uno como secuencia de velas."
  },
  {
   "id": "T19",
   "title": "Seguimiento y calibración de escenarios",
   "deps": [
    "T17",
    "T18"
   ],
   "state": "done",
   "notes": "v2/eim/forecast: `calibration.py` (evaluador por pronóstico: escenario cumplido, bandas 50/80/90 terminal y por vela, Brier, pinball y dirección vs caminata aleatoria con la misma σ; curva de calibración; veredicto textual), `backfill.py` (walk-forward sin mirar el futuro; CLI). `ForecastSet.quantiles` (aditivo). API `eim/api/calibration.py`: `GET /v2/calibration`, `POST /v2/calibration/backfill`. UI: pestaña «Calibración» (`calibration_ui.ts`). Backfill ETH 1h fixture: 826 evaluados (muestra efectiva ≈33): cob. 56/83/90 %, Brier skill +0.6 %, pinball skill +0.2 %, dirección 56 % → **no supera la caminata aleatoria**. **Pendiente: decisión humana sobre el veredicto antes de dar por buena la proyección.**",
   "effort": "medio",
   "phase": 4,
   "goal": "Medir si las probabilidades y bandas de los escenarios son fiables, y mostrarlo."
  },
  {
   "id": "T20",
   "title": "Síntesis v1",
   "deps": [
    "T06",
    "T07",
    "T12"
   ],
   "state": "done",
   "notes": "v2/eim/synthesis (`synthesize`: sesgo ponderado por peso·confianza, acuerdo, penalización por desacuerdo/degradados/ausentes, pesos y régimen en `params.py`, tesis por plantilla; `drift_of`). Integrado: plan usa la síntesis (`combine`), Forecaster inclina la proyección con su deriva, API `/v2/synthesis` + campo `synthesis` en WS y replay, UI sin «simulada». Tests en tests/synthesis.",
   "effort": "medio",
   "phase": 5,
   "goal": "Combinar los reportes de los agentes en una tesis con sesgo, confianza y nivel de acuerdo, y alimentar con ella al plan y a la proyección."
  },
  {
   "id": "T21",
   "title": "Agente de derivados (funding/OI/basis)",
   "deps": [
    "T03",
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/agents/derivatives (z de funding y de cambio de OI; 6 reglas precio/OI/funding con evidencia y advertencia de squeeze; ajustes contrarian por long/short y basis; `no_data` sin funding u OI). Proveedor Binance con `long_short_ratio` y `basis`, `sync_derivatives` y `MarketSnapshot` ampliados (opcionales). Registrado en `default_registry`. Tests en tests/agents/derivatives.",
   "effort": "medio",
   "phase": 5,
   "goal": "Agente que lee funding, open interest y (si hay) basis/long-short ratio y emite sesgo y advertencias de apalancamiento extremo."
  },
  {
   "id": "T22",
   "title": "Agente de régimen (BOCPD + transición)",
   "deps": [
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/agents/regime: `bocpd.py` (Adams–MacKay Normal–Gamma propio, hazard 1/800, sin instalar Kats), `labeling.py` (etiquetas tendencia↑/↓, rango, volátil por tramo; matriz de transición, permanencia, entropía), `agent.py` (BOCPD sobre retorno y log\\|ret\\|; sesgo 0; advertencia si el esquema es inestable; overlays `marker`). Registrado en `default_registry` y excluido del voto en síntesis. Tests con series sintéticas (retraso ≤ ~11 velas, 0 falsas alarmas en 9000 velas de ruido).",
   "effort": "medio-alto",
   "phase": 5,
   "goal": "Detectar cambios de régimen (tendencia/rango/alta volatilidad) y validar que el esquema de regímenes es estable y no ruido."
  },
  {
   "id": "T23",
   "title": "Microestructura: recolector + agente OFI",
   "deps": [
    "T03",
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/data/collectors (`binance_ws` aggTrade+depth@100ms → Parquet por hora; `book.py` reconstrucción con `pu`/poda de fantasmas, resync por snapshot REST, reconexión; `writer.py`), `data/micro.py` (OFI/delta/profundidad por vela), `MicroBar` + `MarketSnapshot.micro/orderbook` poblados en `build_snapshot`. Agente `microstructure` (OFI, CVD, profundidad, divergencia, Parkinson/GK; `no_data` sin recolección; degradado con huecos), registrado. Tests: tests/data/test_collector.py, tests/agents/microstructure. **Corrida real (32 min, ETHUSDT, 2026-10-13):** 11 416 trades con ids contiguos, 18 740 diffs de profundidad sin ruptura de `pu`, 1 874 muestras top-10, 0 huecos. Binance sirve `aggTrade` por `/market/stream` (conexión aparte). Reanudación tras corte probada solo en tests (no se cortó la red en vivo).",
   "effort": "alto",
   "phase": 5,
   "goal": "Recolectar trades y order book en vivo y calcular order flow imbalance (OFI), CVD y volatilidad realizada."
  },
  {
   "id": "T24",
   "title": "Agente de contexto (LLM)",
   "deps": [
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/agents/context (`ContextAgent` con `analyzer` inyectado; salida pydantic `{tema, sentimiento, catalizadores[{texto,fuente}], riesgo_evento, fuentes}`; bias siempre 0, métricas `confidence_multiplier`/`event_pause`; afirmaciones sin fuente válida descartadas; titulares con patrones de inyección excluidos antes del LLM; sin clave/red/titulares → `no_data`). I/O en data/providers: `news.py` (RSS → `NewsItem`, `MarketSnapshot.headlines`) y `claude_context.py` (API con `cache_control`, tool_choice forzado, temperatura 0.1, `CostGuard`). Tests con LLM simulado en tests/agents/context. Pendiente manual: ejecución con clave real.",
   "effort": "medio",
   "phase": 5,
   "goal": "Un agente que lee noticias/sentimiento y devuelve contexto estructurado (el calendario económico lo cubre el agente determinista `calendar`, T36; este agente puede leer su salida). **Solo informa; nunca ejecuta ni fija tamaño.**"
  },
  {
   "id": "T25",
   "title": "Backtest con costos de perpetuos",
   "deps": [
    "T13",
    "T20"
   ],
   "state": "done",
   "notes": "v2/eim/backtest: motor propio (decisión y prueba mínima con Nautilus en PLAN/notas/T25_motor.md). `engine.py` (ejecución en apertura siguiente, SL antes que TP, funding 8 h, margen aislado y liquidación), `perp.py`, `params.py` (comisiones maker/taker, deslizamiento por volatilidad/tamaño), `strategy.py` (contrato `Strategy`/`Signal` + `PlanStrategy` agentes→síntesis→plan), `walkforward.py` (ventanas disjuntas), `metrics.py` (Sharpe/Sortino/DD/R/acierto/PF/exposición con IC bootstrap, desglose de costos), `report.py`+`cli.py` (JSON/MD en reports/backtest/). Tests de integridad en tests/backtest (sin look-ahead, costos 0 = bruto, liquidación, funding). Backtest real es lento (~1 s/evaluación del agente de plan): usar `eval_step`>1.",
   "effort": "alto",
   "phase": 6,
   "goal": "Evaluar la estrategia completa (agentes → síntesis → plan) con costos y mecánica reales de futuros perpetuos, sin sesgo de anticipación."
  },
  {
   "id": "T26",
   "title": "Calibración (optuna, walk-forward)",
   "deps": [
    "T25"
   ],
   "state": "done",
   "notes": "v2/eim/calibration: `space.py` (9 params acotados: umbrales del plan ↔ VRM C-1, peso structure/levels y desacuerdo ↔ C-2; C-3 al BACKLOG), `inputs.py` (caché de structure/levels; fidelidad 7/7 entradas idénticas), `evaluate.py` (mediana Sharpe por ventana − 2·DD − 0.05·nº params), `search.py` (optuna TPE + selección por peor caso ±10 %), `nested.py` (1 año train → 6 meses test, 5 pliegues, control ETHUSDT), `cli.py`. PlanAgent acepta `synth`/`raw`. **Resultado (reports/calibration/params_v1_btc_1h.md): fuera de muestra no mejora de forma robusta (gana 1/5 pliegues, Sharpe OOS −2.45 vigente vs −2.40) → se mantienen los valores previos** (versión `eim/calibration/versions/params_v1_btc_1h.json`, estado rechazado). La estrategia pierde en todos los pliegues y en ETH: insumo clave para T27.",
   "effort": "medio-alto",
   "phase": 6,
   "goal": "Calibrar umbrales θ, pesos de síntesis y parámetros del plan sin sobreajustar. Salda la deuda pendiente del VRM (Fase VI)."
  },
  {
   "id": "T27",
   "title": "Puerta de edge (informe de decisión)",
   "deps": [
    "T26",
    "T19"
   ],
   "state": "done",
   "notes": "v2/reports/edge_gate.md (criterios C1–C7 fijados antes de calcular, resultados, Holm, veredicto) + datos en v2/reports/edge/edge_results.json; código `eim/backtest/edge.py` (réplica con lado aleatorio, bootstrap/permutación, Holm) y `eim/calibration/gate_cli.py`, tests en tests/backtest/test_edge.py. **Veredicto: NO PASA**: 7 ventanas OOS por activo, BTC Sharpe −2.39 / ETH −2.80 (comprar y mantener +0.88 / +0.39), R neto −0.49/−0.51 con IC95 % negativo, DD ≈70 %, 0/14 ventanas positivas; no supera la entrada aleatoria ni antes de costos (costos ≈0.3–0.36 R/operación); escenarios sin skill (Brier −0.4 %, pinball −1.2 %) aunque con bandas calibradas. Hipótesis en BACKLOG. **Decisión del usuario (2026-10-13): acepta el NO PASA** → no se avanza a T29; siguiente paso: hipótesis del BACKLOG.",
   "effort": "medio",
   "phase": 6,
   "goal": "Responder con evidencia: ¿el sistema tiene ventaja estadística fuera de muestra, neta de costos? De la respuesta depende seguir a T29 o volver atrás."
  },
  {
   "id": "T28",
   "title": "(Opcional) Laboratorio ESN con conectoma",
   "deps": [
    "T27"
   ],
   "state": "done",
   "notes": "v2/lab/esn_connectome (fuera de `eim/`): `connectome.py` (subgrafo voraz de 1.000 neuronas de FlyWire v783, CC BY 4.0, signo por neurotransmisor; solo se versiona `data/subgraph_1000.npz`), `esn.py` (ESN numpy, variantes aleatorio/conectoma/topología), `models.py` (lectura de cuantiles μ̂+ŝ·q), `run_lab.py` (walk-forward 1 año→6 meses, 12 celdas BTC/ETH, h=25, costos 12 pb), `summarize.py`, `test_lab.py`. **Veredicto (v2/reports/esn_connectome.md): NO GANA → archivado**: conectoma ≈ aleatorio en N=100/500/1000 (C1 falla); todos los ESN ≈ +1 % pinball vs cono, igual que una regresión lineal con rezagos; dirección 50–51 %, neto −13 a −19 pb/op. Kronos sin evaluar (sin torch).",
   "effort": "medio",
   "phase": 6,
   "goal": "Probar si un Echo State Network con reservorio basado en el conectoma de Drosophila mejora la proyección frente a un ESN aleatorio y a los motores de T16. Evidencia previa: resistencia al sobreajuste en series caóticas (no financieras); la única prueba financiera encontrada fue negativa."
  },
  {
   "id": "T29",
   "title": "Motor de riesgo (veto determinista)",
   "deps": [
    "T27"
   ],
   "state": "done",
   "notes": "**Construido con T27 en NO PASA por decisión del usuario (2026-10-14)**: capa solo defensiva, sin órdenes; T30/T31 siguen sin dinero real. v2/eim/risk: `config.py` + `versions/risk_v1.json` (pydantic frozen, versión = nombre de archivo, SHA-256 en cada decisión; REAL prohibido), `rules.py` (plan/geometría y R:R, modo, datos obsoletos/agentes críticos degradados, ventana de evento `calendar.blackout` + pausa de `context`, pérdida diaria/semanal, máx. abiertas total/por símbolo, enfriamiento tras pérdidas seguidas), `sizing.py` (riesgo fijo 0.5 % a SL, apalancamiento entero ≤3× con dist. liquidación ≥2× dist. SL, tope de nocional/margen), `killswitch.py` (global, manual o por drawdown/desconexión/reconciliación; solo se apaga a mano), `engine.py` (`RiskDecision` siempre registrada, sellada con HMAC de proceso; `verify` caduca a 60 s), `inputs.py` (plan desde reporte, cuenta desde el libro SIMULADO), `journal.py` (DuckDB `risk_decisions`). `eim/execution/gateway.py`: única puerta a un `Broker` (T30), exige `verify`. API `/v2/risk` (+`/decisions`, `/kill-switch[/activate|/deactivate]`); UI pestaña «Plan» (`web/src/risk_ui.ts`) con tamaño aprobado o motivos del veto y kill-switch. Tests en tests/risk (184: cada regla, combinaciones de hasta 3 vetos, sello/alteración/caducidad/kill-switch en la puerta, escaneo estático de endpoints de órdenes); cobertura risk+gateway 99 %, api/risk 97 %. Verificado en navegador (sin plan vigente en vivo; aprobado/vetado con respuesta de ejemplo). Revisión de código (high): 10 hallazgos, 9 corregidos — tamaño al precio actual y regla «vigencia» (edad del plan ≤2 velas, precio sin cruzar SL/TP1, R:R desde el precio actual), kill-switch persistido en `data/kill_switch.json` y POST con cabecera `X-EIM-Confirm` (anti-CSRF), registro con una fila por resultado distinto, sin eventos repetidos, UI con errores visibles y aviso en reproducción.",
   "effort": "alto",
   "phase": 7,
   "goal": "Capa determinista que decide tamaño y puede vetar cualquier plan. Ningún LLM ni agente puede saltársela."
  },
  {
   "id": "T30",
   "title": "Ejecución en testnet + reconciliación",
   "deps": [
    "T29"
   ],
   "state": "done",
   "notes": "v2/eim/execution: `broker.py` (contrato `Broker`, ids de cliente deterministas), `sim_broker.py` (`SimBroker`, SIMULADO), `binance_testnet.py` (`BinanceTestnetBroker`: solo hosts de testnet, claves por `EIM_TESTNET_API_KEY/SECRET`, firma HMAC en cuerpo, SL/TP por `/fapi/v1/algoOrder`), `service.py` (SL y TP `closePosition` ANTES de la entrada → todo fill nace protegido; reintentos que consultan por id antes de reenviar; rechazos y fills parciales), `reconcile.py` (libro vs exchange, SL perdido → se repone o cierra, huérfanas, desvío/desconexión → kill-switch y cierre ordenado), `smoke.py` (prueba E2E en testnet). `RiskDecision` sella entrada/SL/TP; `OrderGateway` es la única puerta. API: `EIM_EXECUTION=testnet` → modo TESTNET, `POST /v2/risk/execute`, `/v2/execution` (+`/reconcile`, `/flatten`), reconciliación cada `EIM_RECON_S`; UI: cabecera y pestaña Plan en Testnet con botón «Ejecutar en testnet». Tests en tests/execution (39, exchange simulado con caídas de red, respuestas perdidas, 503, rechazos, fills parciales). Revisión de código: 10 hallazgos, 9 corregidos. Fusionado en main (PR #39, `a77746e`, 2026-10-14). **Pendiente manual: prueba E2E en testnet real (`python -m eim.execution.smoke`) con claves de testnet; los criterios «abrir/cerrar con SL/TP en testnet» y «cortar la red no deja posición sin SL» solo están probados contra el exchange simulado.**",
   "effort": "alto",
   "phase": 7,
   "goal": "Adaptador de ejecución para Binance Futures **testnet**, con la misma interfaz que el simulador, y reconciliación de posición."
  },
  {
   "id": "T31",
   "title": "Paper trading + kill-switch + monitoreo",
   "deps": [
    "T30"
   ],
   "state": "progress",
   "notes": "**Construido; falta la corrida de ≥ 4 semanas** (criterio de aceptación). Por decisión del usuario (2026-10-14) corre en papel con `SimBroker` (T30 sin la prueba E2E en testnet); alertas: notificación local de Windows + UI. v2/eim/operation: `cycle.py` (datos REST → agentes → pronóstico → `RiskDesk.execute` por la puerta única → precio del simulador por el camino de cada vela de 15m con SL/TP en su disparo → capital → kill-switch por drawdown → reconciliación → alertas), `supervisor.py` (bucle con latido `data/operation/heartbeat.json`, reintento exponencial, alerta tras 3 fallos, informe semanal automático cada lunes UTC), `watchdog.py` + `__main__.py` (`python -m eim.operation run`: relanza la API si muere o si el latido se detiene), `state.py` (libro y SimBroker persistidos: sobreviven al reinicio), `equity.py` (historial `op_equity` → inicio de día/semana y pico reales para el motor de riesgo), `alerts.py`/`notify.py` (desconexión, divergencia, kill-switch, drawdown ≥5 %, agentes degradados; por transición, en DuckDB `op_alerts`, registro JSONL por día), `weekly.py`/`report.py` (resultados vs ventanas OOS de T27, desviaciones, calibración de escenarios, incidentes, vetos → `reports/operation/semana_AAAA-Www.md/json`). `RiskDesk` extraído de `api/risk.py` (API y servicio comparten ruta). API `GET /v2/operation`, `POST /v2/operation/report`; UI pestaña «Operación» (`web/src/operation_ui.ts`). Tests en tests/operation (30). **Verificado en vivo (2026-10-14):** ciclo con datos reales de Binance (BTC/ETH 1h), kill-switch → alerta crítica + notificación, informe parcial, `taskkill` del proceso → relanzado en 10 s con cursores restaurados; estado de prueba borrado. Arranque: `python -m eim.operation run` desde `v2/`.",
   "effort": "medio",
   "phase": 7,
   "goal": "Operar de forma continua en testnet/paper durante semanas con monitoreo y alertas, y producir la evidencia para decidir si se pasa a capital real."
  },
  {
   "id": "T32",
   "title": "Endurecimiento y documentación",
   "deps": [
    "T31"
   ],
   "state": "done",
   "notes": "**Hecha en paralelo a la corrida de 4 semanas de T31 por decisión del usuario (2026-10-14).** Auditoría en v2/docs/SEGURIDAD.md (+ skill security-review: sin hallazgos): API solo local (`eim/api/security.py`: Host permitido contra DNS rebinding, cliente de bucle local o `EIM_API_TOKEN`, Origin en WebSocket), `X-EIM-Confirm` en `calibration/backfill` + test que recorre todo POST, límite de cuerpo de 41 MB (413), Vite 5→6.4.4 (`npm audit` 0), `pip-audit` 0, hash de `risk_v1` independiente de CRLF + `.gitattributes`. Docs en v2/docs/ (ARQUITECTURA, OPERACION, RUNBOOK, NUEVO_AGENTE). Copias: `eim/data/backup.py` (en caliente bajo el cerrojo DuckDB, verificación por SHA-256, restauración, poda; CLI `python -m eim.data.backup`, `POST /v2/backup`, copia diaria automática del servicio con alerta), `tests/test_param_versions.py` (versiones inmutables), `requirements-lock.txt` + política de dependencias. `F7/` → `legacy/F7/` con README (solo oráculo de regresión). BACKLOG priorizado (P0–P3). Gate: 689 tests. Revisión de código (high): 10 hallazgos, 10 corregidos (CLI con variables de entorno, copia a demanda serializada con el ciclo, reintento horario, restauración sin pisar copias previas, rutas con comillas, token en WebSocket, límite de cuerpo por petición, cliente común `eim/data/local_api.py`). **Pendiente: reiniciar la corrida de papel para cargar los cambios.**",
   "effort": "medio",
   "phase": 7,
   "goal": "Dejar el sistema mantenible y seguro."
  },
  {
   "id": "T33",
   "title": "Auditoría de repos y fuentes (4 agentes nuevos)",
   "deps": [],
   "state": "done",
   "notes": "`PLAN/notas/T33_auditoria.md`: 27 candidatos con veredicto y evidencia (clones aislados en `C:\t33clones`, sin ejecutar). Copy: Hyperliquid `/info`+WS oficial = base (sin leaderboard oficial → universo vía WS `trades.users` + `vaultDetails`); Binance solo manual (endpoints `/bapi` privados, `robots.txt` los prohíbe); Hype-W = señuelo APK. Arb: conector oficial Binance + ccxt/SDK HL, solo funding/basis. Ind: TA-Lib + pandas-ta-classic (pandas-ta original: repo 404). Cal: FOMC+BLS ICS+BEA JSON+FRED (sin consenso gratis). **Alcance aprobado por el usuario (2026-10-13)** → T40 desbloqueada.",
   "effort": "medio",
   "phase": 8,
   "goal": "Verificar con evidencia (no solo README) qué repos y fuentes de datos se pueden usar para copy trading, arbitraje, calendario económico e indicadores técnicos, y fijar el alcance de copy trading."
  },
  {
   "id": "T34",
   "title": "Biblioteca de indicadores técnicos (catálogo Binance)",
   "deps": [
    "T05"
   ],
   "state": "done",
   "notes": "v2/eim/indicators: `CATALOG.md` (28 indicadores ☑ + 4 series directas del proveedor descartadas con motivo; fuentes y fecha 2026-10-13; lista B y parámetros pendientes de confirmar en la interfaz), un archivo por familia (`trend`, `momentum`, `volatility`, `volume`, `flow`) + `_core.py` (convenciones NaN/ventanas) + `registry.py` (`SPECS`, `compute`, `candle_arrays`). `Candle` ampliado con `taker_buy_v`/`trades` (proveedor, WS, almacén compatible con Parquet previo). FRM (agente `ema`) usa ahora `indicators.ema`/`true_range` (golden intacto). Tests en tests/indicators: referencia fijada (rtol 1e-9), truncado sin look-ahead, casos borde. **Límite:** la referencia es una implementación ingenua propia (se hizo antes del veredicto de T33) → contraste con TA-Lib/pandas-ta-classic pendiente en BACKLOG.",
   "effort": "alto",
   "phase": 8,
   "goal": "Implementar, validar y catalogar todos los indicadores técnicos del gráfico de Binance, más los derivables de sus datos propios (taker buy/sell, mark/index/premium)."
  },
  {
   "id": "T35",
   "title": "Agente technical (confluencia multi-marco)",
   "deps": [
    "T34"
   ],
   "state": "done",
   "notes": "v2/eim/agents/technical: `rules.py` (24 reglas de voto documentadas: cruces, umbrales, divergencias RSI/CVD, %b; ATR/TradeSize/AVL/Basis no votan, con motivo), `combine.py` (duplicados exactos colapsados + grupos por correlación ≥0.85 dentro de cada familia → test: duplicar un indicador no cambia el sesgo; régimen ADX/ancho BOLL → pesos por familia en `params.py`), `frame.py` (marcos vecinos: `MarketSnapshot.candles_tf` nuevo, rellenado por `build_snapshot`; superior agregado si falta), `agent.py`. En `default_registry`; **fuera de la síntesis** (`excluded`) hasta T44. UI: tarjeta «Técnico» con familias desplegables (`web/src/technical_ui.ts`); se restauró el estilo base `.bar` perdido en T10. **IC (reports/technical_ic.md, `python -m eim.analytics.technical_ic`)**: solo h=1 vela de 1h es significativo tras Holm y con signo de reversión (tendencia IC≈−0.03, osciladores ≈+0.04); a 6/24 velas nada supera el azar; el sesgo agregado no es significativo en ninguna prueba → agente descriptivo, sin edge. Flujo sin medir (histórico sin `taker_buy_v`).",
   "effort": "alto",
   "phase": 8,
   "goal": "Agente que lee **todos** los indicadores de T34 y los convierte en un sesgo único y honesto, sin contar 40 veces la misma señal."
  },
  {
   "id": "T36",
   "title": "Calendario económico: proveedor + agente",
   "deps": [
    "T05"
   ],
   "state": "done",
   "notes": "Fuentes oficiales de T33 (sin consenso → `forecast=None`, nunca inventado): `eim/data/providers/calendar.py` (Fed FOMC HTML → 14:00 ET, BLS ICS en ET, BEA JSON en UTC; ET→UTC con `zoneinfo`, probado en EST/EDT), `providers/fred.py` (opcional `EIM_FRED_API_KEY`: real/anterior/revisado por *vintage* ALFRED). `eim/data/calendar.py`: historial **point-in-time** solo-añadir (`data/calendar/events.parquet` + `fetches.parquet`; revisiones y cancelaciones = filas nuevas), vencimientos trimestrales Binance por regla (último viernes 08:00 UTC, contrastado con `exchangeInfo`); `calendar_sync.py` (al arrancar la API y cada 6 h, `EIM_CALENDAR`). `EconEvent` en `core/events.py`; `snapshot.events` −24 h…+7 d con `sources`/`coverage` por fuente. Agente `eim/agents/calendar/` (`bias=0` siempre): próximo alto impacto, minutos, ventana pre/post, `blackout` (+1 vela de margen; lo veta T29), `risk_windows`, sorpresa (n/d sin consenso), confianza = completitud×frescura, `degraded` si fuente obsoleta/ausente/horizonte corto, marcador por evento. UI: tarjeta «Calendario» con próximos eventos (`web/src/calendar_ui.ts`). Tests: tests/agents/calendar (21) + tests/data/test_calendar_provider.py (14, recortes reales en tests/fixtures/calendar). Verificado en vivo (2026-10-14): IPC 12:30 UTC e IPP 15-oct en la tarjeta. Pendientes en BACKLOG (T36).",
   "effort": "medio",
   "phase": 8,
   "goal": "Que el sistema conozca los eventos macro y cripto de alto impacto (FOMC, CPI, NFP, PCE, PIB, vencimientos de futuros trimestrales, decisiones regulatorias) y cuantifique el riesgo de evento. **Es un agente de riesgo, no direccional.**"
  },
  {
   "id": "T37",
   "title": "Calendario: impacto histórico y ventanas",
   "deps": [
    "T36",
    "T03"
   ],
   "state": "done",
   "notes": "`v2/eim/analytics/event_study.py` (velas 15 m, ventana −60 min…+4 h; normal = misma hora UTC en 20 días hábiles sin eventos; log-cociente de rango, distribución p10…p90, bootstrap + Holm; ventana = velas contiguas significativas ≥×1.25; `by_surprise` listo sin consenso) + `event_report.py` (`python -m eim.analytics.event_report [--fetch]`, eventos usados en `reports/calendar/events.csv`). **`reports/calendar_impact.md`**: FOMC −30/+225 (n=30), IPC −15/+30, NFP +45, IPP +30, PIB/PCE/JOLTS +15 (n≈20, desde 2025), vencimiento −60/0 (n=13, solo BTC); comercio exterior no mueve el mercado → sin ventana; ECI n=7 insuficiente → ventana por impacto; la dirección no es predecible. Ventanas con cita (n, p Holm) en `agents/calendar/params.py` (`T37_WINDOWS`, prioridad sobre impacto; IPP abre `blackout` aunque sea «medio»); `risk_windows` lleva `blackout`/`basis`; agente 1.1.0. T29 (regla `evento`) consulta `blackout`. Velas 15 m BTC/ETH rellenadas desde 2023. Tests: test_event_study (9, sintéticos con efecto conocido) + test_t37_windows (7).",
   "effort": "medio",
   "phase": 8,
   "goal": "Medir con datos cuánto mueven BTC/ETH cada tipo de evento y fijar las ventanas de pausa por evidencia, no por intuición."
  },
  {
   "id": "T38",
   "title": "Arbitraje: motor de oportunidades netas (Binance)",
   "deps": [
    "T03",
    "T05"
   ],
   "state": "done",
   "notes": "Contratos `eim/core/arbitrage.py` (`CostModel`: VIP/BNB configurables, VIP 0 verificado 2026-10-15, `fill` = VWAP recorriendo el libro; `Leg`, `Costs`, `Risk`, `Opportunity` exige `net = bruto − costos` y desglose; `ArbScan` ok/degraded/no_data) y `core/arb_market.py` (`ArbMarket`). I/O: `data/providers/binance_arb.py` (spot+USDⓈ-M/USDC-M: exchangeInfo, depth, premiumIndex+fundingInfo, funding realizado) y `data/arb_market.py` (errores por pieza en `errors`). `eim/arbitrage/` puro, una estrategia por archivo: `funding_carry` (previsto vs realizado, cruce de liquidaciones; inversa solo con préstamo manual), `basis` (spot/perpetuo vs trimestral al vencimiento; funding como costo), `triangular` (informativo: T33 lo deja fuera del selector), `related_perps` (USDT-M vs USDC-M vía USDCUSDT); `selector.py` (pb/día × (1 − aversión·riesgo), descartes con motivo), CLI `python -m eim.arbitrage.cli`. Tests: tests/arbitrage (32) + tests/data/test_arb_provider.py (3); gate 779. **Escaneo en vivo 2026-10-15:** triangular neto −29…−39 pb en 16 ciclos, carry de funding −20 pb a 24 h, USDT-M/USDC-M −18 pb; solo pasa el cash-and-carry trimestral (≈1,7–3,3 % anual, riesgo de liquidación ×2 alto). Pendientes en BACKLOG (T38).",
   "effort": "alto",
   "phase": 8,
   "goal": "Detectar y valorar, en una sola capa, las oportunidades de arbitraje dentro de Binance, siempre **netas de costos y con su riesgo declarado**."
  },
  {
   "id": "T39",
   "title": "Agente arbitrage + escáner UI",
   "deps": [
    "T38",
    "T10"
   ],
   "state": "done",
   "notes": "Agente `eim/agents/arbitrage/` (`agent.py`, `rows.py`, `params.py`): `bias=0` siempre (excluido de la síntesis), `metrics` con mejores oportunidades y costos desglosados del motor T38, funding previsto/próximo/realizado + histórico corto, base anualizada y descartes con motivo (`Rejected.code` nuevo en el selector); confianza = frescura × profundidad × cobertura. `MarketSnapshot.arb` (aditivo) desde `data/arb_store.py` (últimos 20 escaneos en `data/arbitrage/`, nunca posteriores a `asof`); escáner `data/arb_sync.py` dentro de la API cada ~10 s (`EIM_ARBITRAGE`), libros en paralelo en `arb_market.py` (8–10 s → ~1,4 s). API `GET /v2/arbitrage/opportunities` + WS `arbitrage` (`api/arbitrage.py`), alertas `arbitrage/alerts.py` (≥3 pb/día ajustados sostenidos 60 s). UI: pestaña «Arbitraje» (`web/src/arb_ui.ts`, `arb_view.ts`, `arb.css`): modo Análisis, «neto estimado, no garantizado», tabla con patas/bruto/costos/neto/anualizado/capital/riesgo/vigencia, filas expandibles, filtros, funding, base, aviso en la pestaña. Tests: 28 nuevos (agente, alertas, almacén, API sobre fixture real `tests/fixtures/arbitrage/`); gate 807. **Verificado en vivo 2026-10-15** (Binance, 22 libros): 28 filas renderizadas = API = `scan_all` de T38 sobre la misma fotografía (0 diferencias); solo pasa el cash-and-carry trimestral (≈1,8–3,1 % anual); alertas probadas con umbral 0,3 pb/día. **Satélite en el río** (decisión del usuario 2026-10-15, `web/src/river_arb.ts`): esfera propia junto a la central, sin haz hacia ella (carril propio, T44); su % es el neto anual estimado de la mejor oportunidad (▲ ganancia / ▼ pérdida, no dirección del precio), en vivo por WS sin reiniciar la esfera; tooltip con desglose, funding, base y alertas. Pendientes en BACKLOG (T39).",
   "effort": "medio",
   "phase": 8,
   "goal": "Exponer el motor de T38 como agente y como escáner visible, sin mezclarlo con el sesgo direccional."
  },
  {
   "id": "T40",
   "title": "Copy trading: datos y descubrimiento de líderes",
   "deps": [
    "T03",
    "T33"
   ],
   "state": "done",
   "notes": "Contratos `eim/core/leaders.py` (`Leader`, `LeaderPosition`, `LeaderFill`, `LeaderFunding`; `t` del exchange vs `observed_at` local **corregido con el desfase medido** frente al servidor, ≈1,2 s) + `MarketSnapshot.leaders` (aditivo; lo rellena T41). I/O: `data/providers/leaders.py` (Hyperliquid `/info` + WS oficiales, sin claves: reintentos, presupuesto de peso, paginación; WS con `ping` y reconexión exponencial), `data/leader_watch.py` (≤10 líderes por WS `userFills`, resto por REST; huecos por `startPosition`/corte del WS/reconciliación con relleno `userFillsByTime`; reconciliación cada 30 s con re-comprobación a 5/10/15 s antes de resincronizar), `data/leader_store.py` (`data/leaders.duckdb`: ejecuciones con acción apertura/aumento/reducción/cierre/giro, comisión y PnL, funding, apalancamiento, fotos de posiciones, reconciliaciones, huecos; dedupe por clave), `data/leader_discover.py` (muestra del WS `trades` → candidatos; Binance solo manual), `data/leader_report.py`. Puro: `eim/leaders/` (parseo con `Decimal`, libro esperado, descubrimiento); CLI `python -m eim.leaders`. Tests sin red sobre respuestas reales grabadas (`tests/fixtures/leaders/`): 44 (reconexión, duplicado, hueco, cierre parcial, giro, apalancamiento, liquidación, retraso del endpoint); gate 851. **Verificado en vivo 2026-10-15 (35 min, 7 billeteras reales, 5 por WS y 2 por REST):** 441/441 reconciliaciones con posiciones idénticas al exchange al primer intento (0 resincronizaciones, 0 huecos); latencia WS p50 194 ms, p90 372 ms, p99 704 ms, máx. 2,0 s (n = 4 123); 2 457 pagos de funding. Pendientes en BACKLOG (T40).",
   "effort": "alto",
   "phase": 8,
   "goal": "Capturar de forma fiable y legítima las posiciones y operaciones de los traders a seguir, y guardarlas con historial propio."
  },
  {
   "id": "T41",
   "title": "Copy trading: evaluación de líderes + agente smart_money",
   "deps": [
    "T40",
    "T05"
   ],
   "state": "done",
   "notes": "Puro `eim/copytrading/`: viajes de plano a plano (`trades.py`: giro reparte comisión; apertura no vista o hueco en la cadena de posiciones → parcial, fuera), `metrics.py` (neto de comisiones y funding, FB, G/P, caída, consistencia diaria, concentración, apalancamiento, promediado, martingala), `stats.py` (Sharpe por operación **deflactado por N billeteras** + IC con Bonferroni), `portfolio.py` (`portfolio` de HL, Modified Dietz: solo preselecciona), `copyability.py` (latencia medida + 300 ms, ask/bid vigente grabado en vivo, comisión tomador), `forward.py` (adelante = tras la 1.ª foto; días = tiempo realmente cubierto; cohortes por veredicto), `scorecard.py` (reglas duras → descartado; adelante < 30 op o < 7 d → vigilancia; DSR < 0,95 o seguidor ≤ 0 → descartado; si no aprobado, calidad = DSR × retención; cada veredicto con motivos), `board.py`. I/O: `data/leader_service.py` (vigilante T40 + WS `bbo`/`allMids` → `leader_follow`, `portfolio` cada 6 h, tablero cada 5 min en `data/leaders/`), `leader_eval.py` (veredicto → estado + historial), `leader_board.py`, `leader_score_store.py`; `rejected` sigue capturado (grupo de control). `build_snapshot` rellena `leaders` + `leader_weights` (nuevo). Agente `smart_money` (calidad, tope 40 % por líder; fuera de la síntesis hasta T44). API `GET /v2/leaders/board`; pestaña «Líderes» (`leaders_ui.ts`, `leaders_view.ts`, `leaders.css`); CLI `score [--portfolio]`. Tests: 36 nuevos (racha con n chico descartada, consistente aprobado, sin líderes → no_data, servicio sobre ejecuciones reales grabadas); gate 941. **Verificado en vivo 2026-10-16** (7 billeteras reales, 30 min): 385/385 reconciliaciones idénticas, 0 huecos, latencia WS p50 194 ms; 12 292 precios del seguidor (`bbo`, antigüedad p50 262 ms); 0 aprobados (nadie tiene 7 d adelante), 3 en vigilancia y 4 descartados con motivo (cartera −26 M USD, caídas ~100 %, latentes −262 k USD); 0xf5d8: en 172 operaciones adelante el líder +366 USD y el seguidor −812 USD (comisiones de tomador). Runner de la API: `smart_money` corrió en la vela de 15:00 UTC con el tablero real → `no_data` («ningún líder aprobado»). Pendientes en BACKLOG (T41).",
   "effort": "alto",
   "phase": 8,
   "goal": "Decidir a quién vale la pena seguir con métricas robustas (no con \"100 % de acierto\") y convertir sus posiciones en un agente direccional."
  },
  {
   "id": "T42",
   "title": "Copy trading: replicación simulada",
   "deps": [
    "T41",
    "T25"
   ],
   "state": "done",
   "notes": "**Corrida en vivo de ≥ 24 h cumplida** (verificación 2026-10-19 00:35 UTC, 2.º intento): ventana 2026-10-18 00:04 → 2026-10-19 00:16 UTC (primera reconciliación 00:07:27 tras resincronizar el hueco de la suspensión; 24,1 h), 18 725 reconciliaciones en la ventana, hueco máximo entre ellas 11,8 min, sin suspensiones de Windows; 0 pausas, 0 kill-switch, ninguna diferencia no explicada nueva (la última sigue siendo 2026-10-16 20:25 UTC). Un reinicio del proceso a las 17:16 UTC: falso «latido detenido» del vigilante (lectura fallida de `heartbeat.json` → BACKLOG T42 (12)); hueco 4 min, resincronizado con motivo. En la ventana: 92 aperturas decididas (95 vetadas por riesgo, 206 bajo mínimo, 119 sin precio), 11 órdenes de cierre/reducción en la bitácora. Informe regenerado (reproducción, 7 billeteras, ninguna aprobada → medición): aparente −1 780 USD → copiable −200 USD (tamaño +1 724, comisiones −232, no copiados +147). Puro `eim/copytrading/`: `replicator.py` (objetivo = líder × capital/cuenta fijada por viaje; nunca contra el movimiento del líder; cierre/giro → cierre total; topes 40 %/moneda y 150 %/líder; `szDecimals` de `meta` y mínimo 10 USDC; deslizamiento ≤ 0,5 %; preexistentes no se copian), `copy_risk.py` (toda apertura/aumento → `PlanRequest` → motor T29 con **`risk_copy_v1`**, stop 5 %, señal ≤ 30 s; kill-switch propio), `copy_book.py` (subcuenta virtual 10 000 USDC, comisión tomador HL, funding horario, stops), `copy_engine.py`/`copy_control.py`/`copy_recon.py` (bitácora señal→decisión→riesgo→orden/rechazo con motivo; reconciliación con la foto real: no explicada 2 veces → pausa + alerta, reanudar solo a mano; huecos de captura > 5 min y reinicios se resincronizan con motivo, sin abrir nada), `copy_attrib.py` + `copy_report.py` (aparente vs copiable con causas que suman la brecha). I/O: `data/copy_live.py` dentro del servicio de líderes (`EIM_COPY_SIM=tracked|approved|off`; nunca tumba la captura; relee de la base tras un reinicio), `copy_replay.py` (mismo motor sobre el historial: cotizaciones grabadas, velas 1 min HL `hl_market.py`, costos T25), `copy_store.py` (`copy_state`, `copy_journal`, `copy_sim.json`, instantánea a pedido). CLI `python -m eim.leaders copy-sim|copy-status|copy-resume`; API `GET /v2/leaders/copy`; UI «Líderes» → «Copia simulada» (modo Simulado). Tests: 5 escenarios pedidos + reales grabados (caída a mitad, reenvío del WS antes que el relleno REST, hueco nocturno). **`reports/copytrading_sim.md`** (1.ª versión, 22 h: aparente +784 → copiable −55 USD; 94 % de órdenes al bid/ask grabado). En vivo desde 2026-10-16 19:16 UTC.",
   "effort": "alto",
   "phase": 8,
   "goal": "Convertir los cambios de posición de un líder aprobado en órdenes propias proporcionales, **solo en simulación**, y medir lo que realmente habría ocurrido."
  },
  {
   "id": "T43",
   "title": "Arbitraje: simulación y backtest con costos",
   "deps": [
    "T38",
    "T25"
   ],
   "state": "done",
   "notes": "Simulador puro `eim/arbitrage/sim/`: reproduce el motor T38 sobre el histórico (mismo `scan_*` + `select` en cada decisión, cada 8 h) y simula cada oportunidad vela a vela: funding real, margen y rebalanceo, liquidación (regla T25), deslizamiento con perfiles de libros reales capturados (adelgazados por volumen) y pata incompleta (costo esperado + distribución por latencia). I/O `data/arb_history_sync.py` + `arb_history.py`: spot 1 h, perpetuos USDT/USDC, 34 trimestrales (30 vencidos con precio real de liquidación), funding, pares triangulares 1 min (30 d), mínimos de orden y capturas de libros; `Store(kind=\"spot_candles\")`, `1m` solo de almacén. CLI `python -m eim.arbitrage.sim sync|run`. **`reports/arbitrage_edge.md`** (2023-01 → 2026-10, BTC+ETH, VIP 0): carry a 90 d **Marginal** (+4,1 %/año; últimos 12 m +1,2 %), base spot/trimestral **Marginal** (+3,5 %; 12 m +2,4 %), USDT-M/USDC-M **No viable** (nunca seleccionada), triangular **No viable** (0 de 256 ciclos > 0 con libros reales; el ticker solo da artefactos). `ArbParams` fijados con esa evidencia: `selectable` sin `related_perps`, `disabled_variants` = base perpetuo/trimestral (−12 pb/op; el selector la marca «informativa»), `carry_horizon_h` 2160, `perp_leverage` 3, `daily_move` 0,0514, `basis_floor_bps` 10,1, `funding_shock_rate` 7,1e-5 (`min_net_bps` 2: 0–10 pb indistintos). Tests: 24 nuevos (funding constante = retorno analítico, libro delgado reduce el neto, pata incompleta genera pérdida, rebalanceo/liquidación, convergencia, sin mirar al futuro, estimado = realizado); los de mecánica T38 fijan sus supuestos (`T38`); gate 1007. Pendientes en BACKLOG (T43): **T45 debe rebalancear margen**.",
   "effort": "alto",
   "phase": 8,
   "goal": "Responder con datos si cada estrategia de arbitraje deja dinero neto en Binance y con qué riesgo, antes de ejecutar nada."
  },
  {
   "id": "T44",
   "title": "Integración de agentes nuevos (síntesis, riesgo, UI)",
   "deps": [
    "T20",
    "T35",
    "T36",
    "T37",
    "T41",
    "T39"
   ],
   "state": "done",
   "notes": "Síntesis (`eim/synthesis/`): papel por agente (`role_of`: direccional / riesgo / carril / derivado); `calendar` y `arbitrage` en `NON_DIRECTIONAL` (nunca votan, ni forzando `excluded`/pesos; test); `technical` y `smart_money` votan como direccionales con peso de `T44_WEIGHTS` y penalización por correlación (peso × (1 − ρ⁺) solo si `ema`/`structure` votan; ρ medida 0,68/0,58); calendario en ventana → confianza ×0,75 (×0,5 con blackout); `Synthesis.weights`/`factors` (aditivos). Riesgo: **`risk_v2` vigente** (= v1 + `event_size_factor` 0,5: tamaño a la mitad en ventana sin blackout), `market_context` evalúa `risk_windows` a la hora real de decidir (cierra BACKLOG T36-1); blackout sigue vetando (regla `evento`). **Prueba marginal** (`eim/analytics/agent_panel.py` panel real de agentes cada 4 velas 1 h 2023-01→2026-10, snapshots = `build_snapshot`; `agents_marginal*.py`, regla fijada antes; **`reports/agents_marginal.md`**): `technical` no aporta (BTC ΔSharpe −0,00, ΔIC24 +0,0004; ETH +0,12 pero 57 % de ventanas y con peso 1 empeora) y `smart_money` no es medible (sin historia) → **peso inicial 0 ambos** (a la vista, sin voto); la síntesis base pierde en la prueba (Sharpe −2,39 BTC / −1,05 ETH). API `/v2/agents` + `role`/`weight`. UI: reloj del próximo evento con cuenta atrás en la barra superior (`event_clock.ts`; ventana/blackout en color), filtros por tipo en el río (`agent_roles.ts`), haz punteado y etiqueta para quien no vota, pesos y factores en el detalle de la síntesis. Tests: tests/synthesis/test_t44_integration.py (19), tests/risk/test_event_window.py (8), tests/analytics (6). Verificado en navegador (API aislada en 8001). Pendientes en BACKLOG (T44).",
   "effort": "medio",
   "phase": 8,
   "goal": "Conectar cada agente nuevo al lugar correcto del sistema, respetando que no todos son direccionales."
  },
  {
   "id": "T45",
   "title": "Arbitraje en testnet (dos patas, selección automática)",
   "deps": [
    "T30",
    "T43"
   ],
   "state": "progress",
   "notes": "**Construido y probado contra el exchange simulado; falta la corrida E2E en testnet real con claves** (`python -m eim.execution.arb_smoke`: carry abierto→mantenido→cerrado, pata fallida deshecha, corte de red; su lógica pasa contra el simulado, `tests/execution/test_arb_smoke.py`). Brokers: `execution/binance_rest.py` (firma común, extraída de T30), `binance_spot_testnet.py` (spot testnet, comisión en base vía `fills`/`myTrades`), `binance_testnet.py` + libro, profundidad, riesgo de posición, `positionMargin`, funding cobrado. Ejecutor `arb_executor.py`/`arb_legs.py`/`arb_book.py`: la pata menos líquida (profundidad de la testnet) primero, LIMIT con tiempo límite y cancelación, persecución de la 2.ª acotada por el tope, **unwind** de la 1.ª (precio límite = tope 50 pb; si no llena, a mercado + kill-switch `regla:pata`), ids `eia-` deterministas, idempotencia, fills parciales, orden anotada antes de enviarse. `arb_recon.py`: órdenes sin respuesta por id, descubiertos recortados (sin huérfanas tras cortar la red), liquidación/cierre externo adoptados, margen, liquidación y funding real vs esperado; desconexión ≥ 5 min → kill-switch compartido → cierre de ambas patas. Gestión pura `eim/arbitrage/live/` (rebalanceo al 50 % del margen objetivo: margen libre o reducir ambas patas; cierre por funding < 0 en 3 lecturas, base agotada, vencimiento, tenencia, liquidación < 8 %). Selector `arb_runner.py`: fotografía T38 re-seleccionada a la hora real, estrategias Viable/Marginal (T43), riesgo `risk/arb_engine.py` + `versions/risk_arb_v1.json` (solo TESTNET; margen y exposición de TODA la cuenta; conflicto con el carril direccional) → la de mayor puntuación aprobada, 1 por ciclo, enfriamiento 1 h tras una apertura fallida; puerta `ArbGateway` (sello). T30 respeta los futuros del arbitraje (`Reconciler.external`, `flatten(keep)`). Bitácora y estado en `data/arb_exec/`. API `EIM_ARB_EXECUTION=testnet` → `/v2/arbitrage/execution` (+`/cycle`, `/close`, `/flatten`, `X-EIM-Confirm`); UI «Arbitraje» → «Ejecución automática» (Modo: Testnet; verificada en navegador con API de demostración). Tests: 81 nuevos (pata incompleta, rechazo, desconexión con posición abierta, funding que cambia de signo, libro que se vacía, rebalanceo, riesgo, API); gate 1124. Revisión de código: 8 hallazgos, 7 corregidos. **Pruebas en el bróker simulado (decisión del usuario 2026-10-18, sin cuenta de Binance):** exchange en memoria `execution/arb_sim.py` + `arb_sim_brokers.py` (modo SIMULADO, un venue por mercado, comisiones VIP 0, liquidación, funding; riesgo `risk_arb_sim_v1`, solo SIMULADO; el ejecutor toma el modo de sus brokers, nunca REAL) movido por velas reales de 1 h (spot y perpetuo) y funding realizado (`data/arb_sim_data.py`); escenarios `paper/arb_tests.py` (CLI `python -m eim.paper.arb_cli`, API `/v2/paper/arbitrage` + `/run` con `X-EIM-Confirm: paper-arb`), pestaña «Arbitraje» del Bróker simulado con gráfico spot/perpetuo y cada orden marcada (`web/src/paper_arb.ts`). **Corrida real 2026-10-14 16:00 → 10-16 23:00 UTC: 3 de 3 superados** — carry abierto, 48 h con 7 cobros de funding (+0,19 USD real vs +0,10 esperado), cerrado (−3,23 USD: comisiones 2,93; el carry necesita semanas, T43); pata fallida deshecha (−0,19 USD, tope 5 USD); corte de red sin huérfanas. Verificado en navegador. Pendientes en BACKLOG (T45).",
   "effort": "alto",
   "phase": 9,
   "goal": "Ejecutar automáticamente, **solo en testnet**, las estrategias que T43 declaró Viable o Marginal, con selección automática entre ellas."
  },
  {
   "id": "T46",
   "title": "Copy trading en testnet + asignador de capital",
   "deps": [
    "T30",
    "T42",
    "T45"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 9,
   "goal": "Replicar líderes aprobados en testnet y repartir el capital entre los tres carriles (direccional, copy trading, arbitraje) sin que uno consuma el margen de otro."
  },
  {
   "id": "T47",
   "title": "Bróker simulado: estrategias en papel, 3 perfiles y automejora",
   "deps": [
    "T15",
    "T17",
    "T20",
    "T25",
    "T34"
   ],
   "state": "done",
   "notes": "v2/eim/paper: contexto compacto por vela (`context`, `generate` walk-forward en paralelo, `data/paper.duckdb` vía `eim/data/paper_store.py`), 29 estrategias en 7 familias (`strategies*`: consenso, plan TP1/TP2, sugerencias #1–#3, escenarios, 8 agentes, 8 indicadores T34, contraria y **control aleatorio**), motor sobre 15 m (`engine`: límite/mercado, SL antes que TP, tiempo, funding real, MFE/MAE), retroalimentación sin mirar el futuro (`feedback`: expectativa contraída con decaimiento, pausa/refuerzo, Holm, vs control; `insights`), 3 perfiles Conservador/Moderado/Agresivo (`book`, `params`). API `/v2/paper` (+`/trades`, `/journal`, `/ideas`, `POST /backtest` con `X-EIM-Confirm`), servicio en vivo `EIM_PAPER`, CLI `python -m eim.paper`. UI: botón «Bróker simulado» arriba a la derecha (`web/src/paper_*.ts`, `paper.css`): tarjetas por perfil, velas con entradas/salidas, cuenta estilo exchange, curvas de capital, Posiciones/Órdenes/Historial/Bitácora/Aprendizaje/Perfiles. Backtest real 60 d BTCUSDT (1.439 velas, 1.591 ops sombra): control −0,20 R/op, ninguna estrategia significativa tras Holm; Conservador −0,8 %, Moderado −67 %, Agresivo −95 % (costos ≥84 % de la pérdida). Tests en tests/paper + tests/api/test_paper_api.py (sin anticipación probada). Verificado en navegador (escritorio y móvil). **Para usarlo: reiniciar la API.** **Ampliación (2026-10-15):** balance superior «ganadas vs perdidas» ponderado de los 3 perfiles (cada operación pesa igual) por periodo (todo/30 d/7 d/24 h): conteo, USDT, R medio, desglose por perfil y por salida, acierto real vs necesario (en R), esperanza, PF, costos y retroalimentación funcionó/no funcionó/mejorar (`eim/paper/balance.py`, `web/src/paper_balance.ts`, tests en tests/paper/test_balance.py). **Foco BTCUSDT (2026-10-15, decisión del usuario):** la UI solo muestra BTCUSDT (`SYMBOLS` de `web/src/api.ts`; etiqueta fija en lugar del selector; ETH oculto en multi-activo, estacionalidad y vetos de Operación); `FOCUS` en `eim/data/timeframes.py` para el servicio de operación y el bróker; escáner y agente de arbitraje en vivo solo BTC (`EIM_ARB_ASSETS`, `EIM_ARB_TRI_ASSETS`). La API y el almacén siguen admitiendo ETHUSDT.",
   "effort": "alto",
   "phase": 7,
   "goal": "Ejecutar de forma virtual (papel, futuros perpetuos de Binance) TODAS las operaciones que proponen los agentes, las sugerencias intradía y los escenarios, en una vista tipo exchange, y medir qué enfoque rinde y cuál no, con retroalimentación que ajusta el peso de cada estrategia sin mirar el futuro."
  },
  {
   "id": "T48",
   "title": "Bróker simulado continuo: 3 temporalidades y aprendizaje de cada pérdida",
   "deps": [
    "T47"
   ],
   "state": "done",
   "notes": "Multi-marco: contextos e ideas en 15 m / 1 h / 4 h; cada estrategia se evalúa y pondera por separado en cada marco (`estrategia@marco`, `Idea.sid`), tenencias escaladas al marco (las sugerencias y escenarios conservan sus horas); perfiles operan los tres. Aprendizaje de cada pérdida: causa por operación (`Outcome.cause`: dirección, SL rápido, casi TP, tiempo, costos) y pausa por contexto estrategia@marco × régimen × lado (`Learner.context_at`, solo cierres ≤ t; test), visible en bitácora («Aprendizaje por contexto»), balance («Por qué se perdió», acierto por marco), Aprendizaje (filtro por marco, causas y contextos) y conclusiones. Servicio continuo: `eim/paper/service.py` (ciclo por marco, latido `data/paper/heartbeat.json`, backtest por marco), franja «Servicio en vivo» en la vista, `v2/scripts/servicio_continuo.ps1` (vigilante + web, sin duplicar) e `instalar_inicio_automatico.ps1` (tarea al iniciar sesión, no instalada). API `tf` en trades/journal/ideas/backtest; CLI `--tf`. Datos reales: 4 h 60 d (360 velas, −0,19 R/op sombra), 1 h 60 d (−0,28), 15 m en curso; posiciones abiertas en los 3 marcos. Tests en tests/paper/test_t48.py. **T48b (decisión del usuario: «máxima rentabilidad, más acertadas que fallidas»)**, con evidencia en `PLAN/notas/T48_decisiones.md`: filtro de costo por perfil (`max_cost_r`), tendencia del marco mayor obligatoria (`eim/paper/trend.py`, `Idea.htf`), break-even + que cubre costos solo en 1 h/4 h (salida `BE`), pausa ante expectativa negativa en los 3 perfiles y Conservador «solo lo probado». Mismos datos: ponderado 36,3 % → 44,5 % de acierto, esperanza −0,30 → −0,09 R; 1 h Moderado/Agresivo +0,10/+0,13 R con 53 % de acierto. Configuración elegida sobre esos mismos 60 días: validar con la corrida en vivo. **T48c**: pestaña «Señales en vivo» (inicial): cada decisión en tiempo real con su estado en la sombra y qué hizo cada perfil y por qué (`eim/paper/live_feed.py`, `GET /v2/paper/live`, `web/src/paper_live.ts`); el botón pasa a «Reconstruir historial (backtest)». Verificado con datos reales: 42 señales en vivo, todas rechazadas por los perfiles por «estrategia en pausa» (lo esperado con T48b). Tests en tests/paper/test_live_feed.py y tests/api/test_paper_api.py.",
   "effort": "alto",
   "phase": 7,
   "goal": "Que el bróker simulado opere sin parar en segundo plano sobre BTCUSDT en 15 m, 1 h y 4 h, y que cada pérdida se convierta en aprendizaje (por contexto y por causa) para que con el tiempo las ganadas prevalezcan sobre las perdidas."
  },
  {
   "id": "T49",
   "title": "Puerta de validación por estrategia (criterios v1, versiones, registro de intentos)",
   "deps": [
    "T27",
    "T48"
   ],
   "state": "done",
   "notes": "**Veredicto (v2/reports/validation/validation_v1_2026-10-18.md + .json): ninguna estrategia validada** — 87 intentos: 54 EN OBSERVACIÓN, 33 RECHAZADA; en 1 h las 26 versiones con ≥ 100 operaciones fuera de muestra tienen R medio neto negativo (25 claramente; la mejor, sugerencia_1@1h@v1, −0,063 R, IC95 % [−0,111, −0,015]); V5 pendiente en todas (vivo solo desde 2026-10-16). Criterios inmutables `eim/validation/versions/validation_v1.json` + `criteria.py` (hash fijado; commit 18e7283, anterior al primer cálculo real). Versión = huella de reglas + mecánica (`paper/versioning.py`, `Idea.version`); intentos, ventanas de ajuste y veredictos en `data/paper.duckdb` (`data/validation_store.py`, `validation/lineage.py` + `lineage.json` con la ventana T48b); puerta pura `validation/gate.py` (+`stats.py`, `evidence.py`); recálculo al cierre de cada vela de 4 h en la API (`validation/service.py`), `GET /v2/validation` (+`/history`), CLI `python -m eim.validation`. Historia: 1 h desde 2023-01-11 (33 038 contextos), 4 h desde 2026-03-19, 15 m sin reconstruir. Tests en v2/tests/validation.",
   "effort": "alto",
   "phase": 10,
   "goal": "Decidir, con criterios fijados antes de calcular, qué `estrategia@marco@versión` del bróker simulado tiene evidencia fuera de muestra suficiente (neta de costos, con drawdown y estabilidad aceptables) para alimentar «Operaciones sugeridas intradía»; ninguna estrategia se declara rentable solo porque ganó en un backtest, y «ninguna validada» es un resultado válido."
  },
  {
   "id": "T50",
   "title": "Publicador de sugerencias validadas (/v2/setups + panel)",
   "deps": [
    "T49"
   ],
   "state": "done",
   "notes": "Publicador puro `eim/suggestions/publisher.py`: cruza las ideas vivas de la última vela cerrada de 15 m y 1 h (cualquier estrategia, tenencia ≤ 36 h) con los veredictos de T49 y publica ≤ 3 de versiones VALIDADAS (cruce por `estrategia@marco` + huella), ordenadas por el límite inferior del IC95 % fuera de muestra, deduplicadas (mismo lado, entrada < 0,5 ATR) y sin vencidas; si no hay ninguna, lista vacía y motivo `sin_validadas` / `sin_senal` / `datos_viejos`. `GET /v2/setups` (`eim/api/setups.py`, contrato en `CONTRATOS.md`) ya no publica la salida cruda de `suggest()` (queda como generador de candidatas del bróker). Panel (`web/src/setups_ui.ts`): tarjetas con entrada/SL/TP/riesgo, estrategia@marco@versión, evidencia, razón y hora, «Sugerida · no ejecutada» + aviso, y estado vacío «Sin operaciones validadas para sugerir» con motivo (lo esperable hoy: T49 no validó ninguna). Tests en `tests/suggestions`, `tests/api/test_setups_api.py`. Verificado en navegador con respuesta simulada de la API (tarjetas y estado vacío, screenshot); falta mirarlo con datos reales en la máquina del usuario. **Para usarlo: reiniciar la API.**",
   "effort": "medio",
   "phase": 10,
   "goal": "Que el panel «Operaciones sugeridas intradía» muestre solo oportunidades de estrategias VALIDADAS por la puerta de T49, con su evidencia, o el mensaje explícito «Sin operaciones validadas para sugerir»; siempre como oportunidades potenciales, nunca como operaciones ejecutadas ni garantías de rentabilidad."
  },
  {
   "id": "T51",
   "title": "Seguimiento de sugerencias publicadas + ciclo de mejora",
   "deps": [
    "T50"
   ],
   "state": "done",
   "notes": "Registro inmutable de publicaciones y de intervalos sin sugerencia (`eim/data/suggestion_store.py`, tablas `sug_*` en `paper.duckdb`), resolución con `paper/engine` sobre velas de 15 m posteriores a la publicación, sin anticipación (`eim/suggestions/tracking.py`), `Tracker` (registro idempotente, señal contra resultado, degradación: media de las últimas 20 < límite inferior del IC95 % ⇒ «en revisión» y el publicador la excluye hasta un veredicto nuevo de T49) enganchado al ciclo del bróker; `GET /v2/setups/history` y sección «Historial de sugerencias» (`web/src/setups_history.ts`); ciclo de mejora en `v2/docs/OPERACION.md`. Tests sin red en `tests/suggestions/test_tracking.py` y `tests/api/test_setups_history.py`. Verificado en navegador solo el estado vacío (sin red a Binance en este entorno ⇒ sin velas ni veredictos reales; screenshot `v2/reports/t51_historial.png`): falta mirarlo con datos reales.",
   "effort": "medio",
   "phase": 10,
   "goal": "Registrar cada oportunidad que el panel publica, resolver qué habría ocurrido con ella y comparar señal contra resultado, para que el ciclo de mejora (diagnóstico → versión nueva → nueva validación en T49) se alimente de lo que de verdad se mostró y para retirar a tiempo una estrategia que se degrada."
  },
  {
   "id": "T52",
   "title": "Biblioteca de trading: ingesta local, catálogo y fichas citadas",
   "deps": [
    "T05"
   ],
   "state": "done",
   "notes": "**◆ revisado (2026-10-18): las 138 fichas `revisada_usuario`** (Nison y Murphy ficha a ficha; conducta y cruces por delegación del usuario) y bibliografía aprobada. Ingesta local `eim/data/library.py` + `library_extract.py` (pypdf, EPUB con stdlib, OCR Tesseract con caché por página), catálogo con SHA-256 y búsqueda BM25 propia (`eim/library/bm25.py`); CLI `python -m eim.library ingest|list|search|show|cards|verify|mark`; libros vía `EIM_LIBRARY_DIR`, índice local fuera de git. Los 7 libros catalogados (Murphy por OCR: 572/596 págs.). Esquema `KnowledgeCard` (`eim/library/schema.py`) con guardas de derechos de autor e inyección (`guards.py`). **138 fichas** en `eim/library/cards/` (Nison 43, Murphy 48, Douglas 8+8, Steenbarger 11, Schwager 10, Lefèvre 7, cruces 3), todas verificadas contra el texto (`verify`). Revisión: `PLAN/notas/T52_fichas_revision.md`; estados con `python -m eim.library mark`. Tests en `tests/library/` (sintéticos, sin red). Pendientes en BACKLOG (T52).",
   "effort": "alto",
   "phase": 11,
   "goal": "Convertir los libros de trading del usuario (más obras de dominio público y artículos académicos abiertos) en **fichas de conocimiento** estructuradas, parafraseadas y citadas (libro, capítulo, página), que los agentes de T53–T55 puedan usar, sin que el texto de los libros entre al repositorio ni salga de la máquina."
  },
  {
   "id": "T53",
   "title": "Agente literature: reglas de los libros y apoyo a los escenarios",
   "deps": [
    "T52",
    "T17",
    "T34"
   ],
   "state": "done",
   "notes": "v2/eim/agents/literature/ (9 reglas codificadas, fichas → `codificada`: Nison velas, Murphy RSI y canal 4 sem.; `scenario_support` por escenario, confianza ≤ 0,5, peso 0 en síntesis); `GET /v2/library/cards/{id}` (eim/api/library.py); UI «Lo que dice la literatura» en tarjetas de escenario (literature_ui.ts). Verificado con 1000 velas reales ETHUSDT (fixture) y captura de la UI; el gate pasa salvo 2 tests legacy que requieren el paquete `binance` (no instalado aquí).",
   "effort": "medio",
   "phase": 11,
   "goal": "Un agente puro que evalúa sobre el `MarketSnapshot` las fichas codificables de la biblioteca (T52) y dice qué reglas de la literatura están activas ahora y si **apoyan o contradicen cada uno de los 3 escenarios** de la proyección, siempre con su cita (autor, libro, página). Informa; no cambia probabilidades ni publica sugerencias."
  },
  {
   "id": "T54",
   "title": "Retroalimentación con evidencia: estrategias «literatura» y ajuste de escenarios",
   "deps": [
    "T53",
    "T49",
    "T19"
   ],
   "state": "done",
   "notes": "**◆ revisado (2026-10-19): sin evidencia suficiente; nada activado** (v2/reports/literature/lit_v1_2026-10-19.md, BTCUSDT, 1.256 contextos 1 h desde 2026-08-28 y 1.096 de 4 h desde 2026-03-24 reconstruidos con `python -m eim.paper backtest`). Reglas: las 9 versiones de la familia `literatura` EN OBSERVACIÓN (V1 falla en las 9; 36 operaciones fuera de muestra en total; ningún IC95 % excluye 0; RSI −0,50 R con 11 op., envolvente −0,18 R con 19). Ajuste de escenarios (`lit_tilt_v1`, k 0,5): 54 pronósticos, solo 4 con neto ≠ 0; Brier +0,010 y log-loss +0,007 con IC que incluyen 0, ECE empeora (0,018→0,039); SIN EVIDENCIA, queda apagado (`lit_tilt_state.json`). Preregistro `PLAN/notas/T54_preregistro.md` (commits previos al código). Entregado en PR #93; aquí el cierre y la corrección del `+nan` del informe. Las reglas solo se activan en ~7 % de los orígenes: T1 (≥ 100 con neto ≠ 0) exige ~35.000 cierres de 1 h (~4 años); ver BACKLOG T54.",
   "effort": "alto",
   "phase": 11,
   "goal": "Que lo que dicen los libros pase de opinión a evidencia por dos caminos, ambos fuera de muestra y con criterios fijados antes de calcular: (a) cada regla comprobable se vuelve **estrategia candidata** del bróker simulado y la puerta T49 decide; (b) el apoyo bibliográfico de T53 **retroalimenta las probabilidades de los escenarios** solo si mejora su calibración. Si ninguno mejora nada, ese es el resultado y se informa tal cual."
  },
  {
   "id": "T55",
   "title": "Consulta a la biblioteca (LLM, solo informa) + panel",
   "deps": [
    "T52",
    "T24"
   ],
   "state": "done",
   "notes": "`eim/library/qa.py` (puro: BM25 de T52 + fichas → LLM inyectado → `{resumen, puntos[{texto, fuente}], relacion_con_escenarios, advertencias}`; fuente = `card_id` o `libro#página` entregados, si no el punto se descarta; páginas con texto dirigido a un modelo no viajan; fragmentos ≤ 280 car.) y cliente `data/providers/claude_library.py` (apagado salvo `EIM_LIBRARY_LLM=1` + `ANTHROPIC_API_KEY`, caché de prompt, temp. 0,1, ≤ 0,02 USD/consulta). API `GET /v2/library/catalog` y `POST /v2/library/ask` (`X-EIM-Confirm: library-ask`); panel «Biblioteca» (`web/src/library_ui.ts`). Tests `tests/library/test_qa.py` (LLM simulado, inyección, degradación `no_data`). Verificado en el navegador (catálogo real, consulta apagada). Pendiente manual: una consulta con clave real.",
   "effort": "medio",
   "phase": 11,
   "goal": "Poder preguntar en lenguaje natural «¿qué dice la literatura sobre la situación actual o sobre este escenario?» y recibir una respuesta breve con citas verificables a fichas y páginas de los libros locales. Solo informa: nunca ejecuta, nunca fija tamaño ni cambia probabilidades."
  },
  {
   "id": "T56",
   "title": "Escuadrón de bots: auditoría ampliada y catálogo con ficha común",
   "deps": [],
   "state": "done",
   "notes": "47 repos clonados aislados (sin ejecutar nada) → 50 fichas en `v2/eim/bots/registry/` (+`SCHEMA.md` con las reglas operativa/seguridad fijadas antes de puntuar; `tests/bots/test_registry_cards.py`) e informe `PLAN/notas/T56_auditoria.md` (alertas, veredictos, universo fila por fila, licencias GPL/AGPL en modo B). **Aprobado por el usuario (2026-10-19) para T58:** `hummingbot-directional` (A), `freqtrade`+`freqtrade-strategies` (B, GPL aceptada para uso privado, sin distribuir; entorno Python 3.12 aparte), `passivbot` (L, B). Fuera por ahora: NFI, Jesse-ejemplos, TrendRider, IA. Alertas: señuelo `fearfulincid/Grid-Trading-Bot` (R1), Superalgos (R5), 3 repos sin licencia (R2), Hummingbot depende de `pandas-ta` sin licencia. Límite: sin API de GitHub, búsqueda por temas parcial (BACKLOG).",
   "effort": "medio",
   "phase": 12,
   "goal": "Convertir el universo de `PLAN/notas/T56_universo_bots.md` (≥ 45 candidatos, la mitad sin verificar) en un **catálogo verificado** de estrategias empaquetadas (`bot@estrategia`), cada una con licencia real, mantenimiento, riesgos y **modo de integración**, para que el usuario apruebe qué entra al escuadrón. Aquí nace la mitad del «concepto» de cada bot: las dimensiones **operativa** y **seguridad** (rendimiento y evidencia las mide T59)."
  },
  {
   "id": "T57",
   "title": "Escuadrón de bots: contrato BotSignal, ejecutor aislado y agente bots",
   "deps": [
    "T56",
    "T05"
   ],
   "state": "done",
   "notes": "Contrato `eim/core/bots.py` (`BotSignal`, `extra=forbid`, sin campos de orden/tamaño/claves) + fichas tipadas `eim/bots/card.py`; `snapshot.bot_signals` (aditivo); `bot_signals` en DuckDB solo-añadir/point-in-time (`eim/data/bots/store.py`); servicio `eim/bots/service.py` (Hub y ciclo de operación) y rutas `GET /v2/bots/{signals,catalog}`. Modo A `hummingbot-directional` (`bollinger_v1`, `macd_bb_v1`; paridad con el bot nativo a 1e-9: la prueba destapó que `pandas-ta` usa σ muestral). Modo B `freqtrade-strategies`/`FSupertrendStrategy` en `eim/data/bots/runner.py` (entorno por lista blanca, sin claves ni red, límites, SHA fijado y checkout limpio); paridad con `get_entry_signal`/`get_exit_signal` reales en 234 velas (0 diferencias). Agente `bots` (peso 0, `excluded`, papel `contexto`; solo vota con estado `vota`, ninguno hasta T59) en `eim/agents/bots/`. Docs: `PLAN/CONTRATOS.md`, `docs/SEGURIDAD.md`, `docs/BOTS.md`, `THIRD_PARTY.md`; límites en BACKLOG.",
   "effort": "alto",
   "phase": 12,
   "goal": "Construir la cáscara que **encapsula** cualquier bot: un contrato único de salida, un ejecutor que corre el bot sin claves y sin autoridad de operar, y el agente `bots` que consolida las posturas. Se prueba de extremo a extremo con **dos adaptadores de referencia** (uno modo A y uno modo B)."
  },
  {
   "id": "T58",
   "title": "Escuadrón de bots: adaptadores por oleadas (paridad con el bot nativo)",
   "deps": [
    "T57"
   ],
   "state": "done",
   "notes": "Los 3 bots aprobados quedan **adaptados**. `hummingbot-directional` (A) y `freqtrade-strategies` (B) ya venían de T57; T58 les añadió el relleno histórico (`eim/bots/backfill.py`, `FreqtradeAdapter.history`): 8 818 + 4 409 posturas 1 h BTCUSDT 2026-04-19→10-19 en `bot_signals` (corrida única = vela a vela, 0 diferencias). `passivbot` (L, B): carril de simulación sin voto (`eim/core/botsim.py` `SimRun`, `eim/bots/pb_adapter.py`, `bot_sim_runs`, CLI `eim.bots.sim_lane`), paridad exacta con el bot nativo, sin anticipación, tiempo acotado; 7,6 meses reales de 1 min (868 fills `trailing_martingale`, 50 `ema_anchor`), solo largos. Arreglos del ejecutor (ruta relativa, FAT32, CRLF). Gate 1683 ok. Entornos en `D:/eim-bots` y `D:/eim-toolchain`; datos en el `data/` del worktree; límites en BACKLOG y `docs/BOTS.md`.",
   "effort": "medio",
   "phase": 12,
   "goal": "Encapsular **todos los bots aprobados en T56** detrás del contrato de T57, de modo que cada uno produzca `BotSignal`s reproducibles. Es una sola tarea con oleadas: añadir un bot no crea una tarea nueva, crea un adaptador y una fila en el registro."
  },
  {
   "id": "T59",
   "title": "Escuadrón de bots: puntuación, puerta de edge y degradación",
   "deps": [
    "T58",
    "T49",
    "T47",
    "T25"
   ],
   "state": "done",
   "notes": "Código y tests listos (`eim/bots/{shadow,scorecard,concept,marginal,health,scorer,scorecard_cli}.py`, `bot_scorecard`, `GET /v2/bots/scorecard`, `docs/BOTS.md`). Informe real `v2/reports/bots_scorecard.md` (BTCUSDT, 6 meses, copia de datos de T58; V5 en vivo pendiente): **ningún bot vota ni es publicable**; FSupertrend y Bollinger RECHAZADOS por la puerta, MACD+BB solo informa (5 operaciones). Regla marginal con guardia ≥ 2 ventanas añadida tras ver la 1.ª corrida (declarado). Gate completo ok. Pendiente ◆ del usuario.",
   "effort": "alto",
   "phase": 12,
   "goal": "Asignar a cada bot su **concepto** con evidencia, usando la puerta que ya valida estrategias del bróker simulado (T49) en vez de crear una segunda vara de medir. Responde a la pregunta del usuario: ¿qué bots merecen influir en una decisión, cuáles solo se observan y cuáles se descartan?"
  },
  {
   "id": "T60",
   "title": "Escuadrón de bots: síntesis, riesgo, UI y operación",
   "deps": [
    "T57",
    "T59",
    "T44",
    "T10"
   ],
   "state": "done",
   "notes": "Política del escuadrón `eim/synthesis/squad.py` (vota solo clase D en estado `vota`, peso medido por T59 con penalización de correlación; L/IA nunca; sin votantes el agente se omite → sesgo idéntico al previo, probado); canales (a) `factors['escuadron']` y (b) «N de M bots apoyan» (solo informan, apagados si T59 no midió ayuda); cuarentena de bots degradados (`eim/bots/quarantine.py`) + latido/alerta en `BotService`. API `GET /v2/bots`, `/v2/agents` con peso vigente; UI pestaña «Escuadrón» (cuatro dimensiones, discrepancia, carril L aparte) verificada en navegador, oscuro y claro. Docs BOTS/NUEVO_AGENTE/SEGURIDAD/RUNBOOK §13. Tests: `tests/synthesis/test_t60_squad.py`, `tests/bots/test_squad_service.py`, `tests/api/test_bots_api.py`. Pendiente BACKLOG (T60).",
   "effort": "medio",
   "phase": 12,
   "goal": "Mostrar el escuadrón al usuario y dejar que influya en las decisiones **en la medida que T59 mida su aporte al núcleo** (no por su rentabilidad aislada), sin tocar la autoridad del motor de riesgo ni la puerta de ejecución."
  },
  {
   "id": "T61",
   "title": "Experiencia compartida entre equipos: exportar, importar y unir historiales",
   "deps": [
    "T49",
    "T47",
    "T40",
    "T32"
   ],
   "state": "done",
   "notes": "**Construido y probado sin red (`tests/share/`, 39 tests); ◆ pendiente: el usuario revisa el informe de la primera mezcla real antes de darla por cerrada.** `python -m eim.data.share export|import [--apply]|status` (`v2/eim/data/share*.py`, `machine.py`): identidad de máquina (`data/machine_id`, `EIM_MACHINE`), exportación consistente de `reports.duckdb`, `paper.duckdb` y `leaders.duckdb` a Parquet + `manifest.json` (SHA-256, esquema, commit) en `EIM_SHARED_DIR/<máquina>/<fecha>/` (en frío, o en caliente vía `POST /v2/share/snapshot` y la instantánea del servicio de líderes), importación idempotente y conmutativa con simulacro por defecto e informe por tabla y máquina (nuevas / ya estaban / conflicto / incompatibles), copia previa, una transacción por base, `import_log`/`share_origin`/`share_conflicts`; versiones de validación unidas por huella con `n`/`parent` remapeados y ventanas unidas; derivados recalculados, kill-switch/estado y secretos nunca viajan; procedencia en `GET /v2/validation` e informe. `leader_recon`/`leader_gaps` ganan `machine` (migración idempotente). **Automático** (`share_auto.py`): tras `python -m eim.data.share setup` (una vez), la API (`reports`+`paper`) y el servicio de líderes (`leaders`) importan en vivo lo de las demás máquinas (cada hora, con copia previa y recálculo de veredictos) y exportan lo propio si cambió (cada 6 h, exportaciones parciales `-api`/`-leaders`, poda de las propias), con estado en `GET /v2/share/status`. Transporte por **repo git privado aparte** (`share_git.py`, `setup --git-url`): cada máquina publica solo su rama `machine/<id>` (commit raíz único, `push --force`) y lee las de las demás con clones superficiales; alternativa: carpeta de nube. Protocolo en `v2/docs/OPERACION.md` §3.1.",
   "effort": "alto",
   "phase": 13,
   "goal": "Que dos o más computadores (cada colaborador con su propia copia local) acumulen **una sola experiencia**: operaciones simuladas, contextos del bróker, capturas de líderes y registro de intentos de validación. Lo que haga uno debe poder verlo el otro, sin duplicar filas, sin pisar datos y sin inflar la evidencia."
  },
  {
   "id": "T62",
   "title": "Motores de IA locales: auditoría y banco de pruebas en este equipo",
   "deps": [],
   "state": "pending",
   "notes": "Especificada (`PLAN/T62.md`, insumo `PLAN/notas/T62_universo_motores.md`, 2026-10-19). Equipo de referencia: i5-8250U, 7,9 GB, MX130 2 GB (medido). ◆ qué motores entran + postura frente a YouTube.",
   "effort": "alto",
   "phase": 14,
   "goal": "Decidir con evidencia **qué motores de código abierto entran** y que corren de verdad en el equipo de referencia (i5-8250U, 7,9 GB, GPU MX130 de 2 GB): captación, ASR, escenas, OCR, visión-lenguaje, LLM de texto y embeddings. Salen una lista aprobada con licencia (código **y** pesos), versión fijada y una tabla de rendimiento medido; lo que no cabe se descarta con motivo."
  },
  {
   "id": "T63",
   "title": "Capa de motores locales: interfaces, recursos y trazabilidad",
   "deps": [
    "T62",
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 14,
   "goal": "Construir **una sola capa** (`eim/localai/`) por la que cualquier parte del proyecto use motores de IA de código abierto en local: LLM de texto, ASR, OCR, visión-lenguaje y embeddings. Es el concepto nuevo del plan: el motor es intercambiable, medible y auditable, y nunca decide por sí mismo (los LLM solo informan, `CLAUDE.md`)."
  },
  {
   "id": "T64",
   "title": "Video: vigilancia de canales, catálogo y cola de relevancia",
   "deps": [
    "T62"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 14,
   "goal": "Saber **qué videos existen, cuáles importan y en qué orden procesarlos**, sin descargar nada pesado todavía. Descubrir → clasificar → puntuar → encolar; descargar es una decisión posterior y acotada por el presupuesto de T62."
  },
  {
   "id": "T65",
   "title": "Video: transcripción con marcas de tiempo (subtítulos primero, ASR local)",
   "deps": [
    "T63",
    "T64"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 14,
   "goal": "Convertir cada video de la cola en **segmentos de texto con tiempo** recuperables (`video_id`, `t_inicio`, `t_fin`, texto, origen y calidad). Vía barata primero (subtítulos); si no existen o son malos, ASR local de T63. Es la base de toda afirmación trazable."
  },
  {
   "id": "T66",
   "title": "Video: escenas, fotogramas, OCR y lectura de gráficos",
   "deps": [
    "T63",
    "T64"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 14,
   "goal": "Extraer lo que **se ve** y no se dice: cifras en pantalla, titulares, diapositivas, y de los gráficos de precio el activo, el marco temporal, los niveles y los indicadores visibles. Cada observación lleva su fotograma, su caja en la imagen y su marca de tiempo. Se mide contra una muestra revisada a mano antes de confiar en ella."
  },
  {
   "id": "T67",
   "title": "Video: afirmaciones estructuradas y trazables",
   "deps": [
    "T63",
    "T65",
    "T66"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 14,
   "goal": "Pasar de texto y observaciones a **afirmaciones** que se pueden comprobar: qué dijo quién, cuándo, con qué evidencia y con qué condiciones. El LLM local solo **propone candidatas**; un verificador determinista acepta o descarta cada una. Sin cita verificable, no existe la afirmación."
  },
  {
   "id": "T68",
   "title": "Video: verificación contra datos reales y contradicciones",
   "deps": [
    "T67",
    "T03",
    "T36"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 14,
   "goal": "Contrastar cada afirmación con **fuentes primarias que el proyecto ya tiene** (velas, funding/OI, calendario económico) y marcar su estado. Sin LLM en este paso: la verificación es código determinista; lo que no se puede comprobar se dice «no verificable»."
  },
  {
   "id": "T69",
   "title": "Video: reputación y calibración de analistas (puerta de evidencia)",
   "deps": [
    "T68",
    "T49",
    "T64"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 14,
   "goal": "Responder con rigor: **¿algún analista de YouTube anticipa el mercado mejor que el azar?** Mismo estándar que la puerta T49: fuera de muestra, contra el azar, con corrección por múltiples comparaciones y sin premiar la popularidad ni la seguridad al hablar."
  },
  {
   "id": "T70",
   "title": "Agente video_intel: síntesis, UI y operación",
   "deps": [
    "T68",
    "T69",
    "T44",
    "T10",
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 14,
   "goal": "Poner el módulo a trabajar dentro de EIM **sin decretar su importancia**: un agente puro que resume lo que dicen los analistas vigilados, su verificación y su historial; se ve en el tablero con la evidencia hasta el segundo y el fotograma; y su peso en la síntesis lo decide la prueba marginal (T44), no una opinión."
  },
  {
   "id": "T71",
   "title": "Motores locales para el resto del sistema (medido)",
   "deps": [
    "T63",
    "T24",
    "T52"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 14,
   "goal": "Cumplir la promesa del plan — «potenciar el proyecto en su conjunto» — **solo donde se demuestre**: probar los motores locales de T63 en lo que EIM ya tiene y adoptar un cambio únicamente si iguala o mejora al método actual en una muestra etiquetada. Si no gana, se documenta y no se cambia nada."
  },
  {
   "id": "T72",
   "title": "Observatorio: decisión de piezas, contrato de eventos y catálogo",
   "deps": [],
   "state": "done",
   "notes": "**Decisión en `PLAN/notas/T72_decisiones.md` (pendiente de revisión del usuario antes de T73–T75):** Cytoscape.js (MIT, +138 KB gzip, 60 nodos medidos); el diseño «JSONL por proceso, un indexador» aguanta 2×1 000 ev/s sin líneas corruptas (indexa 20 000 en 0,35 s; dos escritores directos en DuckDB fallan); umbrales fijados en `eim/observability/thresholds.py`. Código en `v2/eim/observability/`: `events.py` (`ObsEvent`, `trace_for`), `emit.py` (`emit`/`span` sin lanzar ni bloquear, cola acotada, `EIM_OBS=off`), `redact.py`, `catalog/` (76 componentes: 17 agentes + 41 servicios + 18 planeados, con `title_es`/`explain_es`, etapas y glosario). Tests en `tests/observability/` (38); medición reproducible `v2/scripts/obs_bench.py`. Regla de proceso en `docs/NUEVO_AGENTE.md` y la skill `eim-new-agent`. Nada instrumentado todavía (T74).",
   "effort": "medio",
   "phase": 15,
   "goal": "Fijar el lenguaje común de la observabilidad **antes de instrumentar nada**, gastando en investigación solo lo que cambia la decisión: qué librería dibuja el grafo, que el diseño «los procesos escriben archivos, uno indexa» aguanta la carga, y qué componentes existen. Sale el evento normalizado, el catálogo de componentes y un emisor que no puede romper el sistema que observa."
  },
  {
   "id": "T73",
   "title": "Observatorio: indexador, almacén y API de solo lectura",
   "deps": [
    "T72"
   ],
   "state": "done",
   "notes": "`v2/eim/observability/`: `store.py` (`obs.duckdb`: components/edges versionados, events, refs, runs, decisions, spool_files), `indexer.py` (JSONL → base por *offset* en la misma transacción que los datos, idempotente por `event_id`, líneas corruptas/truncadas contadas, retención 7 d spool / 30 d eventos / 180 d runs y decisiones), `derive.py`, `bridge.py` (latidos, `op_alerts`, `risk_decisions` como eventos, solo lectura). API `eim/api/obs.py`: 7 GET `/v2/obs/*` con `source`, `asof` y retraso del propio observatorio, sin POST; arranca en `create_app` y entra en la copia diaria (`backup.py`, `extra_dbs`); T61: derivado, no viaja. Medido: 100 000 eventos se indexan en 5,7 s y toda consulta queda en p95 ≤ 32 ms (umbral 100); base de 15 MB. Umbrales nuevos en `thresholds.py` y `notas/T72_decisiones.md` §6. El catálogo marca `observability.indexer` como construido. Tests: `tests/observability/test_{indexer,bridge,obs_backup}.py`, `tests/api/test_obs_api.py`. Nada instrumentado todavía (T74). |",
   "effort": "medio",
   "phase": 15,
   "goal": "Convertir los archivos JSONL de eventos en un **registro consultable** (`obs.duckdb`) con un único indexador y exponerlo por una API de solo lectura. Guarda solo lo necesario para reconstruir *qué pasó, con qué datos y por qué*, sin duplicar los libros que ya existen."
  },
  {
   "id": "T74",
   "title": "Observatorio: instrumentación de la capa existente",
   "deps": [
    "T72"
   ],
   "state": "done",
   "notes": "**Una vela cerrada deja la traza completa** (`trace_for(símbolo, marco, cierre)`): `data_fetch` (fuente, cobertura, antigüedad) → `signal` ×17 (sesgo, confianza, estado, hash de entrada y de reporte) → `synthesis` → `forecast` → `plan` → `risk_decision` (id y sello recortado, reglas falladas) → `order_intent` → `order_sent` → `fill`, con `parent_run_id` donde hay causalidad; un agente que lanza o excede el tiempo deja su `signal` en `error` y el ciclo sigue. Ganchos en `eim/observability/hooks.py` (cadena; solo emiten dentro de una traza abierta, así backtests y consultas de la UI no producen nada) y `hooks_service.py` (latido con cadencia real, errores, descargas). Instrumentado: `agents/runner.py`, `operation/{cycle,supervisor,watchdog}.py`, `api/{live,forecast,main}.py`, `data/sync.py`, `risk/engine.py`, `execution/{gateway,service,reconcile}.py`, calendario, bróker simulado, líderes y recolector (cada proceso fija su nombre con `configure`). **Los paquetes `agents/<nombre>/` no se tocaron.** Medido: 59 eventos por ciclo (límite 100), sobrecosto dentro del ruido (<1 % de ≈1,4 s); salidas de los 17 agentes idénticas con y sin observar; ciclo idéntico con el emisor roto. `tests/conftest.py` apaga el observatorio en la suite (`EIM_OBS=off`). Tests en `tests/observability/test_instrument.py` (12). Comprobado de extremo a extremo con la API real (`create_app` + `Supervisor` + indexador de T73, 19 agentes reales): `/v2/obs/traces` lista la traza de la vela y `/v2/obs/traces/{id}` devuelve 68 eventos (22 tramos, `data_fetch`, 19 `signal`, `synthesis`, `forecast`, `plan`); con un agente `plan` de prueba la cadena llega a `risk_decision` → `order_intent` → `order_sent` → `fill` (SIMULADO). **Repetido con velas REALES de Binance (2026-10-19):** `fapi.binance.com` responde 451 desde el contenedor de desarrollo, pero `data-api.binance.vision` (spot, público) sí; con ese feed como proveedor, los 19 agentes reales produjeron un plan de verdad (largo, R:B 1,84) y `/v2/obs/traces/{id}` devolvió 70 eventos con `data_fetch` declarando la fuente `binance-spot (data-api.binance.vision)` y cobertura (1,0 en 1 h; 0,095 en el marco vecino de 15 m, que el ciclo solo sincroniza 2 días) y un `risk_decision` rechazado por «2 agentes degradados» en un directorio de datos nuevo. Con el agente `plan` de prueba sobre las mismas velas reales la cadena llegó a `risk_decision` → `order_intent` → `order_sent` → `fill` (SIMULADO, 25 eventos, resultado «ejecutada»). **Cerrado con el feed de futuros (2026-10-19):** el usuario corrió `python scripts/obs_verify_traces.py` en su equipo, con `fapi.binance.com` alcanzable: proveedor `binance-futures`, traza `tr_66850a43ff289916` (68 eventos, 22 tramos), 14 de 14 comprobaciones en OK (19/19 señales, fuente y cobertura declaradas, sin tramos sin cerrar, todo en SIMULADO). También pasó con el feed spot y dio la misma traza (el `trace_id` depende solo de símbolo, marco y cierre de la vela). Esa vela no tuvo plan vigente, así que la cadena de órdenes quedó cubierta por las pruebas con el agente `plan` de prueba, no por esta pasada. El script para repetirlo: `python scripts/obs_verify_traces.py` (desde `v2/`) la hace en un comando y da veredicto (lógica en `eim/observability/verify.py`, 5 tests). **Seguimiento (2026-10-19):** también emiten latido (muestreado a ≥ 60 s, con `detail.runs` = vueltas reales) y errores el escáner de arbitraje (`data.arb_market`), el ejecutor de arbitraje (`arbitrage.executor`, modo TESTNET), el precio en vivo (`data.live_ticks`, con caída y reconexión como eventos) y la experiencia compartida (`operation.experience_sync`); `pyproject.toml` declara `scipy` (agente `regime`) y `python-binance` en `dev` (oráculo legado), y los 2 tests legados ya pasan. 5 tests en `tests/observability/test_service_heartbeats.py`.",
   "effort": "alto",
   "phase": 15,
   "goal": "Hacer que lo que ya existe emita eventos **sin cambiar su lógica**. Al terminar, una vela cerrada deja una traza completa de datos → agentes → síntesis → plan → riesgo → (orden) y los servicios dejan latido y errores. Puede hacerse en paralelo con T73: sin el indexador, los eventos simplemente quedan en el JSONL."
  },
  {
   "id": "T75",
   "title": "Observatorio: mapa visual del flujo de trabajo (vista central, pedagógica)",
   "deps": [
    "T73",
    "T74",
    "T10"
   ],
   "state": "done",
   "notes": "**Validada por el usuario (2026-10-20).** Botón «Mapa del sistema» en `main.ts`; `web/src/obs_{view,graph,detail,story,legend,types}.ts` + `obs.css` (≤ 210 líneas c/u): nivel 1 «Ruta» (7 tarjetas con frase armada con conteos reales), nivel 2 «Etapa» (SVG propio, formas por tipo, planeado punteado, desvíos vistos/no declarados), nivel 3 panel con «En palabras simples» por plantillas sobre el último evento, glosario emergente, leyenda fija, recorrido de 5 pasos, «Ver la última vela» (solo trazas reales), pulsos en vivo, sondeo 10 s con pausa si la pestaña no se ve, «Abrir al iniciar». Estados `ok/degradado/error/obsoleto/pausado/sin datos/planeado` con icono+borde (no solo color); si el observatorio cae, todo pasa a «sin datos». API `/v2/obs/graph` ampliada (glosario, texto de etapas, modo, aristas de DATOS observadas por referencias entrada/salida y desvíos). Alertas: `observability/alert_rules/obs_alerts_v1.json` + `obs_alerts.py` (sin latido, dato obsoleto, indexador atrasado) por transición vía `op_alerts` + notificación local, llamadas desde `Supervisor.step`. **Desvío frente a T72:** el grafo es SVG propio, sin Cytoscape (0 KB añadidos; la nota T72 seguía pendiente de revisión). Verificado en el navegador: estados renderizados = respuesta de la API (0 diferencias), escritorio y tablet, claro; build OK. Hallazgo real: 5 agentes (arbitrage, bots, calendar, context, literature) alimentan la síntesis sin estar declarados en el catálogo.",
   "effort": "alto",
   "phase": 15,
   "goal": "**Es la pieza central de la Fase 15**: una vista aparte, pedagógica e ilustrada, que muestra **todo el flujo de trabajo del proyecto** —de los datos a la decisión y de ahí a la validación y el aprendizaje— y deja entender a simple vista, sin leer logs ni código, qué está pasando ahora: qué corre, qué está quieto, qué falló, qué dato está viejo y qué depende de qué. Todo lo demás de la fase (T72–T74, T76) existe para alimentarla. Debe poder leerla alguien que no programa."
  },
  {
   "id": "T76",
   "title": "Observatorio: trazabilidad de una decisión y calidad de la evidencia",
   "deps": [
    "T75",
    "T15"
   ],
   "state": "done",
   "notes": "Pestaña «Trazas y calidad» en el Mapa del sistema: selector (símbolo, marco, resultado, modo), grafo de ejecución en orden temporal con camino causal resaltado (⚑), relato por plantillas con Anterior/Siguiente, tres hechos (señal, decisión, orden), agentes frente a la síntesis y reglas de riesgo (RiskDecision real si existe). Backend: `observability/{trace_view,trace_text}.py`, `api/obs_trace.py`: `/v2/obs/traces/{id}/explain`, `/v2/obs/quality`, filtro `mode` y marca por traza (limpia / datos obsoletos / agente crítico degradado / error; el veto no contamina). Solo informa. `derive.py`: nuevo resultado «sin_plan». Verificado en navegador con trazas sintéticas de cada fallo (informe 3 de 7 = recuento manual); **falta una traza real de vela cerrada y capturas con la API real**. Enlace a la mesa vía evento `eim:replay` (T15). Tests: `tests/api/test_obs_trace_api.py` (9).",
   "effort": "medio",
   "phase": 15,
   "goal": "Elegir una vela o decisión y ver lo que realmente ocurrió —datos, señales, síntesis, plan, riesgo, orden—, con el **camino causal** resaltado cuando algo falló o se vetó. Además, marcar qué decisiones se tomaron con datos obsoletos o agentes críticos degradados, para que la evidencia de papel, del bróker (T47–T48) y de la puerta T49 se pueda leer sabiendo cuánta está contaminada. Es lo que más aporta a la eficiencia y a la fiabilidad del aprendizaje."
  },
  {
   "id": "T104",
   "title": "Microestructura: diagnóstico y puesta en marcha en vivo de lo ya construido (T23)",
   "deps": [
    "T23"
   ],
   "state": "progress",
   "notes": "Pedido del usuario 2026-10-19: la esfera «Microestructura» de la interfaz dice «sin datos» aunque el agente y el recolector existen. Causa probable: el recolector no está en el arranque continuo (ver `PLAN/T104.md`). **Es el primer paso útil de la Fase 16 y no depende de T77.** **Avance 2026-10-19:** `servicio_continuo.ps1` lanza el recolector de microestructura (BTCUSDT, sin duplicar) y el de liquidaciones en vivo (`liq_ws`); verificado 2,5 min contra Binance real (526 trades, libro top-10, agente «1/24 velas»). La esfera dice «recolector apagado» / «acumulando n/24» / «sin datos» (`web/src/no_data_label.ts`, motivo que ya devuelve el agente). **Avance 2026-10-20:** diagnóstico escrito (`PLAN/notas/T104_diagnostico.md`); vigilante `eim.data.collectors.supervise` (cerrojo, latido `data/micro/heartbeat.json`, reinicio probado en vivo matando el proceso, poda de profundidad a 30 d, avisos de disco/flujo) integrado en `servicio_continuo.ps1`; Parquet ZSTD (~493 MB/día medidos); `GET /v2/micro/status`; esfera «degradado por huecos»; tests en `tests/data/test_micro_health.py`. Pendiente (calendario): ≥ 24 h en marcha con captura de pantalla, corte de red provocado, y con ≥ 7 d la línea base `agents_marginal_report`; para supervisar el recolector ya en marcha, detenerlo y relanzar `servicio_continuo.ps1`. **Arreglo 2026-10-23:** el vigilante moría (dejando al recolector huérfano) cuando `health.disk_report` hacía `stat()` de una parte que la compactación acababa de borrar; ahora salta esas partes, y `Maintenance.tick` registra cualquier fallo de comprobación/poda (`mantenimiento_fallido` + evento de hooks, sin repetir) sin tumbar al Watchdog (Ctrl+C sigue pasando). Tests de la carrera en `tests/data/test_micro_health.py`. Requiere relanzar el vigilante en vivo para aplicarse. Sigue ◐.",
   "effort": "medio",
   "phase": 16,
   "goal": "El agente `microstructure` (T23, con su recolector, la lectura por vela y los tests) **ya existe y está registrado, pero en la interfaz su esfera dice «sin datos»** (`no_data`: «sin recolección de microestructura (colector no corre)») y el informe marginal de T44 lo muestra con 100 % de `no_data` (sin historia). Antes de construir nada nuevo hay que **hacerlo funcionar de verdad en vivo**, entender por qué no lo hacía y dejarlo como la base —y la línea base a superar— de toda la Fase 16."
  },
  {
   "id": "T77",
   "title": "HFT: viabilidad medida, hipótesis nula y decisión de alcance",
   "deps": [],
   "state": "done",
   "notes": "**◆ Nota de decisiones `PLAN/notas/T77_decisiones.md` aprobada por escrito por el usuario el 2026-10-23** (presupuesto, horizonte, alcance híbrido, criterios `hft_v1`, motor propio, Python, extra `hft`): T79–T85 desbloqueadas. Banco `v2/scripts/hft_latency.py` (+ `eim/hft/latency*.py`, `scripts/hft_client_capacity.py`): 3 × 60 min (21–23 h UTC) en `v2/reports/hft_latency.md`, reacción p99 **310 ms** (2,3 s en ráfagas de `bookTicker`), WS API 237 ms p50, Python = 8,8 % del presupuesto → sin Rust. Fuentes y repos en `PLAN/notas/T77_fuentes.md` (VIP 0 = `CostParams`, límites y filtros de BTCUSDT verificados; HftBacktest solo aislado por `numpy<2.3`; MOSAIC y quant-research sin enlace). Cota `v2/reports/hft_cost_bound.md`: por debajo de 10 s no paga ni con previsión perfecta → horizonte mínimo 30 s. Criterios `hft_v1` numéricos fijados antes de T80. Tests `tests/hft/`; BACKLOG T77. Plan y alcance aprobados por el usuario el 2026-10-19.",
   "effort": "medio",
   "phase": 16,
   "goal": "Fijar con mediciones, **antes de construir**, qué clase de HFT es viable aquí y qué se va a probar. Salen el presupuesto de latencia real, los límites y costos de Binance verificados en la fuente, la decisión sobre cada repositorio de la investigación y los criterios de éxito **escritos antes de ver resultados**."
  },
  {
   "id": "T78",
   "title": "HFT: captura profunda de mercado y calidad de datos (amplía el recolector de T23/T104)",
   "deps": [
    "T104"
   ],
   "state": "pending",
   "notes": "Tras T104 (camino crítico: T80 y T84 necesitan 14–30 días contiguos).",
   "effort": "medio",
   "phase": 16,
   "goal": "**Amplía, no reemplaza, lo ya construido** (recolector T23 puesto en marcha por T104): empezar a acumular **cuanto antes** los datos que necesitan el simulador y los modelos: libro L2 completo con doble sello de tiempo, mejores precios, operaciones, precio de referencia y liquidaciones de BTCUSDT, con control de calidad automático. Es el camino crítico real de la fase (T80 y T84 necesitan 14–30 días contiguos); no espera a T77, solo a que T104 deje el servicio vivo."
  },
  {
   "id": "T79",
   "title": "HFT: simulador de ejecución a nivel de libro (latencia, cola, fills)",
   "deps": [
    "T78",
    "T77"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 16,
   "goal": "Un simulador que reproduzca el libro evento a evento y diga **qué habría pasado con una orden**: latencia de feed y de envío, posición en cola, fills parciales, rechazos y comisiones. Es el sustituto honesto de testnet para medir ejecución (el libro de testnet no es el real). Debe ser **más pesimista que optimista** y medir su propio sesgo."
  },
  {
   "id": "T80",
   "title": "HFT: features, marco de evaluación y prueba de techo",
   "deps": [
    "T78",
    "T23"
   ],
   "state": "pending",
   "notes": "◆ ¿el techo supera los costos? Si no, se archiva antes de T81–T85.",
   "effort": "alto",
   "phase": 16,
   "goal": "Construir las variables de microestructura y un marco de evaluación sin trampas, y responder **barato y pronto** a la pregunta que decide el resto de la fase: ¿el movimiento predecible del precio supera los costos? Si no, se detiene la inversión antes de modelos y estrategias."
  },
  {
   "id": "T81",
   "title": "HFT: modelos cuantitativos de microestructura",
   "deps": [
    "T80",
    "T79"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 16,
   "goal": "Implementar y medir los modelos econométricos, estocásticos y probabilísticos del catálogo (`PLAN/notas/T77_universo_hft.md` §5) como funciones puras en `eim/hft/models/`. **Un modelo entra solo si mejora su línea base fuera de muestra** (IC 95 % y Holm); si no, queda archivado en el informe con su resultado."
  },
  {
   "id": "T82",
   "title": "HFT: estrategias (direccional, Avellaneda–Stoikov) y selector de estado",
   "deps": [
    "T79",
    "T81"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 16,
   "goal": "Convertir los modelos aprobados en estrategias que compiten bajo las mismas condiciones, y un selector determinista que decide **si conviene proveer liquidez, tomarla, esperar o no operar**. Una señal positiva no basta: la ventaja esperada neta debe superar costos y riesgo de ejecución."
  },
  {
   "id": "T83",
   "title": "HFT: riesgo y ejecución de baja latencia (veto determinista)",
   "deps": [
    "T77",
    "T30"
   ],
   "state": "pending",
   "notes": "Paralelizable con T79–T82.",
   "effort": "alto",
   "phase": 16,
   "goal": "La capa que **protege el capital e impide errores de operación** del carril HFT, independiente de la IA y de las estrategias. Puede construirse en paralelo con T79–T82: solo necesita la interfaz `Broker` y los límites verificados en T77."
  },
  {
   "id": "T84",
   "title": "HFT: torneo de estrategias y puerta de edge (hft_v1)",
   "deps": [
    "T82",
    "T83",
    "T49"
   ],
   "state": "pending",
   "notes": "◆ ¿alguna estrategia supera la validación?",
   "effort": "alto",
   "phase": 16,
   "goal": "Medir, con criterios fijados antes de mirar, si alguna estrategia tiene ventaja **neta de costos y latencia** fuera de muestra. Es el equivalente de T27/T49 para HFT y puede terminar en «ninguna pasa»: ese resultado es válido y se documenta."
  },
  {
   "id": "T85",
   "title": "Microestructura v2 (la misma esfera), servicio en vivo y paper trading",
   "deps": [
    "T84",
    "T83",
    "T31",
    "T104"
   ],
   "state": "pending",
   "notes": "◆ ¿pasa a testnet funcional? Nunca dinero real sin T31.",
   "effort": "alto",
   "phase": 16,
   "goal": "**No se crea una esfera nueva:** el agente existente `microstructure` (la esfera que hoy muestra T104) evoluciona a la versión 2 con lo aprobado en T81–T84. Poner el agente en el sistema y comprobarlo **en vivo con datos reales y órdenes simuladas** durante semanas. El agente de ciclo de vela informa el estado microestructural; el servicio rápido, en proceso aparte, ejecuta el ciclo libro → features → modelos → estrategia → riesgo → bróker simulado. Solo corre lo que T84 dejó pasar."
  },
  {
   "id": "T86",
   "title": "HFT: integración (síntesis, capital, interfaz, Observatorio)",
   "deps": [
    "T85",
    "T44",
    "T10",
    "T72"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 16,
   "goal": "Que el agente de microestructura (v2 de la esfera existente) y su servicio HFT sean ciudadanos completos del sistema: visible, trazable, con su propio cupo de capital y documentado, mostrando siempre el modo (Análisis, Simulado o Testnet) y la evidencia de la puerta T84."
  },
  {
   "id": "T87",
   "title": "Multiactivo: auditoría de acoplamientos, medición y decisión de alcance",
   "deps": [],
   "state": "pending",
   "notes": "Especificada (`PLAN/T87.md`, insumo `PLAN/notas/T87_universo_multiactivo.md`, 2026-10-19). Auditoría rápida ya hecha en la nota (17 agentes: 10 solo `candles`; acoplamientos a cripto localizados). ◆ alcance, horizontes, datos, orden de clases.",
   "effort": "medio",
   "phase": 17,
   "goal": "Convertir la auditoría rápida de `PLAN/notas/T87_universo_multiactivo.md` en una **matriz de reutilización completa** (qué se conserva, qué se adapta, qué es específico de cripto) con el costo real de cada agente, y fijar el alcance con el usuario antes de tocar código. Sin cambios en `eim/`."
  },
  {
   "id": "T88",
   "title": "Multiactivo: auditoría de repositorios y de proveedores de datos",
   "deps": [],
   "state": "pending",
   "notes": "◆ qué repos y proveedores entran (licencia y condiciones de uso verificadas en la fuente).",
   "effort": "medio",
   "phase": 17,
   "goal": "Verificar en la fuente lo que la investigación del usuario **declara** (licencia, mantenimiento, pruebas, compatibilidad) y decidir qué repositorios y proveedores entran, con qué rol y con qué límites. Los datos son la mitad del riesgo: sin una fuente con licencia clara no hay clase de activos."
  },
  {
   "id": "T89",
   "title": "Registro universal de instrumentos y calendarios",
   "deps": [
    "T87"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 17,
   "goal": "Un catálogo único donde cada instrumento tiene identidad estable, clase, estructura de mercado, reglas contractuales y datos disponibles, de modo que ningún módulo nuevo vuelva a codificar «BTCUSDT». Compatible hacia atrás: el símbolo cripto de hoy sigue siendo un identificador válido."
  },
  {
   "id": "T90",
   "title": "Contratos de datos multifuente, almacén y calidad",
   "deps": [
    "T89"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 17,
   "goal": "Hacer que el almacén y los proveedores hablen de instrumentos y no de símbolos de Binance, con calidad y procedencia por dato: huecos que entienden calendarios, precios ajustados frente a crudos, marcos diario y semanal, y licencia/uso por fuente. Sin esto no hay clase nueva que pueda validarse."
  },
  {
   "id": "T91",
   "title": "Agentes: capacidades declaradas, elegibilidad y supuestos de tiempo",
   "deps": [
    "T87",
    "T89"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 17,
   "goal": "Que cada agente declare **a qué instrumentos, marcos y datos aplica** y que el sistema decida su elegibilidad con una razón escrita, y que los diez agentes de velas funcionen en mercados con sesiones y sin volumen real **sin cambiar ni un resultado en BTC/ETH**."
  },
  {
   "id": "T92",
   "title": "Costos, margen y simulación por clase de activo",
   "deps": [
    "T89"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 17,
   "goal": "Generalizar el modelo de perpetuos (comisión, funding, liquidación aislada, apalancamiento entero) a un **modelo de costos y de márgenes por clase**, de modo que backtest, bróker simulado y riesgo valoren una operación en acciones, FX o futuros con sus reglas reales. Es lo que decide si una «oportunidad» sobrevive a los costos."
  },
  {
   "id": "T93",
   "title": "Escáner global (1/2): universo, embudo, cola y caché",
   "deps": [
    "T89",
    "T90",
    "T91"
   ],
   "state": "pending",
   "notes": "Primer universo: todos los perpetuos USDⓈ-M de Binance (sin licencias nuevas).",
   "effort": "alto",
   "phase": 17,
   "goal": "La infraestructura que permite mirar miles de instrumentos con un presupuesto de cómputo medido: descubrir el universo, filtrarlo, calcular una puntuación barata y vectorizada de todo el universo y entregar solo una lista corta a los agentes profundos. **Sin ejecutar órdenes.** Se prueba primero con el universo completo de perpetuos de Binance."
  },
  {
   "id": "T94",
   "title": "Escáner global (2/2): agentes sobre el universo, oportunidades trazables, API y panel",
   "deps": [
    "T93"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 17,
   "goal": "Conectar la lista corta de T93 con los agentes **elegibles** de cada instrumento y producir **oportunidades candidatas trazables** (nunca órdenes), visibles en la API y en una pestaña, con el modo siempre a la vista."
  },
  {
   "id": "T95",
   "title": "Ranking global y control de multiplicidad (placebo, Holm/FDR)",
   "deps": [
    "T94",
    "T49"
   ],
   "state": "pending",
   "notes": "◆ ¿el escáner muestra algo que supere el azar?",
   "effort": "alto",
   "phase": 17,
   "goal": "Hacer comparables oportunidades de instrumentos, horizontes y clases distintos **y** medir cuántas serían falsos descubrimientos por azar. Escanear miles de instrumentos con 17 agentes es una máquina de generar hipótesis: sin este control el panel mostraría ruido con buena presentación (T27 y T49 ya dijeron que en BTC/ETH no hay edge validado)."
  },
  {
   "id": "T96",
   "title": "Cartera y riesgo transversal multiactivo",
   "deps": [
    "T92",
    "T95"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 17,
   "goal": "Pasar de oportunidades sueltas a una **cartera simulada** con exposición, correlación, concentración, margen y moneda controlados por un componente determinista con poder de veto, independiente de los agentes. Solo simulación."
  },
  {
   "id": "T97",
   "title": "Clase: renta variable (acciones, ETF e índices)",
   "deps": [
    "T90",
    "T91",
    "T92",
    "T93"
   ],
   "state": "pending",
   "notes": "◆ ¿la clase sigue? Molde de la lista de aceptación.",
   "effort": "alto",
   "phase": 17,
   "goal": "Llevar la primera clase fuera de cripto de punta a punta y comprobar **toda** la lista de aceptación por clase (descubrimiento, datos, agentes, backtesting, riesgo, ejecución simulada, observabilidad, validación). Sirve de molde para las demás clases."
  },
  {
   "id": "T98",
   "title": "Clase: divisas (FX)",
   "deps": [
    "T97"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 17,
   "goal": "Incorporar pares de divisas respetando que el mercado es OTC, 24/5, sin volumen central y con costos de swap, y completar la lista de aceptación por clase."
  },
  {
   "id": "T99",
   "title": "Clase: materias primas y futuros tradicionales",
   "deps": [
    "T97"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 17,
   "goal": "Incorporar futuros con vencimiento (energía, metales, agrícolas, índices, tasas) y sus particularidades — curva, contango/backwardation, roll, estacionalidad natural — y completar la lista de aceptación por clase."
  },
  {
   "id": "T100",
   "title": "Renta fija, derivados y opciones: viabilidad y modelos propios",
   "deps": [
    "T88",
    "T92"
   ],
   "state": "pending",
   "notes": "◆ qué producto merece su propia clase.",
   "effort": "medio",
   "phase": 17,
   "goal": "Decidir con evidencia si bonos, repos, operaciones de financiación y opciones se pueden cubrir y cómo. **No basta aplicar indicadores técnicos a sus precios**: requieren curvas, duración, convexidad, carry/roll-down, cadenas de opciones, volatilidad implícita y griegas. Esta tarea produce especificación y prototipo mínimo, no una clase completa."
  },
  {
   "id": "T101",
   "title": "Validación multiactivo: matriz agente × clase",
   "deps": [
    "T95",
    "T97"
   ],
   "state": "pending",
   "notes": "◆ qué celdas se publican (probable: pocas o ninguna).",
   "effort": "alto",
   "phase": 17,
   "goal": "Responder con evidencia **dónde funciona cada agente y dónde no**: una puerta de validación a escala de universo que cuenta todas las hipótesis y publica solo los pares (agente, clase, horizonte) que la superan. El resultado más probable, a la vista de T27 y T49, es «pocos o ninguno»; debe decirse tal cual."
  },
  {
   "id": "T102",
   "title": "Observabilidad y despliegue gradual multiactivo",
   "deps": [
    "T94",
    "T72"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 17,
   "goal": "Que cada instrumento, dato, agente, oportunidad y decisión sea rastreable de punta a punta y que el paso de «alerta» a «simulación» y a «papel» siga un protocolo escrito. El sistema debe poder decir en cualquier momento qué mercados vigila, con qué datos y qué no puede ver."
  },
  {
   "id": "T103",
   "title": "Ejecución multiactivo: adaptador de papel y decisión de intermediario",
   "deps": [
    "T96",
    "T101",
    "T31"
   ],
   "state": "pending",
   "notes": "◆ intermediario; solo papel, nunca dinero real.",
   "effort": "alto",
   "phase": 17,
   "goal": "Dar al sistema un camino de ejecución **solo en cuenta de papel/simulada** para las clases que superen la puerta, sin tocar nunca dinero real. Verifica que el contrato de órdenes, la reconciliación y el riesgo funcionan con acciones, FX o futuros reales de un intermediario."
  },
  {
   "id": "T105",
   "title": "Cuarto perfil: Progressive Profit Protection — BTCUSDT (SL dinámico por escalones)",
   "deps": [
    "T47",
    "T48",
    "T49"
   ],
   "state": "done",
   "notes": "Perfil `ppp_btcusdt` (2026-10-20): SL inicial por riesgo, protección desde +10 USDT netos y escalones de +5, sin TP ni cierre por tiempo, solo BTCUSDT y simulado. Código `eim/paper/{ladder,ladder_book,ladder_audit,ladder_stats,strategies_ppp}.py` + `params.py`; UI `web/src/paper_*.ts` (compila con tsc, **sin captura visual**); doc `v2/docs/PPP.md`; tests `tests/paper/test_ladder*.py`, `test_strategies_ppp.py` (18 escenarios). Incluye reservas de deslizamiento/funding en el SL, aprendizaje propio, freno de entradas, **velas de 1 min para las velas ambiguas de 15 m** (el servicio sincroniza 1 m), **entrada propia `ppp_tendencia`** (familia `ppp`) y **funding real** en el backtest. **Backtest 40 días (`reports/ppp_backtest.md`): NO rentable** (−537 USDT, PF 0,54, 86 ops, 0 violaciones, 0 funding supuesto; fuera de muestra peor y ninguna variante de la rejilla positiva). Entradas propias: solo 9 operaciones (+31 USDT), muestra insuficiente. Pendiente: acumular meses y pasar `ppp_tendencia` por T49; captura visual de la UI.",
   "effort": "alto",
   "phase": 18,
   "goal": "Un perfil simulado más, **independiente de Conservador/Moderado/Agresivo y integrado en el mismo flujo** (ideas de las estrategias → libro → resumen → API → pestañas de la mesa). Su diferencia: **sin TP final ni cierre por tiempo**. SL inicial por riesgo; al llegar a +10 USDT netos se activa la protección y cada +5 USDT de beneficio máximo sube un escalón (10, 15, 20, …). Solo cierra el SL vigente; la protección nunca retrocede ni vuelve a la entrada. Solo BTCUSDT, solo simulado (el modelo rechaza `real_money`, `time_exit` y `fixed_take_profit`)."
  },
  {
   "id": "T106",
   "title": "Auditoría de salidas, contabilidad y métricas de los tres perfiles",
   "deps": [
    "T105"
   ],
   "state": "done",
   "notes": "Informe `PLAN/notas/T106_auditoria_salidas.md` (2026-10-21, solo lectura). Toda vía de cierre inventariada con archivo y línea (SL, SL en la vela del llenado, TP, BE+, TIEMPO, GEOMETRIA, NO_LLENADA, OBJETIVO_SIN_LLENAR, SL/SLD de la escalera) y **probado que nadie más cierra**: los topes y frenos (`caps`, `LadderRisk`) solo vetan entradas, no hay POST de cierre y el capital se muta en un único sitio (`book.py:226`). Cifras del panel: las filas del Moderado y del Agresivo son **imposibles** en un mismo render (mezclan `balance` con `return_pct`, que usa `equity`); el DD de 1204 % exige capital ≈ −110.400 USDT porque no hay liquidación ni suelo (reproducido: 299,70 % de DD con 3 operaciones); las 19.132 operaciones **no caben** en este almacén (techo 4.856 cierres) y la vista no guarda instantánea, así que no es auditable. Confirmado: los costos ya están dentro del PnL y no existe ninguna recarga de capital. Tests que fijan el defecto: `tests/paper/test_accounting_audit.py` (6). Seis ◆ respondidas por el usuario el 2026-10-21: **◆1 cambia el alcance** (la salida la elegiría el orquestador de forma dinámica → T113/T114), ◆2 BTC y ETH (exige 1 m de ETH y tick/paso por símbolo), ◆3 conservar BE+ y escalones, ◆4 sí, ◆5 conservar `ppp_btcusdt` como control, ◆6 umbral en R.",
   "effort": "medio",
   "phase": 18,
   "goal": "Antes de llevar la protección progresiva (ya construida en T105 para el 4.º perfil `ppp_btcusdt`) a **Conservador, Moderado y Agresivo**, dejar escrito qué cierra hoy una operación, quién puede cerrarla y **si las cifras del panel son correctas** (el Agresivo muestra un drawdown de 1204 %, imposible salvo con capital negativo). Sin esta auditoría la comparación «antes/después» de T111 no significaría nada: podría atribuirse a la escalera una mejora que en realidad arregla la contabilidad."
  },
  {
   "id": "T107",
   "title": "Contabilidad honesta del capital: liquidación simulada, equity y drawdown",
   "deps": [
    "T106"
   ],
   "state": "done",
   "notes": "Margen aislado de verdad (2026-10-22): ninguna posición pierde más que su margen, así que el capital no puede quedar negativo ni el drawdown pasar del 100 %. Si el precio atraviesa la liquidación (hueco que deja el stop atrás) la posición se cierra con motivo propio `LIQUIDACION` y pierde el margen entero; con el capital realizado ≤ 1 % del inicial el perfil queda **agotado** (deja de abrir, mantiene lo abierto, **sin recargas**). Una sola definición de cada cifra (`balance` realizado · `equity = balance + upnl` · `return_pct` siempre sobre equity, declarado en `return_base`), drawdown con base y ventana declaradas (`dd`) y recuento con origen, ventana y alcance (`counts`, incluido el aviso de T61). Arreglado de paso el agujero A5 de T106: un cierre que viola las reglas de la escalera se sigue auditando pero su PnL **ya se contabiliza** (antes el dinero desaparecía). Código `eim/paper/account.py` (nuevo) + `vetoes.py` (nuevo, sale de `book.py`), `book.py`, `summary.py`, `params.py` (`min_equity_frac`), `api/paper.py` (categorías `liquidacion` y `cuenta`); UI `web/src/paper_{head,profiles,tables,journal,fmt,types}.ts` + `paper.css` (tsc limpio, **sin captura visual**). Tests `tests/paper/test_account.py` (9) y los de T106 actualizados al comportamiento correcto. Medido: con el almacén de hoy **ninguna** de las 157 operaciones cerradas se habría liquidado (peor pérdida 25,4 % de su margen), así que **ninguna cifra del panel cambia**; el caso de T106 pasa de −19.970 USDT y 299,70 % de DD a 7.000 USDT y 30 %. Nota de cierre: `PLAN/notas/T107_contabilidad.md`. Pendiente: instantánea auditable de la vista (A4).",
   "effort": "medio",
   "phase": 18,
   "goal": "Que las cifras de los tres perfiles sean creíbles antes de comparar reglas de salida. Hoy el libro resta el PnL del capital sin suelo: si un perfil pierde más de lo que tiene, la curva se vuelve negativa y el drawdown pasa del 100 % (el Agresivo muestra 1204 %). Un perfil simulado debe **liquidarse como una cuenta real**, no seguir operando con capital imposible."
  },
  {
   "id": "T108",
   "title": "Protección progresiva por perfil: parámetros centralizados y validados",
   "deps": [
    "T106"
   ],
   "state": "done",
   "notes": "Escalera por perfil en un solo sitio (2026-10-22): `LADDER_BY_PROFILE` en `params.py` da a Conservador, Moderado y Agresivo sus umbrales **en R** (◆6 de T106: 0,100/0,050 · 0,100/0,050 · 0,075/0,0375 R), que con el capital inicial son exactamente los +5/2,5 · +10/5 · +15/7,5 USDT del encargo; `LadderParams.steps(riesgo)` los resuelve por operación y `basis` distingue R de USDT fijos, así que el control `ppp_btcusdt` (◆5) no cambia ni un número (sus 40 tests dan lo mismo). Ficha de instrumento por símbolo (A6): `SymbolSpec`/`SYMBOL_SPECS` con tick, paso y mínimo reales de `fapi/v1/exchangeInfo` (BTCUSDT 0,1/0,001/0,001 · ETHUSDT 0,01/0,001/0,001); `simulate_ladder` exige la ficha por nombre y `open_ladder` rechaza por debajo del mínimo negociable. Validación ruidosa al arrancar: `check_profiles` en `PaperDesk.__init__` (API y servicio) + validadores de `LadderParams`/`ProfileParams`/`SymbolSpec`: umbral o incremento no positivo, escalera sin parámetros, símbolo sin ficha o identificador repetido impiden arrancar con el motivo exacto. Efecto colateral buscado (◆2): el servicio ya sincroniza 1 min también de ETHUSDT. **Lo que NO hace**: los tres perfiles siguen con `exit_mode=\"tp\"` (salen por TP/BE/tiempo) y `be_with_ladder=True` solo **declara** la convivencia BE+/escalones de ◆3; encender la escalera y la precedencia de stops es T109, por eso ningún trade ni evento de los tres perfiles cambia hoy. Código `eim/paper/{params,ladder,ladder_book,ladder_stats,summary,desk}.py`; doc `v2/docs/PPP.md` §2.1–2.2; tests `tests/paper/test_ladder_profiles.py` (28: casos L y M, fichas por símbolo, 1 min de ETH) + `test_ladder.py` adaptado. Gate verde (ruff limpio, suite completa exit 0).",
   "effort": "medio",
   "phase": 18,
   "goal": "Dar a Conservador, Moderado y Agresivo **su propia** configuración de protección progresiva, en un solo módulo, validada al arrancar, y con las especificaciones del instrumento (tick y paso de cantidad) tomadas del símbolo en vez de las constantes de BTCUSDT que hoy trae `LadderParams`."
  },
  {
   "id": "T109",
   "title": "Motor: en los tres perfiles solo cierra el stop (inicial o dinámico)",
   "deps": [
    "T108",
    "T107"
   ],
   "state": "done",
   "notes": "Los cuatro perfiles salen solo por su stop (2026-10-22): Conservador, Moderado y Agresivo pasan a `exit_mode=\"ladder\"` (sin TP fijo ni cierre por tiempo; el objetivo queda como estimación de los filtros de entrada). Solo cierran `SL`, `SLD` (escalón o BE+: el mejor de los dos, nunca retrocede, ◆3), `LIQUIDACION` y `SALVAGUARDA`, contados aparte en `ladder.exits`; cualquier otro cierre es violación **y no se ejecuta** (`book._reject`), la incidencia deja la posición abierta y las señales contrarias solo informan (`against`). Aprenden de sus propios cierres con peso ≤ 1,5 (`max_weight`); el veto «una por vela» y el freno propio quedan solo en el control, así que sus entradas no cambian. Código `eim/paper/{book,ladder,ladder_audit,ladder_book,ladder_stats,summary,vetoes,params}.py` + `ladder_math.py`/`ladder_params.py` (nuevos, por el límite de 300 líneas); tests `tests/paper/test_ladder_stop_only*.py` (79: casos A–G, I, J, K × 3 perfiles × largo/corto, y libro) y los de mecánica TP fijados con `tp_mode`; doc `v2/docs/PPP.md` §2.3. Corrida de 32 días BTC+ETH (`v2/reports/t109_stop_only.md`): 0 cierres por TP/tiempo, 0 violaciones, el BE+ nunca cerró; `ppp_btcusdt` idéntico a `main` (73 ops) y el modo `tp` idéntico a T108. Con escalera el Agresivo perdió más en ese periodo (lo mide T111) y hay un sesgo de deslizamiento de entrada anotado en BACKLOG.",
   "effort": "alto",
   "phase": 18,
   "goal": "Llevar los tres perfiles al mismo camino de salida que ya usa el 4.º: **sin take profit fijo y sin cierre por tiempo**. Antes del primer umbral manda el stop inicial; a partir de ahí manda el stop dinámico, que sube de escalón y **nunca retrocede**. Ninguna otra cosa cierra una operación de la estrategia."
  },
  {
   "id": "T110",
   "title": "Persistencia y recuperación del estado de protección",
   "deps": [
    "T109"
   ],
   "state": "done",
   "notes": "El escalón sobrevive a un reinicio y nunca baja (2026-10-22). **Diario** `paper_protection` en `data/paper.duckdb` (solo adición, clave `perfil|símbolo|idea|seq`, la fila de mayor `seq` es la vigente): alta, una fila por cada cambio del stop y cierre, con entrada, cantidad, umbral e incremento, máximo neto, escalón, SL vigente, costos y reservas, estado, historial del stop y motivo de cierre; `paper_protection_pass` recuerda qué dejó abierto cada pasada. **Recuperación**: el diario se lee ANTES de recalcular y su estado entra como suelo del SL (`ladder_floor.py`): si el recálculo da menos se adopta el guardado (fila `recuperacion`, aviso `warn`); al arrancar, si va por delante se adopta el recálculo (aviso `info`); salvaguarda `_never_lower`. **Estado inconsistente** (instantánea ausente o corrupta, símbolo/identidad que no cuadran, cierre recalculado anterior a lo guardado, velas que no llegan, operación desaparecida): no se cierra sola ni mueve su stop por lo guardado, se congela su diario, cuenta en `/v2/paper` (`protection`, `profiles[].protection.inconsistent`) y alerta crítica en `op_alerts`; CLI `python -m eim.paper proteccion lista|historial|reconciliar`. Observatorio: evento `alert` de `paper.broker` por fila y recuperación, una traza por operación. API `GET /v2/paper/protection[/history]`, `POST …/resolve` (`X-EIM-Confirm`). Código `eim/paper/{ladder_floor,protection,protection_sync,protection_desk,protection_cli}.py` + `ladder,ladder_book,ladder_audit,book,desk`; tests `tests/paper/test_protection*.py` (19: caso H, menor/mayor, corrupta/ausente/ajena, cierre anterior, historial completo, avisos, CLI) + ruta en `test_paper_api.py`; doc `docs/PPP.md` §5, `RUNBOOK.md` §14. **Reinicio real** (API de la rama sobre datos sintéticos, puerto 8011, la API en vivo intacta): escalón 1 / SL 69 646,4 antes y después, 0 filas nuevas; con parámetros ×3 el recálculo daba SL 67 979,2 y la API devolvió 69 646,4 (`v2/reports/t110_reinicio.md`). Revisión `code-review high`: 6 arreglos; pendientes de diseño en BACKLOG T110. Gate verde.",
   "effort": "medio",
   "phase": 18,
   "goal": "Que una posición abierta con protección activa **no pierda su escalón** si se reinicia la API o el servicio de papel. Hoy el libro se recalcula en cada consulta y solo los cierres en vivo se guardan (`ledger.py`): el estado de lo abierto (escalón, máximo alcanzado, stop vigente, historial de cambios) no se persiste en ninguna parte."
  },
  {
   "id": "T111",
   "title": "Métricas, comparación antes/después y decisión de adopción",
   "deps": [
    "T107",
    "T109",
    "T110",
    "T49"
   ],
   "state": "done",
   "notes": "A/B reproducible (2026-10-23) en `v2/reports/ppp_profiles_ab.md` (+ `.json`, `.csv` por operación): `scripts/ppp_profiles_ab.py` sobre una copia del almacén vivo, mismas ideas, camino, costos y motor; A = TP/BE+/tiempo, B = escalera del encargo y sensibilidad 0,5 R y 1 R; emparejado (las entradas de A con la salida B: aísla la salida) y libro completo; fuera de muestra = decisiones antes de 2026-08-16 (3,6 años de 1 h) con velas de 1 min reales (sincronizadas en la copia); condiciones de mercado por día y régimen ex ante; criterios de T49 tal cual (estricto: 0 ops fuera de muestra → EN OBSERVACIÓN; informativo: RECHAZADA lo que tiene muestra). **Resultado: la escalera NO mejora a ningún perfil fuera de muestra** (emparejado, encargo: Conservador −2.993 frente a −2.919 USDT, Moderado −7.458 frente a −4.474, Agresivo −13.411 frente a −9.325; corta las ganadoras de +1,6 R a ≈ +0,1 R) y ningún escenario es rentable. **◆ Decisión del usuario (2026-10-23): adoptar en los tres perfiles** (sin cambio de código). Antes del A/B se corrigió el deslizamiento de entrada de la escalera (BACKLOG T109 (1)). Código `eim/paper/{ladder_metrics,ab_pairs,ab_conditions,ab_gate}.py`, `ladder.py`, `book.py` (riesgo y MFE/MAE en la operación), `validation/evidence.py` (`ref_price` compartido); tests `tests/paper/test_ab_compare.py` (8); doc `v2/docs/PPP.md` §12; BACKLOG T111. Gate verde.",
   "effort": "alto",
   "phase": 18,
   "goal": "Medir si la protección progresiva mejora de verdad los tres perfiles, aislando su efecto de todo lo demás, y **decidir con el usuario** si se adopta, se adopta solo donde mejora, o se archiva. La hipótesis de partida es la misma que en T27: **no mejora** hasta que los datos lo demuestren."
  },
  {
   "id": "T112",
   "title": "Panel: estado de la protección por perfil (con captura)",
   "deps": [
    "T109"
   ],
   "state": "done",
   "notes": "Bloque «Protección por perfil» en la pestaña «Perfiles» (2026-10-23, `web/src/paper_protect.ts`; el detalle anterior queda plegado y ya muestra los umbrales reales en R, no los 10/5 USDT fijos): por perfil, umbral e incremento (USDT de referencia + fracción de R), abiertas con protección activa, último escalón alcanzado, cierres por motivo, incidencias, fuera de regla y violaciones; por operación abierta, estado, nivel protegido (o lo que falta), stop vigente, máximo y flotante neto «no realizado» y **neto estimado si salta el stop** con su advertencia (hueco, deslizamiento, latencia). Estados con color y glifo propios: stop inicial · protección inactiva (a favor, bajo el umbral) · protección activa · cerrada por stop inicial · cerrada por stop dinámico; aparte liquidación, salvaguarda e incidencia técnica (incl. `inconsistente` de T110). Violaciones en aviso rojo (bloque y Bitácora, con «Ver solo violaciones»); Bitácora con el motivo de cierre delante (antes lo tapaba un texto genérico) e Historial con el estado de cada cierre; modo y «dinero real deshabilitado» visibles. Backend mínimo: `ladder.stop_est_usd` (abiertas), `ladder.last_step` y `ladder.violations_recent` en el resumen, `reason` en los eventos de cierre y texto «nivel protegido … estimado» (`eim/paper/{ladder,ladder_stats,summary,book}.py`); tests `tests/paper/test_protection_panel.py` (15); doc `v2/docs/PPP.md` §6.1. Capturas en `v2/reports/t112/` (tema único de T122, sin claro/oscuro): bloque por perfil e Historial con datos reales comparados por script con la API en vivo; los estados de abiertas y las violaciones con datos SINTÉTICOS rotulados (la mesa no tenía abiertas ni violaciones). `npm run build` y gate verdes. Pendiente: desplegar (reiniciar la API en vivo, con permiso) y BACKLOG T112.",
   "effort": "medio",
   "phase": 18,
   "goal": "Que la mesa muestre, para cada perfil, en qué estado está la protección de cada operación, sin presentar nunca el beneficio protegido como si ya estuviera ganado. T105 dejó la interfaz del 4.º perfil compilando pero **sin captura visual**: aquí se cierra esa deuda y se extiende a los tres perfiles."
  },
  {
   "id": "T113",
   "title": "Auditoría de orquestadores multiagente de inversión",
   "deps": [],
   "state": "done",
   "notes": "Informe `PLAN/notas/T113_auditoria_orquestadores.md` (2026-10-23, solo lectura; clones aislados en `C:\\t113clones`, nada instalado): 7 candidatos nuevos y 4 reevaluaciones con licencia, actividad, pruebas, red, secretos, orquestador y ejecución. **Hipótesis confirmada: no falta nada esencial**: el contraste pieza por pieza (síntesis, estado, evaluación, riesgo, ejecución, traza) no encuentra nada que EIM no tenga; solo P1 (sensibilidad al calentamiento, BACKLOG) y P2 (insumo de T114). 🚩 `hotbridgeLab/future-trading-ai-agent` es un señuelo de malware (dependencia npm `oracle-redis` que suplanta ioredis y arrastra paquetes retirados por npm); LynchzDEV deja que el LLM envíe órdenes reales; AI Hedge Fund también usa TypeSafe (no lo anotó T56). Alertas de T04/T56 reconfirmadas. **◆ del usuario (2026-10-23): no adoptar nada**; descartados hotbridgeLab, LynchzDEV, gucky25 y Tomortec; P1 solo a BACKLOG. Pendientes en BACKLOG T113. Gate verde.",
   "effort": "medio",
   "phase": 19,
   "goal": "Cerrar la pregunta de fondo de las investigaciones del usuario sobre «agentes orquestadores de otros agentes»: **¿hay algo en esos proyectos que el coordinador propio (síntesis T20/T44 + riesgo T29 + trazabilidad T72–T76) no cubra ya?** El proyecto no necesita más bots que repiten indicadores; necesita saber si falta un patrón de coordinación, de estado o de evaluación. Hipótesis de partida: **no falta nada esencial**; la auditoría debe demostrar lo contrario con evidencia."
  },
  {
   "id": "T114",
   "title": "Propuesta única y autoridad determinista: nadie salta el riesgo",
   "deps": [
    "T113"
   ],
   "state": "done",
   "notes": "Una puerta y un contrato para toda fuente (2026-10-23): `TradeProposal` y `RiskDecision` en `eim/core/authority.py` (el de T29, traído y ampliado: propuesta, autoridad, versión del perfil y salida concedida; `risk/models.py` lo reexporta). Registro de fuentes y reglas comunes en `eim/risk/authority.py` (`fuente` registrada, activa, no LLM y con esa autoridad; `propuesta` = plan; `caducidad`), que corren el motor T29 (`agents.plan`, `copy.leaders`, `ops.smoke`), el del arbitraje (`arb.scanner`) y la política del bróker simulado, extraída tal cual a `eim/paper/policy.py` (`paper.strategies`: el hueco de T113); `OrderGateway`, `ArbGateway` y `book._open` vuelven a verificar la ruta; `bots.squad` y `agents.context` (LLM) solo informan; T85/T70 planeadas. Proyecciones `PlanRequest`/`Idea`/`BotSignal`/`ArbPlan.as_proposal`; una copia ignora señales de otro líder. Observatorio: `risk_decision` con fuente, versión, datos usados (`proposal`, `data`) y autoridad; el bróker emite sus decisiones en vivo con su traza (`paper/authority_obs.py`, `event_id` determinista). Pruebas `tests/architecture/` (rutas reales con y sin registro, inventario AST de primitivas, ningún LLM alcanzable ni llamado, señal contraria en todas las fuentes) + `tests/core/test_authority_contract.py` + `tests/observability/test_authority_e2e.py`; atajo a propósito detectado y revertido (commits `22f7225`/`b8a49e5`). Doc `v2/docs/ARQUITECTURA.md` «Autoridad de ejecución», `PLAN/CONTRATOS.md`; revisión `code-review high`: 7 arreglos; BACKLOG T114. Gate verde. Pendiente: desplegar (reiniciar la API en vivo, con permiso).",
   "effort": "alto",
   "phase": 19,
   "goal": "Una sola puerta de entrada a la ejecución, con un contrato único: **toda** fuente de señal (agentes, estrategias del bróker, bots de T57, copy trading de T41, arbitraje de T39, HFT de T85, video de T70) propone en el mismo formato, y solo el motor determinista de riesgo autoriza. El consenso de diez agentes no puede anular un límite, y ninguna regla de salida vigente puede ser anulada por una señal contraria. Hoy esto es cierto por construcción en varios caminos, pero **no está demostrado en un solo lugar**."
  },
  {
   "id": "T115",
   "title": "Copia de seguridad completa: las tres bases y restauración probada",
   "deps": [
    "T32",
    "T61"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 20,
   "goal": "Que una copia de seguridad contenga **todo el historial**, no solo los reportes. Hoy `backup create` copia `reports.duckdb` (y `obs.duckdb`, derivado) y deja fuera `paper.duckdb` (contextos del bróker simulado, operaciones y el registro inmutable de sugerencias de T51) y `leaders.duckdb` (capturas en vivo irrepetibles). Restaurar desde `backups/` recupera los reportes y pierde lo demás: ver `PLAN/notas/DIAGNOSTICO_ESTABILIDAD_2026-10-22.md` §A."
  },
  {
   "id": "T116",
   "title": "Gate estable y reproducible en cualquier equipo",
   "deps": [
    "T72",
    "T73"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 20,
   "goal": "Que `python -m ruff check eim tests && python -m pytest -q` dé el mismo resultado en el equipo del usuario, en el del colaborador y con el equipo cargado. Hoy no: la prueba de rendimiento del observatorio falla por milisegundos y la suite completa puede tardar más de 25 minutos con Ollama y los recolectores activos (`PLAN/notas/DIAGNOSTICO_ESTABILIDAD_2026-10-22.md` §B). Un gate que falla por el equipo enseña a ignorarlo."
  },
  {
   "id": "T117",
   "title": "Primera mezcla real de la experiencia compartida (cierra ◆ T61)",
   "deps": [
    "T61",
    "T115"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 20,
   "goal": "Estrenar T61 con **dos equipos de verdad** (el del usuario y el del segundo colaborador) y dejar el informe que el usuario tiene pendiente de revisar (◆ de T61). Hasta ahora todo se probó sin red, con fixtures. Mientras no se haga, cada equipo acumula historial en paralelo sin que el otro lo vea."
  },
  {
   "id": "T118",
   "title": "Cifras auditables del bróker simulado (instantánea y motivos reales)",
   "deps": [
    "T107",
    "T106"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 20,
   "goal": "Que una cifra que se vio ayer se pueda volver a ver hoy. Hoy el panel se recalcula desde **todo** el almacén en cada consulta y el capital se re-simula desde 10 000 USDT, así que una captura pasada no es auditable (alerta A4 de `T106_auditoria_salidas.md`, pendiente (1) de `T107_contabilidad.md`), y con capital ≤ 0 el motivo de rechazo que se registra no es el real (`v2/eim/paper/book.py:168-169`). Con dos colaboradores mirando el mismo panel desde equipos distintos, esto deja de ser un detalle."
  },
  {
   "id": "T119",
   "title": "Puntuación del escuadrón de bots verificada en la base real",
   "deps": [
    "T59",
    "T60"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 20,
   "goal": "Que lo que dice la interfaz sobre los bots sea lo mismo que dice el informe. El recálculo dentro de la API cayó por memoria y se arregló (`query_lean`, topes de DuckDB) **midiendo con 105 000 posturas sintéticas**, porque la API viva tiene `reports.duckdb` bloqueada; `GET /v2/bots/scorecard` puede seguir mostrando la medición anterior mientras la buena vive en `v2/reports/bots_scorecard.md` (`PLAN/notas/DIAGNOSTICO_ESTABILIDAD_2026-10-22.md` §D). Hasta comprobarlo, el escuadrón vota (o calla) según cifras no verificadas."
  },
  {
   "id": "T120",
   "title": "Recolectores y esferas: cerrar «sin datos» de una vez (cierra T104)",
   "deps": [
    "T104",
    "T23"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 20,
   "goal": "Que el estado que pinta cada esfera sea el estado real del sistema, en cualquier equipo, y que arrancar sea una sola cosa. Queda abierto el último tramo de T104 (≥ 24 h con captura y ≥ 7 días para la línea base marginal) y los pendientes de la auditoría de módulos: los servicios se habían lanzado desde un worktree en vez del checkout principal, el disco externo se desconecta y el contexto sale a veces `degraded` (`PLAN/notas/auditoria_modulos_2026-10-19.md`, `PLAN/notas/T104_diagnostico.md`)."
  },
  {
   "id": "T121",
   "title": "Documentación, variables y tablero al día",
   "deps": [],
   "state": "pending",
   "notes": "",
   "effort": "bajo",
   "phase": 20,
   "goal": "Que quien vuelva (o quien llegue) no descubra el sistema a golpes: variables documentadas, dependencias nuevas dichas, tablero que dibuja todas las tareas y ningún paquete con claves suelto en el repositorio. Detalle en `PLAN/notas/DIAGNOSTICO_ESTABILIDAD_2026-10-22.md` §G."
  },
  {
   "id": "T122",
   "title": "Interfaz más ligera, solo BTC y tres operaciones sugeridas priorizadas",
   "deps": [
    "T50",
    "T51",
    "T75"
   ],
   "state": "done",
   "notes": "Encargo del usuario (2026-10-22). **Tema futurista único** (fuera el interruptor, los temas claro/oscuro, la preferencia guardada y los repintados de tema) y **sin la franja radar** `cy-sweep`. **Solo BTCUSDT operativo**: `FOCUS`, `EIM_ARB_ASSETS=BTC`, recolectores de `servicio_continuo.ps1` y UI (ETH oculto en multiactivo/estacionalidad); la API y el almacén conservan la historia de ETH. **Mapa del sistema bajo el Río** (sin botón ni pantalla propia; sondea solo a la vista; listas plegadas que conservan lo abierto) e **historial de sugerencias como pestaña tras Bitácora** (carga solo con la pestaña abierta). **Ranking de 3 posiciones** `eim/suggestions/ranking.py` + `GET /v2/setups` → `ranking`/`funnel`: solo validadas por T49 en el orden del publicador, vacías con su motivo (nunca rellenadas con ideas en observación), acierto fuera de muestra con IC de Wilson rotulado «no es probabilidad calibrada», invalidación, riesgos del contexto, estado de validación y de la sombra; embudo identificada → analizada → validada → ranking / pendiente / descartada con motivos. UI `web/src/{setups_ui,setups_cards,obs_view,setups_history,main,river_sphere,theme}.ts`; de paso: el panel inferior ya crece con su pestaña (`sim.css` lo fijaba en 190 px) y las pestañas no desbordan. Tests `tests/suggestions/test_ranking.py` (7) + contrato de la ruta; gate verde. Verificado en el navegador contra la API en vivo (la tarjeta validada solo con carga sintética: hoy 0 de 104 versiones validadas). Pendiente: desplegar (reiniciar la API en vivo, con permiso) y BACKLOG T122.",
   "effort": "medio",
   "phase": 20,
   "goal": "Encargo del usuario del 2026-10-22: una mesa más limpia y rápida con el tema futurista como única apariencia, foco operativo exclusivo en BTCUSDT, el mapa del sistema bajo el Río de decisión, el historial de sugerencias en su pestaña inferior y siempre tres posiciones de operación sugerida ordenadas por la evidencia validada, sin rellenar huecos con señales sin validar."
  }
 ]
};
