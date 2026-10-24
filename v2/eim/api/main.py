"""API v2: REST + WebSocket. Arranque: `python -m uvicorn eim.api.main:app --port 8000`."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from eim.agents.registry import AgentRegistry, default_registry
from eim.api.arb_execution import arb_loop, build_arb_execution_router, build_arb_runtime
from eim.api.arbitrage import ArbDesk, build_arbitrage_router
from eim.api.backup import build_backup_router
from eim.api.bots import build_bots_router
from eim.api.calibration import build_calibration_router
from eim.api.config import Settings
from eim.api.execution import build_execution_router, build_runtime, recon_loop
from eim.api.forecast import Forecaster, build_forecast_router
from eim.api.history import HistoryLoader
from eim.api.leaders import LeaderDesk, build_leaders_router
from eim.api.library import build_library_router
from eim.api.live import Hub, overlays_of, synthesis_of
from eim.api.micro import build_micro_router
from eim.api.more import MoreSources, build_more_router
from eim.api.obs import build_obs_router, build_observatory
from eim.api.operation import build_operation_router
from eim.api.paper import build_paper_router
from eim.api.paper_arb import build_paper_arb_router
from eim.api.reports_db import ReportStore
from eim.api.risk import RiskDesk, build_risk_router
from eim.api.security import BodyLimitMiddleware, LocalOnlyMiddleware, ws_token_subprotocol
from eim.api.setups import build_setups_router
from eim.api.share import build_share_router
from eim.api.sources import BinanceKlineSource, LiveSource
from eim.api.trades import build_trades_router
from eim.api.validation import build_validation_router
from eim.arbitrage.alerts import AlertParams
from eim.bots.scorer import BotScorer
from eim.bots.service import default_service
from eim.bots.squad_runtime import SquadRuntime
from eim.data.arb_store import ArbStore
from eim.data.arb_sync import ArbSync
from eim.data.bots.scorestore import ScoreStore
from eim.data.bots.simstore import SimRunStore
from eim.data.bots.store import BotSignalStore
from eim.data.calendar_sync import CalendarSync
from eim.data.paper_store import PaperStore
from eim.data.providers.binance import BinanceFutures
from eim.data.share_auto import Live, make_agent, share_loop
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.data.suggestion_store import SuggestionStore
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.data.validation_store import ValidationStore
from eim.observability.emit import configure
from eim.operation.alerts import AlertCenter
from eim.operation.cycle import OperationParams
from eim.operation.supervisor import Operation, Supervisor
from eim.operation.task_watch import watch_supervisor
from eim.paper.desk import PaperDesk
from eim.risk import global_kill_switch, load_config
from eim.suggestions.tracker import Tracker
from eim.synthesis.params import role_of
from eim.synthesis.squad import default_params
from eim.validation.service import Validator

API_VERSION = "2.0.0"


def _check(symbol: str, tf: str) -> None:
    if symbol not in SYMBOLS:
        raise HTTPException(400, f"símbolo no soportado: {symbol} (válidos: {list(SYMBOLS)})")
    if tf not in TF_MS:
        raise HTTPException(400, f"marco no soportado: {tf} (válidos: {list(TF_MS)})")


def create_app(
    settings: Settings | None = None,
    source: LiveSource | None = None,
    registry: AgentRegistry | None = None,
    more: MoreSources | None = None,
    history: HistoryLoader | None = None,
    operation_provider=None,
) -> FastAPI:
    cfg = settings or Settings.from_env()
    store = Store(cfg.data_dir)
    reports = ReportStore(cfg.reports_path)
    reg = registry or default_registry(arb_assets=cfg.arb_assets)
    src = source or BinanceKlineSource(cfg.ws_url, cfg.reconnect_max_s)
    forecaster = Forecaster(store, reports)
    if history is None and source is None and cfg.auto_history:  # en vivo: historia automática
        history = HistoryLoader(store, BinanceFutures())
    # T57: modo A siempre; modo B solo si el entorno aparte de Freqtrade está configurado.
    bot_store = BotSignalStore(*reports.connection)
    bots = default_service(cfg.data_dir, bot_store, lambda sym, tf, last_t, n: store.read_candles(
        sym, tf, end=last_t + 1, last=n))   # Jesse/TrendRider piden más velas que el snapshot
    hub = Hub(src, store, reports, reg, cfg.snapshot_bars, cfg.agent_timeout_s, forecaster, history,
              bots)
    obs_store, obs_indexer, obs_dbs = build_observatory(cfg.data_dir, reports)   # T73
    paper_store = PaperStore(cfg.data_dir / "paper.duckdb")       # T47; base propia
    backup_dbs = {**obs_dbs, "paper.duckdb": paper_store.connection}  # T115: entra en la copia
    rcon, rlock = reports.connection
    kill = global_kill_switch()
    kill.attach(cfg.data_dir / "kill_switch.json")
    runtime = build_runtime(cfg.execution, kill, load_config())
    configure(process="api", mode=runtime.mode, spool_dir=cfg.data_dir / "obs" / "spool")
    desk = RiskDesk(store, reports, kill=kill, runtime=runtime)
    op = None
    if cfg.operate:   # T31: el ciclo continuo reconcilia; no hace falta el bucle aparte
        op = Operation(store=store, provider=operation_provider or BinanceFutures(),
                       reports=reports, registry=reg, desk=desk,
                       params=OperationParams(timeframe=cfg.operate_tf,
                                              extra_timeframes=cfg.operate_extra_tfs,
                                              poll_s=cfg.operate_poll_s,
                                              snapshot_bars=cfg.snapshot_bars,
                                              agent_timeout_s=cfg.agent_timeout_s),
                       data_dir=cfg.data_dir, reports_dir=cfg.operation_reports,
                       edge_path=cfg.edge_results, forecaster=forecaster, bots=bots,
                       backup_dir=cfg.backup_dir, backup_keep=cfg.backup_keep,
                       extra_dbs=backup_dbs, backup_in_thread=source is None)

    # T36: solo en vivo (con fuente inyectada —tests— no hay red).
    calendar = (CalendarSync(cfg.data_dir, interval_s=cfg.calendar_interval_s)
                if source is None and cfg.calendar else None)
    # T39: escáner de arbitraje, también solo en vivo; la fotografía va a data/arbitrage/.
    arb_sync = (ArbSync(cfg.data_dir, interval_s=cfg.arbitrage_interval_s, assets=cfg.arb_assets,
                        tri_assets=cfg.arb_tri_assets)
                if source is None and cfg.arbitrage else None)
    arb_agent = reg.get("arbitrage") if "arbitrage" in reg.ids() else None  # mismo foco
    arb_desk = ArbDesk(ArbStore(cfg.data_dir), agent=arb_agent, alerts=AlertParams(
        min_score=cfg.arb_alert_score, hold_s=cfg.arb_alert_hold_s))
    # T45: arbitraje en testnet. Comparte kill-switch y cuenta de futuros con el carril
    # direccional: cada uno respeta la parte del otro (reconciliación, cierre y riesgo).
    svc = runtime.svc
    arb_rt = build_arb_runtime(
        cfg.arb_execution, kill, cfg.data_dir, ArbStore(cfg.data_dir),
        directional_qty=lambda s: svc.expected_qty(s) if svc is not None else 0.0,
        directional_symbols=lambda: tuple(t.symbol for t in svc.active()) if svc else (),
        interval_s=cfg.arb_exec_interval_s)
    if runtime.recon is not None:
        runtime.recon.external = arb_rt.futures_qty
    runtime.extra_open = arb_rt.open_symbols
    # T47: bróker simulado; servicio en vivo solo con la fuente real.
    paper = PaperDesk(store, paper_store, reg,
                      provider=BinanceFutures() if source is None else None,
                      poll_s=cfg.paper_poll_s)
    paper.alerts = op.alerts if op is not None else AlertCenter(rcon, rlock)   # T110 → op_alerts
    # T49: puerta de validación por estrategia; se recalcula al cierre de cada vela de 4 h.
    validator = Validator(paper, ValidationStore(paper_store))
    paper.after_tick.append(validator.maybe_run)
    paper.after_tick.append(paper.ledger_tick)    # libro de registro fijo (solo adición)
    # T61: experiencia compartida automática (solo si hay carpeta compartida configurada):
    # importa lo de las demás máquinas y exporta lo propio, sin comandos.
    share = None
    if source is None:
        share = make_agent(
            "api", cfg.data_dir, {"reports.duckdb": Live(*reports.connection),
                                  "paper.duckdb": Live(*paper_store.connection)},
            backup_dir=cfg.backup_dir,
            on_imported=lambda: [validator.compute(s) for s in paper.symbols])

    def now_ms() -> int:
        return int(time.time() * 1000)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if op is not None:
            task = watch_supervisor(asyncio.create_task(Supervisor(op).run()), op)
        elif runtime.recon is not None:
            task = asyncio.create_task(recon_loop(runtime, cfg.recon_interval_s, now_ms))
        else:
            task = None
        cal_task = asyncio.create_task(calendar.loop()) if calendar is not None else None
        arb_task = (asyncio.create_task(arb_sync.loop(
            lambda mkt: hub.broadcast_all(arb_desk.payload(mkt))))
            if arb_sync is not None else None)
        paper_task = (asyncio.create_task(paper.loop())
                      if source is None and cfg.paper else None)
        arb_exec_task = (asyncio.create_task(arb_loop(arb_rt))
                         if arb_rt.pilot is not None else None)
        share_task = asyncio.create_task(share_loop(share)) if share is not None else None
        obs_task = asyncio.create_task(obs_indexer.loop()) if source is None else None
        yield
        for t in (task, cal_task, arb_task, paper_task, arb_exec_task, share_task, obs_task):
            if t is not None:
                t.cancel()
        paper.stop_backtest()
        await hub.close()
        reports.close()
        paper_store.close()
        obs_store.close()

    app = FastAPI(title="EIM API", version=API_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=list(cfg.cors_origins), allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BodyLimitMiddleware)   # 413 antes de recibir cuerpos enormes (T32)
    # Exterior: rechaza Host ajeno / cliente remoto antes que cualquier otra cosa (T32).
    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=cfg.allowed_hosts,
                       origins=cfg.cors_origins, token=cfg.api_token)
    app.state.hub, app.state.reports, app.state.store = hub, reports, store
    app.state.forecaster = forecaster
    app.include_router(build_trades_router(store, reports))
    app.include_router(build_library_router())
    app.state.operation = op
    app.include_router(build_risk_router(store, reports, desk=desk))
    app.include_router(build_operation_router(desk, lambda: op, cfg.operation_reports))
    app.include_router(build_execution_router(runtime, now_ms))
    app.include_router(build_backup_router(reports, cfg.data_dir, cfg.backup_dir,
                                           cfg.backup_keep, lambda: op, extra_dbs=backup_dbs))
    app.include_router(build_obs_router(obs_store, obs_indexer, (rcon, rlock)))
    app.state.obs_store, app.state.obs_indexer = obs_store, obs_indexer
    app.include_router(build_share_router(reports, paper_store, cfg.data_dir, lambda: share))
    app.include_router(build_forecast_router(forecaster))
    # T59: puntuación del escuadrón; se recalcula al cierre de cada vela de 4 h.
    bot_scorer = BotScorer(bot_store, ScoreStore(rcon, rlock), store, paper_store,
                           SimRunStore(rcon, rlock))
    paper.after_tick.append(bot_scorer.maybe_run)
    SquadRuntime(bot_scorer, bots.quarantine).refresh()   # T60: política vigente desde T59
    app.include_router(build_bots_router(bot_store, bots, bot_scorer))
    # T51: registro y resolución de lo publicado; el bróker lo llama tras cada ciclo.
    setups_router = build_setups_router(
        paper, validator, tracker=Tracker(SuggestionStore(paper_store), paper.ep))
    paper.after_tick.append(setups_router.tick)
    app.include_router(setups_router)
    app.include_router(build_calibration_router(store, forecaster))
    app.include_router(build_more_router(store, more, cfg.data_dir / "cache" / "liquidations"))
    app.include_router(build_arbitrage_router(arb_desk))
    app.state.arb_desk = arb_desk
    app.include_router(build_arb_execution_router(arb_rt))
    app.state.arb_exec = arb_rt
    # T41: tablero de líderes (lo escribe el vigilante en data/leaders/; aquí solo se lee).
    sm = reg.get("smart_money") if "smart_money" in reg.ids() else None
    app.state.leader_desk = LeaderDesk(cfg.data_dir, agent=sm)
    app.include_router(build_leaders_router(app.state.leader_desk))
    app.include_router(build_micro_router(cfg.data_dir))
    app.include_router(build_paper_router(paper))
    app.include_router(build_paper_arb_router(store, cfg.data_dir))  # T45: pruebas en papel
    app.state.paper = paper
    app.include_router(build_validation_router(validator))
    app.state.validator = validator

    @app.get("/v2/health")
    def health() -> dict:
        return {"status": "ok", "version": API_VERSION, "now": int(time.time() * 1000),
                "agents": len(reg.ids()), "live_source": src.name, "mode": runtime.mode.value,
                "operation": op.status["state"] if op is not None else "apagado"}

    @app.get("/v2/snapshot")
    def snapshot(symbol: str = "ETHUSDT", tf: str = "1h", n: int = Query(500, ge=1, le=5000)):
        _check(symbol, tf)
        if history is not None:
            history.ensure(symbol, tf)
        snap = build_snapshot(store, symbol, tf, n)
        if not snap.candles:
            raise HTTPException(404, f"sin velas almacenadas para {symbol} {tf}")
        return snap.model_dump(exclude={"arb"})  # libros completos: /v2/arbitrage/*

    @app.get("/v2/agents")
    def agents(symbol: str = "ETHUSDT", tf: str = "1h") -> list[dict]:
        _check(symbol, tf)
        last = {r.agent_id: r for r in reports.latest(symbol, tf)}
        sp = default_params()
        out = []
        for a in reg.latest():
            r = last.get(a.id)
            role = role_of(a.id, sp)
            out.append({
                "id": a.id, "version": a.version, "requires": sorted(a.requires),
                "last_asof": r.asof if r else None, "status": r.status if r else "sin_ejecutar",
                "bias": r.bias if r else None, "confidence": r.confidence if r else None,
                # T44: papel en la síntesis y peso base (None si no vota por su papel)
                "role": role, "weight": sp.weights.get(a.id, 1.0) if role == "direccional"
                else None,
            })
        return out

    @app.get("/v2/reports")
    def get_reports(
        symbol: str = "ETHUSDT", tf: str = "1h", agent: str | None = None,
        start: int | None = None, end: int | None = None, limit: int = Query(100, ge=1, le=1000),
    ) -> list[dict]:
        _check(symbol, tf)
        rows = reports.query(symbol, tf, start, end, agent, limit)
        return [r.model_dump() for r in rows]

    @app.get("/v2/synthesis")
    def get_synthesis(symbol: str = "ETHUSDT", tf: str = "1h") -> dict:
        """Síntesis real (T20); `synthesis` es null si ningún agente aporta."""
        _check(symbol, tf)
        return {"synthesis": synthesis_of(reports.latest(symbol, tf), [a.id for a in reg.latest()])}

    @app.get("/v2/overlays")
    def overlays(symbol: str = "ETHUSDT", tf: str = "1h") -> list[dict]:
        _check(symbol, tf)
        return overlays_of(reports.latest(symbol, tf))

    @app.websocket("/v2/stream")
    async def stream(ws: WebSocket, symbol: str = "ETHUSDT", tf: str = "1h"):
        if symbol not in SYMBOLS or tf not in TF_MS:
            await ws.close(code=1008, reason="símbolo o marco no soportado")
            return
        # Acceso remoto con token: el subprotocolo ofrecido debe devolverse al aceptar.
        hdrs = {k.lower(): v for k, v in ws.headers.items()}
        await ws.accept(subprotocol=ws_token_subprotocol(hdrs))
        ch, q = hub.subscribe(symbol, tf)
        try:
            await ws.send_json(ch.status)
            if ch.last_tick:
                await ws.send_json(ch.last_tick)
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=cfg.heartbeat_s)
                except TimeoutError:
                    msg = {"type": "heartbeat", "t": int(time.time() * 1000)}
                await ws.send_json(msg)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.unsubscribe(ch, q)

    return app


def __getattr__(name: str) -> FastAPI:
    """`eim.api.main:app` se crea al pedirse (uvicorn), no al importar el módulo."""
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(name)
