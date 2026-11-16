"""T169: los descartes mecánicos son los de la ficha, por banda, y el MinTRL es el de T161."""

from __future__ import annotations

import math

import pytest

from eim.nursery.exam import verdict as vd
from eim.validation.power import min_track_record


def _ph(**kw) -> dict:
    base = {"days": 448.0, "filled": 300, "closed": 290, "ops_month": 20.1, "cost_r_mean": 0.12,
            "cost_r_sd": 0.05, "hold_h_median": 6.0, "pos_days_frac": 0.5,
            "pos_days_by_block": [0.5] * 16}
    return base | kw


@pytest.mark.parametrize(("hold", "band"), [(1.5, "scalping"), (2.0, "scalping"),
                                            (2.1, "intradia"), (23.9, "intradia"),
                                            (24.0, "tres_dias"), (120.0, "tres_dias"),
                                            (121.0, "semanal")])
def test_band_by_median_hold(hold: float, band: str) -> None:
    assert vd.band_of(hold) == band


@pytest.mark.parametrize(("band", "need"), [("scalping", 20), ("intradia", 8), ("tres_dias", 5)])
def test_cadence_threshold_per_band(band: str, need: float) -> None:
    hold = {"scalping": 1.0, "intradia": 6.0, "tres_dias": 48.0}[band]
    keep = vd.judge(band, _ph(ops_month=need + 0.1, hold_h_median=hold), False)
    drop = vd.judge(band, _ph(ops_month=need - 0.1, hold_h_median=hold), False)
    assert not keep["discarded"] and drop["discarded"]
    assert "operaciones al mes" in drop["reasons"][0] and drop["days_to_verdict"] is None


def test_weekly_band_counts_days_in_position() -> None:
    hold = 24 * 10.0
    assert not vd.judge("semanal", _ph(hold_h_median=hold, pos_days_frac=0.31), False)[
        "discarded"]
    v = vd.judge("semanal", _ph(hold_h_median=hold, pos_days_frac=0.29), False)
    assert v["discarded"] and "30 %" in v["reasons"][0]
    ok = vd.judge("semanal", _ph(hold_h_median=hold, pos_days_frac=0.6), False)
    assert ok["no_first_team"]                       # 0,6 × 182 = 109 < 120 días con posición
    assert "pos_days" in ok["days_to_verdict"]["mu_0_10_alfa_0_05"]


def test_cost_and_anticipation_discard() -> None:
    v = vd.judge("intradia", _ph(cost_r_mean=0.31), False)
    assert v["discarded"] and "V6" in v["reasons"][0]
    assert vd.judge("intradia", _ph(), True)["reasons"] == [
        "anticipación: sus ideas cambian al truncar los datos"]


def test_band_is_reassigned_and_its_thresholds_apply() -> None:
    v = vd.judge("intradia", _ph(hold_h_median=50.0, ops_month=6.0), False)
    assert v["reassigned"] and v["band"] == "tres_dias" and not v["discarded"]
    few = vd.judge("intradia", _ph(hold_h_median=50.0, ops_month=6.0, closed=9), False)
    assert few["measured_band"] is None and few["band"] == "intradia" and few["discarded"]


def test_report_says_when_the_declared_band_would_keep_it() -> None:
    v = vd.judge("semanal", _ph(hold_h_median=50.0, ops_month=4.0, pos_days_frac=0.5), False)
    assert v["band"] == "tres_dias" and v["discarded"] and v["kept_with_declared_band"] is True
    v = vd.judge("semanal", _ph(hold_h_median=50.0, ops_month=4.0, pos_days_frac=0.2), False)
    assert v["discarded"] and v["kept_with_declared_band"] is False
    assert vd.judge("intradia", _ph(), False)["kept_with_declared_band"] is None


def test_a_rule_that_never_fires_says_so() -> None:
    v = vd.judge("intradia", _ph(ideas=0, filled=0, closed=0, ops_month=0.0,
                                 hold_h_median=None, cost_r_mean=None), False)
    assert v["discarded"] and v["reasons"][0].startswith("ninguna idea")
    assert "0,0 operaciones al mes" in v["reasons"][1]


def test_no_first_team_below_100_operations_in_six_months() -> None:
    per_day = 99 / vd.TERM_DAYS
    v = vd.judge("intradia", _ph(filled=round(per_day * 448), ops_month=per_day * 30), False)
    assert not v["discarded"] and v["no_first_team"]
    v = vd.judge("intradia", _ph(), False)
    assert not v["no_first_team"]


def test_mintrl_uses_t161_with_the_family_correction() -> None:
    assert vd.z_of(vd.ALPHAS["familia"]) == pytest.approx(3.09, abs=0.005)
    rows = {(r["mu_r"], r["alpha"]): r["ops"] for r in vd.mintrl_table()}
    assert rows[(0.10, 0.05)] == math.ceil(min_track_record(0.10, 0.0, 0.0, 3.0, 0.05)) == 273
    assert rows[(0.25, 0.05)] == 46
    assert rows[(0.10, 0.001)] == 961 and rows[(0.25, 0.001)] == 159
    v = vd.judge("intradia", _ph(), False)
    d = v["days_to_verdict"]["mu_0_25_familia"]
    assert d["ops"] == 159 and d["days"] == pytest.approx(158.5 / (300 / 448), abs=0.5)


def test_borderline_cadence_is_flagged() -> None:
    v = vd.judge("intradia", _ph(filled=118, ops_month=118 / 448 * 30), False)
    assert v["discarded"] and "cadencia" in v["borderline"]
    lo, hi = vd.poisson_ci(0)
    assert lo == 0.0 and hi == pytest.approx(3.689, abs=1e-3)
