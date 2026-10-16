"""Tablero de líderes en la API (T41): `GET /v2/leaders/board`. Modo ANÁLISIS siempre: no hay
ninguna ruta que copie órdenes (eso es T42, simulado).

El tablero lo escribe el servicio de vigilancia (`python -m eim.leaders run`) en
`data/leaders/` (es el único proceso que puede abrir `leaders.duckdb`); aquí solo se lee y se
corre el agente `smart_money` (puro) por símbolo con el último tablero vigente.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter

from eim.agents.smart_money import SmartMoneyAgent
from eim.copytrading import LABEL
from eim.data.leader_board import MAX_AGE_MS, BoardStore, leaders_snapshot
from eim.data.timeframes import SYMBOLS

MODE = "ANALISIS"


class LeaderDesk:
    def __init__(self, root: Path | str, agent: SmartMoneyAgent | None = None,
                 symbols: tuple[str, ...] = SYMBOLS,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.store, self.agent = BoardStore(root), agent or SmartMoneyAgent()
        self.symbols, self.clock = symbols, clock

    def payload(self) -> dict:
        board, now = self.store.latest(), self.clock()
        signals = {s: self.agent.run(leaders_snapshot(board, s, now)).model_dump()
                   for s in self.symbols}
        return {
            "type": "leaders", "mode": MODE, "label": LABEL, "now": now,
            "board_asof": board.asof if board else None,
            "age_s": round((now - board.asof) / 1000, 1) if board else None,
            "stale": board is None or now - board.asof > MAX_AGE_MS,
            "board": board.model_dump() if board else None, "signals": signals,
        }


def build_leaders_router(desk: LeaderDesk) -> APIRouter:
    router = APIRouter(prefix="/v2/leaders", tags=["copy trading"])

    @router.get("/board")
    def board() -> dict:
        """Ranking de líderes con métricas e intervalos, veredicto y motivos, posiciones,
        cambios recientes, cohortes adelante y la señal `smart_money` por símbolo."""
        return desk.payload()

    return router
