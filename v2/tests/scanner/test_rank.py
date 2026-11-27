"""T95 — ranking comparable: unidades invariantes a escala y divisa, horizontes normalizados,
puntuaciones separadas, una sola combinación al final y pesos calibrados solo fuera de muestra."""

from __future__ import annotations

import copy

import numpy as np
import pytest

from eim.scanner import rank

DAY = 86_400_000


def opp(oid="op-a", iid="crypto.binance.usdm.AUSDT", side="largo", last=100.0, bull=106.0,
        neutral=100.5, bear=96.0, p=(0.5, 0.3, 0.2), inv=97.0, cost=0.002, h=25,
        q=0.6, v=0.8, r=0.7) -> dict:
    sc = {"bull": {"p": p[0], "median_end": bull, "band_end": [bull * 0.9, bull * 1.1],
                   "invalidation": inv if side == "largo" else None},
          "neutral": {"p": p[1], "median_end": neutral, "band_end": [98, 102],
                      "invalidation": None},
          "bear": {"p": p[2], "median_end": bear, "band_end": [bear * 0.9, bear * 1.1],
                   "invalidation": inv if side == "corto" else None}}
    return {"opportunity_id": oid, "instrument_id": iid, "symbol": iid.rsplit(".", 1)[1],
            "side": side, "horizon_bars": h, "horizon_ms": h * DAY,
            "forecast": {"scenarios": sc},
            "scores": {"signal_quality": q, "viability": v, "risk_cost": r,
                       "components": {"round_trip_cost": cost}}}


def closes(last=100.0, n=120, seed=0, sigma=0.02) -> list[float]:
    rng = np.random.default_rng(seed)
    c = np.exp(np.cumsum(rng.normal(0, sigma, n)))
    return list(c / c[-1] * last)


def scaled(o: dict, k: float) -> dict:
    """La misma oportunidad con todos los precios ×k (otra escala u otra divisa)."""
    o = copy.deepcopy(o)
    for s in o["forecast"]["scenarios"].values():
        s["median_end"] *= k
        s["band_end"] = [x * k for x in s["band_end"]]
        if s["invalidation"] is not None:
            s["invalidation"] *= k
    return o


def test_units_are_invariant_to_scale_and_currency():
    o, c = opp(), closes()
    a = rank.normalize(o, c)
    for k in (1e-4, 3_900.0, 1e6):                  # céntimos, COP, otra escala
        b = rank.normalize(scaled(o, k), [x * k for x in c])
        for f in ("sigma_bar", "sigma_h", "gross", "net", "edge_sigma", "edge_r",
                  "uncertainty_sigma", "r_unit"):
            assert getattr(b, f) == pytest.approx(getattr(a, f), rel=1e-9), f
        assert b.scores == pytest.approx(a.scores)
        assert rank.priority(b) == pytest.approx(rank.priority(a))


def test_net_of_cost_and_in_sigma_of_its_own_horizon():
    c = closes()
    n = rank.normalize(opp(cost=0.004), c)
    assert n.net == pytest.approx(n.gross - 0.004)
    assert n.sigma_h == pytest.approx(rank.bar_sigma(c) * 5)            # √25
    assert n.edge_sigma == pytest.approx(n.net / n.sigma_h)
    assert n.r_unit == pytest.approx(0.03) and "SL" in n.r_source       # 100 → 97
    # mismo movimiento en σ de su horizonte con horizonte 4× más largo ⇒ misma ventaja en σ
    c4 = closes(sigma=0.01)
    long = rank.normalize(opp(h=100, cost=0.004), c4)
    assert long.sigma_h == pytest.approx(rank.bar_sigma(c4) * 10)
    assert long.edge_sigma == pytest.approx(long.net / long.sigma_h)


def test_short_side_and_missing_invalidation_say_what_was_assumed():
    n = rank.normalize(opp(side="corto", inv=None, bull=104, bear=94, p=(0.2, 0.3, 0.5)),
                       closes())
    assert n.gross > 0                                   # a la baja es a favor del corto
    assert n.r_unit == pytest.approx(n.sigma_h) and "supuesto" in n.r_source


def test_scores_stay_separate_and_only_the_priority_combines_them():
    n = rank.normalize(opp(q=0.9, v=0.1, r=0.5), closes())
    assert set(n.scores) == set(rank.SCORE_KEYS)
    assert n.scores["quality"] == 0.9 and n.scores["viability"] == 0.1
    assert rank.priority(n) == pytest.approx(sum(n.scores.values()) / 4)
    w = rank.Weights({"quality": 1.0, "viability": 0, "risk": 0, "edge": 0})
    assert rank.priority(n, w) == pytest.approx(0.9)


def test_not_comparable_without_its_class_cost_or_sigma():
    n = rank.normalize(opp(cost=None), closes())
    assert not n.comparable and rank.priority(n) is None and "costo" in n.notes[0]
    short = rank.normalize(opp(), closes(n=10))
    assert not short.comparable and short.sigma_h is None


def test_rank_orders_by_priority_and_puts_the_incomparable_last():
    o1, o2, o3 = opp("op-1", q=0.2), opp("op-2", q=0.9), opp("op-3", cost=None)
    rows = rank.rank([o1, o3, o2], {o1["instrument_id"]: closes()})
    assert [r["opportunity_id"] for r in rows] == ["op-2", "op-1", "op-3"]
    assert [r["position"] for r in rows] == [1, 2, None]
    assert rank.rank([o2, o1], {o1["instrument_id"]: closes()}) == rows[:2]   # sin orden previo


def test_weights_load_save_and_fall_back_to_equal(tmp_path):
    assert rank.load_weights(tmp_path) == rank.DEFAULT_WEIGHTS
    w = rank.Weights({"quality": 2, "viability": 1, "risk": 1, "edge": 0}, True, "prueba")
    rank.save_weights(tmp_path, rank.Weights(rank._clean(w.values), True, "prueba"), {"n": 1})
    got = rank.load_weights(tmp_path)
    assert got.calibrated and got.values["quality"] == pytest.approx(0.5)
    assert got.fingerprint != rank.DEFAULT_WEIGHTS.fingerprint
    rank.weights_path(tmp_path).write_text('{"values": {"quality": -1}}', encoding="utf-8")
    assert rank.load_weights(tmp_path) == rank.DEFAULT_WEIGHTS


def _rows(n, predictive: str | None, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for t in range(n):
        s = {k: float(rng.random()) for k in rank.SCORE_KEYS}
        y = (3 * s[predictive] if predictive else 0.0) + rng.normal(0, 0.5)
        out.append({"t": t * DAY, "scores": s, "outcome": y})
    return out


def test_calibration_needs_sample_and_only_adopts_out_of_sample_gains():
    small = rank.calibrate(_rows(50, "viability"))
    assert not small["adopted"] and "insuficiente" in small["reason"]
    good = rank.calibrate(_rows(400, "viability"))
    assert good["adopted"] and good["weights"]["viability"] == 1.0
    assert good["holdout_corr"] > good["holdout_default_corr"]
    assert good["n_fit"] + good["n_holdout"] == 400
    noise = rank.calibrate(_rows(400, None, seed=3))
    assert noise["holdout_corr"] is None or noise["holdout_corr"] < 0.2
