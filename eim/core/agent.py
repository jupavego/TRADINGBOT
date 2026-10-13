"""Protocolo de agente: función pura sobre el snapshot."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from eim.core.market import MarketSnapshot
from eim.core.report import AgentReport


@runtime_checkable
class Agent(Protocol):
    """Analizador puro: sin red, sin disco, sin estado global; determinista."""

    id: str
    version: str
    requires: set[str]  # campos del snapshot que necesita

    def run(self, snapshot: MarketSnapshot) -> AgentReport: ...
