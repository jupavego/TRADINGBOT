"""Rutas de solo lectura del escuadrón de bots (T57): señales guardadas y catálogo utilizable."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from eim.bots.card import default_cards
from eim.bots.service import BotService
from eim.data.bots.store import BotSignalStore
from eim.data.timeframes import SYMBOLS, TF_MS

MODE_NOTE = "ANALISIS: los bots solo opinan; no tienen voto en la síntesis ni envían órdenes"


def build_bots_router(store: BotSignalStore, service: BotService) -> APIRouter:
    router = APIRouter()

    @router.get("/v2/bots/signals")
    def signals(symbol: str = "ETHUSDT", tf: str = "1h", bot: str | None = None,
                start: int | None = None, end: int | None = None,
                limit: int = Query(200, ge=1, le=2000)) -> dict:
        if symbol not in SYMBOLS or tf not in TF_MS:
            raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")
        rows = store.query(symbol, tf, start, end, bot, limit)
        return {"mode": MODE_NOTE, "signals": [s.model_dump() for s in rows]}

    @router.get("/v2/bots/catalog")
    def catalog() -> dict:
        active = {a.bot_id for a in service.adapters}
        cards = [{"id": c.id, "name": c.name, "repo": c.repo, "commit_sha": c.commit_sha,
                  "license": c.license.spdx, "mode": c.integration_mode, "class": c.bot_class,
                  "verdict": c.verdict, "approval": c.approval.state,
                  "security_enabled": c.security.enabled, "usable": c.usable,
                  "adapter_active": c.id in active}
                 for c in default_cards().values() if c.usable]
        return {"mode": MODE_NOTE, "bots": cards}

    return router
