"""Registro y runner: errores y timeouts degradan, nunca rompen el ciclo."""

from __future__ import annotations

import time

import pytest

from eim.agents.registry import AgentRegistry, default_registry
from eim.agents.runner import run_agents
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


def test_timeout_degrades():
    t0 = time.monotonic()
    reps = run_agents([_Slow(), _Good()], _snap(), timeout=0.1)
    assert reps[0].status == "degraded" and "timeout" in reps[0].warnings[0]
    assert reps[1].status == "ok"
    assert time.monotonic() - t0 < 0.9


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
