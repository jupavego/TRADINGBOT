window.EIM_STATUS = {
 "generated": "2026-10-15T21:35:14",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "notes": "Multi-marco: contextos e ideas en 15 m / 1 h / 4 h; cada estrategia se evalúa y pondera por separado en cada marco (`estrategia@marco`, `Idea.sid`), tenencias escaladas al marco (las sugerencias y escenarios conservan sus horas); perfiles operan los tres. Aprendizaje de cada pérdida: causa por operación (`Outcome.cause`: dirección, SL rápido, casi TP, tiempo, costos) y pausa por contexto estrategia@marco × régimen × lado (`Learner.context_at`, solo cierres ≤ t; test), visible en bitácora («Aprendizaje por contexto»), balance («Por qué se perdió», acierto por marco), Aprendizaje (filtro por marco, causas y contextos) y conclusiones. Servicio continuo: `eim/paper/service.py` (ciclo por marco, latido `data/paper/heartbeat.json`, backtest por marco), franja «Servicio en vivo» en la vista, `v2/scripts/servicio_continuo.ps1` (vigilante + web, sin duplicar) e `instalar_inicio_automatico.ps1` (tarea al iniciar sesión, no instalada). API `tf` en trades/journal/ideas/backtest; CLI `--tf`. Datos reales: 4 h 60 d (360 velas, −0,19 R/op sombra), 1 h 60 d (−0,28), 15 m en curso; posiciones abiertas en los 3 marcos. Tests en tests/paper/test_t48.py. **T48b (decisión del usuario: «máxima rentabilidad, más acertadas que fallidas»)**, con evidencia en `PLAN/notas/T48_decisiones.md`: filtro de costo por perfil (`max_cost_r`), tendencia del marco mayor obligatoria (`eim/paper/trend.py`, `Idea.htf`), break-even + que cubre costos solo en 1 h/4 h (salida `BE`), pausa ante expectativa negativa en los 3 perfiles y Conservador «solo lo probado». Mismos datos: ponderado 36,3 % → 44,5 % de acierto, esperanza −0,30 → −0,09 R; 1 h Moderado/Agresivo +0,10/+0,13 R con 53 % de acierto. Configuración elegida sobre esos mismos 60 días: validar con la corrida en vivo.",
   "effort": "alto",
   "phase": 7,
   "goal": "Que el bróker simulado opere sin parar en segundo plano sobre BTCUSDT en 15 m, 1 h y 4 h, y que cada pérdida se convierta en aprendizaje (por contexto y por causa) para que con el tiempo las ganadas prevalezcan sobre las perdidas."
  }
 ]
};
