"""Utilidades comunes de agentes: reportes vacíos/degradados con el contrato `AgentReport`."""

from __future__ import annotations

from typing import Literal

from eim.core import Agent, AgentReport

__all__ = ["Agent", "degraded_report", "no_data_report"]


def _empty(
    agent_id: str, version: str, asof: int, status: Literal["degraded", "no_data"], reason: str
) -> AgentReport:
    return AgentReport(
        agent_id=agent_id, version=version, asof=asof, bias=0, confidence=0,
        horizon_bars=0, status=status, warnings=[reason],
    )


def no_data_report(agent_id: str, version: str, asof: int, reason: str) -> AgentReport:
    """Faltan datos requeridos: sesgo 0, confianza 0."""
    return _empty(agent_id, version, asof, "no_data", reason)


def degraded_report(agent_id: str, version: str, asof: int, reason: str) -> AgentReport:
    """El agente falló (excepción/timeout): el ciclo continúa sin su aporte."""
    return _empty(agent_id, version, asof, "degraded", reason)
