"""T93 — etapa 3: vectorizada, determinista, con calidad y sin depender del orden de entrada."""

from __future__ import annotations

import numpy as np
import pytest

from eim.scanner import screen as S
from eim.scanner.panel import synthetic


def test_same_inputs_give_bitwise_identical_scores():
    p = synthetic(300, 90, seed=11)
    a, b = S.screen(p, ["crypto"] * 300), S.screen(p, ["crypto"] * 300)
    assert a.fingerprint() == b.fingerprint()
    assert np.array_equal(a.score, b.score, equal_nan=True)
    for k in a.metrics:
        assert np.array_equal(a.metrics[k], b.metrics[k], equal_nan=True), k


def test_input_order_does_not_change_any_score():
    p = synthetic(120, 90, seed=12)
    rev = p.take(list(range(p.size))[::-1])
    a, b = S.screen(p, ["crypto"] * p.size), S.screen(rev, ["crypto"] * p.size)
    assert a.ids == b.ids and a.fingerprint() == b.fingerprint()


def test_metrics_match_their_definitions():
    p = synthetic(5, 90, seed=13)
    r = S.screen(p, ["crypto"] * 5)
    c = p.c
    assert np.allclose(r.metrics["ret_1"], np.log(c[:, -1] / c[:, -2]))
    assert np.allclose(r.metrics["ret_20"], np.log(c[:, -1] / c[:, -21]))
    lr = np.diff(np.log(c[:, -61:]), axis=1)
    assert np.allclose(r.metrics["vol_20"], lr[:, -20:].std(axis=1, ddof=1))
    assert ((r.score >= 0) & (r.score <= 1)).all()


def test_relative_strength_uses_btc_for_crypto_and_the_median_elsewhere():
    p = synthetic(6, 90, seed=14)
    ids = ("crypto.binance.usdm.BTCUSDT", "crypto.binance.usdm.ETHUSDT",
           "crypto.binance.usdm.SOLUSDT", "commodity.binance.usdm.XAUUSDT",
           "commodity.binance.usdm.XAGUSDT", "commodity.binance.usdm.XPTUSDT")
    p = type(p)(**{**p.__dict__, "ids": ids, "symbols": tuple(i.rsplit(".", 1)[1] for i in ids)})
    classes = ["crypto"] * 3 + ["commodity"] * 3
    r = S.screen(p, [classes[ids.index(i)] for i in p.ids])
    m = dict(zip(r.ids, r.metrics["rs"], strict=True))
    ret = dict(zip(r.ids, r.metrics["ret_20"], strict=True))
    assert m["crypto.binance.usdm.BTCUSDT"] == 0.0
    assert m["crypto.binance.usdm.ETHUSDT"] == pytest.approx(
        ret["crypto.binance.usdm.ETHUSDT"] - ret["crypto.binance.usdm.BTCUSDT"])
    med = np.median([ret[i] for i in ids[3:]])
    assert m["commodity.binance.usdm.XAUUSDT"] == pytest.approx(
        ret["commodity.binance.usdm.XAUUSDT"] - med)


def test_quality_penalises_zero_volume_flat_bars_and_jumps():
    p = synthetic(4, 90, seed=15)
    v, h, c = p.v.copy(), p.h.copy(), p.c.copy()
    v[1, -20:] = 0.0                                    # sin volumen
    h[2, -20:] = p.l[2, -20:]                           # velas planas
    c[3, -5] = c[3, -6] * 1.8                           # salto de +80 %
    q = type(p)(**{**p.__dict__, "v": v, "h": h, "c": c})
    r = S.screen(q, ["crypto"] * 4)
    assert r.quality[0] == 1.0
    assert r.quality[1] == 0.0 and r.quality[2] == 0.0
    assert 0 < r.quality[3] < 1.0 and r.metrics["jumps"][3] >= 1


def test_pct_rank_averages_ties_and_keeps_nan():
    x = np.array([3.0, 1.0, 3.0, np.nan, 2.0])
    r = S.pct_rank(x)
    assert r[1] == 0.0 and r[4] == pytest.approx(1 / 3) and r[0] == r[2] == pytest.approx(5 / 6)
    assert np.isnan(r[3])


def test_shortlist_is_ordered_by_score_then_id():
    p = synthetic(40, 90, seed=16)
    r = S.screen(p, ["crypto"] * 40)
    top = r.shortlist(10)
    scores = [r.score[r.ids.index(i)] for i in top]
    assert scores == sorted(scores, reverse=True) and len(top) == 10
    rows = r.rows()
    assert [x["rank"] for x in rows] == list(range(1, 41)) and rows[0]["instrument_id"] == top[0]


def test_short_series_are_refused_not_guessed():
    p = synthetic(3, 90, seed=17)
    short = type(p)(**{**p.__dict__, "n": np.array([90, 40, 90])})
    with pytest.raises(ValueError, match="61"):
        S.screen(short, ["crypto"] * 3)


def test_cost_per_instrument_is_measured_and_tiny():
    p = synthetic(2000, 90, seed=18)
    r = S.screen(p, ["crypto"] * 2000)
    assert r.elapsed_ms > 0 and r.ms_per_instrument < 2.0     # presupuesto de T87: 20 ms
