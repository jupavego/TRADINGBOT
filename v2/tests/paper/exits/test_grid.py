"""T134 — la rejilla pre-registrada hecha variantes, y sus vecinos.

Lo que se vigila: que salgan **todas** las combinaciones declaradas y ninguna más, que lo que no se
corre se declare con su motivo en vez de desaparecer, y que los vecinos de la meseta solo se muevan
por parámetros numéricos dentro de la misma familia.
"""

from __future__ import annotations

from collections import Counter

import pytest

from eim.paper.exits import features, grid
from eim.paper.exits.prereg import load_prereg
from eim.paper.params import LADDER_BY_PROFILE
from tests.paper.exits.helpers import coherent_path

SIGMAS = ("atr14", "parkinson", "garman_klass", "yang_zhang", "harrv_1m")


@pytest.fixture(scope="module")
def world():
    p, fine = coherent_path(400, seed=13)
    feats = {n: features.build(p, n, swing_bars=5, fine=fine) for n in SIGMAS}
    return p, feats


def expand(world, **kw):
    p, feats = world
    factory = kw.pop("quantile_for", lambda q: (lambda sid, t: 2.0 * q))
    return grid.expand(load_prereg(), feats, LADDER_BY_PROFILE["moderado"], p.t,
                       quantile_for=factory, **kw)


def test_the_grid_yields_exactly_the_pre_registered_combinations(world):
    vs, skipped = expand(world)
    pr = load_prereg()
    by_fam = Counter(v.family for v in vs)
    for g in pr.grid:
        if g.status == "implementada":
            assert by_fam[g.id] == g.combos, g.id
    assert sum(by_fam.values()) == len(vs) == 89
    assert len({v.id for v in vs}) == len(vs), "hay identificadores repetidos"
    assert set(skipped) == {"M4", "S2", "S3"}
    assert skipped["M4"] == "descartada_T133"


def test_m8_is_declared_not_dropped_when_there_is_no_quantile(world):
    vs, skipped = expand(world, quantile_for=None)
    assert all(v.family != "M8" for v in vs)
    assert "M8" in skipped and "cuantil" in skipped["M8"]


def test_each_m8_variant_gets_its_own_quantile(world):
    """`q` es justo el parámetro que M8 varía: si todas compartieran cuantil, serían la misma
    política contada tres veces y entrarían en la corrección como copias correlacionadas."""
    seen = {}

    def factory(q: float):
        def of(sid: str, t: int) -> float:
            seen[q] = seen.get(q, 0) + 1
            return 2.0 * q
        return of

    vs, _ = expand(world, quantile_for=factory)
    m8 = [v for v in vs if v.family == "M8"]
    assert len(m8) == 3
    assert sorted(v.knobs["q"] for v in m8) == [0.8, 0.9, 0.95]
    # cada variante usa SU fábrica: tres distancias mínimas distintas para la misma idea
    from eim.paper.exits.policy import ExitContext
    from eim.paper.params import spec_for
    from tests.paper.exits.helpers import ZERO
    from tests.paper.helpers import idea
    p, _feats = world
    i = idea(entry=float(p.c[200]), sl=float(p.c[200]) * 0.9999, t=int(p.t[200]) + p.step)
    ctx = ExitContext(path=p, ep=ZERO, spec=spec_for("BTCUSDT"))
    dists = {v.knobs["q"]: v.policy.min_dist_of(i, ctx) for v in m8}
    assert len({round(x, 9) for x in dists.values() if x is not None}) == 3, dists


def test_every_variant_carries_its_own_identity(world):
    vs, _ = expand(world)
    for v in vs:
        assert v.policy.id == v.id
        assert v.params["policy"] in {"ladder", "shadow_tp_be_time", "M2", "M3", "M5", "M6",
                                      "M7", "S1", "M8"}


def test_the_neighbours_only_move_numeric_parameters(world):
    vs, _ = expand(world)
    nb = grid.neighbours(vs)
    assert set(nb) == {v.id for v in vs}
    knobs = {v.id: v.knobs for v in vs}
    for vid, others in nb.items():
        for o in others:
            a, b = knobs[vid], knobs[o]
            diff = [k for k in a if a[k] != b.get(k)]
            assert len(diff) == 1, (vid, o, diff)
            assert isinstance(a[diff[0]], (int, float)), (vid, o, diff)


def test_the_sigma_estimator_is_not_a_step_of_the_grid(world):
    """No hay «un paso» entre Parkinson y Yang–Zhang: cada estimador tiene su propia meseta."""
    vs, _ = expand(world)
    nb = grid.neighbours(vs)
    by_id = {v.id: v for v in vs}
    for vid, others in nb.items():
        own = by_id[vid].knobs.get("sigma")
        if own is None:
            continue
        assert all(by_id[o].knobs.get("sigma") == own for o in others), vid


def test_the_neighbours_never_cross_families(world):
    vs, _ = expand(world)
    nb = grid.neighbours(vs)
    fam = {v.id: v.family for v in vs}
    for vid, others in nb.items():
        assert all(fam[o] == fam[vid] for o in others), vid


def test_the_extremes_of_a_grid_have_one_neighbour_and_the_middle_two(world):
    vs, _ = expand(world)
    nb = grid.neighbours(vs)
    assert nb["M0 first_r=0.075"] == ["M0 first_r=0.1"]
    assert sorted(nb["M0 first_r=0.25"]) == ["M0 first_r=0.1", "M0 first_r=0.5"]
    assert nb["M0 first_r=1"] == ["M0 first_r=0.5"]


def test_a_missing_sigma_estimator_is_declared_not_silently_substituted(world):
    p, feats = world
    few = {k: v for k, v in feats.items() if k in ("atr14", "parkinson")}
    vs, skipped = grid.expand(load_prereg(), few, LADDER_BY_PROFILE["moderado"], p.t,
                              quantile_for=lambda q: (lambda sid, t: 2.0 * q))
    assert any("garman_klass" in k for k in skipped) or any(
        "garman_klass" in str(v) for v in skipped.values())
    assert all(v.knobs.get("sigma") in (None, "atr14", "parkinson") for v in vs)
