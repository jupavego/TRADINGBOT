"""T137: el control con entradas al azar y el informe de decisión."""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from eim.paper.ideas import Idea
from eim.paper.params import ExecParams
from eim.validation import entry_control as ec
from eim.validation import entry_report
from eim.validation import entry_run as er
from eim.validation import entry_versions as ev
from eim.validation.entry_prereg import load_prereg
from eim.validation.gate import RECHAZADA, Check, Measure, Verdict
from eim.validation.lineage import iso_ms
from tests.paper.exits.helpers import SPEC, coherent_path
from tests.paper.helpers import M15
from tests.validation.helpers import trades

PR = load_prereg()
S1 = PR.variant("s1")
EP = ExecParams(funding_8h_assumed=0.0)
SID = "consenso_sintesis@1h"


def _ideas(path, n, sl_frac, strategy):
    out = []
    for k in range(n):
        j = 100 + k * 8
        px = float(path.c[j])
        side = 1 if k % 2 == 0 else -1
        out.append(Idea(id=f"i{k}", strategy=strategy, family="control", symbol="BTCUSDT",
                        t=int(path.t[j]) + M15, side=side, kind="market", entry=px,
                        sl=px - side * sl_frac * px, tp=px + side * 2 * sl_frac * px, fill_ms=0,
                        hold_ms=12 * 3_600_000, conf=0.5, why=("test",), timeframe="1h",
                        regime="range", origin="backtest"))
    return out


# --- control y regresión -------------------------------------------------------------------------
def test_control_null_puts_the_geometry_to_the_test():
    """El caso que T134 no medía: con cuantil, M8 mueve SL en las entradas al azar y no es M0."""
    path, fine = coherent_path(1500, seed=11, sigma=0.002)
    pr = PR.model_copy(update={"control": PR.control.model_copy(update={
        "surrogates": 3, "bars": 300, "ideas": 40})})
    real = _ideas(path, 40, 0.003, "control_aleatorio")
    g = ec.control_geometry(real)
    assert g is not None and ec.control_geometry([]) is None
    variants = ["base", "m8", "tope", "s1_tope"]
    null, moved = ec.null_gross(pr, variants, fine.c, float(path.c[0]), int(path.t[0]), g, EP,
                                SPEC.tick, q0=50.0)
    assert np.mean(moved["m8"]) > 0.5 and np.mean(moved["base"]) == 0
    assert len(null["base"]) == 3 and null["m8"] != null["base"]
    # el tope sin geometría veta el SL del 0,3 %, así que no deja nada que medir
    assert null["tope"] == [] and null["s1_tope"] != null["base"]


def _control_runs(moved: int, ideas: int = 100) -> dict:
    run = er.VariantRun("m8")
    run.stats["control_aleatorio@1h"] = Counter(ideas=ideas, moved=moved)
    run.trades["control_aleatorio@1h"] = trades(n=30, mean=0.0, t0=iso_ms("2025-01-01T00:00:00Z"))
    return {"m8": run}


def test_control_that_barely_moves_stops_is_not_an_approval():
    """El «sí» de T134 no medía nada: ahora se declara que no pone a prueba la geometría."""
    null = {"m8": [1.0] * 19}                  # el bruto real no destaca sobre el nulo
    moved = {"m8": [0.5]}
    start = iso_ms(PR.control.real_from)
    low = ec.control_report(PR, _control_runs(5), null, moved, start)["m8"]
    high = ec.control_report(PR, _control_runs(90), null, moved, start)["m8"]
    assert low["ok"] is True and low["tested"] is False
    assert high["ok"] is True and high["tested"] is True
    assert high["n_real"] == 30 and high["moved_frac_real"] == 0.9


def test_control_above_the_null_is_rejected():
    null = {"m8": [-5.0] * 39}
    got = ec.control_report(PR, _control_runs(90), null, {"m8": [0.5]},
                            iso_ms(PR.control.real_from))["m8"]
    assert got["ok"] is False and got["p_one_sided"] <= PR.control.alpha


