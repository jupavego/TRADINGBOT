"""API v2: REST + WebSocket. Arranque: `python -m uvicorn eim.api.main:app --port 8000`."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from eim.agents.registry import AgentRegistry, default_registry
from eim.api.calibration import build_calibration_router
from eim.api.config import Settings
from eim.api.forecast import Forecaster, build_forecast_router
from eim.api.history import HistoryLoader
from eim.api.live import Hub, overlays_of, synthesis_of
from eim.api.more import MoreSources, build_more_router
from eim.api.reports_db import ReportStore
from eim.api.risk import build_risk_router
from eim.api.sources import BinanceKlineSource, LiveSource
from eim.api.trades import build_trades_router
from eim.data.providers.binance import BinanceFutures
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.risk import global_kill_switch

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
) -> FastAPI:
    cfg = settings or Settings.from_env()
    store = Store(cfg.data_dir)
    reports = ReportStore(cfg.reports_path)
    reg = registry or default_registry()
    src = source or BinanceKlineSource(cfg.ws_url, cfg.reconnect_max_s)
    forecaster = Forecaster(store, reports)
    if history is None and source is None and cfg.auto_history:  # en vivo: historia automática
        history = HistoryLoader(store, BinanceFutures())
    hub = Hub(src, store, reports, reg, cfg.snapshot_bars, cfg.agent_timeout_s, forecaster, history)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await hub.close()
        reports.close()

    app = FastAPI(title="EIM API", version=API_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=list(cfg.cors_origins), allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.hub, app.state.reports, app.state.store = hub, reports, store
    app.state.forecaster = forecaster
    app.include_router(build_trades_router(store, reports))
    global_kill_switch().attach(cfg.data_dir / "kill_switch.json")
    app.include_router(build_risk_router(store, reports))
    app.include_router(build_forecast_router(forecaster))
    app.include_router(build_calibration_router(store, forecaster))
    app.include_router(build_more_router(store, more, cfg.data_dir / "cache" / "liquidations"))

    @app.get("/v2/health")
    def health() -> dict:
        return {"status": "ok", "version": API_VERSION, "now": int(time.time() * 1000),
                "agents": len(reg.ids()), "live_source": src.name}

    @app.get("/v2/snapshot")
    def snapshot(symbol: str = "ETHUSDT", tf: str = "1h", n: int = Query(500, ge=1, le=5000)):
        _check(symbol, tf)
        if history is not None:
            history.ensure(symbol, tf)
        snap = build_snapshot(store, symbol, tf, n)
        if not snap.candles:
            raise HTTPException(404, f"sin velas almacenadas para {symbol} {tf}")
        return snap.model_dump()

    @app.get("/v2/agents")
    def agents(symbol: str = "ETHUSDT", tf: str = "1h") -> list[dict]:
        _check(symbol, tf)
        last = {r.agent_id: r for r in reports.latest(symbol, tf)}
        out = []
        for a in reg.latest():
            r = last.get(a.id)
            out.append({
                "id": a.id, "version": a.version, "requires": sorted(a.requires),
                "last_asof": r.asof if r else None, "status": r.status if r else "sin_ejecutar",
                "bias": r.bias if r else None, "confidence": r.confidence if r else None,
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
        await ws.accept()
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
