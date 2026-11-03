"""T131 — bootstrap por días, Romano-Wolf (E3) y PBO por CSCV.

Lo que se comprueba no es que las cifras salgan bonitas, sino que las pruebas se comportan como
pruebas: bajo la hipótesis nula no rechazan más de lo que dicen, el ajuste es monótono y ordena
igual que el estadístico, y el PBO detecta el sobreajuste cuando lo hay y no lo ve cuando no.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.paper.exits import stats as st

RNG = lambda s=131: np.random.default_rng(s)      # noqa: E731
REPS = 1500


def diffs(values: list[float], per_day: int = 1, day0: int = 0) -> list[tuple[int, float]]:
    return [(day0 + i // per_day, v) for i, v in enumerate(values)]


def test_the_cluster_se_grows_when_the_trades_of_a_day_are_correlated():
    same = [0.5] * 20 + [-0.5] * 20
    spread = st.cluster_se(np.arange(40), np.array(same, dtype=float))
    clumped = st.cluster_se(np.array([0] * 20 + [1] * 20), np.array(same, dtype=float))
    assert clumped > spread > 0        # dos días de 20 operaciones iguales informan menos


def test_the_paired_ci_covers_the_true_mean_and_narrows_with_more_days():
    rng = RNG()
    d = list(rng.normal(0.1, 1.0, 400))
    lo, hi = st.paired_ci(diffs(d), REPS, 0.95, RNG())
    assert lo < 0.1 < hi
    wide = st.paired_ci(diffs(d[:40]), REPS, 0.95, RNG())
    assert (hi - lo) < (wide[1] - wide[0])


def test_the_paired_ci_of_a_tiny_sample_is_not_invented():
    assert all(np.isnan(x) for x in st.paired_ci([(0, 0.1)], REPS, 0.95, RNG()))


def test_romano_wolf_does_not_reject_pure_noise():
    """20 variantes sin efecto: ningún p ajustado baja de 0,05 (control del error por familia)."""
    rng = RNG(7)
    d = {f"v{k}": diffs(list(rng.normal(0.0, 1.0, 200))) for k in range(20)}
    out = st.romano_wolf(d, REPS, RNG())
    assert min(out["p_rw"].values()) > 0.05
    assert len(out["p_rw"]) == 20 and out["skipped"] == []


def test_romano_wolf_finds_a_real_effect_among_noise():
    rng = RNG(11)
    d = {f"v{k}": diffs(list(rng.normal(0.0, 1.0, 300))) for k in range(9)}
    d["real"] = diffs(list(rng.normal(0.6, 1.0, 300)))
    out = st.romano_wolf(d, REPS, RNG())
    assert out["p_rw"]["real"] < 0.05
    assert min(out["p_rw"][k] for k in d if k != "real") > 0.05


def test_the_adjusted_p_is_monotone_and_keeps_the_order_of_the_statistic():
    rng = RNG(13)
    d = {"a": diffs(list(rng.normal(0.5, 1.0, 200))),
         "b": diffs(list(rng.normal(0.2, 1.0, 200))),
         "c": diffs(list(rng.normal(-0.3, 1.0, 200)))}
    out = st.romano_wolf(d, REPS, RNG())
    order = sorted(out["t"], key=lambda k: -out["t"][k])
    adj = [out["p_rw"][k] for k in order]
    assert adj == sorted(adj)                       # monótono por pasos
    for k in d:
        assert out["p_rw"][k] >= out["p_raw"][k]    # ajustar nunca abarata
        assert 0 < out["p_rw"][k] <= 1


def test_holm_is_reported_as_a_reference_and_is_never_cheaper_than_the_raw_p():
    rng = RNG(17)
    d = {f"v{k}": diffs(list(rng.normal(0.3, 1.0, 150))) for k in range(6)}
    out = st.romano_wolf(d, REPS, RNG())
    assert set(out["p_holm"]) == set(out["p_raw"])
    for k in out["p_raw"]:
        assert out["p_holm"][k] >= out["p_raw"][k]


def test_variants_without_enough_data_are_reported_not_silently_dropped():
    out = st.romano_wolf({"a": diffs([0.1, 0.2, 0.3]), "sin": [(0, 0.5)],
                          "plana": diffs([0.2, 0.2, 0.2])}, 200, RNG())
    assert "sin" in out["skipped"]            # menos de 2 observaciones
    assert "plana" in out["skipped"]          # varianza 0: no hay estadístico


def test_pbo_sees_overfitting_when_the_in_sample_winner_is_noise():
    """Variantes que solo se distinguen por ruido: la ganadora dentro no lo es fuera."""
    rng = RNG(19)
    m = {f"v{k}": list(rng.normal(0.0, 1.0, 16)) for k in range(12)}
    got = st.pbo(m, splits=8)
    assert got["pbo"] > 0.3
    assert got["combinations"] == 70 and got["variants"] == 12


def test_pbo_is_low_when_one_variant_is_genuinely_better():
    rng = RNG(23)
    m = {f"v{k}": list(rng.normal(0.0, 0.2, 16)) for k in range(8)}
    m["buena"] = list(rng.normal(3.0, 0.2, 16))
    got = st.pbo(m, splits=8)
    assert got["pbo"] < 0.1 and got["degradation_mean"] < 1.0


def test_pbo_says_why_it_cannot_be_computed():
    assert st.pbo({"a": [1, 2, 3]}, splits=8)["pbo"] is None
    out = st.pbo({"a": [1, 2], "b": [2, 1]}, splits=8)
    assert out["pbo"] is None and "tramos" in out["reason"]


def test_the_plateau_needs_the_neighbours_to_keep_the_improvement():
    scores = {"a": 1.0, "b": 1.1, "c": 0.2}
    nb = {"a": ["b"], "b": ["a", "c"], "c": ["b"]}
    got = st.plateau(scores, nb, keep=0.7)
    assert got["a"] is True            # su vecino conserva el 110 %
    assert got["b"] is False           # un vecino cae al 18 %
    assert st.plateau({"a": 1.0}, {}, keep=0.7)["a"] is False      # sin vecinos no hay meseta
    assert st.plateau({"a": -1.0}, {"a": ["b"]}, keep=0.7)["a"] is False


def test_the_statistics_are_reproducible_with_the_same_seed():
    d = {"a": diffs([0.3, -0.1, 0.2, 0.4, -0.2, 0.1] * 10)}
    first = st.romano_wolf(d, REPS, RNG(131))
    assert first["p_rw"] == st.romano_wolf(d, REPS, RNG(131))["p_rw"]
    assert st.paired_ci(d["a"], REPS, 0.95, RNG(131)) == pytest.approx(
        st.paired_ci(d["a"], REPS, 0.95, RNG(131)))
