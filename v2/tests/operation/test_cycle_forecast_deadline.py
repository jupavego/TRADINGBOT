"""T123: un pronóstico colgado no para el ciclo de operación.

Antes el ciclo llamaba al pronóstico sin plazo: si se colgaba, no había decisión, ni
reconciliación, ni reglas del kill-switch. Ahora tiene plazo, se salta, se registra y la vuelta
siguiente no lanza otro hilo mientras el anterior siga colgado.
"""

from __future__ import annotations

import threading
import time

from eim.agents import runner
from eim.operation import cycle as cyc
from eim.operation.cycle import OperationCycle, OperationParams


class Log:
    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def write(self, event, level="info", **kw) -> None:
        self.rows.append((event, kw))


class Reports:
    def latest(self, sym, tf):
        return []

    def save(self, sym, tf, reps) -> None:
        self.saved = reps


def test_hung_forecast_is_skipped_within_its_deadline(monkeypatch):
    monkeypatch.setattr(cyc, "build_snapshot", lambda *a, **k: object())
    monkeypatch.setattr(cyc, "run_agents", lambda agents, snap, timeout: [])
    monkeypatch.setattr(cyc.hooks, "snapshot_fetches", lambda *a: None)
    gate, calls = threading.Event(), []

    class Hung:
        def run(self, sym, tf):
            calls.append(sym)
            gate.wait(10)

    c = OperationCycle.__new__(OperationCycle)
    c.store, c.reports, c.bots, c.forecaster, c.log = None, Reports(), None, Hung(), Log()
    c.registry = type("R", (), {"latest": lambda self: []})()
    c.desk = type("D", (), {"mode": None})()
    c.p = OperationParams(forecast_timeout_s=0.1)
    try:
        t0 = time.monotonic()
        c._run_agents("BTCUSDT", "1h", 1)
        c._run_agents("BTCUSDT", "1h", 2)              # sigue colgado: ni espera ni otro hilo
        took = time.monotonic() - t0
    finally:
        gate.set()
    assert took < 2.0 and calls == ["BTCUSDT"]
    errs = [kw["error"] for ev, kw in c.log.rows if ev == "pronostico_fallido"]
    assert len(errs) == 2 and "timeout" in errs[0] and "busy" in errs[1]
    for _ in range(200):
        if runner.stuck_for(("forecast", "BTCUSDT", "1h")) is None:
            break
        time.sleep(0.01)
