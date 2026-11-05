"""T136: las mediciones del banco (costos, tope, frenos, Kelly y volatilidad objetivo)."""

from __future__ import annotations

import math

import pytest

from eim.paper.caps import CapParams
from eim.paper.exits import risk_study as rs
from eim.paper.kelly import KellyParams
from tests.paper.exits.helpers import trade


def _ts(n: int = 20, r: float = -0.15, cost_r: float = 0.167):
    return [trade(r, day=i // 4, tid=f"t{i}", cost_r=cost_r) for i in range(n)]


def test_cost_profile_says_how_much_more_is_risked_today():
    ts = _ts()
    ex = {t.id: 0.16 for t in ts}
    out = rs.cost_profile(ts, ex)
    assert out["n"] == len(ts)
    assert out["cost_r_ex_ante"]["mean"] == pytest.approx(0.16)
    assert out["risk_overrun"] == pytest.approx(1.16)
    assert out["qty_ratio_with_costs"] == pytest.approx(1 / 1.16)
    assert out["by_timeframe"]["1h"]["n"] == len(ts)


def test_cost_profile_without_ex_ante_does_not_invent_numbers():
    out = rs.cost_profile(_ts(), {})
    assert out["cost_r_ex_ante"]["n"] == 0
    assert math.isnan(out["risk_overrun"])
    assert out["by_timeframe"]["1h"]["cost_r_ex_ante_mean"] is None


def test_cost_cap_grid_keeps_only_what_passes_the_cap():
    ts = [trade(-1.0, tid="caro", cost_r=0.0), trade(0.5, tid="barato", cost_r=0.0)]
    ex = {"caro": 0.30, "barato": 0.05}
    grid = rs.cost_cap_grid(ts, ex, (0.08, 0.10, 0.12, 0.20, 0.40))
    by = {g["cap_r"]: g for g in grid}
    assert by[0.08]["n"] == 1 and by[0.08]["expectancy_r"] == pytest.approx(0.5)
    assert by[0.40]["n"] == 2 and by[0.40]["expectancy_r"] == pytest.approx(-0.25)
    assert by[0.08]["share"] == pytest.approx(0.5)
    assert by[0.08]["pf"] is None                   # sin perdedoras no hay cociente


def test_equity_run_without_caps_is_plain_compounding():
    ts = [trade(1.0, day=i, tid=f"t{i}") for i in range(3)]
    out = rs.equity_run(ts, 0.01, CapParams(), initial=10_000.0)
    assert out["n_taken"] == 3 and out["halted"] == 0 and out["cut"] == 0
    assert out["equity_final"] == pytest.approx(10_000 * 1.01**3)
    assert out["max_dd_pct"] == pytest.approx(0.0)
    assert out["ruined"] is False


def test_equity_run_gradual_brake_cuts_and_the_all_or_nothing_halts():
    losers = [trade(-1.0, day=i, tid=f"t{i}") for i in range(20)]
    plain = rs.equity_run(losers, 0.02, CapParams())
    grad = rs.equity_run(losers, 0.02, CapParams(dd_steps=((0.05, 0.5), (0.15, 0.0))))
    hard = rs.equity_run(losers, 0.02, CapParams(dd_brake=0.05, dd_pause_hours=24))
    assert grad["cut"] > 0 and grad["halted"] > 0
    assert hard["halted"] > 0
    # los dos frenos pierden menos que operar sin freno: es su razón de ser
    assert grad["equity_final"] > plain["equity_final"]
    assert hard["equity_final"] > plain["equity_final"]
    assert grad["max_dd_pct"] < plain["max_dd_pct"]


def test_equity_run_stops_at_ruin_instead_of_going_negative():
    out = rs.equity_run([trade(-1.0, day=i, tid=f"t{i}") for i in range(10)], 1.0, CapParams())
    assert out["ruined"] is True
    assert out["equity_final"] <= 0 or out["equity_final"] <= 100.0


def test_brake_grid_covers_the_preregistered_values_plus_today():
    ts = [trade(-0.15, day=i // 3, tid=f"t{i}") for i in range(30)]
    grid = rs.brake_grid(ts, 0.01, (0.05, 0.08, 0.10), (0.3, 0.5))
    names = [g["caso"] for g in grid]
    assert names[0].startswith("hoy")
    assert sum("gradual" in n for n in names) == 3
    assert sum("todo o nada" in n for n in names) == 3
    assert sum("CVaR" in n for n in names) == 2
    assert all("equity_final" in g for g in grid)


def test_kelly_view_gives_zero_size_with_the_ladder_as_measured():
    """La escalera pierde: ningún perfil recibe tamaño, y eso es el resultado correcto."""
    out = rs.kelly_view(_ts(60, r=-0.15), KellyParams(),
                        {"conservador": 0.005, "moderado": 0.01, "agresivo": 0.02})
    assert out["n"] == 60
    assert out["mean_r"] == pytest.approx(-0.15)
    assert out["lower_r"] < 0
    assert out["fraction"] == 0.0
    assert set(out["risk_pct"].values()) == {0.0}


def test_kelly_view_sizes_a_clear_edge_but_never_above_the_profile():
    ts = [trade(0.6 if i % 2 else 0.4, day=i // 4, tid=f"t{i}") for i in range(200)]
    out = rs.kelly_view(ts, KellyParams(), {"conservador": 0.005, "agresivo": 0.02})
    assert out["lower_r"] > 0 and out["fraction"] > 0
    assert out["risk_pct"]["conservador"] == pytest.approx(0.005)
    assert out["risk_pct"]["agresivo"] == pytest.approx(0.02)


def test_vol_target_view_reduces_dispersion_and_reports_the_base():
    ts = [trade(1.0 if i % 2 else -1.0, day=i // 4, tid=f"t{i}") for i in range(40)]
    sig = {t.id: (0.02 if i % 2 else 0.005) for i, t in enumerate(ts)}
    out = rs.vol_target_view(ts, sig, (0.01,))
    assert out["n"] == 40
    assert out["base"]["sd_r"] is not None
    got = out["targets"][0]
    assert got["weight_median"] == pytest.approx(1.0, abs=0.75)
    assert got["sd_r"] < out["base"]["sd_r"] * 2.5


def test_vol_target_view_skips_trades_without_sigma():
    ts = [trade(1.0, tid="a"), trade(-1.0, tid="b")]
    out = rs.vol_target_view(ts, {"a": 0.01}, (0.01,))
    assert out["n"] == 1
    assert out["base"]["expectancy_r"] == pytest.approx(1.0)


def test_cvar_is_not_reported_below_the_minimum_sample():
    few = rs.equity_run([trade(-1.0, day=0, tid="a")], 0.01, CapParams())
    assert few["n_taken"] == 1 and few["cvar95_r"] is None
    many = rs.equity_run([trade(-0.1, day=i // 3, tid=f"t{i}") for i in range(rs.CVAR_MIN_N)],
                         0.001, CapParams())
    assert many["cvar95_r"] is not None


def test_cases_are_today_plus_the_preregistered_grid():
    got = rs.cases((0.05, 0.10), (0.3,))
    assert [n for n, _ in got] == ["hoy (sin frenos)", "todo o nada dd=5%", "gradual dd=5%",
                                   "todo o nada dd=10%", "gradual dd=10%", "CVaR ≥ -0.30 R"]
    # el gradual se construye desde el dd_brake pre-registrado: su mitad y el valor entero
    grad = dict(got)["gradual dd=10%"]
    assert grad.dd_steps == ((0.05, 0.5), (0.10, 0.0))
    assert dict(got)["hoy (sin frenos)"] == CapParams()


def test_brake_grid_by_fold_gives_each_fold_fresh_capital():
    fold = [trade(-1.0, day=i, tid=f"a{i}") for i in range(5)]
    out = rs.brake_grid_by_fold([fold, fold], 0.02, (0.05,), (0.3,))
    hoy = next(g for g in out if g["caso"].startswith("hoy"))
    assert hoy["folds"] == 2
    # los dos pliegues son iguales, así que la mediana es su valor y el peor también
    assert hoy["return_median_pct"] == pytest.approx(hoy["return_worst_pct"])
    solo = rs.equity_run(fold, 0.02, CapParams())
    assert hoy["return_median_pct"] == pytest.approx(solo["return_pct"])


def test_brake_grid_by_fold_ignores_empty_folds():
    fold = [trade(0.5, day=i, tid=f"b{i}") for i in range(4)]
    out = rs.brake_grid_by_fold([fold, []], 0.01, (0.05,), ())
    assert all(g["folds"] == 1 for g in out)


def test_vol_target_reports_saturation_and_adds_the_parameter_free_one():
    ts = [trade(1.0 if i % 2 else -1.0, day=i // 4, tid=f"t{i}") for i in range(40)]
    sig = {t.id: 0.0025 for t in ts}
    out = rs.vol_target_view(ts, sig, (0.5, 1.0))
    labels = [g["label"] for g in out["targets"]]
    assert labels == ["0.5", "1", "mediana"]
    # 0,5 / 0,0025 = 200: el multiplicador se queda en el tope en todas
    assert out["targets"][0]["saturated"] == pytest.approx(1.0)
    assert out["targets"][0]["weight_median"] == pytest.approx(rs.W_MAX)
    # el objetivo sin parámetro libre es la propia mediana: peso 1 y nada cambia
    med = out["targets"][-1]
    assert med["saturated"] == pytest.approx(0.0)
    assert med["weight_median"] == pytest.approx(1.0)
    assert med["expectancy_r"] == pytest.approx(out["base"]["expectancy_r"])
