"""Contrato de estrategia del backtest y la estrategia completa agentes → síntesis → plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eim.agents.plan import PlanAgent
from eim.core import MarketSnapshot


@dataclass(frozen=True)
class Signal:
    """Orden deseada, decidida con datos hasta el cierre de la última vela del snapshot.

    Se ejecuta SIEMPRE en la apertura de la vela siguiente. `sl`/`tp` son precios absolutos.
    """

    side: int          # +1 largo, −1 corto
    sl: float
    tp: float
    tag: str = ""      # identificador del plan (evita reabrir el mismo)


class Strategy(Protocol):
    """Decide con un snapshot que termina en la última vela cerrada (sin futuro)."""

    def on_bar(self, snapshot: MarketSnapshot) -> Signal | None: ...


class PlanStrategy:
    """Estrategia completa: el agente de plan (structure + levels → síntesis → entrada/SL/TP).

    Opera cada plan VIGENTE una sola vez (por `created_t`). `tp_index` elige TP1 o TP2.
    """

    def __init__(self, agent: PlanAgent | None = None, tp_index: int = 0) -> None:
        self.agent = agent or PlanAgent()
        self.tp_index = tp_index
        self._seen: set[int] = set()

    def on_bar(self, snapshot: MarketSnapshot) -> Signal | None:
        rep = self.agent.run(snapshot)
        plan = rep.metrics.get("plan") if rep.status == "ok" else None
        if not plan or plan["status"] != "VIGENTE" or plan["created_t"] in self._seen:
            return None
        self._seen.add(plan["created_t"])
        tps = plan["tp"]
        tp = tps[min(self.tp_index, len(tps) - 1)]
        return Signal(side=1 if plan["side"] == "long" else -1, sl=plan["sl"], tp=tp,
                      tag=str(plan["created_t"]))
