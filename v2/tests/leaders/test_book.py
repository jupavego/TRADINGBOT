"""Libro esperado (T40) sobre respuestas reales grabadas y escenarios sintéticos."""

from __future__ import annotations

from decimal import Decimal

import pytest

from eim.leaders.book import LeaderBook
from eim.leaders.parse import classify, order_fills, parse_positions
from tests.leaders.helpers import ACTIVE, CLOSER, fill, leader, load, state


def _book(addr: str, st: dict) -> LeaderBook:
    b = LeaderBook(leader(addr))
    t, pos = parse_positions(b.leader, st, 0)
    b.load(t, pos)
    return b


def _apply_all(b: LeaderBook, raws: list[dict], channel: str = "ws") -> tuple[list, list]:
    fills, gaps = [], []
    for r in order_fills(raws):
        f, g = b.apply(r, 1, channel)
        fills += [f] if f else []
        gaps += [g] if g else []
    return fills, gaps


@pytest.mark.parametrize(("start", "end", "action", "side"), [
    ("0", "1.5", "open", "long"), ("0", "-2", "open", "short"),
    ("1", "1.5", "increase", "long"), ("-1", "-3", "increase", "short"),
    ("2", "0.5", "reduce", "long"), ("-2", "-1", "reduce", "short"),
    ("2", "0", "close", "long"), ("-2", "0", "close", "short"),
    ("1", "-1", "flip", "short"), ("-1", "2", "flip", "long"),
])
def test_classify(start, end, action, side):
    assert classify(Decimal(start), Decimal(end)) == (action, side)


def test_recorded_rest_fills_reproduce_exchange_state():
    """Estado real → 101 ejecuciones reales → coincide con el estado real 2 min después."""
    b = _book(ACTIVE, load("active_state0"))
    fills, gaps = _apply_all(b, load("active_fills_by_time"), "rest_backfill")
    t1, p1 = parse_positions(b.leader, load("active_state1"), 0)
    rec = b.compare(t1, p1)
    assert not gaps and rec.match and not rec.skipped
    assert len(rec.checked) == 6
    live = [f for f in fills if f.t > b.as_of]
    assert {f.action for f in live} >= {"reduce", "increase"}  # incluye cierres parciales
    assert len(fills) == len(load("active_fills_by_time"))  # las previas quedan como historial


def test_recorded_ws_stream_reproduces_state_and_ignores_snapshot_history():
    b = _book(ACTIVE, load("active_state0"))
    for m in load("active_ws_user_fills"):
        d = m["data"]
        for r in order_fills(d["fills"]):
            _, g = b.apply(r, m["_observed_at"], "ws_snapshot" if d.get("isSnapshot") else "ws")
            assert g is None
    t1, p1 = parse_positions(b.leader, load("active_state1"), 0)
    assert b.compare(t1, p1).match


def test_rest_newest_first_order_is_rebuilt_by_chain():
    """`userFills` (REST) llega del más nuevo al más viejo: mismo resultado invertido."""
    raws = load("active_fills_by_time")
    a, b = _book(ACTIVE, load("active_state0")), _book(ACTIVE, load("active_state0"))
    _, gaps_a = _apply_all(a, raws)
    _, gaps_b = _apply_all(b, list(reversed(raws)))
    assert not gaps_a and not gaps_b and a.positions() == b.positions()


def test_real_close_of_whole_position():
    b = _book(CLOSER, load("close_state0"))
    fills, gaps = _apply_all(b, load("close_fills_by_time"))
    live = [f for f in fills if f.t > b.as_of]
    assert [f.action for f in live] == ["close"] and not gaps
    assert live[0].end_position == 0 and b.positions() == {}
    t1, p1 = parse_positions(b.leader, load("close_state1"), 0)
    assert b.compare(t1, p1).match


def test_duplicate_events_are_ignored():
    b = _book(ACTIVE, load("active_state0"))
    raws = load("active_fills_by_time")
    first, _ = _apply_all(b, raws)
    before = b.positions()
    again, gaps = _apply_all(b, raws + raws[:5])
    assert first and again == [] and gaps == [] and b.positions() == before


