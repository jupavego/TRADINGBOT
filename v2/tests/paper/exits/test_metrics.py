"""T131 — las métricas de §5.3, con los casos que motivan cada una (el libro real de T129).

La más importante es la **devolución desde el MFE**: con la escalera, 307 operaciones cerraron con
un acierto del 75,6 % y una ganadora media de +0,108 R aunque el precio hubiera llegado mucho más
lejos. Una métrica que no mide eso no habría visto el defecto.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.paper.exits import metrics as mt
from tests.paper.exits.helpers import series, trade

RNG = np.random.default_rng(131)


def test_the_empty_case_says_nothing_instead_of_inventing_zeros():
    assert mt.summary([]) == {"n": 0}
    assert mt.cvar(np.array([])) is None
    assert mt.sharpe_sortino([]) == (None, None)


def test_the_ladder_shape_of_t129_is_visible_in_the_metrics():
    """Muchas ganadoras pequeñas y pocas perdedoras grandes: acierto alto y PF malo."""
    rs = [0.108] * 23 + [-0.964] * 7
    m = mt.summary(series(rs))
    assert m["win_rate"] == pytest.approx(23 / 30)
    assert m["avg_win_r"] == pytest.approx(0.108)
    assert m["avg_loss_r"] == pytest.approx(-0.964)
    assert m["win_loss_ratio"] == pytest.approx(0.108 / 0.964, rel=1e-6)
    assert m["pf"] == pytest.approx((23 * 0.108) / (7 * 0.964), rel=1e-6)
    assert m["pf"] < 1 and m["expectancy_r"] < 0


def test_the_giveback_from_the_mfe_measures_what_the_exit_left_on_the_table():
    hot = [trade(0.1, day=d, tid=f"g{d}", mfe=1.4) for d in range(10)]
    m = mt.summary(hot)
    assert m["giveback_r"] == pytest.approx(1.3)
    assert m["giveback_winners_r"] == pytest.approx(1.3)
    assert m["mfe1r_n"] == 10 and m["mfe1r_to_loss"] == pytest.approx(0.0)


def test_winners_that_end_in_a_loss_are_counted():
    rows = ([trade(-0.9, day=d, tid=f"a{d}", mfe=1.5) for d in range(4)]
            + [trade(0.5, day=10 + d, tid=f"b{d}", mfe=1.5) for d in range(6)]
            + [trade(-0.3, day=20 + d, tid=f"c{d}", mfe=0.2) for d in range(5)])
    m = mt.summary(rows)
    assert m["mfe1r_n"] == 10
    assert m["mfe1r_to_loss"] == pytest.approx(0.4)      # 4 de las 10 con MFE ≥ 1 R pierden


def test_the_drawdown_follows_the_order_of_closing_not_the_order_given():
    rows = [trade(1.0, day=5, tid="late"), trade(-2.0, day=1, tid="early"),
            trade(1.0, day=9, tid="last")]
    m = mt.summary(rows)
    assert m["max_dd_r"] == pytest.approx(2.0)           # la pérdida es la PRIMERA en cerrar
    assert m["net_r"] == pytest.approx(0.0)
    assert m["recovery_factor"] == pytest.approx(0.0)
    assert mt.max_dd(np.array([])) == 0.0


def test_cvar_is_the_mean_of_the_worst_tail_not_the_worst_value():
    r = np.array([-3.0, -2.0] + [0.1] * 38)
    assert mt.cvar(r, 0.95) == pytest.approx(-2.5)       # el 5 % peor = 2 de 40
    assert mt.cvar(np.array([0.5])) == pytest.approx(0.5)


def test_sharpe_and_sortino_use_the_daily_r_and_annualise_with_365():
    rows = series([0.5, -0.5] * 30, per_day=2)           # cada día suma 0
    days, r = mt.daily_r(rows)
    assert len(days) == 30 and np.allclose(r, 0.0)
    assert mt.sharpe_sortino(rows) == (None, None)       # sin dispersión no hay Sharpe
    good = series([0.2] * 20 + [-0.1] * 5)
    s, so = mt.sharpe_sortino(good)
    assert s is not None and so is not None and so > s > 0


def test_sortino_only_punishes_the_downside():
    only_up = series([0.1, 0.3, 0.2, 0.5])
    s, so = mt.sharpe_sortino(only_up)
    assert s is not None and so is None                  # sin días negativos no hay Sortino


def test_the_ruin_risk_grows_with_the_risk_per_trade():
    rs = [-1.0] * 12 + [0.3] * 18
    rows = series(rs, per_day=1)
    low = mt.ruin_risk(rows, 0.005, 200, 400, np.random.default_rng(1))
    high = mt.ruin_risk(rows, 0.05, 200, 400, np.random.default_rng(1))
    assert 0.0 <= low < high <= 1.0
    assert mt.ruin_risk(rows, 0.0, 200, 400, RNG) is None
    assert mt.ruin_risk([], 0.01, 200, 400, RNG) is None


def test_the_ruin_risk_is_reproducible_and_optional():
    rows = series([-1.0] * 10 + [0.5] * 10)
    a = mt.summary(rows, risk_pct=0.02, ruin_reps=200, rng=np.random.default_rng(5))
    b = mt.summary(rows, risk_pct=0.02, ruin_reps=200, rng=np.random.default_rng(5))
    assert a["ruin_risk"] == b["ruin_risk"]
    assert a["ruin_params"]["floor"] == mt.RUIN_FLOOR
    assert "ruin_risk" not in mt.summary(rows)           # por defecto no se calcula


def test_the_costs_in_r_and_the_gross_expectancy_are_separated():
    rows = series([0.1] * 10, cost_r=0.12)
    m = mt.summary(rows)
    assert m["cost_r"] == pytest.approx(0.12)
    assert m["expectancy_r"] == pytest.approx(0.1)
    assert m["expectancy_gross_r"] == pytest.approx(0.22)


def test_the_cuts_of_5_3_group_without_losing_operations():
    rows = (series([0.2] * 6, regime="trend_up")
            + series([-0.4] * 4, day0=10, policy="M0b", regime="range", side=-1))
    for key in ("regime", "timeframe", "sid", "side"):
        got = mt.by_group(rows, key)
        assert sum(v["n"] for v in got.values()) == 10, key
    assert set(mt.by_group(rows, "regime")) == {"trend_up", "range"}
    assert set(mt.by_group(rows, "side")) == {"largo", "corto"}


def test_the_span_and_the_exit_reasons_come_from_the_record():
    rows = series([0.2, -0.3])
    m = mt.summary(rows)
    assert m["exits"] == {"SL": 2}
    assert m["span"][0] == rows[0].t and m["span"][1] == rows[-1].exit_t
