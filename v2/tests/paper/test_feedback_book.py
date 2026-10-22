"""Retroalimentación (sin mirar el futuro) y libro por perfil (tamaño, filtros, margen)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.paper.book import leverage_for, liq_price, run_profile
from eim.paper.engine import Outcome
from eim.paper.feedback import Learner, judge, strategy_stats
from eim.paper.params import PROFILES, FeedbackParams, ProfileParams
from tests.paper.helpers import H1, T0, idea

FB = FeedbackParams(n_min=5, prior_n=5, half_life=50, z_pause=1.0)
MOD = next(p for p in PROFILES if p.id == "moderado")
CONS = next(p for p in PROFILES if p.id == "conservador")


def closed(r: float, k: int, strategy: str = "s", family: str = "consenso", side: int = 1,
           fill: float = 100.0, sl: float = 98.0) -> Outcome:
    """Operación cerrada en la hora `k` (señal en k, llenado en k, cierre en k + 1)."""
    i = idea(t=T0 + k * H1, strategy=strategy, family=family, side=side, sl=sl if side > 0
             else 102.0, tp=104.0 if side > 0 else 96.0, iid=f"{strategy}:{k}")
    risk = abs(fill - i.sl) / fill
    return Outcome(i, "CERRADA", "TP" if r > 0 else "SL", T0 + k * H1, fill,
                   T0 + (k + 1) * H1, fill * (1 + side * r * risk), gross=r * risk, r=r)


def test_judge_states_and_bounds():
    assert judge([], FB).state == "observacion"
    assert judge([1.0] * 3, FB).state == "observacion"
    j = judge([-1.0] * 20, FB)
    assert j.state == "pausa" and j.weight == 0
    up = judge([1.5, -1.0] * 15, FB)
    assert up.state == "reforzada" and 1 < up.weight <= FB.w_max
    assert judge([0.05, -0.05] * 10, FB).state == "activa"


def test_learner_uses_only_closed_before_t():
    outs = [closed(-1.0, k) for k in range(10)]
    lr = Learner(outs)
    assert lr.at("s@1h", T0, FB).n == 0                  # nada cerrado aún
    assert lr.at("s@1h", T0 + 5 * H1, FB).n == 5         # cierres en 1..5 h (exit_t ≤ t)
    assert lr.at("s@1h", T0 + 5 * H1 - 1, FB).n == 4
    assert lr.at("s@1h", T0 + 99 * H1, FB).state == "pausa"


def test_stats_and_control_comparison():
    outs = ([closed(1.0, k) for k in range(8)] + [closed(-1.0, k, "ctrl", "control")
                                                  for k in range(8)])
    infos = [{"id": f"{k}@1h", "name": k.upper(), "family": f, "timeframe": "1h"}
             for k, f in (("s", "consenso"), ("ctrl", "control"), ("z", "agentes"))]
    rows = strategy_stats(outs, infos)
    s, c, z = rows
    assert s["n"] == 8 and s["win_rate"] == 1 and s["mean_r"] == 1 and s["vs_control"] == 2
    assert s["p"] is not None and s["p_holm"] >= s["p"]
    assert z["n"] == 0 and z["mean_r"] is None and z["judgement"]["state"] == "observacion"
    assert c["max_dd_r"] == 8


def test_profile_sizing_and_pnl_consistent_with_r():
    o = closed(2.0, 0)
    st = run_profile(MOD, [o], Learner([o]), mmr=0.004)
    tr = st.trades[0]
    risk_usd = MOD.initial_equity * MOD.risk_pct * MOD.feedback.observe_w
    assert tr["pnl"] == pytest.approx(2.0 * risk_usd)
    assert st.equity == pytest.approx(MOD.initial_equity + tr["pnl"])
    lev = tr["leverage"]
    assert 1 <= lev <= MOD.max_leverage
    liq = liq_price(1, 100.0, lev, 0.004)
    assert (100 - liq) >= MOD.liq_buffer * 2 * 0.99   # liquidación lejos del SL
    assert [e["cat"] for e in st.events] == ["orden", "llenada", "tp"]


def test_conservative_filters():
    against = replace(closed(1.0, 0).idea, syn_bias=-0.5)
    o1 = replace(closed(1.0, 0), idea=against)
    o2 = closed(1.0, 2, "contra", "contrarias")
    open_cons = CONS.model_copy(update={"feedback": CONS.feedback.model_copy(
        update={"observe_w": 0.5})})                         # sin el filtro de «solo probado»
    st = run_profile(open_cons, [o1, o2], Learner([]), mmr=0.004)
    assert [e["cat"] for e in st.events] == ["rechazada"]   # contrarias: fuera del universo
    assert "síntesis" in st.events[0]["text"] and not st.trades
    st = run_profile(CONS, [closed(1.0, 0)], Learner([]), mmr=0.004)
    assert "observación" in st.events[0]["text"]             # Conservador: solo lo probado


def test_capacity_and_hedge():
    p = ProfileParams(**{**MOD.model_dump(), "max_open": 1, "allow_hedge": False})
    a = Outcome(idea(t=T0, iid="a"), "ABIERTA", "", T0, 100.0, mark=101.0, gross=0.01)
    b = Outcome(idea(t=T0 + H1, side=-1, sl=102, tp=96, iid="b"), "ABIERTA", "", T0 + H1, 100.0,
                mark=101.0, gross=-0.01)
    st = run_profile(p, [a, b], Learner([]), mmr=0.004)
    assert len(st.slots) == 1 and "cupo" in st.events[-1]["text"]
    p2 = ProfileParams(**{**MOD.model_dump(), "allow_hedge": False})
    st2 = run_profile(p2, [a, b], Learner([]), mmr=0.004)
    assert "opuesto" in st2.events[-1]["text"]


def test_paused_strategy_rejected_and_logged():
    hist = [closed(-1.0, k) for k in range(12)]
    late = closed(1.0, 40)
    st = run_profile(MOD, hist + [late], Learner(hist + [late]), mmr=0.004)
    cats = [e["cat"] for e in st.events]
    assert "aprendizaje" in cats and cats[-1] == "rechazada"
    assert "pausa" in st.events[-1]["text"]


def test_trade_paused_profile_takes_paused_strategy_at_min_weight():
    hist = [closed(-1.0, k) for k in range(12)]
    late = closed(1.0, 40)
    bold = MOD.model_copy(update={"trade_paused": True})
    st = run_profile(bold, hist + [late], Learner(hist + [late]), mmr=0.004)
    order = next(e for e in st.events if e["cat"] == "orden" and e["idea"] == late.idea.id)
    assert order["paused"] and order["weight"] == bold.feedback.w_min
    assert st.trades[-1]["id"] == late.idea.id and st.trades[-1]["weight"] == bold.feedback.w_min
    assert next(p for p in PROFILES if p.id == "agresivo").trade_paused
    assert not any(p.trade_paused for p in PROFILES if p.id != "agresivo")


def test_cancel_releases_margin():
    o = Outcome(idea(kind="limit", entry=99, sl=97, fill_h=2, iid="L"), "CANCELADA", "NO_LLENADA",
                exit_t=T0 + 2 * H1)
    st = run_profile(MOD, [o], Learner([]), mmr=0.004)
    assert st.used == pytest.approx(0) and not st.slots
    assert [e["cat"] for e in st.events] == ["orden", "cancelada"]


def test_leverage_respects_cap_and_buffer():
    assert leverage_for(MOD, 100, 98, 0.004) <= MOD.max_leverage
    assert leverage_for(MOD, 100, 80, 0.004) == 2      # SL a 20 %: 1/(2·0,2 + 0,004) → 2


def test_cost_and_htf_filters():
    tight = Outcome(idea(sl=99.5, tp=101, iid="tight"), "ABIERTA", "", T0, 100.0, mark=100.0)
    st = run_profile(MOD, [tight], Learner([]), mmr=0.004)       # 0,0016 / 0,005 = 0,32 R
    assert "costo estimado" in st.events[-1]["text"]
    against = Outcome(replace(idea(iid="against"), htf=-1), "ABIERTA", "", T0, 100.0, mark=100.0)
    st = run_profile(MOD, [against], Learner([]), mmr=0.004)
    assert "tendencia del marco mayor" in st.events[-1]["text"]
    loose = MOD.model_copy(update={"require_htf": False})        # sin exigir la tendencia
    st = run_profile(loose, [against], Learner([]), mmr=0.004)
    assert [e["cat"] for e in st.events] == ["orden", "llenada"]

