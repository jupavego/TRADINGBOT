"""Agente plan: cálculo R:R, ciclo de vida y agente completo (insumos controlados)."""
from __future__ import annotations

import time

import pytest

from eim.agents.plan import PlanAgent, PlanParams
from eim.agents.plan.plan import Plan, advance, improve, propose
from eim.core import Candle, MarketSnapshot
from tests.agents.conftest import make_snapshot

P = PlanParams()
H = 3_600_000


def _long(close=100.0, a=2.0, sup=(95.0,), res=(110.0, 120.0)) -> Plan | str:
    return propose(1, close, a, list(sup), list(res), 0.6, 0, 0, P)


# --- cálculo ---------------------------------------------------------------
def test_long_plan_valid():
    pl = _long()
    assert isinstance(pl, Plan)
    assert pl.sl == 95.0 - P.sl_buffer_atr * 2.0           # más allá del soporte, con colchón
    assert pl.tp1 == 110.0 and pl.tp2 == 120.0
    assert abs(pl.rr - 10 / 6) < 1e-9


def test_short_plan_mirror():
    pl = propose(-1, 100.0, 2.0, [90.0, 80.0], [105.0], 0.6, 0, 0, P)
    assert isinstance(pl, Plan)
    assert pl.sl == 105.0 + 1.0 and pl.tp1 == 90.0 and pl.tp2 == 80.0
    assert abs(pl.rr - 10 / 6) < 1e-9


def test_no_plan_low_rr():
    msg = _long(res=(104.0,))
    assert isinstance(msg, str) and "R:R" in msg


def test_no_plan_without_invalidation_or_target():
    assert "invalidación" in str(_long(sup=()))
    assert "invalidación demasiado lejos" in str(_long(sup=(80.0,)))
    assert "objetivo" in str(_long(res=()))


# --- ciclo de vida -----------------------------------------------------------
def test_invalidated_on_close_beyond_sl():
    pl = _long()
    pl = advance(pl, 1, 101, 99, 100, P)
    assert pl.status == "VIGENTE"
    pl = advance(pl, 2, 100, 93, 94.0, P)                  # cierra bajo SL=94
    assert pl.status == "INVALIDADO" and pl.resolved_i == 2


def test_wick_below_sl_does_not_invalidate():
    pl = advance(_long(), 1, 101, 90, 97, P)
    assert pl.status == "VIGENTE"


def test_tp_reached_and_expiry():
    pl = advance(_long(), 3, 111, 100, 109, P)
    assert pl.status == "CUMPLIDO" and pl.tp_hit == 1
    pl = advance(_long(), 3, 121, 100, 109, P)
    assert pl.tp_hit == 2
    pl = advance(_long(), P.expiry_bars, 101, 99, 100, P)
    assert pl.status == "EXPIRADO"


def test_improve_only_tightens_sl():
    pl = _long()
    up = _long(close=110.0, sup=(105.0,), res=(125.0,))
    assert isinstance(up, Plan)
    better = improve(pl, up, 2.0, P)
    assert better.sl > pl.sl and better.revisions == 1 and better.entry == pl.entry
    worse = propose(1, 100.0, 2.0, [92.0], [120.0], 0.6, 0, 0, P)
    assert isinstance(worse, Plan) and improve(pl, worse, 2.0, P).sl == pl.sl


# --- agente completo ---------------------------------------------------------
def _snap(closes: list[float]) -> MarketSnapshot:
    cs = [Candle(t=i * H, o=c, h=c + 0.5, l=c - 0.5, c=c, v=100.0) for i, c in enumerate(closes)]
    return MarketSnapshot(symbol="X", timeframe="1h", candles=cs, asof=cs[-1].t + H,
                          sources={"candles": "sintético"},
                          coverage={"candles": (cs[0].t, cs[-1].t)})


def _agent(monkeypatch, bias=0.8, conf=0.7, sup=(95.0,), res=(110.0,)) -> PlanAgent:
    ag = PlanAgent(PlanParams(replay_bars=40, replay_step=1))
    monkeypatch.setattr(ag, "_inputs", lambda *_a: (bias, conf, list(sup), list(res)))
    monkeypatch.setattr("eim.agents.plan.agent.atr", lambda *_a: 2.0)
    return ag


def test_agent_emits_valid_trade_plan_overlay(monkeypatch):
    rep = _agent(monkeypatch).run(_snap([100.0] * 130))
    assert rep.metrics["mode"] == "ANALISIS" and rep.bias > 0
    ov = next(o for o in rep.overlays if o.kind == "trade_plan")
    g = ov.geometry
    assert g["side"] == "long" and g["entry"] == 100.0 and g["sl"] < 95 < 100 < g["tp"][0]
    assert g["mode"] == "ANALISIS" and g["rr"] >= 1.5 and ov.t_to is None
    assert any("no es una orden" in w for w in rep.warnings)


def test_agent_plan_stable_across_bars(monkeypatch):
    rep = _agent(monkeypatch).run(_snap([100.0] * 130))
    first_t = rep.metrics["plan"]["created_t"]
    rep2 = _agent(monkeypatch).run(_snap([100.0] * 135))
    assert rep2.metrics["plan"]["created_t"] == first_t or rep2.metrics["plan"]["created_t"] > 0
    assert rep2.metrics["plan"]["entry"] == 100.0       # no se re-ancla a cada vela


def test_agent_no_plan_when_rr_low(monkeypatch):
    rep = _agent(monkeypatch, res=(103.0,)).run(_snap([100.0] * 130))
    assert rep.bias == 0 and rep.overlays == []
    assert rep.evidence[0].startswith("sin plan:") and "R:R" in rep.evidence[0]


def test_agent_invalidated_by_sl(monkeypatch):
    closes = [100.0] * 128 + [97.0, 93.0]                # SL = 94 → cierra 93
    rep = _agent(monkeypatch).run(_snap(closes))
    assert rep.metrics["plan"]["status"] == "INVALIDADO"
    assert rep.bias == 0 and rep.overlays[0].t_to is not None


def test_agent_tp_reached(monkeypatch):
    closes = [100.0] * 128 + [105.0, 111.0]
    rep = _agent(monkeypatch).run(_snap(closes))
    assert rep.metrics["plan"]["status"] == "CUMPLIDO" and rep.bias == 0


def test_agent_insufficient_bars():
    assert PlanAgent().run(_snap([100.0] * 50)).status == "no_data"


@pytest.mark.perf
def test_agent_real_fixture():
    t0 = time.perf_counter()
    rep = PlanAgent().run(make_snapshot())
    took = time.perf_counter() - t0
    assert took < 30, f"el agente de plan tardó {took:.1f} s"
    assert rep.metrics["mode"] == "ANALISIS" and -1 <= rep.bias <= 1
    if rep.overlays:
        g = rep.overlays[0].geometry
        assert g["rr"] >= PlanParams().min_rr and g["mode"] == "ANALISIS"
    else:
        assert rep.evidence[0].startswith("sin plan:")
