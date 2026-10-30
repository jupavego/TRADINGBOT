"""Evaluación incremental de líderes (T41, I/O sin red): `EvalCache` vuelta a vuelta da lo
mismo que releer todo el historial (`score(gather(...))`) aunque lleguen rellenos de huecos, un
mismo milisegundo partido entre vueltas, cotizaciones tarde o una unión de otro equipo (T61).
Y la base de líderes tiene tope de memoria y se lee sin el candado de la captura."""

from __future__ import annotations

import random

import duckdb

from eim.copytrading import ScoreParams
from eim.copytrading.scorecard import score
from eim.data.leader_eval import context, evaluate, gather
from eim.data.leader_fold_io import QUOTE_FINAL_MS, EvalCache
from eim.data.leader_store import LeaderStore
from tests.copytrading import helpers as H
from tests.copytrading.fold_stream import _quote, stream

P = ScoreParams()
TICK = 5 * 60_000


def _store(tmp_path) -> LeaderStore:
    store = LeaderStore.at_root(tmp_path)
    store.upsert_leader(H.leader(), 0)
    store.set_status(H.LID, "watch", 0)
    return store


def _feed(store: LeaderStore, s, lo: int, hi: int) -> None:
    """Lo que la captura habría grabado en (lo, hi]: ejecuciones, cotizaciones y funding."""
    store.add_fills([f for f in s.fills if lo < f.observed_at <= hi])
    store.add_follow([q for at, q in s.quotes if lo < at <= hi])
    store.add_funding([r for r in s.funding if lo < r.observed_at <= hi])
    photos = [(H.LID, t, t, "[]") for t in range(H.T0 + 40 * 60_000, hi + 1, 600_000) if t > lo]
    if photos:
        store._insert("leader_positions", "leader_id, t, observed_at, positions", photos)


def _check(store: LeaderStore, cache: EvalCache, asof: int):
    (ld,) = store.leaders()
    want, want_fwd = score(gather(store, ld, asof), 100, asof, P)
    got, got_fwd = cache.score(store, ld, asof, 100, context(store, ld, asof))
    assert got.model_dump() == want.model_dump(), asof
    assert [t.net for t in got_fwd] == [t.net for t in want_fwd]
    return got


def _ticks(store, cache, s, start: int, end: int) -> int:
    prev = start
    for asof in range(start + TICK, end, TICK):
        _feed(store, s, prev, asof)
        _check(store, cache, asof)
        prev = asof
    return prev


def test_incremental_evaluation_equals_rereading_everything(tmp_path):
    s = stream()
    store, cache = _store(tmp_path), EvalCache(P)
    last = _ticks(store, cache, s, H.T0 - 1, s.end + 4 * TICK)
    card = _check(store, cache, last)
    assert card.fwd.n > 5 and card.hist.n > 5 and card.copyability.trades > 0
    assert cache.rebuilds == 1  # solo la primera vuelta lee el historial entero
    assert cache.redone > 0  # los rellenos tardíos rehicieron su moneda, no al líder
    fold = cache.states[H.LID].fold
    assert fold.n == len(s.fills) and not any(tr.legs for tr in fold.trips([]))
    board = evaluate(store, last, P, record=False, cache=cache)
    assert board.model_dump() == evaluate(store, last, P, record=False).model_dump()


def test_union_from_another_machine_rebuilds_the_leader(tmp_path):
    s = stream(seed=5)
    store, cache = _store(tmp_path), EvalCache(P)
    mid = _ticks(store, cache, s, H.T0 - 1, H.T0 + (s.end - H.T0) // 2)
    assert cache.rebuilds == 1
    old = [f for f in s.held if f.observed_at <= mid - TICK]  # los huecos, con su hora vieja
    assert old
    store.add_fills(old)
    _check(store, cache, mid + 1)
    assert cache.rebuilds == 2
    have = {(q.tid, q.oid) for _, q in s.quotes}
    lone = next(f for f in s.fills if (f.tid, f.oid) not in have and f.channel == "ws"
                and f.observed_at < mid - QUOTE_FINAL_MS - TICK)
    store.add_follow([_quote(random.Random(1), lone)[1]])  # cotización vieja de otro equipo
    _check(store, cache, mid + 2)
    assert cache.rebuilds == 3
    _check(store, cache, mid + 3)
    assert cache.rebuilds == 3  # sin novedades no se rehace nada


def test_store_caps_duckdb_memory_and_reads_without_the_capture_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("EIM_DUCKDB_MEMORY", "256MB")
    store = LeaderStore.at_root(tmp_path)
    ref = duckdb.connect()
    ref.execute("SET memory_limit = '256MB'")
    want = ref.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    assert store.query("SELECT current_setting('memory_limit')")[0][0] == want
    assert store.query("SELECT current_setting('threads')")[0][0] == 2
    store.add_fills([H.fill("BTC", 0.0, 1.0, 100.0, H.T0, 1)])
    count = "SELECT count(*) FROM leader_fills"
    with store.reader() as cur:
        assert cur.execute(count).fetchone()[0] == 1
        with store._lock:  # la captura escribiendo: la lectura no espera al candado
            assert cur.execute(count).fetchone()[0] == 1
        store.add_fills([H.fill("BTC", 1.0, 0.0, 101.0, H.T0 + 1, 2)])
        assert cur.execute(count).fetchone()[0] == 1  # instantánea coherente
    assert store.query(count)[0][0] == 2
    store.close()
