"""Puerta única hacia la ejecución: solo acepta decisiones selladas y aprobadas por el riesgo.

El envío real lo implementa un `Broker` (T30: testnet). Ningún otro módulo de `eim/` puede
hablar con un exchange para operar (lo comprueba `tests/risk/test_gate.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eim.core import Mode
from eim.risk.engine import RiskEngine
from eim.risk.models import RiskDecision


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: int
    size: float
    leverage: float
    mode: Mode
    plan_id: str


class Broker(Protocol):
    mode: Mode

    def place(self, order: OrderIntent) -> str: ...


class OrderGateway:
    def __init__(self, engine: RiskEngine, broker: Broker) -> None:
        self._engine, self._broker = engine, broker

    def submit(self, decision: RiskDecision, now: int) -> str:
        """Verifica la decisión con el motor (lanza `PermissionError` si no autoriza) y envía."""
        self._engine.verify(decision, now)
        if decision.mode != self._broker.mode:
            raise PermissionError(f"decisión en modo {decision.mode.value} y broker en "
                                  f"{self._broker.mode.value}")
        return self._broker.place(OrderIntent(
            symbol=decision.symbol, side=decision.side, size=decision.size,
            leverage=decision.leverage, mode=decision.mode, plan_id=decision.plan_id))
