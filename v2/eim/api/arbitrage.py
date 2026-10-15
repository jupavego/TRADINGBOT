"""Escáner de arbitraje en la API (T39): `GET /v2/arbitrage/opportunities` y mensaje WS
`arbitrage`. Modo ANÁLISIS siempre: no hay ninguna ruta que ejecute (T45).

La fotografía la escribe `ArbSync` (en vivo) en `data/arbitrage/`; aquí se lee la última, se
corre el agente `arbitrage` (puro) y se actualizan las alertas cuando llega un escaneo nuevo.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from fastapi import APIRouter

from eim.agents.arbitrage import LABEL, ArbitrageAgent
from eim.agents.arbitrage.rows import all_rows
from eim.arbitrage.alerts import AlertParams, AlertTracker
from eim.core import ArbMarket
from eim.data.arb_store import ArbStore, arb_snapshot

MODE = "ANALISIS"


class ArbDesk:
    """Último resultado del escáner con sus alertas (estado en memoria del proceso)."""

    def __init__(self, store: ArbStore, agent: ArbitrageAgent | None = None,
                 alerts: AlertParams | None = None,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.store, self.agent, self.clock = store, agent or ArbitrageAgent(), clock
        self.tracker = AlertTracker(alerts)
        self._lock = threading.Lock()

    def payload(self, mkt: ArbMarket | None = None) -> dict:
        """Cuerpo de la respuesta y del mensaje WS para la fotografía más reciente.

        El reporte se evalúa a la hora actual (la confianza cae con la edad de la fotografía);
        las alertas solo avanzan una vez por escaneo nuevo."""
        mkt = mkt if mkt is not None else self.store.latest()
        now = self.clock()
        asof = max(now, mkt.asof) if mkt is not None else now
        res, rep = self.agent.analyze(arb_snapshot(mkt, asof))
        alerts = []
        if mkt is not None and res is not None:
            with self._lock:
                alerts = self.tracker.update(res.selection, mkt.asof)
        p = self.tracker.p
        return {
            "type": "arbitrage", "mode": MODE, "label": LABEL, "now": now,
            "scan_asof": mkt.asof if mkt is not None else None,
            "age_s": round((asof - mkt.asof) / 1000, 1) if mkt is not None else None,
            "stale": mkt is None or (asof - mkt.asof) / 1000 > self.agent.params.stale_s,
            "report": rep.model_dump(), "opportunities": all_rows(res) if res else [],
            "alerts": [a.model_dump() for a in alerts],
            "alert_params": {"min_score": p.min_score, "hold_s": p.hold_s},
            "errors": dict(mkt.errors) if mkt is not None else {},
        }


def build_arbitrage_router(desk: ArbDesk) -> APIRouter:
    router = APIRouter(prefix="/v2/arbitrage", tags=["arbitraje"])

    @router.get("/opportunities")
    def opportunities() -> dict:
        """Oportunidades netas (seleccionadas y descartadas con motivo), funding, base,
        alertas y calidad de la fotografía. Importes en USD para el nocional configurado."""
        return desk.payload()

    return router
