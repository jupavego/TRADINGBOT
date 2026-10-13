# Estado del plan (actualizar al cerrar cada tarea)

Leyenda: ☐ pendiente · ◐ en curso · ☑ hecha

| ID | Tarea | Depende de | Estado | Notas de cierre |
|---|---|---|---|---|
| T01 | Cimientos: paquete, contratos, git, gate | — | ☑ | v2/eim/core (contratos pydantic) + v2/tests/core; pyproject, .gitignore, skill eim-new-agent. Gate OK (12 tests). |
| T02 | Red de seguridad: regresión del legado | T01 | ☑ | v2/tests/legacy (_runner, generate_golden, test_golden) + golden JSON en v2/tests/fixtures/golden (no parquet: sin pyarrow y *.parquet está en .gitignore) + fixture ethusdt_1h_1000.csv. Cubiertos: FRM, BRM, IRM, VWAP (día/semana/quincena/mes + anclado), price action (+zonas S/R), Elliott, estacionalidad (con cierres mensuales sintéticos: el CSV cubre ~6 semanas). NO cubiertos: eim_engine (orquesta feed de red; su pipeline FRM→BRM→IRM sí), eim_liquidations/market_data/data/web/bitacora (requieren red/estado). Tolerancia rtol/atol 1e-9; umbral θ-001 alterado en copia (EIM_LEGACY_DIR) hace fallar el test. Gate OK (19 tests). |
| T03 | Capa de datos y almacén | T01 | ☑ | v2/eim/data: `providers/` (Provider, BinanceFutures con reintentos/tasa), `store.py` (Parquet+DuckDB, huecos), `sync.py` (relleno incremental), `snapshot.py` (`build_snapshot`). Manual real: 6000 velas 1h BTCUSDT, 0 huecos. Evaluación OpenBB en PLAN/notas/T03_openbb.md. Gate OK (19 tests). |
| T04 | Auditoría de repos (licencia/seguridad) | — | ☑ | PLAN/notas/T04_auditoria.md: 13 repos con veredicto. Rojas: market-regime y limit-order-book sin licencia real, Freqtrade GPL, OpenBB redirige a org nueva, circuit-framework descartado. Usar: Optuna, Kronos oficial. |
| T05 | Runner de agentes + agente `structure` | T01 T02 T03 | ☑ | v2/eim/agents: `base.py` (reportes degraded/no_data), `registry.py` (id+versión, `default_registry`), `runner.py` (paralelo, timeout, excepción→degraded). `structure/` (frm/brm/irm/params/agent, sin I/O): salida idéntica al golden de T02 (RTOL 1e-9); sesgo=(convicción−50)/50, confianza=score IRM/100, evidencia con reglas SR/M disparadas. Tests en tests/agents. Gate OK. |
| T06 | Agentes VWAP + price action | T05 | ☑ | v2/eim/agents: `vwap/` (diario/semanal/quincenal/mensual+anclado, bandas ±1σ/±2σ, overlays `level` por período, avisa período parcial), `price_action/` (swings, patrones, BOS/CHOCH, zonas S/R como `zone`), y `ema/` (extra pedido: las 44 variables FRM en `metrics.variables`/`groups`, overlays EMA y cruces). Los 3 en `default_registry` y corren en el runner. Regresión contra golden RTOL 1e-9. Gate OK. |
| T07 | Agentes Elliott + estacionalidad + liquidaciones | T05 | ☑ | v2/eim/agents: `elliott/` (zigzag+conteo 0-C, overlays `marker` por pivote y `level` de invalidación/solape, avisa heurística), `seasonality/` (cierres mensuales desde velas, matriz Año×Mes, sesgo del mes en curso; `strict_gaps` corrige el hueco que el legado interpolaba), `liquidations/` (consume `snapshot.liquidations`; obsoleto→`degraded` sin sesgo, expone `stale`/`most_recent_date`/`liquidation_symbol` vs `requested_symbol`). I/O en `eim/data/providers/liquidations.py`; contrato nuevo `Liquidations` en `core/market.py`. Equivalencia con golden T02. Gate OK. |
| T08 | API v2 (REST + WebSocket + persistencia) | T05 | ☑ | v2/eim/api: `main.py` (`create_app`; REST `/v2/health|snapshot|agents|reports|overlays`, `WS /v2/stream` con latido y estado de fuente), `live.py` (hub por símbolo/marco; al cierre de vela corre agentes y difunde reportes+overlays), `sources.py` (kline WS de Binance con reconexión exponencial; fuente inyectable), `reports_db.py` (tabla `reports` en DuckDB, consulta por rango), `config.py` (env `EIM_*`, CORS). Verificado en 127.0.0.1 con fuente simulada: ticks→reportes persistidos. Gate OK. |
| T09 | Frontend base + gráfico de velas en vivo | T08 | ☑ | v2/eim/web (Vite 5 + TS + Lightweight Charts 5): `api.ts` (REST snapshot + WS con reconexión exponencial), `chart.ts`, `theme.ts` (claro por defecto/oscuro), `main.ts`, tipos a mano en `types.ts`. Layout UI_SPEC con barra superior (activo, marco, precio, En vivo/Sin conexión, modo), columna derecha y pestañas vacías. Verificado con API real: 500 velas BTCUSDT, última vela y precio cambian por tick; claro/oscuro/tablet por screenshot; banner "Sin conexión" y reconexión; ETH/15m. Gate OK. |
| T10 | Panel de agentes + síntesis (UI) | T09 | ☑ | v2/eim/web/src: `panels.ts` (tarjetas por agente: barra de sesgo −1..+1, confianza, estado, 3 líneas de evidencia, expandible a métricas/advertencias; bitácora de `/v2/reports`), `synth.ts` (síntesis SIMULADA en el navegador hasta T20, acuerdo, contribuciones, alerta de desacuerdo). Se actualiza con el mensaje WS `reports`. Verificado con API sobre fixture, claro y oscuro; falta ver el cambio al cerrar vela en vivo (sin red). Pendiente: visto bueno del usuario a la interfaz antes de Fase 3. |
| T11 | Portar pestañas legadas | T10 | ☑ | Vista «Más análisis» (botón en la barra): `web/src/more*.ts` + API `eim/api/more.py` (`/v2/more/*`). Portado: `backtest/vrm.py` (idéntico al legado, test de regresión), `analytics/bitacora*.py` (ledger>historial>estimado, apalancamiento obligatorio), `providers/multi_asset.py` (Binance/Yahoo); liquidaciones (`stale` visible), estacionalidad (cobertura real) y VWAP por periodos reutilizan los agentes v2. Verificado con navegador y contra el legado. Bug heredado corregido: el proveedor de liquidaciones duplicaba importes (faltaba `drop_duplicates`). Diferencia consciente: estacionalidad excluye el mes en curso. F7/web intacto. |
| T12 | Agente de niveles (S/R, canal, rango) | T05 | ☑ | v2/eim/agents/levels: `pivots.py` (ATR, fractales, clustering 1D → zonas con toques/recencia/volumen, 2 arriba y 2 abajo), `channel.py` (Theil–Sen sobre pivotes, rango si deriva/ancho<0.35, canal roto tras 3 cierres fuera, extendido adelante), `agent.py` (sesgo por posición en canal + cercanía a zonas; overlays `zone`/`channel`/`range`), registrado en `default_registry`. Tests sintéticos + fixture en tests/agents/levels. |
| T13 | Agente de plan (entrada/SL/TP/R:R) | T12 | ☑ | v2/eim/agents/plan: `plan.py` (propose: SL tras soporte/resistencia estructural + colchón ATR, TP1/TP2 en zonas opuestas, R:R≥1.5; advance: invalidado por cierre más allá del SL, cumplido, expirado; improve: solo acerca el SL), `agent.py` (sesgo combinado structure+levels hasta T20; reproduce las últimas 96 velas cada 6 para mantener el plan estable; overlay `trade_plan`, siempre `mode=ANALISIS`, sin tamaño de posición). Registrado en `default_registry`. Tests en tests/agents/plan. Test API relajado (range 6→40) por el coste extra del pipeline. |
| T14 | Capas sobre el gráfico + hover de evidencia | T09 T12 T13 | ☑ | v2/eim/web/src: `layers.ts` (LayerEngine: overlays por id, reemplazo por agente, primitiva de Lightweight Charts que dibuja zonas como bandas, canal como 2 líneas + relleno, plan con etiquetas y R:R; extrapola tiempo futuro), `layers_ui.ts` (fila de capas con estado en localStorage; tarjeta de evidencia al hover), `api.fetchOverlays`; etiqueta "Propuesta · Análisis" en el plan. Verificado con datos reales BTCUSDT 1h: coordenadas de capas = priceToCoordinate de los precios del overlay; claro y oscuro. Plan probado con overlay sintético (el agente no emitió plan con esos datos). Niveles = solo agente `levels`. |
| T15 | Marcas de operaciones + bitácora + reproducción | T14 | ☑ | v2/eim/execution/sim_ledger.py (libro SIMULADO reconstruido desde los planes persistidos: entrada al cierre del plan, SL vigente/TP1/TP2/invalidez, comisión+funding supuestos, R neto; DuckDB `sim_trades`). API `eim/api/trades.py`: /v2/trades, /v2/journal, /v2/replay, /v2/replay/asofs (+ `ReportStore.at/asofs`). Web: `trades_ui.ts` (marcadores + pestaña Bitácora) y deslizador en main.ts. Test: replay devuelve el plan emitido en ese instante (tests/api/test_trades.py). Sin llamadas a exchange.
| T16 | Proyección: trayectorias OHLC (base + Kronos opc.) | T03 T05 | ☐ | |
| T17 | Escenarios (3, probabilidad, invalidación) + API | T16 T08 | ☐ | |
| T18 | Escenarios sobre el gráfico (+ toggle velas) | T09 T17 | ☐ | |
| T19 | Seguimiento y calibración de escenarios | T17 T18 | ☐ | |
| T20 | Síntesis v1 | T06 T07 T12 | ☐ | |
| T21 | Agente de derivados (funding/OI/basis) | T03 T05 | ☐ | |
| T22 | Agente de régimen (BOCPD + transición) | T05 | ☐ | |
| T23 | Microestructura: recolector + agente OFI | T03 T05 | ☐ | |
| T24 | Agente de contexto (LLM) | T05 | ☐ | |
| T25 | Backtest con costos de perpetuos | T13 T20 | ☐ | |
| T26 | Calibración (optuna, walk-forward) | T25 | ☐ | |
| T27 | **Puerta de edge** (informe de decisión) | T26 T19 | ☐ | |
| T28 | (Opcional) Laboratorio ESN con conectoma | T27 | ☐ | |
| T29 | Motor de riesgo (veto determinista) | T27 | ☐ | |
| T30 | Ejecución en testnet + reconciliación | T29 | ☐ | |
| T31 | Paper trading + kill-switch + monitoreo | T30 | ☐ | |
| T32 | Endurecimiento y documentación | T31 | ☐ | |
| T33 | Auditoría de repos y fuentes (4 agentes nuevos) | — | ☐ | |
| T34 | Biblioteca de indicadores técnicos (catálogo Binance) | T05 | ☐ | |
| T35 | Agente `technical` (confluencia multi-marco) | T34 | ☐ | |
| T36 | Calendario económico: proveedor + agente | T05 | ☐ | |
| T37 | Calendario: impacto histórico y ventanas | T36 T03 | ☐ | |
| T38 | Arbitraje: motor de oportunidades netas (Binance) | T03 T05 | ☐ | |
| T39 | Agente `arbitrage` + escáner UI | T38 T10 | ☐ | |
| T40 | Copy trading: datos y descubrimiento de líderes | T03 T33 | ☐ | |
| T41 | Copy trading: evaluación de líderes + agente `smart_money` | T40 T05 | ☐ | |
| T42 | Copy trading: replicación simulada | T41 T25 | ☐ | |
| T43 | Arbitraje: simulación y backtest con costos | T38 T25 | ☐ | |
| T44 | Integración de agentes nuevos (síntesis, riesgo, UI) | T20 T35 T36 T37 T41 T39 | ☐ | |
| T45 | Arbitraje en testnet (dos patas, selección automática) | T30 T43 | ☐ | |
| T46 | Copy trading en testnet + asignador de capital | T30 T42 T45 | ☐ | |
