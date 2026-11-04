"""T134 — el motor del experimento: que los lotes no cambien el resultado y que no inventen nada.

La prueba que de verdad importa es
`test_running_in_batches_gives_the_same_numbers_as_running_everything_at_once`: la rejilla se corre
por lotes solo por memoria, y si los lotes cambiaran una cifra, todo el experimento valdría cero.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.paper.exits import experiment, features, grid
from eim.paper.exits import walkforward as wf
from eim.paper.exits.policy import ExitContext
from eim.paper.params import LADDER_BY_PROFILE, spec_for
from tests.paper.exits.helpers import COSTED, coherent_path, random_ideas

MONTH_BARS = 30 * 96


@pytest.fixture(scope="module")
def world():
    path, fine = coherent_path(13 * MONTH_BARS, seed=29)
    feats = {n: features.build(path, n, swing_bars=5, fine=fine)
             for n in ("atr14", "parkinson")}
    ideas = random_ideas(path, 150, seed=31, strategy="consenso")
    return path, fine, feats, ideas


@pytest.fixture(scope="module")
def small(world):
    """Un pre-registro de tramos cortos y una rejilla recortada, para que quepa en una prueba."""
    import json

    from eim.paper.exits.prereg import VERSIONS_DIR
    from eim.paper.exits.prereg import load_prereg as load

    d = json.loads((VERSIONS_DIR / "prereg_t131_v3.json").read_bytes())
    d["version"] = "prereg_t131_v9"
    d["design"] |= {"fit_months": 2, "test_months": 1, "step_months": 1,
                    "embargo_feature_hours": 24, "start": "2025-01-01T00:00:00Z",
                    "end": "2030-01-01T00:00:00Z"}
    d["bootstrap"]["reps"] = 1000
    d["multiple"]["reps"] = 1000
    d["ruin"] |= {"reps": 20, "trades": 50}
    for g in d["grid"]:                       # solo M0, M1 y dos variantes de M2
        if g["id"] == "M0":
            g["params"] = {"first_r": [0.1, 0.25]}
        elif g["id"] == "M1":
            g["params"] = {"be_trigger_r": [1.0], "be_lock_r": [0.1]}
        elif g["id"] == "M2":
            g["params"] = {"k": [2, 3], "sigma": ["parkinson"], "activate_r": [0.0]}
        else:
            g["status"] = "fuera_de_la_prueba"
    import tempfile
    from pathlib import Path as FsPath

    p = FsPath(tempfile.mkdtemp()) / "prereg_t131_v9.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return load(path=p)


def _setup(world, small):
    path, fine, feats, ideas = world
    vs, _ = grid.expand(small, feats, LADDER_BY_PROFILE["moderado"], path.t,
                        quantile_of=lambda s, t: 2.0)
    bases = [v for v in vs if v.family in ("M0", "M1")][:1] + [
        v for v in vs if v.family == "M1"][:1]
    bases = [next(v for v in vs if v.id == "M0 first_r=0.1"),
             next(v for v in vs if v.family == "M1")]
    ctx = ExitContext(path=path, ep=COSTED, spec=spec_for("BTCUSDT"), fine=fine)
    lo, hi = min(i.t for i in ideas), max(i.t for i in ideas)
    fs = wf.folds(lo, hi, 24 * 3_600_000, 2, 1, 1)
    return vs, bases, ctx, fs, ideas


def test_running_in_batches_gives_the_same_numbers_as_running_everything_at_once(world, small):
    """Los lotes son solo para la memoria: no pueden cambiar una sola cifra."""
    vs, bases, ctx, fs, ideas = _setup(world, small)
    cands = [v for v in vs if v.id not in {b.id for b in bases}]
    assert len(cands) >= 2 and len(fs) >= 3
    rng = np.random.default_rng(7)
    whole = experiment.run_batch(ideas, bases, cands, ctx, small, fs, rng)
    rng = np.random.default_rng(7)
    parts: dict = {}
    for k in range(0, len(cands), 1):
        got = experiment.run_batch(ideas, bases, cands[k:k + 1], ctx, small, fs, rng)
        for key, val in got.items():
            parts.setdefault(key, val)
    for k in whole:
        a, b = whole[k].test, parts[k].test
        for field in ("n", "expectancy_r", "pf", "max_dd_r", "cvar95_r", "win_loss_ratio"):
            assert a.get(field) == pytest.approx(b.get(field), nan_ok=True), (k, field)
        assert whole[k].folds == pytest.approx(parts[k].folds, nan_ok=True)
        for base, d in whole[k].diffs.items():
            assert [x[1] for x in d] == pytest.approx([x[1] for x in parts[k].diffs[base]])


def test_the_batch_keeps_the_pairing_exact(world, small):
    vs, bases, ctx, fs, ideas = _setup(world, small)
    rng = np.random.default_rng(3)
    tot = experiment.run_batch(ideas, bases, [v for v in vs if v.family == "M2"], ctx, small,
                               fs, rng)
    for k, x in tot.items():
        for base, d in x.diffs.items():
            assert base != k
            assert len(d) <= x.test.get("n", 0)      # nunca más pares que operaciones medidas


def test_the_plateau_is_measured_on_the_improvement_over_the_base(world, small):
    vs, bases, ctx, fs, ideas = _setup(world, small)
    rng = np.random.default_rng(5)
    tot = experiment.run_batch(ideas, bases, [v for v in vs if v.family == "M2"], ctx, small,
                               fs, rng)
    got = experiment.plateau_of(tot, vs, bases[0].id, 0.7)
    assert set(got) >= set(tot)
    assert got[bases[0].id] is False               # la base no mejora a la base


def test_the_power_inputs_carry_the_variance_and_the_pace(world, small):
    vs, bases, ctx, fs, ideas = _setup(world, small)
    rng = np.random.default_rng(11)
    tot = experiment.run_batch(ideas, bases, [v for v in vs if v.family == "M2"], ctx, small,
                               fs, rng)
    p = experiment.power_inputs(small, tot, ideas, bases)
    assert "_nota" in p and "E9" in p["_nota"]
    for k in tot:
        assert p[k]["n_closed"] >= 0
        assert p[k]["trades_per_week"] is None or p[k]["trades_per_week"] > 0
        for base, sd in p[k]["sd_paired"].items():
            assert base != k
            assert sd is None or sd >= 0


def test_trades_per_week_needs_a_span_and_some_trades():
    assert experiment.trades_per_week([], 10) is None
    from tests.paper.exits.helpers import coherent_path as cp
    p, _ = cp(100, seed=1)
    ideas = random_ideas(p, 5, seed=2)
    assert experiment.trades_per_week(ideas, 0) is None
    assert experiment.trades_per_week(ideas, 5) > 0


def test_the_multiplicity_block_never_compares_a_base_with_itself(world, small):
    vs, bases, ctx, fs, ideas = _setup(world, small)
    rng = np.random.default_rng(13)
    tot = experiment.run_batch(ideas, bases, [v for v in vs if v.family == "M2"], ctx, small,
                               fs, rng)
    blk = experiment.multiplicity(small, tot, bases[0].id, "prueba")
    assert bases[0].id not in blk.get("p_raw", {})
    assert blk["base"] == bases[0].id
