"""Ganchos del bróker fuera de su ciclo (T128, entregable 3)."""

from __future__ import annotations

import asyncio
import sys
import threading
import time

import pytest

from eim.observability import hooks_service
from eim.operation import priority
from eim.paper.hooks import COMPONENT, HookRunner
from eim.paper.service import DeskService


@pytest.fixture
def events(monkeypatch):
    got = []
    monkeypatch.setattr(hooks_service, "beat",
                        lambda cid, **kw: got.append(("beat", cid, kw)))
    monkeypatch.setattr(hooks_service, "service_error",
                        lambda cid, err, **kw: got.append(("error", cid, kw)))
    return got


def test_a_pass_runs_every_hook_in_order_and_one_failure_does_not_stop_the_rest(events):
    seen = []
    r = HookRunner()
    r.add("validacion", lambda: seen.append("v") or True, "validation.gate")
    r.add("libro", lambda: 1 / 0)
    r.add("bots", lambda: seen.append("b") or False, "bots.scoring")
    r.add("setups", lambda: seen.append("s"))
    out = r.run_once()
    assert seen == ["v", "b", "s"]
    assert out["ran"] == ["validacion"] and set(out["ms"]) == {"validacion", "libro", "bots",
                                                               "setups"}
    assert out["errors"] == {"libro": "ZeroDivisionError: division by zero"}
    st = r.status()
    assert st["passes"] == 1 and not st["running"] and st["hooks"]["libro"]["error"]
    assert st["hooks"]["validacion"]["ran"] and not st["hooks"]["bots"]["ran"]
    # latido propio solo de quien trabajó; el del conjunto, degradado por el error
    beats = [(cid, kw) for k, cid, kw in events if k == "beat"]
    assert [c for c, _ in beats] == ["validation.gate", COMPONENT]
    assert beats[1][1]["status"] == "degraded" and beats[1][1]["min_interval_s"] > 0
    assert [(cid, kw["detail"]) for k, cid, kw in events if k == "error"] == [
        (COMPONENT, {"hook": "libro"})]


def test_kicks_during_a_pass_leave_one_more_pass_not_a_queue(events):
    gate, entered = threading.Event(), threading.Event()
    calls = []

    def slow():
        calls.append(1)
        entered.set()
        gate.wait(5)

    r = HookRunner()
    r.add("lento", slow)
    r.start()
    r.kick()
    assert entered.wait(5)
    for _ in range(5):          # cinco ciclos del bróker mientras la pasada sigue
        r.kick()
    gate.set()
    deadline = time.monotonic() + 5
    while r.passes < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.1)
    r.stop()
    assert r.passes == 2 and len(calls) == 2


class _Broker(DeskService):
    def __init__(self, hooks: HookRunner) -> None:
        self.hooks, self.poll_s, self.ticks = hooks, 0.01, 0

    def tick(self) -> int:
        self.ticks += 1
        return 0


def test_the_broker_keeps_ticking_while_a_slow_hook_runs(events):
    """Antes el ciclo esperaba a los ganchos: la validación de 4 h lo callaba minutos."""
    gate = threading.Event()
    r = HookRunner()
    r.add("validacion", lambda: gate.wait(5))
    b = _Broker(r)

    async def run():
        task = asyncio.create_task(b.loop())
        await asyncio.sleep(0.5)
        task.cancel()

    asyncio.run(run())
    still = r.running
    gate.set()
    r.stop()
    assert still and b.ticks >= 10


@pytest.mark.skipif(sys.platform != "win32", reason="prioridad de hilos de Windows")
def test_hooks_run_at_batch_level_and_only_their_thread(events, monkeypatch):
    monkeypatch.setenv(priority.ENV, "on")
    got, done = [], threading.Event()
    r = HookRunner()
    r.add("mide", lambda: got.append(priority.thread_priority()) or done.set())
    main = priority.thread_priority()
    r.start()
    r.kick()
    assert done.wait(5)
    r.stop()
    assert got == [priority.THREAD_LOWEST] and priority.thread_priority() == main


@pytest.mark.skipif(sys.platform != "win32", reason="prioridad de hilos de Windows")
def test_lower_thread_needs_the_switch():
    out = []
    t = threading.Thread(target=lambda: out.extend(
        [priority.lower_thread(), priority.thread_priority(),
         priority.lower_thread(env={priority.ENV: "on"}), priority.thread_priority()]))
    t.start()
    t.join()
    assert out == [False, 0, True, priority.THREAD_LOWEST]
