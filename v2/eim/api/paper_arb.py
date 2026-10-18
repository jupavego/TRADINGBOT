"""Pruebas del arbitraje en el bróker simulado (T45, modo SIMULADO) en la API.

`GET /v2/paper/arbitrage` devuelve el último informe (`data/paper/arb_tests.json`);
`POST /v2/paper/arbitrage/run` (cabecera `X-EIM-Confirm: paper-arb`) corre los tres escenarios
sobre las velas y el funding reales del almacén local. Sin cuenta de Binance ni órdenes reales.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query

from eim.api.execution import confirm
from eim.data.arb_sim_data import load_report, load_sim_series, save_report
from eim.data.store import Store
from eim.paper.arb_tests import run_all


def build_paper_arb_router(store: Store, data_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/v2/paper/arbitrage", tags=["bróker simulado"])
    lock = threading.Lock()

    @router.get("")
    def report() -> dict:
        """Último informe de las pruebas (null si nunca se corrieron)."""
        return {"mode": "SIMULADO", "report": load_report(data_dir)}

    @router.post("/run")
    def run(hold_h: int = Query(48, ge=6, le=240), notional: float = Query(1000.0, gt=0, le=1000),
            x_eim_confirm: str | None = Header(None)) -> dict:
        """Carry abierto→mantenido→cerrado, pata fallida deshecha y corte de red, con el
        ejecutor, el riesgo y la reconciliación de T45 sobre un exchange simulado."""
        confirm(x_eim_confirm, "paper-arb")
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "ya hay una prueba en curso")
        try:
            series = load_sim_series(store, hours=hold_h + 8)
            if series is None:
                raise HTTPException(409, "faltan velas de 1 h de spot y perpetuo en el almacén "
                                    "(sincronizar con `python -m eim.arbitrage.sim sync`)")
            rep = run_all(series, hold_h, notional)
            rep["generated_at"] = int(time.time() * 1000)
            save_report(data_dir, rep)
            return {"mode": "SIMULADO", "report": rep}
        finally:
            lock.release()

    return router
