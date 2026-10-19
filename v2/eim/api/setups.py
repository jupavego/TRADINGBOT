"""Ruta `GET /v2/setups` (T50): operaciones sugeridas intradía de estrategias VALIDADAS.

Cruza las ideas vivas del bróker simulado (última vela cerrada de 15 m y 1 h) con los veredictos
vigentes de la puerta de T49 (`eim/suggestions/publisher.py`). Nunca publica la salida cruda de
`synthesis.setups.suggest()`. Siempre oportunidades potenciales, no ejecutadas (Análisis).
"""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException

from eim.agents.levels.pivots import atr
from eim.data.timeframes import SYMBOLS
from eim.paper.desk import PaperDesk
from eim.paper.generate import now_ms
from eim.suggestions.publisher import NOTE, PublishParams, publish
from eim.validation.service import Validator

ATR_TF, ATR_BARS, ATR_PERIOD = "1h", 60, 14
DEAD = ("CANCELADA", "RECHAZADA", "CERRADA")   # la sombra ya la descartó o resolvió


def _atr(desk: PaperDesk, symbol: str) -> float | None:
    cs = desk.store.read_candles(symbol, ATR_TF, last=ATR_BARS)
    if len(cs) < ATR_PERIOD + 2:
        return None
    return atr(np.array([c.h for c in cs]), np.array([c.l for c in cs]),
               np.array([c.c for c in cs]), ATR_PERIOD)


def build_setups_router(desk: PaperDesk, validator: Validator,
                        params: PublishParams | None = None) -> APIRouter:
    router = APIRouter()
    p = params or PublishParams()

    @router.get("/v2/setups")
    def setups(symbol: str = "BTCUSDT") -> dict:
        if symbol not in SYMBOLS:
            raise HTTPException(400, f"símbolo no soportado: {symbol} (válidos: {list(SYMBOLS)})")
        now = now_ms()
        v_asof, _, verdicts = validator.vstore.latest(validator.crit.version, symbol)
        view = desk.cached_view(symbol, wait_s=5.0)
        ideas, last_t, price, stale = [], {}, None, False
        if view is not None:
            ideas = [o.idea for o in view.outcomes
                     if o.idea.timeframe in p.timeframes and o.status not in DEAD]
            last_t = {tf: view.stamp[0][k][1] for k, tf in enumerate(desk.tfs)}
            price = float(view.path.c[-1]) if view.path is not None and len(view.path.t) else None
            stale = bool(desk.view_state(view)["stale"])
        pub = publish(ideas, verdicts, now=now, price=price, atr=_atr(desk, symbol),
                      last_t=last_t, verdicts_asof=v_asof, heartbeat=desk.last_tick,
                      view_stale=stale, params=p)
        return {"mode": "ANALISIS", "symbol": symbol, "asof": view.path.end if view and view.path
                is not None else None, "now": now, "criteria_version": validator.crit.version,
                "verdicts_asof": v_asof, "price": price, "timeframes": list(p.timeframes),
                "horizon_hours": [0, p.max_hold_h], "source": "bróker simulado (T47) + puerta T49",
                "status": pub.status, "message": pub.message, "validation": pub.validation,
                "discarded": pub.discarded, "setups": pub.setups, "note": NOTE}

    return router
