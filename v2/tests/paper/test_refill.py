"""Recarga de capital: ningún perfil se queda sin dinero (decisión del usuario, 2026-10-18).

Si un cierre deja el saldo bajo `refill_below` × el capital inicial, se inyecta lo que falta hasta
el inicial; queda en la bitácora y la rentabilidad y el drawdown no la esconden.
"""

from __future__ import annotations

import pytest

from eim.paper.book import run_profile
from eim.paper.engine import Outcome
from eim.paper.feedback import Learner
from eim.paper.params import PROFILES, FeedbackParams
from eim.paper.summary import profile_summary
from tests.paper.helpers import H1, T0, idea

MOD = next(p for p in PROFILES if p.id == "moderado")
# 20 % de riesgo con peso fijo 1: cada −1 R se lleva el 20 % del saldo
HOT = MOD.model_copy(update={"risk_pct": 0.2, "feedback": FeedbackParams(n_min=10**6,
                                                                         observe_w=1.0)})


def trade(r: float, k: int) -> Outcome:
    """Largo a 100 con SL a 90 y TP a 120, abierto en la hora 2k y cerrado una hora después."""
    i = idea(t=T0 + 2 * k * H1, sl=90.0, tp=120.0, iid=f"s:{k}")
    return Outcome(i, "CERRADA", "TP" if r > 0 else "SL", i.t, 100.0, i.t + H1,
                   100.0 * (1 + 0.1 * r), gross=0.1 * r, r=r)


def test_refill_restores_initial_and_keeps_trading():
    outs = [trade(-1.0, k) for k in range(6)] + [trade(2.0, 6)]
    st = run_profile(HOT, outs, Learner([]), mmr=0.004)
    assert len(st.trades) == 7                              # nunca se queda sin margen
    # 10 000 → 8 000 → 6 400 → 5 120 → 4 096 (< 50 %): recarga de 5 904 hasta 10 000
    (t1, a1), = st.refills[:1]
    assert a1 == pytest.approx(10_000 - 4_096) and t1 == outs[3].exit_t
    assert st.injected == pytest.approx(sum(a for _, a in st.refills))
    ev = [e for e in st.events if e["cat"] == "recarga"]
    assert len(ev) == len(st.refills) and ev[0]["amount"] == pytest.approx(a1)
    assert ev[0]["equity"] == pytest.approx(10_000)
    s = profile_summary(st, Learner([]), [], now=outs[-1].exit_t, mmr=0.004)
    pnl = sum(t["pnl"] for t in st.trades)
    assert s["realized"] == pytest.approx(pnl)               # la recarga no es ganancia
    assert s["injected"] == pytest.approx(st.injected) and s["refills"] == len(st.refills)
    assert s["contributed"] == pytest.approx(10_000 + st.injected)
    assert s["return_pct"] == pytest.approx(s["equity"] / s["contributed"] - 1)
    assert s["max_dd_pct"] > 0.59                            # drawdown sin las recargas


def test_no_refill_above_threshold_or_when_disabled():
    outs = [trade(-1.0, k) for k in range(3)]               # 10 000 → 5 120: aún ≥ 50 %
    assert run_profile(HOT, outs, Learner([]), mmr=0.004).injected == 0
    off = HOT.model_copy(update={"refill_below": 0.0})
    st = run_profile(off, [trade(-1.0, k) for k in range(8)], Learner([]), mmr=0.004)
    assert st.injected == 0 and not st.refills and st.equity < 2_000
    assert profile_summary(st, Learner([]), [], now=T0 + 99 * H1, mmr=0.004)["refills"] == 0
