"""Registro y runner: errores y timeouts degradan, nunca rompen el ciclo."""

from __future__ import annotations

import threading
import time

import pytest

from eim.agents.registry import AgentRegistry, default_registry
from eim.agents.runner import call_with_deadline, run_agents, stuck_for
from eim.core import AgentReport, Candle, MarketSnapshot


def _snap() -> MarketSnapshot:
    c = Candle(t=1000, o=1, h=2, l=0.5, c=1.5, v=1)
    return MarketSnapshot(symbol="X", timeframe="1h", candles=[c], asof=2000)


class _Good:
    id, version, requires = "good", "1.0.0", {"candles"}

    def run(self, snapshot):
        return AgentReport(agent_id=self.id, version=self.version, asof=snapshot.asof,
                           bias=0.5, confidence=0.5, horizon_bars=3)


class _Boom:
    id, version, requires = "boom", "1.0.0", {"candles"}

    def run(self, snapshot):
        raise RuntimeError("falla simulada")


class _Slow:
    id, version, requires = "slow", "1.0.0", {"candles"}

    def run(self, snapshot):
        time.sleep(1.0)
        return _Good().run(snapshot)


def test_exception_does_not_break_runner():
    reps = run_agents([_Good(), _Boom(), _Good()], _snap())
    assert [r.agent_id for r in reps] == ["good", "boom", "good"]
    assert reps[1].status == "degraded" and "falla simulada" in reps[1].warnings[0]
    assert reps[0].status == reps[2].status == "ok"


@pytest.mark.perf
def test_timeout_degrades():
    t0 = time.monotonic()
    reps = run_agents([_Slow(), _Good()], _snap(), timeout=0.1)
    assert reps[0].status == "degraded" and "timeout" in reps[0].warnings[0]
    assert reps[1].status == "ok"
    took = time.monotonic() - t0
    assert took < 0.9, f"con timeout de 0,1 s el runner tardó {took:.2f} s"


def test_empty():
    assert run_agents([], _snap()) == []


def test_registry_versions():
    reg = AgentRegistry()
    a = _Good()
    reg.register(a)
    b = _Good()
    b.version = "1.10.0"
    reg.register(b)
    assert reg.get("good").version == "1.10.0" and reg.get("good", "1.0.0") is a
    with pytest.raises(ValueError):
        reg.register(a)
    with pytest.raises(KeyError):
        reg.get("nope")


def test_default_registry_has_structure():
    assert "structure" in default_registry().ids()


# El CSV fixture (~6 semanas, sin liquidaciones) no alcanza para estos dos: deben dar no_data.
NO_DATA = {"seasonality", "liquidations", "derivatives", "microstructure", "context", "calendar",
           "arbitrage",  # arbitrage: el CSV no trae fotografía de libros (T39)
           "smart_money",  # smart_money: sin tablero de líderes (T41)
           "bots"}  # bots: el snapshot del CSV no trae señales del servicio de bots (T57)


def test_new_agents_registered_and_run():
    from tests.agents.conftest import make_snapshot

    reg = default_registry()
    assert {"structure", "ema", "vwap", "price_action"} <= set(reg.ids())
    reps = run_agents(reg.latest(), make_snapshot())
    assert {r.agent_id for r in reps} == set(reg.ids())
    assert all(r.status in {"ok", "degraded"} for r in reps if r.agent_id not in NO_DATA)
    assert not [r for r in reps if r.status == "degraded" and r.agent_id in {"ema", "price_action"}]
    by_id = {r.agent_id: r for r in reps}
    assert {i: by_id[i].status for i in NO_DATA} == dict.fromkeys(NO_DATA, "no_data")
    assert by_id["elliott"].status == "ok"


# --- T123: plazo común, sin hilos acumulados y llamadas con plazo -----------------------------

class _Hung:
    """Agente que se cuelga hasta que se abra su compuerta."""

    version, requires = "1.0.0", {"candles"}

    def __init__(self, id_: str, gate: threading.Event) -> None:
        self.id, self.gate = id_, gate

    def run(self, snapshot):
        self.gate.wait(10)
        return _Good().run(snapshot)


def _threads(prefix: str) -> int:
    return sum(1 for t in threading.enumerate() if t.name.startswith(prefix) and t.is_alive())


@pytest.mark.perf
def test_deadline_is_common_to_all_agents_not_one_per_agent():
    gate = threading.Event()
    hung = [_Hung(f"hung{i}", gate) for i in range(4)]
    try:
        t0 = time.monotonic()
        reps = run_agents([*hung, _Good()], _snap(), timeout=0.3)
        took = time.monotonic() - t0
    finally:
        gate.set()
    assert [r.status for r in reps] == ["degraded"] * 4 + ["ok"]
    assert took < 0.9, f"4 agentes colgados con plazo 0,3 s tardaron {took:.2f} s (en serie: 1,2)"


def test_a_hung_agent_keeps_one_thread_and_degrades_only_itself():
    gate = threading.Event()
    hung, snap = _Hung("colgado", gate), _snap()
    before = _threads("eim-agent-colgado")
    try:
        first = run_agents([hung, _Good()], snap, timeout=0.05)
        later = [run_agents([hung, _Good()], snap, timeout=0.05) for _ in range(5)]
        assert _threads("eim-agent-colgado") - before == 1      # no uno por vela
    finally:
        gate.set()
    assert "timeout" in first[0].warnings[0] and first[1].status == "ok"
    for reps in later:
        assert reps[0].status == "degraded" and "sigue colgado" in reps[0].warnings[0]
        assert reps[1].status == "ok"                           # el resto no se entera
    for _ in range(200):                                        # suelto: vuelve a correr
        if stuck_for(("agent", "colgado", "1.0.0", "X", "1h")) is None:
            break
        time.sleep(0.01)
    assert run_agents([hung], snap, timeout=1.0)[0].status == "ok"


def test_call_with_deadline_ok_error_timeout_and_busy():
    assert call_with_deadline(("t", 1), lambda: 7, 1.0) == ("ok", 7)
    with pytest.raises(ZeroDivisionError):
        call_with_deadline(("t", 2), lambda: 1 / 0, 1.0)
    gate = threading.Event()
    try:
        assert call_with_deadline(("t", 3), lambda: gate.wait(10), 0.05) == ("timeout", None)
        st, age = call_with_deadline(("t", 3), lambda: 1, 0.05)
        assert st == "busy" and age >= 0                        # no lanza un segundo hilo
    finally:
        gate.set()
    for _ in range(200):
        if stuck_for(("t", 3)) is None:
            break
        time.sleep(0.01)
    assert call_with_deadline(("t", 3), lambda: 1, 1.0) == ("ok", 1)
