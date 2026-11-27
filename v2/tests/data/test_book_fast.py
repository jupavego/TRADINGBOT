"""`FastBook` (T80) tiene que dar exactamente el mismo libro que `LocalBook` (T23)."""

from __future__ import annotations

import numpy as np

from eim.data.collectors.book import LocalBook
from eim.data.collectors.book_fast import FastBook

TICK = 0.1


def _snapshot(mid: float = 100_000.0, n: int = 40):
    bids = [(round(mid - (i + 1) * TICK, 1), 1.0 + i) for i in range(n)]
    asks = [(round(mid + (i + 1) * TICK, 1), 1.0 + i) for i in range(n)]
    return bids, asks


def _diffs(rng: np.random.Generator, n: int, mid: float = 100_000.0):
    """Secuencia encadenada de diffs con niveles nuevos, borrados y libros cruzados."""
    out, u = [], 1000
    for _ in range(n):
        prev, u = u, u + rng.integers(1, 5)
        side_b, side_a = [], []
        for _k in range(int(rng.integers(0, 4))):
            p = round(mid + float(rng.normal(0, 3)), 1)
            q = 0.0 if rng.random() < 0.3 else float(round(rng.random() * 5, 3))
            (side_b if rng.random() < 0.5 else side_a).append((p, q))
        out.append((prev + 1, u, prev, side_b, side_a))
    return out


def test_mismo_libro_y_mismo_top_que_localbook():
    rng = np.random.default_rng(7)
    bids, asks = _snapshot()
    slow, fast = LocalBook(), FastBook()
    slow.load_snapshot(1002, bids, asks)      # el primer diff lo contiene (U ≤ id ≤ u)
    fast.load_snapshot(1002, bids, asks)
    seen = {"ok": 0, "gap": 0, "stale": 0, "unsynced": 0}
    for first, last, prev, b, a in _diffs(rng, 400):
        r_slow = slow.apply(first, last, prev, b, a)
        r_fast = fast.apply(first, last, prev, b, a)
        assert r_slow == r_fast
        seen[r_slow] = seen.get(r_slow, 0) + 1
        assert slow.bids == fast.bids
        assert slow.asks == fast.asks
        assert slow.top(5) == fast.top(5)
        assert slow.ghosts_pruned == fast.ghosts_pruned
        assert sorted(slow.last_pruned) == sorted(fast.last_pruned)
        if r_slow == "gap":                      # resincroniza los dos igual y sigue
            slow.load_snapshot(last + 2, bids, asks)
            fast.load_snapshot(last + 2, bids, asks)
    assert seen["ok"] > 100
    assert fast.ghosts_pruned > 0                # la secuencia cruza el libro de verdad


def test_hueco_de_secuencia_desincroniza():
    bids, asks = _snapshot()
    fast = FastBook()
    assert fast.apply(1, 2, 0, [], []) == "unsynced"
    fast.load_snapshot(100, bids, asks)
    assert fast.apply(90, 110, 89, [(99_999.9, 2.0)], []) == "ok"
    assert fast.apply(200, 210, 199, [], []) == "gap"       # `pu` no encadena
    assert fast.bids == {} and fast.top(3) == ([], [])


def test_top_y_mejores_precios():
    bids, asks = _snapshot(n=3)
    fast = FastBook()
    fast.load_snapshot(1, bids, asks)
    assert fast.best_bid == 99_999.9
    assert fast.best_ask == 100_000.1
    top_b, top_a = fast.top(2)
    assert [p for p, _ in top_b] == [99_999.9, 99_999.8]
    assert [p for p, _ in top_a] == [100_000.1, 100_000.2]
