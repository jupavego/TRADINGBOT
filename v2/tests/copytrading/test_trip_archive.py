"""Archivo de lo viejo de un líder (T128, puro): arrancar el plegado desde lo archivado y
aplicar solo lo posterior da lo mismo que `build_trips` + `copy_stats` sobre todo el
historial, corte donde se corte; se corta con la posición abierta o no (el viaje abierto se
archiva plegado), pero solo con todo definitivo."""

from __future__ import annotations

from eim.copytrading import ScoreParams
from eim.copytrading.copyability import copy_stats
from eim.copytrading.forward import forward_trips
from eim.copytrading.trades import build_trips
from eim.copytrading.trip_archive import Counts, advance
from eim.copytrading.trip_fold import LeaderFold
from tests.copytrading import helpers as H
from tests.copytrading.fold_stream import stream
from tests.copytrading.test_trip_fold import _row, _same_trips, _sorted_rows

P = ScoreParams()


def _bases(rows, limit: int, final: int, max_rows=None) -> dict:
    out = {}
    for sym in sorted({r.symbol for r in rows}):
        base = None
        while True:
            new = advance(base, sym, [r for r in rows if r.symbol == sym and
                                      (base is None or r.t > base.cut_t) and r.t <= limit],
                          final, P, max_rows)
            if new is None:
                break
            assert base is None or new.cut_t > base.cut_t
            base = new
        if base is not None:
            out[sym] = base
    return out


def _resumed(rows, bases: dict, final: int) -> LeaderFold:
    fold = LeaderFold(P)
    fold.begin(final, {})
    for b in bases.values():
        fold.restore(b)
    for r in rows:
        b = bases.get(r.symbol)
        if b is None or r.t > b.cut_t:
            fold.observe(r)
            fold.apply(r)
    fold.settle()
    return fold


def test_resuming_from_the_archive_equals_the_full_history_at_any_cut():
    s = stream(n=1_200)
    quotes = {(q.tid, q.oid): q for _, q in s.quotes}
    rows = _sorted_rows(s.fills, quotes)
    trips = build_trips(s.fills, s.funding, P.avg_down_tol)
    start = H.T0 + 40 * 60_000
    want = copy_stats(forward_trips(trips, start), s.fills, quotes, P)
    archived, opened = 0, 0
    for frac in (0.1, 0.35, 0.6, 0.9, 1.0):
        limit = H.T0 + int((s.end - H.T0) * frac)
        bases = _bases(rows, limit, s.end)
        for b in bases.values():  # cada corte deja todo plegado: ninguna pata pendiente
            assert b.cut_t <= limit and all(not tr.legs for tr in b.trips)
            assert (b.open is None) == (abs(b.prev) < 1e-9)
            assert b.open is None or not b.open.legs
            opened += b.open is not None
        archived = max(archived, sum(b.n for b in bases.values()))
        fold = _resumed(rows, bases, s.end)
        got_trips = fold.trips(s.funding)
        _same_trips(trips, got_trips)
        assert fold.n == len(rows)
        got = fold.copy_stats(forward_trips(got_trips, start))
        assert got.model_dump() == want.model_dump(), frac
    assert archived > 0.8 * len(rows)
    assert opened  # la prueba pasa también por cortes con la posición abierta


def test_batches_reach_the_same_archive_as_one_pass():
    s = stream(n=600, seed=11)
    rows = _sorted_rows(s.fills, {(q.tid, q.oid): q for _, q in s.quotes})
    one = _bases(rows, s.end, s.end)
    many = _bases(rows, s.end, s.end, max_rows=25)
    assert one.keys() == many.keys()
    for sym in one:
        a, b = one[sym], many[sym]
        assert (a.cut_t, a.prev, a.n, a.taker, a.latency) == (b.cut_t, b.prev, b.n, b.taker,
                                                               b.latency)
        _same_trips(a.trips, b.trips)


def test_cuts_with_an_open_position_but_only_final():
    op = H.fill("BTC", 0.0, 2.0, 100.0, H.T0, 1)
    up = H.fill("BTC", 2.0, 3.0, 101.0, H.T0 + 1_000, 2)
    cl = H.fill("BTC", 3.0, 0.0, 102.0, H.T0 + 2_000, 3, pnl=5.0)
    op2 = H.fill("BTC", 0.0, -1.0, 103.0, H.T0 + 3_000, 4)
    quotes = H.quotes([op, up, cl, op2])
    rows = [_row(f, quotes[(f.tid, f.oid)]) for f in (op, up, cl, op2)]
    base = advance(None, "BTC", rows, H.T0, P)
    assert base.cut_t == op2.t and base.prev == -1.0 and len(base.trips) == 1
    assert base.open.side == "short" and base.open.follow.quoted == 1 and not base.open.legs
    assert base.trips[0].follow.quoted == 3 and base.n == 4
    bare = [_row(f) for f in (op, up, cl)]  # sin cotización: la del cierre aún podría llegar
    got = advance(None, "BTC", bare, cl.observed_at - 1, P)
    assert got.cut_t == up.t and got.open.follow.ok is False and got.n == 2  # no en el cierre
    assert advance(None, "BTC", bare[:1], op.observed_at - 1, P) is None  # nada definitivo
    assert advance(None, "BTC", bare, cl.observed_at, P).cut_t == cl.t  # ya no llegará


def test_a_leader_that_never_goes_flat_is_archived_and_resumes_the_same():
    """El caso que dejaba crecer la base: la posición nunca vuelve a cero."""
    fills, pos = [], 0.0
    for i in range(300):
        nxt = 1.0 + (i * 7919 % 5)  # 1..5, nunca 0
        fills.append(H.fill("BTC", pos, nxt, 100.0 + (i % 13) * 0.5, H.T0 + i * 1_000, i + 1))
        pos = nxt
    quotes = H.quotes(fills)
    rows = _sorted_rows(fills, quotes)
    end = H.T0 + 400_000
    trips = build_trips(fills, [], P.avg_down_tol)
    for frac in (0.2, 0.5, 0.95):
        limit = H.T0 + int(300_000 * frac)
        bases = _bases(rows, limit, end, max_rows=37)
        b = bases["BTC"]
        assert b.open is not None and b.cut_t > H.T0 + int(300_000 * frac) - 2_000
        fold = _resumed(rows, bases, end)
        _same_trips(trips, fold.trips([]))
        assert fold.n == len(rows)
        assert fold.copy_stats(fold.trips([])).model_dump() == copy_stats(
            trips, fills, quotes, P).model_dump()


def test_counts_match_the_fold():
    s = stream(n=400, seed=2)
    rows = _sorted_rows(s.fills, {})
    c, fold = Counts(), LeaderFold(P)
    for r in rows:
        c.observe(r, P)
        fold.observe(r)
    assert c.n == fold.n and [c.taker_x, c.taker_n] == fold.taker
    for ch, xs in fold.latency.items():
        assert sorted(xs) == sorted(float(ms) for ms, k in c.latency[ch].items()
                                    for _ in range(k))
