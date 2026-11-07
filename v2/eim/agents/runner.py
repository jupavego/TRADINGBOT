"""Ejecutor de agentes: paralelo, con plazo común, y nunca rompe el ciclo.

Plazo (T123, medido en `tests/agents/test_runner.py`): `timeout` segundos **desde el envío**,
común a todos los agentes de la llamada; con k agentes colgados la llamada dura `timeout`, no
k × `timeout` (antes se esperaba agente por agente). Un hilo que excede el plazo no se puede
abortar: queda apuntado como colgado y, mientras siga vivo, ese agente (misma versión, símbolo y
marco) sale degradado sin lanzar otro hilo. Así un agente colgado deja como mucho un hilo por
canal en vez de uno por vela (frontera `agentes.hilos`). Los hilos son daemon: un agente colgado
no impide cerrar el proceso. `call_with_deadline` aplica lo mismo a cualquier etapa (pronóstico).
"""

from __future__ import annotations

import contextvars
import threading
import time
from collections.abc import Callable, Hashable
from typing import Any

from eim.agents.base import degraded_report
from eim.core import Agent, AgentReport, MarketSnapshot
from eim.observability import hooks, queues
from eim.observability.emit import span

DEFAULT_TIMEOUT_S = 30.0

_STUCK: dict[Hashable, float] = {}      # clave → instante (monotónico) en que se abandonó
_LOCK = threading.Lock()


class _Job:
    """Una llamada en un hilo daemon. `finished` y `abandoned` cambian bajo `_LOCK`."""

    def __init__(self, key: Hashable, fn: Callable[[], Any], name: str) -> None:
        self.key, self.fn = key, fn
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None
        self.finished = self.abandoned = False
        ctx = contextvars.copy_context()     # el hilo hereda el tramo en curso (trazas)
        threading.Thread(target=ctx.run, args=(self._run,), name=name, daemon=True).start()

    def _run(self) -> None:
        try:
            self.result = self.fn()
        except BaseException as exc:  # noqa: BLE001 - se entrega a quien espera
            self.error = exc
        finally:
            with _LOCK:
                self.finished = True
                if self.abandoned:
                    _STUCK.pop(self.key, None)
            self.done.set()

    def wait(self, deadline: float) -> bool:
        """True si terminó antes de `deadline`; si no, queda apuntado como colgado."""
        self.done.wait(max(0.0, deadline - time.monotonic()))
        with _LOCK:
            if self.finished:
                return True
            self.abandoned = True
            _STUCK[self.key] = time.monotonic()
            return False


def stuck_for(key: Hashable) -> float | None:
    """Segundos que lleva colgada la última llamada abandonada con `key` (None si no hay)."""
    with _LOCK:
        t = _STUCK.get(key)
    return None if t is None else time.monotonic() - t


def stuck_count(kind: str | None = None) -> int:
    """Llamadas colgadas en este proceso (las de claves `(kind, …)` si se indica)."""
    with _LOCK:
        return sum(1 for k in _STUCK if kind is None or (isinstance(k, tuple) and k[0] == kind))


def call_with_deadline(key: Hashable, fn: Callable[[], Any], timeout: float,
                       frontier: str = "pronostico.hilos") -> tuple[str, Any]:
    """Corre `fn` con plazo. ("ok", resultado) · ("timeout", None) · ("busy", segundos colgado).

    Con "busy" no se lanza otro hilo: la llamada anterior con la misma clave sigue colgada. Los
    errores de `fn` se relanzan tal cual. Descartes y causa quedan en la frontera `frontier`.
    """
    g = queues.gauge(frontier)
    age = stuck_for(key)
    if age is not None:
        g.drop(1, f"{key}: sigue colgado desde hace {age:.0f} s; no se lanza otro")
        return "busy", age
    job = _Job(key, fn, f"eim-deadline-{frontier}")
    ok = job.wait(time.monotonic() + timeout)
    g.seen(stuck_count(key[0] if isinstance(key, tuple) else None))
    if not ok:
        g.drop(1, f"{key}: sin respuesta en {timeout:g} s")
        return "timeout", None
    if job.error is not None:
        raise job.error
    return "ok", job.result


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

    Excepción → `status="degraded"` con el error en `warnings`. El agente que no responde en
    `timeout` segundos desde el envío (plazo común) sale degradado; si sigue colgado de una
    llamada anterior, sale degradado sin lanzar otro hilo.
    """
    if not agents:
        return []
    g = queues.gauge("agentes.hilos")
    obs = hooks.begin_agents(snapshot)       # None sin observabilidad o fuera de una traza
    deadline = time.monotonic() + timeout
    jobs: list[_Job | float] = []
    for a in agents:
        key = ("agent", a.id, a.version, snapshot.symbol, snapshot.timeframe)
        age = stuck_for(key)
        if age is not None:
            g.drop(1, f"{a.id} {snapshot.symbol} {snapshot.timeframe}: sigue colgado")
            jobs.append(age)
            continue
        jobs.append(_Job(key, lambda a=a: _run_one(a, snapshot, obs), f"eim-agent-{a.id}"))
    reports: list[AgentReport] = []
    for agent, job in zip(agents, jobs, strict=True):
        if isinstance(job, float):
            reports.append(degraded_report(
                agent.id, agent.version, snapshot.asof,
                f"sigue colgado de una vela anterior (hace {job:.0f} s): no se lanza otro hilo"))
        elif (ok := job.wait(deadline)) and isinstance(job.result, AgentReport):
            reports.append(job.result)
        elif ok:   # terminó a tiempo pero sin reporte (excepción fuera del guardia)
            reports.append(degraded_report(agent.id, agent.version, snapshot.asof,
                                           f"error: {type(job.error).__name__}: {job.error}"))
        else:
            reports.append(degraded_report(
                agent.id, agent.version, snapshot.asof, f"timeout tras {timeout:g}s"))
            g.drop(1, f"{agent.id} {snapshot.symbol} {snapshot.timeframe}: timeout {timeout:g} s")
            if obs is not None:
                hooks.agent_timeout(obs, agent, reports[-1], timeout)
    g.seen(stuck_count("agent"))
    if obs is not None:
        hooks.after_agents(obs, reports, [a.id for a in agents])
    return reports