def test_random_ideas_keep_the_real_geometry_and_do_not_see_the_future():
    path, _ = coherent_path(400, seed=3)
    g = ec.Geometry(np.array([0.02]), np.array([1.5]), 24 * 3_600_000)
    ideas = ec.random_ideas(path, 1, 50, g, "control_aleatorio", "1h")
    assert len(ideas) == 50
    for i in ideas:
        j = int(np.searchsorted(path.t, i.t)) - 1
        assert i.entry == float(path.c[j])                 # el cierre de la vela ya cerrada
        assert abs(i.entry - i.sl) / i.entry == pytest.approx(0.02)
        assert i.rr == pytest.approx(1.5) and i.hold_ms == g.hold_ms


# --- informe -------------------------------------------------------------------------------------
def _res() -> dict:
    v = ev.version_of(SID, S1, PR, "fp")
    m = Measure("x", 0, 150, 0, 0, -0.1, 0.01, {"range": 100, "trend": 50}, (-0.2, -0.05), 0.9,
                100, 0.3, -0.2, [(0, 10, -0.1)], 0, None, 0.2, (None, None), {"win_rate": 0.5})
    cs = tuple(Check(k, k, None, "", k not in ("V2", "V3"), "") for k in
               ("V1", "V2", "V3", "V4", "V5", "V6"))
    row = entry_report.row_of("oficial", Verdict(v, m, RECHAZADA, "falla", cs, 1.0, "c", ()),
                              "s1", {"ideas": 9, "moved": 3, "vetoed": 0}, False)
    summary = {"counts": {RECHAZADA: 1}, "validated": [],
               "most_failed": [{"id": "V2", "name": "Expectativa neta", "n": 1}]}
    agg = {"n": 150, "mean_r": -0.1, "win_rate": 0.5, "pf": 0.8, "cost_r": 0.2, "gross_r": 0.1}
    read = {"summary": summary, "rows": [row], "meets_v1": 1, "period": "p",
            "pooled": {"base": {"1h": agg}, "s1": {"1h": agg, "todos": agg}}}
    cost = {"1h": {"ideas": 9, "moved": 3, "vetoed": 0, "moved_frac": 1 / 3, "vetoed_frac": 0.0,
                   "cost_ex_ante_r": 0.1}}
    ctl = {"n_real": 30, "moved_frac_real": 0.5, "moved_frac_null": 0.4, "observed_gross_r": 0.01,
           "null_mean": 0.02, "null_p95": 0.05, "p_one_sided": 0.6, "tested": True, "ok": True}
    return {"meta": {"symbol": "BTCUSDT", "asof": "2026-11-03", "prereg": "p",
                     "prereg_sha256": "a" * 64, "prereg_commit": "213247f", "criteria": "c",
                     "commit": "abc", "attempts": 520, "family": 832, "csv": "x.csv"},
            "variant_ids": ["s1"], "readings": {k: read for k in ("oficial", "reserva", "banco")},
            "variants": {"base": {"cost": cost}, "s1": {"cost": cost}},
            "cap_left_out": [{"with": "tope", "without": "base", "n_with": 10, "n_without": 100,
                              "left_out": 0.9}],
            "control": {"s1": ctl}, "regression": None,
            "tf15m": {"note": "n", "pooled": {"base": {"todo": agg}}}, "candidates": []}


def test_report_says_plainly_when_none_validated_and_shows_the_mode():
    md = entry_report.render(_res())
    assert "Ninguna versión validada" in md and "SIMULADO" in md
    assert "213247f" in md and "Ninguna versión cumple la regla" in md
    assert "90.0 %" in md                                  # lo que deja fuera el tope
    assert "No se corrió" in md


def test_report_names_the_versions_the_rule_lets_through():
    res = _res() | {"candidates": [{"id": "x@1h@v1372", "variant": "s1", "passed": {}}]}
    assert "`x@1h@v1372`" in entry_report.render(res)


def test_parent_check_needs_both_the_count_and_the_expectancy():
    got = {"n": 100, "mean_r": -0.15}
    assert ec.check_parent(got, {"n": 100, "expectancy_r": -0.15}, 1e-6)["ok"] is True
    assert ec.check_parent(got, {"n": 99, "expectancy_r": -0.15}, 1e-6)["ok"] is False
    assert ec.check_parent(got, {"n": 100, "expectancy_r": -0.14}, 1e-6)["ok"] is False
