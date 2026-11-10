"""Topes de riesgo del libro: riesgo abierto por dirección y freno por drawdown (T-caps)."""

from __future__ import annotations

import pytest

from eim.paper.book import run_profile
from eim.paper.caps import Brake, CapParams, fit_risk
from eim.paper.engine import Outcome
from eim.paper.feedback import Learner
from tests.paper.helpers import H1, T0, idea
from tests.paper.test_feedback_book import MOD, closed


def test_fit_risk_off_by_default_and_scales_down():
    assert fit_risk(CapParams(), 10_000, 5_000, 100.0) == 100.0
    cp = CapParams(max_dir_risk=0.01)                       # tope 100 USDT
    assert fit_risk(cp, 10_000, 0.0, 60.0) == 60.0
    assert fit_risk(cp, 10_000, 70.0, 60.0) == pytest.approx(30.0)   # cabe 30 de 60
    assert fit_risk(cp, 10_000, 95.0, 60.0) == 0.0                   # 5 < 25 % de 60
    assert fit_risk(cp, 10_000, 120.0, 60.0) == 0.0                  # ya excedido


def test_brake_trips_once_and_resets_peak():
    cp, b = CapParams(dd_brake=0.05, dd_pause_hours=24), Brake()
    assert b.closed(cp, 10_000, 10_000, 1_000) is None
    assert b.closed(cp, 9_600, 10_000, 2_000) is None
    assert "drawdown" in (b.closed(cp, 9_400, 10_000, 3_000) or "")
    assert b.activations == 1 and b.peak == 9_400
    assert b.veto(3_000 + 23 * H1) and b.veto(3_000 + 25 * H1) is None
    assert b.closed(CapParams(), 1.0, 10_000, 9_999_999) is None     # sin tope: nunca frena


def _long_lived(k: int, strategy: str) -> Outcome:
    """Posición larga abierta en la hora k que sigue abierta mucho después."""
    i = idea(t=T0 + k * H1, strategy=strategy, family="consenso", iid=f"{strategy}:{k}")
    return Outcome(i, "CERRADA", "TP", T0 + k * H1, 100.0, T0 + 500 * H1, 104.0, gross=0.04, r=2.0)


def test_direction_cap_scales_then_rejects():
    outs = [_long_lived(0, f"s{n}") for n in range(3)]
    base = run_profile(MOD, outs, Learner(outs), 0.005)
    assert len(base.trades) == 3
    capped = run_profile(MOD.model_copy(update={"caps": CapParams(max_dir_risk=0.004)}),
                         outs, Learner(outs), 0.005)
    assert len(capped.trades) == 2                              # la tercera ya no cabe
    risks = sorted(t["qty"] * abs(t["fill"] - t["sl"]) for t in capped.trades)
    assert sum(risks) == pytest.approx(10_000 * 0.004, rel=1e-6)
    assert any("tope de riesgo" in e["text"] for e in capped.events if e["cat"] == "rechazada")


def test_drawdown_brake_blocks_entries_then_resumes():
    outs = [closed(-1.0, k, strategy=f"s{k}") for k in range(2)]
    outs += [closed(1.0, 3, strategy="s3"), closed(1.0, 40, strategy="s40")]
    brake = MOD.model_copy(update={"caps": CapParams(dd_brake=0.004, dd_pause_hours=24)})
    st = run_profile(brake, outs, Learner(outs), 0.005)
    assert st.brake.activations == 1
    assert {t["strategy"] for t in st.trades} == {"s0", "s1", "s40"}   # s3 cae en la pausa
    assert any("freno por drawdown" in e["text"] for e in st.events if e["cat"] == "rechazada")
