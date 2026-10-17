"""Triangular solo con ticker (optimista): precios coherentes no dan oportunidades."""

from __future__ import annotations

import numpy as np

from eim.arbitrage.sim import ArbHistory, Bars
from eim.arbitrage.sim.triangular import scan_ticker
from eim.core import CostModel, SpotPair
from tests.arbitrage.sim.helpers import T0

PAIRS = (SpotPair(symbol="BTCUSDT", base="BTC", quote="USDT"),
         SpotPair(symbol="ETHUSDT", base="ETH", quote="USDT"),
         SpotPair(symbol="ETHBTC", base="ETH", quote="BTC"))
VIP9 = CostModel(spot_vip=9, futures_vip=9, bnb_discount=True)


def _hist(ethbtc: np.ndarray) -> ArbHistory:
    n = len(ethbtc)
    t = T0 + np.arange(n, dtype=np.int64) * 60_000
    bars = {"BTCUSDT": Bars.flat(t, np.full(n, 50_000.0)),
            "ETHUSDT": Bars.flat(t, np.full(n, 2_500.0)),
            "ETHBTC": Bars.flat(t, ethbtc)}
    return ArbHistory(assets={}, tri_bars=bars, tri_pairs=PAIRS)


def test_consistent_prices_leave_no_opportunity():
    res = scan_ticker(_hist(np.full(100, 0.05)), {"VIP 0": CostModel(), "VIP 9": VIP9}, 1e4)
    assert len(res["cycles"]) == 2 and "optimista" in res["label"]
    for c in res["cycles"]:
        assert abs(c["gross_max_bps"]) < 1e-6
        assert c["by_cost"]["VIP 0"]["minutes_pos"] == 0
        assert c["by_cost"]["VIP 0"]["fee_bps"] > 29  # 3 patas a 0,10 %
    assert set(res["no_depth"]) == {"BTCUSDT", "ETHUSDT", "ETHBTC"}  # declarado


def test_mispricing_above_fees_counts_only_with_cheap_fees():
    px = np.full(100, 0.05)
    px[10] = 0.05 * 1.002  # ETH caro en BTC: USDT→ETH→BTC→USDT gana 20 pb brutos
    res = scan_ticker(_hist(px), {"VIP 0": CostModel(), "VIP 9": VIP9}, 1e4)
    best = max(res["cycles"], key=lambda c: c["gross_max_bps"])
    assert best["cycle"] == "USDT→ETH→BTC→USDT"
    assert best["by_cost"]["VIP 0"]["minutes_pos"] == 0
    assert best["by_cost"]["VIP 9"]["minutes_pos"] == 1
    assert best["by_cost"]["VIP 9"]["upper_bound_usd"] > 0


def test_real_books_override_optimistic_ticker():
    from eim.arbitrage.sim.verdict import _tri_verdict

    ticker = {"cycles": [{"by_cost": {"VIP 0": {"minutes_pos": 12}}}]}
    real_neg = {**ticker, "captured": {"captures": 5, "by_cost": {
        "VIP 0": {"cycles": 80, "positive": 0, "best_bps": -12.0}}}}
    label, why = _tri_verdict(real_neg)
    assert label == "No viable" and "cota superior" in why[0] and "0 de 80" in why[1]
    assert _tri_verdict(ticker)[0] == "Marginal"  # sin libros reales, solo la cota
