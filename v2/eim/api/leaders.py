"""Tablero de líderes en la API (T41): `GET /v2/leaders/board`. Modo ANÁLISIS: no hay ninguna
ruta que copie órdenes. La copia simulada (T42) solo se lee: `GET /v2/leaders/copy` (modo
SIMULADO, saldo virtual), que la escribe el servicio en `data/leaders/copy_sim.json`.

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
from eim.data.copy_store import read_summary
from eim.data.leader_board import MAX_AGE_MS, BoardStore, leaders_snapshot
from eim.data.timeframes import SYMBOLS

MODE = "ANALISIS"
COPY_STALE_MS = 60_000  # el servicio escribe el resumen cada 10 s


class LeaderDesk:
    def __init__(self, root: Path | str, agent: SmartMoneyAgent | None = None,
                 symbols: tuple[str, ...] = SYMBOLS,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.root = root
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

    def copy_payload(self) -> dict:
        sim, now = read_summary(self.root), self.clock()
        age = (now - sim["asof"]) / 1000 if sim else None
        return {"type": "copy_sim", "mode": "SIMULADO", "now": now, "age_s": age,
                "stale": sim is None or age * 1000 > COPY_STALE_MS, "sim": sim}


def build_leaders_router(desk: LeaderDesk) -> APIRouter:
    router = APIRouter(prefix="/v2/leaders", tags=["copy trading"])

    @router.get("/board")
    def board() -> dict:
        """Ranking de líderes con métricas e intervalos, veredicto y motivos, posiciones,
        cambios recientes, cohortes adelante y la señal `smart_money` por símbolo."""
        return desk.payload()

    @router.get("/copy")
    def copy() -> dict:
        """Copia simulada en vivo (T42): subcuentas virtuales, posiciones, rechazos con motivo,
        reconciliación y bitácora reciente. Solo lectura; modo SIMULADO."""
        return desk.copy_payload()

    return router
