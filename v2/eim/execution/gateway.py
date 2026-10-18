"""Puerta única hacia la ejecución: solo acepta decisiones selladas y aprobadas por el riesgo.

El envío lo hace un ejecutor (`ExecutionService` sobre `SimBroker` o `BinanceTestnetBroker`).
Ningún otro módulo de `eim/` puede abrir posiciones: `.place(` solo se llama aquí y los
endpoints de órdenes solo existen en `execution/binance_testnet.py` (tests/risk/test_gate.py).
Entrada, SL y TP salen de la decisión sellada: no se pueden alterar después de aprobarla.

T45: `ArbGateway` es la puerta equivalente del arbitraje: solo una `ArbDecision` sellada y
aprobada por `ArbRiskEngine` llega a `ArbExecutor.place_arb` (con la cantidad aprobada).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eim.core import Mode
from eim.risk.arb_engine import ArbRiskEngine
from eim.risk.arb_models import ArbDecision
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
    entry: float = 0.0
    sl: float = 0.0
    tp: tuple[float, ...] = ()
    entry_kind: str = "MARKET"           # MARKET | LIMIT (al precio `entry`)


class Executor(Protocol):
    mode: Mode

    def place(self, order: OrderIntent) -> str: ...


class OrderGateway:
    def __init__(self, engine: RiskEngine, broker: Executor) -> None:
        self._engine, self._broker = engine, broker

    def submit(self, decision: RiskDecision, now: int, entry_kind: str = "MARKET") -> str:
        """Verifica la decisión con el motor (lanza `PermissionError` si no autoriza) y envía."""
        self._engine.verify(decision, now)
        if decision.mode != self._broker.mode:
            raise PermissionError(f"decisión en modo {decision.mode.value} y broker en "
                                  f"{self._broker.mode.value}")
        if entry_kind not in ("MARKET", "LIMIT"):
            raise ValueError(f"tipo de entrada no soportado: {entry_kind}")
        return self._broker.place(OrderIntent(
            symbol=decision.symbol, side=decision.side, size=decision.size,
            leverage=decision.leverage, mode=decision.mode, plan_id=decision.plan_id,
            entry=decision.entry, sl=decision.sl, tp=decision.tp, entry_kind=entry_kind))


class ArbExecutorPort(Protocol):
    mode: Mode

    def place_arb(self, decision: ArbDecision) -> str: ...


class ArbGateway:
    def __init__(self, engine: ArbRiskEngine, executor: ArbExecutorPort) -> None:
        self._engine, self._executor = engine, executor

    def submit(self, decision: ArbDecision, now: int) -> str:
        """Verifica la decisión (lanza `PermissionError` si no autoriza) y abre las dos patas."""
        self._engine.verify_arb(decision, now)
        if decision.mode != self._executor.mode:
            raise PermissionError(f"decisión en modo {decision.mode.value} y ejecutor en "
                                  f"{self._executor.mode.value}")
        return self._executor.place_arb(decision)
