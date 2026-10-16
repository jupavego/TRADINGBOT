"""Motor del bróker simulado: llenado, salidas conservadoras, costos y funding (T47)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.backtest.params import ZERO_COSTS
from eim.paper.engine import Path, run_shadow, simulate
from eim.paper.params import ExecParams
from tests.paper.helpers import H1, M15, T0, flat, idea, with_bar

ZERO = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)


def test_market_long_hits_tp_at_open_fill():
    cs = with_bar(flat(20), 5, 100, 105, 99.5, 104.5)
    o = simulate(idea(), Path(cs), ZERO)
    assert (o.status, o.reason) == ("CERRADA", "TP")
    assert o.fill == 100 and o.fill_t == T0 and o.exit == 104
    assert o.exit_t == T0 + 5 * M15 + M15          # se sabe al cierre de la vela
    assert o.r == pytest.approx(2.0)


def test_sl_before_tp_in_same_bar():
    cs = with_bar(flat(20), 3, 100, 105, 97, 101)
    o = simulate(idea(), Path(cs), ZERO)
    assert o.reason == "SL" and o.exit == 98 and o.r == pytest.approx(-1.0)


def test_gap_through_sl_fills_at_open():
    cs = with_bar(flat(20), 3, 96, 96.5, 95, 96)
    o = simulate(idea(), Path(cs), ZERO)
    assert o.reason == "SL" and o.exit == 96 and o.r == pytest.approx(-2.0)


def test_short_mirror():
    cs = with_bar(flat(20), 4, 100, 100.5, 95.5, 96)
    o = simulate(idea(side=-1, sl=102, tp=96), Path(cs), ZERO)
    assert o.reason == "TP" and o.r == pytest.approx(2.0)


def test_limit_fill_then_tp():
    cs = with_bar(with_bar(flat(20), 2, 100, 100.2, 98.9, 99.5), 6, 100, 104.2, 99.8, 104)
    o = simulate(idea(kind="limit", entry=99, fill_h=2), Path(cs), ZERO)
    assert o.fill == 99 and o.fill_t == T0 + 2 * M15
    assert o.reason == "TP" and o.r == pytest.approx(5.0)


def test_limit_cancelled_when_target_reached_first():
    cs = with_bar(flat(20), 2, 100, 104.5, 99.8, 104)
    o = simulate(idea(kind="limit", entry=99, fill_h=2), Path(cs), ZERO)
    assert (o.status, o.reason) == ("CANCELADA", "OBJETIVO_SIN_LLENAR")


def test_limit_expires_or_stays_pending():
    o = simulate(idea(kind="limit", entry=99, fill_h=2), Path(flat(16)), ZERO)
    assert (o.status, o.reason, o.exit_t) == ("CANCELADA", "NO_LLENADA", T0 + 2 * H1)
    o = simulate(idea(kind="limit", entry=99, fill_h=2), Path(flat(4)), ZERO)
    assert o.status == "PENDIENTE"


def test_limit_fill_and_sl_in_same_bar_is_sl():
    cs = with_bar(flat(20), 2, 100, 100.2, 97.5, 98)
    o = simulate(idea(kind="limit", entry=99, fill_h=2), Path(cs), ZERO)
    assert o.reason == "SL" and o.exit == 98 and o.r == pytest.approx(-1.0)


def test_time_exit_at_open():
    o = simulate(idea(hold_h=1), Path(flat(20)), ZERO)
    assert o.reason == "TIEMPO" and o.exit_t == T0 + H1 and o.r == pytest.approx(0.0)


def test_open_at_end_and_pending_without_data():
    o = simulate(idea(), Path(flat(5)), ZERO)
    assert o.status == "ABIERTA" and o.mark == 100 and o.exit_t is None
    assert simulate(idea(t=T0 + 10 * H1), Path(flat(5)), ZERO).status == "PENDIENTE"


def test_market_geometry_rejected_when_open_beyond_sl():
    cs = with_bar(flat(20), 0, 97, 97.5, 96.5, 97)
    o = simulate(idea(), Path(cs), ZERO)
    assert (o.status, o.reason) == ("RECHAZADA", "GEOMETRIA")


def test_costs_reduce_r():
    cs = with_bar(flat(20), 5, 100, 105, 99.5, 104.5)
    o = simulate(idea(), Path(cs), ExecParams())
    assert o.fill > 100                       # el deslizamiento perjudica al comprador
    assert 1.7 < o.r < 2.0 and o.fee_in > 0 and o.fee_out > 0


def test_funding_real_and_assumed():
    t8 = (T0 // (8 * H1) + 1) * 8 * H1        # próximo cobro de funding
    cs = flat(int((t8 - T0) / M15) + 20)        # termina antes del siguiente cobro
    p = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0002)
    real = simulate(idea(hold_h=24), Path(cs, [(t8, 0.001)]), p)
    assert real.funding == pytest.approx(0.001) and not real.funding_assumed
    assumed = simulate(idea(hold_h=24), Path(cs, []), p)
    assert assumed.funding == pytest.approx(0.0002) and assumed.funding_assumed
    short = simulate(idea(side=-1, sl=102, tp=96, hold_h=24), Path(cs, [(t8, 0.001)]), p)
    assert short.funding == pytest.approx(-0.001)   # el corto cobra


def test_shadow_one_live_idea_per_strategy():
    cs = with_bar(flat(40), 10, 100, 105, 99.5, 104.5)
    ideas = [idea(t=T0, iid="a"), idea(t=T0 + M15, iid="b"),
             idea(t=T0 + 13 * M15 + H1, iid="c"), idea(t=T0 + M15, strategy="otra", iid="d")]
    outs = run_shadow(ideas, Path(cs), ZERO)
    assert [o.idea.id for o in outs] == ["a", "b", "c"][0:1] + ["d", "c"]
    assert outs[0].reason == "TP"


def test_shadow_key_dedupe():
    cs = with_bar(flat(60), 3, 100, 105, 99.5, 104.5)
    ideas = [idea(t=T0, key="plan:1", iid="a"), idea(t=T0 + 3 * H1, key="plan:1", iid="b"),
             idea(t=T0 + 4 * H1, key="plan:2", iid="c")]
    assert [o.idea.id for o in run_shadow(ideas, Path(cs), ZERO)] == ["a", "c"]


def test_breakeven_plus_after_one_r():
    # +1 R (102) en la vela 2; la vela 4 vuelve: el SL ya está en entrada + costo + 0,1 R
    cs = with_bar(with_bar(with_bar(flat(30), 2, 100, 102.2, 99.9, 102), 3, 102, 102.3, 101.5,
                           101.6), 4, 101, 101.1, 97.5, 97.8)
    o = simulate(idea(), Path(cs), ZERO)
    lock_r = 0.1 + ZERO.est_cost_frac * 100 / 2               # +0,1 R neto + costo estimado en R
    assert o.reason == "BE" and o.exit == pytest.approx(100 + 2 * lock_r)
    assert o.r == pytest.approx(lock_r)
    assert o.cause is None                                     # cubre costos: no es pérdida
    off = simulate(idea(), Path(cs), ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0,
                                                 be_trigger_r=0))
    assert off.reason == "SL" and off.r == pytest.approx(-1.0)


def test_breakeven_trigger_and_sl_same_bar_is_sl():
    cs = with_bar(flat(30), 2, 100, 102.5, 97.5, 98)
    assert simulate(idea(), Path(cs), ZERO).reason == "SL"


def test_breakeven_only_in_configured_timeframes():
    cs = with_bar(with_bar(with_bar(flat(30), 2, 100, 102.2, 99.9, 102), 3, 102, 102.3, 101.5,
                           101.6), 4, 101, 101.1, 97.5, 97.8)
    o = simulate(replace(idea(), timeframe="15m"), Path(cs), ZERO)
    assert o.reason == "SL"                                     # 15 m: sin break-even

