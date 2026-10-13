"""Salida de los agentes: Overlay y AgentReport."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from eim.core.market import Frozen

OverlayKind = Literal["zone", "level", "channel", "range", "trade_plan", "marker"]
ReportStatus = Literal["ok", "degraded", "no_data"]


class Overlay(Frozen):
    """Elemento que el agente dibuja sobre el gráfico.

    geometry según kind: zone {p_low,p_high}; level {p};
    channel {upper:[(t,p),(t,p)], lower:[(t,p),(t,p)]};
    trade_plan {side,entry,sl,tp:[..],rr}; marker {t,p,action}.
    """

    id: str
    agent_id: str
    kind: OverlayKind
    t_from: int
    t_to: int | None = None  # None = hasta nuevo aviso
    geometry: dict
    label: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = []
    valid_until: int | None = None


class AgentReport(Frozen):
    """Resultado de `Agent.run`."""

    agent_id: str
    version: str
    asof: int
    bias: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    horizon_bars: int = Field(ge=0)
    evidence: list[str] = []
    metrics: dict = {}
    warnings: list[str] = []
    overlays: list[Overlay] = []
    status: ReportStatus = "ok"
