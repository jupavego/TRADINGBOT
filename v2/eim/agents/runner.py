"""Ejecutor de agentes: paralelo, con timeout, y nunca rompe el ciclo."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from eim.agents.base import degraded_report
from eim.core import Agent, AgentReport, MarketSnapshot

DEFAULT_TIMEOUT_S = 30.0


def _run_one(agent: Agent, snapshot: MarketSnapshot) -> AgentReport:
    try:
        return agent.run(snapshot)
    except Exception as exc:  # un agente roto no tumba el ciclo
        return degraded_report(
            agent.id, agent.version, snapshot.asof, f"error: {type(exc).__name__}: {exc}"
        )


def run_agents(
    agents: list[Agent], snapshot: MarketSnapshot, timeout: float = DEFAULT_TIMEOUT_S
) -> list[AgentReport]:
    """Ejecuta los agentes en paralelo; devuelve un reporte por agente, en el mismo orden.

    Excepción → `status="degraded"` con el error en `warnings`. Si un agente excede `timeout`
    (segundos desde el envío) se devuelve un reporte degradado; su hilo no se puede abortar,
    pero ya no bloquea el ciclo.
    """
    if not agents:
        return []
    pool = ThreadPoolExecutor(max_workers=len(agents), thread_name_prefix="eim-agent")
    try:
        futures = [pool.submit(_run_one, a, snapshot) for a in agents]
        reports: list[AgentReport] = []
        for agent, fut in zip(agents, futures, strict=True):
            try:
                reports.append(fut.result(timeout=timeout))
            except FutureTimeout:
                reports.append(degraded_report(
                    agent.id, agent.version, snapshot.asof, f"timeout tras {timeout:g}s"
                ))
        return reports
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
