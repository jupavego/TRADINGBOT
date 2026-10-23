"""T48: marcos múltiples, causa de cada pérdida y pausa por contexto (sin mirar el futuro)."""

from __future__ import annotations

from dataclasses import replace

from eim.backtest.params import ZERO_COSTS
from eim.paper.book import run_profile
from eim.paper.catalog import generate_ideas
from eim.paper.engine import Outcome, Path, simulate
from eim.paper.feedback import FeedbackParams, Learner, context_key, timeframe_stats
from eim.paper.params import PROFILES, ExecParams
from tests.paper.helpers import H1, M15, T0, flat, idea, tp_mode, with_bar
from tests.paper.test_strategies import ctx_for, walk

ZERO = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
MOD = tp_mode(next(p for p in PROFILES if p.id == "moderado"))  # salida TP (T109)


def test_hold_scales_with_timeframe_but_setups_do_not():
    cs4 = walk(700, t0=T0)                      # serie con paso de 1 h usada como «4 h»
    four = [c.model_copy(update={"t": T0 + i * 4 * H1}) for i, c in enumerate(cs4)]
    ctxs = [{**ctx_for(four[500]), "t": four[500].t + 4 * H1}]
    ideas = {i.strategy: i for i in generate_ideas(ctxs, four, "X", 4 * H1, timeframe="4h")}
    assert ideas["consenso_sintesis"].hold_ms == 24 * 4 * H1          # 24 velas de 4 h
    assert ideas["sugerencia_1"].hold_ms == 36 * H1                   # horas absolutas
    assert ideas["consenso_sintesis"].sid == "consenso_sintesis@4h"
    assert all(i.timeframe == "4h" and ":4h:" in i.id for i in ideas.values())


def test_loss_causes():
    base = flat(40)
    sl_fast = simulate(idea(), Path(with_bar(base, 1, 100, 100.1, 97.5, 98)), ZERO)
    assert sl_fast.cause == "sl_rapido"
    near = with_bar(with_bar(base, 1, 100, 103.2, 99.9, 103), 6, 103, 103.1, 97.5, 98)
    assert simulate(idea(), Path(near), ZERO).cause == "casi_tp"       # llegó a 3,2 de 4
    late = with_bar(with_bar(base, 1, 100, 100.6, 99.9, 100.5), 8, 100, 100.1, 97.5, 98)
    assert simulate(idea(), Path(late), ZERO).cause == "direccion"
    timed = simulate(idea(hold_h=1), Path(with_bar(base, 3, 99.9, 99.9, 99.5, 99.6)), ZERO)
    assert timed.reason == "TIEMPO" and timed.cause in ("tiempo", None)
    win = simulate(idea(), Path(with_bar(base, 5, 100, 105, 99.5, 104.5)), ZERO)
    assert win.cause is None
    costly = simulate(idea(hold_h=1), Path(with_bar(base, 2, 100, 100.05, 99.9, 100)),
                      ExecParams())
    assert costly.cause in ("costos", "tiempo")


def _closed(r: float, k: int, regime: str, side: int = 1) -> Outcome:
    i = replace(idea(t=T0 + k * H1, side=side, sl=98 if side > 0 else 102,
                     tp=104 if side > 0 else 96, iid=f"c{k}"), regime=regime)
    return Outcome(i, "CERRADA", "TP" if r > 0 else "SL", i.t, 100.0, i.t + H1, 100.0,
                   gross=r * 0.02, r=r)


def test_context_learning_pauses_only_that_context():
    fb = FeedbackParams(n_min=5, prior_n=5, z_pause=0.0)
    hist = ([_closed(-1.0, k, "range") for k in range(10)]
            + [_closed(1.0, 20 + k, "trend_up") for k in range(10)])
    lr = Learner(hist)
    assert lr.at("s@1h", T0 + 99 * H1, fb).state != "pausa"           # la estrategia sigue viva
    bad = replace(idea(t=T0 + 50 * H1), regime="range")
    good = replace(idea(t=T0 + 50 * H1), regime="trend_up")
    assert lr.context_at(bad, bad.t, fb).state == "pausa"
    assert lr.context_at(good, good.t, fb).state != "pausa"
    assert lr.context_at(bad, T0, fb).n == 0                         # nada cerrado aún
    assert context_key(bad) == "s@1h|range|largo"


def test_profile_rejects_paused_context_and_logs_it():
    p = MOD.model_copy(update={"feedback": FeedbackParams(n_min=5, prior_n=5, z_pause=0.0)})
    hist = ([_closed(-1.0, k, "range") for k in range(10)]
            + [_closed(1.0, 20 + k, "trend_up") for k in range(10)])
    late = Outcome(replace(idea(t=T0 + 60 * H1, iid="late"), regime="range"), "ABIERTA", "",
                   T0 + 60 * H1, 100.0, mark=100.0)
    st = run_profile(p, hist + [late], Learner(hist), mmr=0.004)
    last = [e for e in st.events if e["idea"] == "late"]
    assert last[-1]["cat"] == "rechazada" and "contexto en pausa" in last[-1]["text"]
    assert any(e["cat"] == "aprendizaje" and e["text"] == "contexto en pausa" for e in st.events)


def test_timeframe_stats_and_sid_gating():
    a = Outcome(replace(idea(t=T0), timeframe="15m"), "CERRADA", "TP", T0, 100.0, T0 + M15,
                104.0, gross=0.04, r=2.0)
    b = Outcome(idea(t=T0), "CERRADA", "SL", T0, 100.0, T0 + H1, 98.0, gross=-0.02, r=-1.0)
    rows = {r["timeframe"]: r for r in timeframe_stats([a, b])}
    assert rows["15m"]["mean_r"] == 2.0 and rows["1h"]["win_rate"] == 0.0
    assert a.idea.sid != b.idea.sid
