"""Viajes plegados de forma incremental (T41, puro): mismo resultado que `build_trips` +
`copy_stats` sobre todo el historial, sin guardar las patas ya plegadas."""

from __future__ import annotations

from eim.copytrading import ScoreParams
from eim.copytrading.copyability import copy_stats
from eim.copytrading.forward import forward_trips
from eim.copytrading.trades import SymbolTrips, build_trips
from eim.copytrading.trip_fold import FillRow, LeaderFold, Quote
from tests.copytrading import helpers as H
from tests.copytrading.fold_stream import stream

P = ScoreParams()
_TRIP = ("symbol", "side", "t_open", "t_close", "complete", "before_history", "pnl", "fees",
         "funding", "size_max", "notional_max", "first_size", "avg_downs", "leverage_max",
         "liquidated", "entry", "exit", "taker_share")


def _row(f, q=None) -> FillRow:
    r = FillRow(f.symbol, f.t, f.observed_at, f.tid, f.oid, f.side, f.action, f.size, f.price,
                f.start_position, f.end_position, f.fee, f.closed_pnl, f.crossed, f.liquidated,
                f.leverage, f.channel)
    if q is not None:
        r = r._replace(q_follow_at=q.follow_at, q_quote_t=q.quote_t, q_bid=q.bid, q_ask=q.ask,
                       q_mid=q.mid, q_src=q.src)
    return r


def _sorted_rows(fills, quotes):
    return [_row(f, quotes.get((f.tid, f.oid)))
            for f in sorted(fills, key=lambda f: (f.symbol, f.t, f.observed_at, f.tid))]


def _same_trips(a, b) -> None:
    assert len(a) == len(b)
    for x, y in zip(a, b, strict=True):
        assert [getattr(x, k) for k in _TRIP] == [getattr(y, k) for k in _TRIP]


def test_symbol_trips_fed_one_by_one_equal_build_trips():
    s = stream()
    full = build_trips(s.fills)
    by_sym: dict[str, SymbolTrips] = {}
    for f in sorted(s.fills, key=lambda f: (f.t, f.observed_at, f.tid)):
        by_sym.setdefault(f.symbol, SymbolTrips(f.symbol)).add(f)
    streamed = sorted((tr for b in by_sym.values() for tr in b.trips()),
                      key=lambda tr: (tr.t_open, tr.symbol))
    assert any(not tr.complete for tr in full) and any(tr.closed for tr in full)
    assert any(tr.t_close and tr.symbol == "BTC" for tr in full)
    _same_trips(full, streamed)
    assert [len(tr.legs) for tr in full] == [len(tr.legs) for tr in streamed]


def test_fold_all_at_once_equals_full_history_and_drops_legs():
    s = stream()
    quotes = {(q.tid, q.oid): q for _, q in s.quotes}
    trips = build_trips(s.fills, s.funding, P.avg_down_tol)
    start = H.T0 + 40 * 60_000
    fwd = forward_trips(trips, start)
    want = copy_stats(fwd, s.fills, quotes, P)
    fold = LeaderFold(P)
    fold.begin(s.end, {})  # todo definitivo
    for r in _sorted_rows(s.fills, quotes):
        fold.observe(r)
        fold.apply(r)
    fold.settle()
    got_trips = fold.trips(s.funding)
    _same_trips(trips, got_trips)
    assert all(not tr.legs for tr in got_trips)  # nada del historial queda en memoria
    got = fold.copy_stats(forward_trips(got_trips, start))
    assert want.trades > 5 and want.stale_quotes > 0 and want.unquoted_trades > 0
    assert got.model_dump() == want.model_dump()


def test_pending_leg_counts_as_unquoted_until_its_quote_is_final():
    op = H.fill("BTC", 0.0, 1.0, 100.0, H.T0, 1, delay=200)
    cl = H.fill("BTC", 1.0, 0.0, 101.0, H.T0 + 60_000, 2, delay=200, pnl=1.0)
    q_op = H.quotes([op])[(1, 1)]
    q_cl = H.quotes([cl])[(2, 2)]
    fold = LeaderFold(P)
    fold.begin(cl.observed_at - 1, {})  # la cotización del cierre aún puede llegar
    for r in (_row(op, q_op), _row(cl)):
        fold.observe(r)
        fold.apply(r)
    fold.settle()
    (tr,) = fold.trips([])
    assert len(tr.legs) == 1  # solo el cierre espera; la apertura ya está plegada
    first = fold.copy_stats([tr])
    assert first == copy_stats(build_trips([op, cl]), [op, cl], {(1, 1): q_op}, P)
    assert (first.trades, first.unquoted_trades, first.quoted_fills) == (0, 1, 1)
    fold.begin(cl.observed_at + 300_000, {(2, 2): Quote(q_cl.follow_at, q_cl.quote_t, q_cl.bid,
                                                        q_cl.ask, q_cl.mid, q_cl.src)})
    fold.settle()
    (tr,) = fold.trips([])
    assert not tr.legs
    full = build_trips([op, cl])
    assert fold.copy_stats([tr]) == copy_stats(full, [op, cl], {(1, 1): q_op, (2, 2): q_cl}, P)


def test_stale_flags_backfill_older_than_applied():
    a = H.fill("BTC", 0.0, 1.0, 100.0, H.T0, 1)
    b = H.fill("BTC", 1.0, 2.0, 100.0, H.T0 + 1_000, 2)
    late = H.fill("BTC", 2.0, 3.0, 100.0, H.T0 + 500, 3)  # relleno de un hueco
    fold = LeaderFold(P)
    for f in (a, b):
        fold.apply(_row(f))
    assert fold.stale([_row(late)]) == {"BTC"}
    assert fold.stale([_row(H.fill("ETH", 0.0, 1.0, 10.0, H.T0, 4))]) == set()  # moneda nueva
    assert fold.stale([_row(H.fill("BTC", 2.0, 3.0, 100.0, H.T0 + 2_000, 5))]) == set()
