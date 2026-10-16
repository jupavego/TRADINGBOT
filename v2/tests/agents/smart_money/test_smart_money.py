"""Agente `smart_money` (T41): sin líderes → no_data; peso por calidad limitado por líder."""

from __future__ import annotations

from eim.agents.smart_money import NO_APPROVED, NO_BOARD, SmartMoneyAgent
from eim.core import Candle, LeaderWeight, MarketSnapshot, PositionChange
from tests.copytrading.helpers import position

ASOF = 1_790_000_000_000
A, B, C = (f"hyperliquid:0x{c * 40}" for c in "abc")


def _w(lid: str, q: float = 0.8, av: float = 1_000_000.0, age: int = 30_000, **kw):
    return LeaderWeight(leader_id=lid, quality=q, account_value=av, hold_ms=6 * 3_600_000,
                        scored_at=ASOF - 10_000, positions_at=ASOF - age, **kw)


def _snap(positions, weights, symbol="BTCUSDT") -> MarketSnapshot:
    candles = [Candle(t=ASOF - 3_600_000 * (3 - i), o=60_000, h=60_100, l=59_900, c=60_000,
                      v=1.0) for i in range(3)]
    return MarketSnapshot(symbol=symbol, timeframe="1h", candles=candles, asof=ASOF,
                          leaders=positions, leader_weights=weights,
                          sources={"leaders": "hyperliquid"}, coverage={"leaders": (ASOF, ASOF)})


def test_no_board_and_no_approved_are_no_data():
    agent = SmartMoneyAgent()
    for snap, why in ((_snap(None, None), NO_BOARD), (_snap([], []), NO_APPROVED)):
        rep = agent.run(snap)
        assert rep.status == "no_data" and rep.bias == 0 and rep.confidence == 0
        assert rep.warnings == [why]


def test_approved_longs_give_positive_bias_weighted_by_quality():
    pos = [position("BTC", "long", 10.0, 59_000.0, ASOF, lid=A),
           position("BTC", "long", 5.0, 59_500.0, ASOF, lid=B),
           position("ETH", "short", 100.0, 2_500.0, ASOF, lid=C)]  # C: plano en BTC → neutral
    rep = SmartMoneyAgent().run(_snap(pos, [_w(A, 0.9), _w(B, 0.6), _w(C, 0.9)]))
    assert rep.status == "ok" and 0 < rep.bias <= 1 and 0 < rep.confidence <= 1
    m = rep.metrics
    assert m["coin"] == "BTC" and m["n_approved"] == 3 and m["n_in_coin"] == 2
    assert m["net_exposure_usd"] == 15.0 * 60_000 and m["short_usd"] == 0
    rows = {r["leader_id"]: r for r in m["leaders"]}
    assert rows[C]["side"] == "plano" and rows[C]["stance"] == 0
    assert all(r["weight"] <= 0.4 for r in rows.values())
    assert rep.horizon_bars == 6


def test_single_leader_cannot_dominate():
    pos = [position("BTC", "long", 100.0, 60_000.0, ASOF, lid=A)]  # exposición 6× la cuenta
    rep = SmartMoneyAgent().run(_snap(pos, [_w(A, 1.0)]))
    assert 0 < rep.bias <= 0.4 and rep.metrics["leaders"][0]["weight"] == 0.4
    assert any("cobertura plena" in w for w in rep.warnings)


def test_opposite_leaders_cancel_and_lower_confidence():
    pos = [position("BTC", "long", 10.0, 60_000.0, ASOF, lid=A),
           position("BTC", "short", 10.0, 60_000.0, ASOF, lid=B)]
    rep = SmartMoneyAgent().run(_snap(pos, [_w(A), _w(B)]))
    assert abs(rep.bias) < 1e-9 and rep.confidence == 0


def test_stale_photos_do_not_vote():
    pos = [position("BTC", "short", 5.0, 60_000.0, ASOF, lid=A),
           position("BTC", "long", 5.0, 60_000.0, ASOF, lid=B)]
    rep = SmartMoneyAgent().run(_snap(pos, [_w(A), _w(B, age=20 * 60_000)]))
    assert rep.status == "degraded" and rep.bias < 0 and rep.metrics["n_stale"] == 1
    only_stale = SmartMoneyAgent().run(_snap(pos, [_w(B, age=20 * 60_000)]))
    assert only_stale.status == "no_data"


def test_recent_changes_and_determinism():
    ch = [PositionChange(symbol="BTC", window_h=1.0, from_size=0.0, to_size=2.0),
          PositionChange(symbol="ETH", window_h=1.0, from_size=0.0, to_size=-1.0)]
    pos = [position("BTC", "long", 2.0, 60_000.0, ASOF, lid=A)]
    snap = _snap(pos, [_w(A, changes=ch)])
    a, b = SmartMoneyAgent().run(snap), SmartMoneyAgent().run(snap)
    assert a == b and -1 <= a.bias <= 1
    assert a.metrics["changes"] == [{"window_h": 1.0, "from": 0.0, "to": 2.0, "delta": 2.0,
                                     "leader_id": A}]
    assert SmartMoneyAgent().coin("ETHUSDT") == "ETH"
