"""Calibración de escenarios (T19): `GET /v2/calibration` y `POST /v2/calibration/backfill`."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from eim.api.forecast import DEFAULT_HORIZON, Forecaster
from eim.data.store import Store
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.forecast.backfill import backfill
from eim.forecast.calibration import evaluate_forecast, summarize
from eim.forecast.engine import MAX_HORIZON, MIN_HORIZON


def calibration_report(store: Store, forecaster: Forecaster, symbol: str, tf: str,
                       horizon: int) -> dict:
    """Evalúa los pronósticos persistidos contra las velas almacenadas."""
    fcs = forecaster.db.horizon_all(symbol, tf, horizon)
    closes = {c.t: c.c for c in store.read_candles(symbol, tf)}
    outs, pending = [], 0
    for fs in fcs:
        o = evaluate_forecast(fs, closes)
        if o is None:
            pending += 1
        else:
            outs.append(o)
    rep = summarize(outs, horizon, pending)
    rep.update(symbol=symbol, timeframe=tf, engine="base",
               n_backfill=sum(any("backfill" in w for w in f.warnings) for f in fcs),
               source="pronósticos persistidos vs velas del almacén")
    return rep


def build_calibration_router(store: Store, forecaster: Forecaster) -> APIRouter:
    router = APIRouter(prefix="/v2")

    def _check(symbol: str, tf: str) -> None:
        if symbol not in SYMBOLS or tf not in TF_MS:
            raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")

    @router.get("/calibration")
    def calibration(symbol: str = "ETHUSDT", tf: str = "1h",
                    h: int = Query(DEFAULT_HORIZON, ge=MIN_HORIZON, le=MAX_HORIZON)) -> dict:
        _check(symbol, tf)
        return calibration_report(store, forecaster, symbol, tf, h)

    @router.post("/calibration/backfill")
    def run_backfill(symbol: str = "ETHUSDT", tf: str = "1h",
                     h: int = Query(DEFAULT_HORIZON, ge=MIN_HORIZON, le=MAX_HORIZON),
                     origins: int = Query(600, ge=1, le=2000)) -> dict:
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
