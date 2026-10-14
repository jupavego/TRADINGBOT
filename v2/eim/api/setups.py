"""Ruta `GET /v2/setups`: las operaciones intradía mejor valoradas según los agentes (ANALISIS)."""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
from fastapi import APIRouter, HTTPException

from eim.agents.levels.pivots import atr
from eim.api.reports_db import ReportStore
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.synthesis import synthesize
from eim.synthesis.setups import SetupParams, levels_of, suggest

HOUR_MS = 3_600_000
VOL_BARS = 200      # velas para estimar la volatilidad
ATR_PERIOD = 14


def build_setups_router(store: Store, reports: ReportStore,
                        expected: Callable[[], list[str]]) -> APIRouter:
    router = APIRouter()

    @router.get("/v2/setups")
    def setups(symbol: str = "ETHUSDT", tf: str = "1h") -> dict:
        if symbol not in SYMBOLS or tf not in TF_MS:
            raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")
        snap = build_snapshot(store, symbol, tf, VOL_BARS + 1)
        if len(snap.candles) < ATR_PERIOD + 2:
            raise HTTPException(404, f"velas insuficientes para {symbol} {tf}")
        c = np.array([x.c for x in snap.candles])
        h = np.array([x.h for x in snap.candles])
        lo = np.array([x.l for x in snap.candles])
        close = float(c[-1])
        bar_h = TF_MS[tf] / HOUR_MS
        sigma_h = float(np.std(np.diff(np.log(c)))) * close / math.sqrt(bar_h)
        a = atr(h, lo, c, ATR_PERIOD)
        latest = reports.latest(symbol, tf)
        syn = synthesize(latest, expected=expected())
        p = SetupParams()
        out = suggest(close, sigma_h, a, levels_of(latest), syn, p, bar_hours=bar_h)
        return {
            "mode": "ANALISIS", "symbol": symbol, "tf": tf, "asof": snap.asof, "close": close,
            "atr": a, "sigma_h": sigma_h, "horizon_hours": [p.min_hours, p.max_hours],
            "fill_hours": p.fill_hours, "fee_rate": p.fee_rate,
            "bias": syn.bias if syn else None, "confidence": syn.confidence if syn else None,
            "source": snap.sources.get("candles", "almacén local"),
            "setups": [s.model_dump() for s in out],
            "note": "Probabilidades estimadas con un modelo de paseo aleatorio con la deriva de "
                    "la síntesis; no están calibradas. Análisis, no es una orden.",
        }

    return router