def test_gap_detected_reanchored_and_late_backfill_is_history_only():
    raws = order_fills(load("active_fills_by_time"))
    b = _book(ACTIVE, load("active_state0"))
    live = [i for i, r in enumerate(raws) if r["time"] > b.as_of]
    missing = next(raws[i] for i in live  # una ejecución con otra posterior de la misma moneda
                   if any(raws[j]["coin"] == raws[i]["coin"] for j in live if j > i))
    rest = [r for r in raws if r is not missing]
    _, gaps = _apply_all(b, rest)
    assert len(gaps) == 1 and gaps[0].cause == "secuencia" and gaps[0].symbol == missing["coin"]
    f, g = b.apply(missing, 2, "rest_backfill")  # llega tarde: historial, no mueve el libro
    assert f is not None and g is None
    t1, p1 = parse_positions(b.leader, load("active_state1"), 0)
    rec = b.compare(t1, p1)
    assert rec.size_ok  # el reanclaje por startPosition deja el tamaño correcto


def test_partial_close_increase_flip_and_entry_average():
    b = _book("0x" + "ab" * 20, state(1000))
    seq = [fill("BTC", "B", "1.0", "100", "0.0", 1001, 1),   # abre long 1 @100
           fill("BTC", "B", "1.0", "110", "1.0", 1002, 2),   # aumenta → 2 @105
           fill("BTC", "A", "0.5", "120", "2.0", 1003, 3),   # cierre parcial → 1.5 @105
           fill("BTC", "A", "2.5", "90", "1.5", 1004, 4),    # giro → short 1 @90
           fill("BTC", "B", "1.0", "95", "-1.0", 1005, 5)]   # cierra
    fills, gaps = _apply_all(b, seq)
    assert [f.action for f in fills] == ["open", "increase", "reduce", "flip", "close"]
    assert [f.side for f in fills] == ["long", "long", "long", "short", "short"]
    assert not gaps and b.positions() == {}
    b2 = _book("0x" + "ab" * 20, state(1000))
    _apply_all(b2, seq[:3])
    size, entry = b2.positions()["BTC"]
    assert size == Decimal("1.5") and entry == pytest.approx(105.0)


def test_leverage_change_detected_once():
    b = _book("0x" + "ab" * 20, state(1000, ("ETH", "-2.0", "2500.0", 10, "cross")))
    t, pos = parse_positions(b.leader, state(2000, ("ETH", "-2.0", "2500.0", 20, "isolated")), 0)
    rec = b.compare(t, pos)
    assert rec.match and len(rec.leverage) == 1
    ch = rec.leverage[0]
    assert (ch.old, ch.new, ch.old_mode, ch.new_mode) == (10, 20, "cross", "isolated")
    b.refresh(pos, rec)
    assert b.compare(t, pos).leverage == ()
    f, _ = b.apply(fill("ETH", "A", "1.0", "2400", "-2.0", 2001, 9), 1, "ws")
    assert f.leverage == 20  # las ejecuciones heredan el último apalancamiento conocido


def test_reconcile_skips_coins_already_ahead_and_reports_size_diff():
    b = _book("0x" + "ab" * 20, state(1000, ("BTC", "1.0", "100", 5, "cross")))
    b.apply(fill("BTC", "B", "1.0", "100", "1.0", 1500, 1), 1, "ws")
    t, pos = parse_positions(b.leader, state(1400, ("BTC", "1.0", "100", 5, "cross"),
                                             ("SOL", "3.0", "10", 3, "cross")), 0)
    rec = b.compare(t, pos)
    assert rec.skipped == ("BTC",) and not rec.size_ok
    assert rec.diffs[0].symbol == "SOL" and rec.diffs[0].actual == "3.0"


def test_liquidation_flag_only_for_the_leader_itself():
    me = "0x" + "ab" * 20
    b = _book(me, state(1000, ("BTC", "1.0", "100", 5, "cross")))
    someone = "0x" + "cd" * 20
    other = fill("BTC", "A", "0.5", "90", "1.0", 1001, 1,
                 liquidation={"liquidatedUser": someone, "markPx": "90", "method": "market"})
    mine = fill("BTC", "A", "0.5", "80", "0.5", 1002, 2,
                liquidation={"liquidatedUser": me, "markPx": "80", "method": "market"})
    f1, _ = b.apply(other, 1, "ws")
    f2, _ = b.apply(mine, 1, "ws")
    assert not f1.liquidated and f2.liquidated and f2.action == "close"


def test_spot_fills_are_not_followed():
    b = _book("0x" + "ab" * 20, state(1000))
    for tid, coin in enumerate(("@107", "PURR/USDC", "xyz:NVDA")):  # spot y HIP-3
        f, g = b.apply(fill(coin, "B", "1.0", "1", "0.0", 1001, tid), 1, "ws")
        assert f is None and g is None
    assert b.positions() == {}
