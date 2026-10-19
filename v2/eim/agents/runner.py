"""Ejecutor de agentes: paralelo, con timeout, y nunca rompe el ciclo."""

from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from eim.agents.base import degraded_report
from eim.core import Agent, AgentReport, MarketSnapshot
from eim.observability import hooks
from eim.observability.emit import span

DEFAULT_TIMEOUT_S = 30.0


def _run_one(agent: Agent, snapshot: MarketSnapshot,
             obs: hooks.AgentRunCtx | None = None) -> AgentReport:
    if obs is None:
        return _guarded(agent, snapshot)[0]
    with span(f"agent.{agent.id}", trace_id=obs.trace_id, inputs=[obs.snap_ref]) as sp:
        obs.runs[agent.id] = sp.run_id
        rep, failed = _guarded(agent, snapshot)
        if failed:
            sp.set(status="error", detail={"error": rep.warnings[0] if rep.warnings else ""})
        hooks.agent_signal(obs, rep, failed=failed, run_id=sp.run_id)
        return rep


def _guarded(agent: Agent, snapshot: MarketSnapshot) -> tuple[AgentReport, bool]:
    try:
        return agent.run(snapshot), False
    except Exception as exc:  # un agente roto no tumba el ciclo
        return degraded_report(
            agent.id, agent.version, snapshot.asof, f"error: {type(exc).__name__}: {exc}"
        ), True


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
    obs = hooks.begin_agents(snapshot)       # None sin observabilidad o fuera de una traza
    try:
        # cada hilo hereda el tramo en curso (los eventos de los agentes cuelgan de la traza)
        futures = [pool.submit(contextvars.copy_context().run, _run_one, a, snapshot, obs)
                   for a in agents]
        reports: list[AgentReport] = []
        for agent, fut in zip(agents, futures, strict=True):
            try:
                reports.append(fut.result(timeout=timeout))
            except FutureTimeout:
                reports.append(degraded_report(
                    agent.id, agent.version, snapshot.asof, f"timeout tras {timeout:g}s"
                ))
                if obs is not None:
                    hooks.agent_timeout(obs, agent, reports[-1], timeout)
        if obs is not None:
            hooks.after_agents(obs, reports, [a.id for a in agents])
        return reports
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
