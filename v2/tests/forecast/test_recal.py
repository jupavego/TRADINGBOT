"""T160: recalibradores pre-registrados y su evaluación (sin red)."""

from __future__ import annotations

import pytest

from eim.forecast import recal, recal_eval
from eim.forecast.recal import Obs


def _o(k: int, probs=(0.3, 0.4, 0.3), real="bear", end_lag: int = 5) -> Obs:
    return Obs(made_at=k, end_t=k + end_lag, probs=dict(zip(recal.IDS, probs, strict=True)),
               realized=real)


def test_priors_moves_mean_to_observed_frequency():
    train = [_o(k, real="bear" if k % 2 else "neutral") for k in range(100)]
    m = recal.fit_priors(train)
    p = m({"bull": 0.3, "neutral": 0.4, "bear": 0.3})
    assert sum(p.values()) == pytest.approx(1)
    assert p["bull"] == pytest.approx(0) and p["bear"] > 0.3


def test_pav_is_monotone_and_pools():
    xs, ys = recal.pav([0.1, 0.2, 0.3, 0.4], [1, 0, 1, 1])
    assert ys == sorted(ys) and len(xs) == 2 and ys[0] == pytest.approx(0.5)


def test_isotonic_clips_and_normalizes():
    train = [_o(k, probs=(0.1 + 0.001 * k, 0.5, 0.4 - 0.001 * k),
                real="bull" if k > 50 else "bear") for k in range(100)]
    p = recal.fit_isotonic(train)({"bull": 0.2, "neutral": 0.5, "bear": 0.3})
    assert sum(p.values()) == pytest.approx(1)
    assert all(v > 0 for v in p.values())


def test_walk_forward_never_uses_unfinished_horizons():
    seen: list[int] = []

    def spy(train):
        seen.append(max(o.end_t for o in train))
        return lambda p: p
    obs = [_o(k, end_lag=10) for k in range(50)]
    out = recal.walk_forward(obs, spy, min_fit=5, refit=7)
    first = out[0][0].made_at
    assert first == 14                       # 5 resultados con end_t ≤ 14 (k = 0..4)
    starts = [o.made_at for o, _ in out][::7]
    assert all(s_end <= s for s_end, s in zip(seen, starts, strict=False))


def test_holm_and_one_sided_t():
    assert recal_eval.holm({"a": 0.01, "b": 0.04}) == {"a": True, "b": True}
    assert recal_eval.holm({"a": 0.03, "b": 0.04}) == {"a": False, "b": False}
    assert recal_eval.holm({"a": 0.001, "b": None}) == {"a": True, "b": False}
    t = recal_eval.one_sided_t([0.1, 0.2, 0.15, 0.12])
    assert t["p"] < 0.01 and t["ci95"][0] > 0
    assert recal_eval.one_sided_t([0.1])["p"] is None


def test_score_pairs_raw_and_recalibrated():
    evals = [(_o(k, real="bear"), {"bull": 0.1, "neutral": 0.2, "bear": 0.7}) for k in range(20)]
    s = recal_eval.score(evals, 2)
    assert s["brier_recal"] < s["brier_raw"] and s["test"]["n"] == 10
    assert s["ece_recal"] < s["ece_raw"] and s["top_hit_recal"] == 1.0
