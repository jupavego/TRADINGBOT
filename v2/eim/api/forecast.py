"""Pronóstico probabilístico: servicio, ruta `GET /v2/forecast` y persistencia (T17)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from eim.api.forecast_db import ForecastStore
from eim.api.reports_db import ReportStore
from eim.core import ForecastSet
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.forecast.base_engine import BaseEngine
from eim.forecast.engine import MAX_HORIZON, MIN_HORIZON
from eim.forecast.scenarios import build_forecast

DEFAULT_HORIZON = 25


class Forecaster:
    """Genera y persiste el `ForecastSet` de un (símbolo, marco) desde el almacén."""

    def __init__(self, store: Store, reports: ReportStore, bars: int = 1500,
                 n_paths: int = 500) -> None:
        self._store, self._reports, self._bars, self._n = store, reports, bars, n_paths
        self.db = ForecastStore(*reports.connection)
        self.engine = BaseEngine()

    def _stops(self, symbol: str, tf: str) -> dict[str, float]:
        """SL del último plan vigente: invalida el escenario de su lado."""
        for r in self._reports.query(symbol, tf, agent_id="plan", limit=1):
            plan = r.metrics.get("plan") or {}
            if plan.get("sl") and plan.get("side") in ("long", "short"):
                return {("bull" if plan["side"] == "long" else "bear"): float(plan["sl"])}
        return {}

    def run(self, symbol: str, tf: str, horizon: int = DEFAULT_HORIZON,
            asof: int | None = None, drift: float | None = None) -> ForecastSet:
        snap = build_snapshot(self._store, symbol, tf, self._bars, asof=asof)
        if not snap.candles:
            raise LookupError(f"sin velas almacenadas para {symbol} {tf}")
        fs = build_forecast(snap, horizon, self._n, drift=drift, stops=self._stops(symbol, tf))
        self.db.save(fs)
        return fs


def build_forecast_router(forecaster: Forecaster) -> APIRouter:
    router = APIRouter(prefix="/v2")

    @router.get("/forecast")
    def forecast(symbol: str = "ETHUSDT", tf: str = "1h",
                 h: int = Query(DEFAULT_HORIZON, ge=MIN_HORIZON, le=MAX_HORIZON)) -> dict:
        if symbol not in SYMBOLS or tf not in TF_MS:
            raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")
        try:
            return forecaster.run(symbol, tf, h).model_dump()
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, f"datos insuficientes para proyectar: {exc}") from exc

    return router
