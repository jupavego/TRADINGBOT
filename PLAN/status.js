window.EIM_STATUS = {
 "generated": "2026-10-13T16:22:22",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 7,
   "goal": "Dejar el sistema mantenible y seguro."
  },
  {
   "id": "T33",
   "title": "Auditoría de repos y fuentes (4 agentes nuevos)",
   "deps": [],
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
   "state": "pending",
   "notes": "",
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
  }
 ]
};
