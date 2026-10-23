"""Ruta `GET /v2/setups` (T50): operaciones sugeridas intradía de estrategias VALIDADAS.

Cruza las ideas vivas del bróker simulado (última vela cerrada de 15 m y 1 h) con los veredictos
vigentes de la puerta de T49 (`eim/suggestions/publisher.py`). Nunca publica la salida cruda de
`synthesis.setups.suggest()`. Siempre oportunidades potenciales, no ejecutadas (Análisis).
T122: suma `ranking` (siempre 3 posiciones; las vacías dicen por qué) y `funnel` (estado de cada
idea de la última vela: identificada, analizada, validada, pendiente o descartada) con
`eim/suggestions/ranking.py`.
"""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException, Query

from eim.agents.levels.pivots import atr
from eim.data.timeframes import SYMBOLS
from eim.paper.desk import PaperDesk
from eim.paper.generate import now_ms
from eim.suggestions.publisher import NOTE, PublishParams, publish
from eim.suggestions.ranking import DEAD, funnel, ranking
from eim.suggestions.tracker import Tracker
from eim.validation.service import Validator

ATR_TF, ATR_BARS, ATR_PERIOD = "1h", 60, 14


def _atr(desk: PaperDesk, symbol: str) -> float | None:
    cs = desk.store.read_candles(symbol, ATR_TF, last=ATR_BARS)
    if len(cs) < ATR_PERIOD + 2:
        return None
    return atr(np.array([c.h for c in cs]), np.array([c.l for c in cs]),
               np.array([c.c for c in cs]), ATR_PERIOD)


def _check(symbol: str) -> None:
    if symbol not in SYMBOLS:
        raise HTTPException(400, f"símbolo no soportado: {symbol} (válidos: {list(SYMBOLS)})")


def build_setups_router(desk: PaperDesk, validator: Validator,
                        params: PublishParams | None = None,
                        tracker: Tracker | None = None) -> APIRouter:
    router = APIRouter()
    p = params or PublishParams()

    def current(symbol: str, wait_s: float = 5.0) -> tuple:
        now = now_ms()
        v_asof, _, verdicts = validator.vstore.latest(validator.crit.version, symbol)
        view = desk.cached_view(symbol, wait_s=wait_s)
        cands, last_t, price, stale = [], {}, None, False
        if view is not None:
            cands = [(o.idea, o.status) for o in view.outcomes if o.idea.timeframe in p.timeframes]
            last_t = {tf: view.stamp[0][k][1] for k, tf in enumerate(desk.tfs)}
            price = float(view.path.c[-1]) if view.path is not None and len(view.path.t) else None
            stale = bool(desk.view_state(view)["stale"])
        a, review = _atr(desk, symbol), tracker.in_review(symbol) if tracker else ()
        pub = publish([i for i, st in cands if st not in DEAD], verdicts, now=now, price=price,
                      atr=a, last_t=last_t, verdicts_asof=v_asof, heartbeat=desk.last_tick,
                      view_stale=stale, params=p, review=review)
        if tracker is not None:
            tracker.record(symbol, pub, now, verdicts, v_asof, validator.crit.version)
        board = {"ranking": ranking(pub, atr=a, statuses={i.id: st for i, st in cands}, params=p),
                 "funnel": funnel(cands, verdicts, pub, last_t=last_t, now=now, price=price,
                                  atr=a, review=review, params=p)}
        return now, v_asof, verdicts, view, price, pub, board

    def tick() -> None:
        """Gancho del bróker (cada ~1 min): registra lo publicado y resuelve lo anterior."""
        for sym in desk.symbols:
            try:
                now, v_asof, verdicts, view, *_ = current(sym, wait_s=0.0)
                if view is not None:
                    tracker.refresh(sym, view.path, verdicts, v_asof, now)
            except Exception:  # nunca tumba el ciclo del bróker
                continue

    router.tick = tick  # type: ignore[attr-defined]

    @router.get("/v2/setups")
    def setups(symbol: str = "BTCUSDT") -> dict:
        _check(symbol)
        now, v_asof, _, view, price, pub, board = current(symbol)
        return {"mode": "ANALISIS", "symbol": symbol, "asof": view.path.end if view and view.path
                is not None else None, "now": now, "criteria_version": validator.crit.version,
                "verdicts_asof": v_asof, "price": price, "timeframes": list(p.timeframes),
                "horizon_hours": [0, p.max_hold_h], "source": "bróker simulado (T47) + puerta T49",
                "status": pub.status, "message": pub.message, "validation": pub.validation,
                "discarded": pub.discarded, "setups": pub.setups, "watch": pub.watch,
                "note": NOTE, **board}

    if tracker is not None:
        @router.get("/v2/setups/history")
        def history(symbol: str = "BTCUSDT", limit: int = Query(100, ge=1, le=1000)) -> dict:
            """Publicadas + resolución, señal contra resultado e intervalos sin sugerencia."""
            _check(symbol)
            now, v_asof, verdicts, view, *_ = current(symbol, wait_s=0.0)
            path = view.path if view else None
            resolved = tracker.refresh(symbol, path, verdicts, v_asof, now)
            out = tracker.history(symbol, resolved, verdicts, view.outcomes if view else [], now,
                                  limit, tracker.resolve_watch(symbol, path))
            return {**out, "asof": path.end if path is not None and len(path.t) else None,
                    "criteria_version": validator.crit.version, "verdicts_asof": v_asof}

    return router
