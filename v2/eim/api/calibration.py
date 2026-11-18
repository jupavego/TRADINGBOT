"""Calibración de escenarios (T19): `GET /v2/calibration`, `POST /v2/calibration/backfill` y el
vigía automático (T184): `GET /v2/calibration/watch`."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from eim.api.execution import confirm
from eim.api.forecast import DEFAULT_HORIZON, Forecaster
from eim.data.store import Store
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.forecast.backfill import backfill
from eim.forecast.calibration import Outcome, evaluate_forecast, summarize
from eim.forecast.engine import MAX_HORIZON, MIN_HORIZON


def outcomes(store: Store, forecaster: Forecaster, symbol: str, tf: str, horizon: int
             ) -> tuple[list[Outcome], int, list]:
    """(resultados evaluados, pendientes, pronósticos) de lo persistido frente a las velas."""
    fcs = forecaster.db.horizon_all(symbol, tf, horizon)
    closes = {c.t: c.c for c in store.read_candles(symbol, tf)}
    outs, pending = [], 0
    for fs in fcs:
        o = evaluate_forecast(fs, closes)
        if o is None:
            pending += 1
        else:
            outs.append(o)
    return outs, pending, fcs


def calibration_report(store: Store, forecaster: Forecaster, symbol: str, tf: str,
                       horizon: int) -> dict:
    """Evalúa los pronósticos persistidos contra las velas almacenadas."""
    outs, pending, fcs = outcomes(store, forecaster, symbol, tf, horizon)
    rep = summarize(outs, horizon, pending)
    rep.update(symbol=symbol, timeframe=tf, engine="base",
               n_backfill=sum(any("backfill" in w for w in f.warnings) for f in fcs),
               source="pronósticos persistidos vs velas del almacén")
    return rep


def build_calibration_router(store: Store, forecaster: Forecaster, watch=None) -> APIRouter:
    router = APIRouter(prefix="/v2")

    def _check(symbol: str, tf: str) -> None:
        if symbol not in SYMBOLS or tf not in TF_MS:
            raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")

    @router.get("/calibration")
    def calibration(symbol: str = "ETHUSDT", tf: str = "1h",
                    h: int = Query(DEFAULT_HORIZON, ge=MIN_HORIZON, le=MAX_HORIZON)) -> dict:
        _check(symbol, tf)
        return calibration_report(store, forecaster, symbol, tf, h)

    @router.get("/calibration/watch")
    def calibration_watch(symbol: str | None = None, tf: str | None = None,
                          limit: int = Query(40, ge=1, le=500)) -> dict:
        """T184: última revisión automática por símbolo y marco, su historial y las reglas."""
        if watch is None:
            return {"enabled": False, "latest": [], "history": [],
                    "note": "vigía apagado: solo corre con el bróker simulado en vivo"}
        return watch.payload(symbol, tf, limit)

    @router.post("/calibration/backfill")
    def run_backfill(symbol: str = "ETHUSDT", tf: str = "1h",
                     h: int = Query(DEFAULT_HORIZON, ge=MIN_HORIZON, le=MAX_HORIZON),
                     origins: int = Query(600, ge=1, le=2000),
                     x_eim_confirm: str | None = Header(None)) -> dict:
        confirm(x_eim_confirm, "backfill")   # escribe en la base: no vale un POST «simple» (T32)
        _check(symbol, tf)
        candles = store.read_candles(symbol, tf)
        k = 0
        for fs in backfill(forecaster.engine, candles, symbol=symbol, timeframe=tf, horizon=h,
                           max_origins=origins):
            forecaster.db.save(fs)
            k += 1
        if not k:
            raise HTTPException(422, "historia insuficiente para backfill")
        return {"saved": k} | calibration_report(store, forecaster, symbol, tf, h)

    return router
