"""T139: las etapas de cobertura y banco, que corren antes de gastar la lectura limpia."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from eim.validation.criteria import load_criteria
from eim.validation.hypotheses import report as rp
from eim.validation.hypotheses import rules as ru
from eim.validation.hypotheses import world as wd
from eim.validation.hypotheses.prereg import load_prereg
from eim.validation.lineage import ms_iso
from tests.validation.t139_market import DAYS, T0, make_world, prior_keys

PR = load_prereg()
CRIT = load_criteria()
EP = ru.exec_params(PR)
DAY = 86_400_000
META = {"symbol": "BTCUSDT", "asof": "x", "prereg": PR.version, "prereg_sha256": PR.sha256,
        "prereg_commit": "3d396f7", "criteria": "validation_v1", "commit": "abc", "family": 841,
        "null_reps": 33640}


@pytest.fixture(scope="module")
def world() -> wd.World:
    return make_world()


def _toy() -> object:
    """El mismo pre-registro con los tramos dentro de los 130 días sintéticos y menos sustitutas."""
    a, b = ms_iso(T0 + 100 * DAY), ms_iso(T0 + (DAYS - 1) * DAY)
    adj = PR.windows.adjust.model_copy(update={"from_": a, "to": b})
    bank = PR.reading("banco").model_copy(update={"ranges": ((a, b),)})
    cov = PR.coverage.model_copy(update={"from_": ms_iso(T0), "to": ms_iso(T0 + 120 * DAY)})
    return PR.model_copy(update={
        "windows": PR.windows.model_copy(update={"adjust": adj}),
        "readings": (PR.reading("oficial"), bank), "coverage": cov,
        "control": PR.control.model_copy(update={"surrogates": 3, "bars": 800})})


def test_coverage_says_what_is_missing(world):
    pr = _toy()
    full = wd.coverage_of(pr, world, lambda tf, _a, _b: 120 * DAY // ru.tf_ms(tf))
    assert full["ok"] and full["flow_ok"] and full["verdict"] == "cumple."
    short = wd.coverage_of(pr, world, lambda tf, _a, _b: 100 * DAY // ru.tf_ms(tf))
    assert not short["ok"] and "P0" in short["verdict"]
    res = {"coverage": full, "sample": {"x@1h": {"ideas": 3}}, "meta": META}
    assert "Cobertura" in rp.render_coverage(res) and "SIMULADO" in rp.render_coverage(res)


def test_missing_taker_drops_only_the_flow_rules(world):
    s = world.series["1h"]
    series = {**world.series, "1h": replace(s, taker=np.full(len(s.t), np.nan))}
    bare = wd.World(world.symbol, series, world.funding, world.path, world.minutes)
    cov = wd.coverage_of(_toy(), bare, lambda tf, _a, _b: 120 * DAY // ru.tf_ms(tf))
    assert cov["ok"] and not cov["flow_ok"] and "H2 y H3" in cov["verdict"]
    got = wd.key_ideas(PR, world, EP, wd.FLOW)
    assert got["flujo_sigue@1h"] == [] and got["flujo_revierte@4h"] == []
    assert got["funding_contra@1h"]


def test_sample_counts_have_no_r(world):
    pr = _toy()
    ideas = wd.key_ideas(pr, world, EP)
    got = wd.sample_counts(pr, world, EP, ideas)
    assert set(got) == set(pr.sids())
    assert all(isinstance(v, int) for row in got.values() for v in row.values())
    row = got["funding_contra@1h"]
    assert row["ideas"] == len(ideas["funding_contra@1h"])
    assert row.get("antes de 2023", 0) == (row.get("antes de 2023 largos", 0)
                                           + row.get("antes de 2023 cortos", 0))


def test_bank_stage_runs_and_its_report_renders(world):
    pr = _toy()
    stored = [{k: c[k] for k in ("t", "close", "atr")} for c in ru.minimal_ctxs(world.series["1h"])
              if c["atr"]][:300]
    res = wd.bank_stage(pr, CRIT, world, EP, prior_keys(), stored, lambda _m: None)
    assert res["family"] == 841 and len(res["rows"]) == 9
    assert all(r["reading"] == "banco" for r in res["rows"])
    assert set(res["control"]) == {"1h", "4h"}
    assert res["regression"]["minimal"]["n"] == res["regression"]["stored"]["n"]
    md = rp.render_bank({**res, "meta": META})
    assert "no aprueba nada" in md and "Regresión contra T137" in md


def test_surrogates_refuse_an_empty_stretch(world):
    with pytest.raises(ValueError, match="sustitutas"):
        wd._closes(world, T0 + 1000 * DAY, T0 + 1001 * DAY)
