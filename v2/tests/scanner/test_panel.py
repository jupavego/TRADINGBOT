"""T93 — panel del universo: filas alineadas a la derecha, recorte y huella de datos."""

from __future__ import annotations

import numpy as np

from eim.scanner import panel as P
from tests.scanner._helpers import candles, rows_of


def _panel(series, width=10, extra=()):
    ids = {s: f"crypto.binance.usdm.{s}" for s in [*series, *extra]}
    return P.from_rows(ids, *rows_of(series), width=width)


def test_rows_are_right_aligned_and_padded_with_nan():
    p = _panel({"AUSDT": candles(4), "BUSDT": candles(10, seed=1)}, extra=("CUSDT",))
    assert p.ids == tuple(f"crypto.binance.usdm.{s}" for s in ("AUSDT", "BUSDT", "CUSDT"))
    assert p.n.tolist() == [4, 10, 0]
    assert np.isnan(p.c[0, :6]).all() and np.isfinite(p.c[0, 6:]).all()
    assert p.t[0, -1] == candles(4)[-1].t and p.c[1, -1] == candles(10, seed=1)[-1].c
    assert (p.last_t() == [candles(4)[-1].t, candles(10, seed=1)[-1].t, 0]).all()


def test_more_bars_than_width_keeps_the_latest():
    cs = candles(15, seed=2)
    p = _panel({"AUSDT": cs}, width=10)
    assert p.n[0] == 10 and p.t[0, 0] == cs[5].t and p.c[0, -1] == cs[-1].c


def test_hash_changes_with_any_bar_and_not_with_the_neighbours():
    a, b = candles(10, seed=3), candles(10, seed=4)
    h0 = _panel({"AUSDT": a, "BUSDT": b}).hashes
    changed = [*a[:-1], a[-1].model_copy(update={"c": a[-1].c * 1.001})]
    h1 = _panel({"AUSDT": changed, "BUSDT": b}).hashes
    assert h0[0] != h1[0] and h0[1] == h1[1]
    h2 = _panel({"AUSDT": a, "BUSDT": b}).hashes
    assert h0 == h2


def test_take_keeps_rows_consistent():
    p = _panel({"AUSDT": candles(10), "BUSDT": candles(10, seed=1)})
    q = p.take([1])
    assert q.ids == (p.ids[1],) and q.hashes == (p.hashes[1],) and (q.c[0] == p.c[1]).all()


def test_synthetic_panel_is_reproducible():
    a, b = P.synthetic(50, 90, seed=7), P.synthetic(50, 90, seed=7)
    assert a.hashes == b.hashes and a.nbytes() == 50 * 90 * 6 * 8 + 50 * 8
