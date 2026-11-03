"""T131 — pliegues con purga y embargo (E1) y la comprobación de fuga que pide la aceptación.

La aceptación de T131 dice: «Una prueba demuestra que ninguna operación usada en un tramo de
ajuste se cierra dentro de su tramo de prueba ni del embargo». Es
`test_no_fit_trade_reaches_its_test_span_or_its_embargo`, con operaciones hechas a propósito para
cruzar los dos bordes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eim.paper.exits import walkforward as wf
from eim.paper.exits.bench import BenchTrade
from tests.paper.exits.helpers import trade

DAY = 86_400_000
H = 3_600_000


def ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


START, END = ms("2023-01-01T00:00:00"), ms("2026-08-16T00:00:00")


def at(t: BenchTrade, decided: int, closes: int | None = None) -> BenchTrade:
    """La misma operación decidida en `decided` y cerrada en `closes` (o tras su duración)."""
    end = closes if closes is not None else decided + t.elapsed_ms
    return type(t)(**{**t.__dict__, "t": decided, "fill_t": decided, "exit_t": end,
                      "elapsed_ms": end - decided})


def fold(embargo_ms: int = 2 * DAY) -> wf.Fold:
    fit_to = ms("2024-01-01T00:00:00")
    return wf.Fold(0, START, fit_to, fit_to, ms("2024-04-01T00:00:00"), embargo_ms)


def test_add_months_keeps_the_day_and_clips_to_the_end_of_the_month():
    assert wf.add_months(ms("2023-01-31T00:00:00"), 1) == ms("2023-02-28T00:00:00")
    assert wf.add_months(ms("2024-01-31T00:00:00"), 1) == ms("2024-02-29T00:00:00")
    assert wf.add_months(ms("2023-12-15T00:00:00"), 3) == ms("2024-03-15T00:00:00")
    assert wf.add_months(ms("2023-05-10T00:00:00"), -2) == ms("2023-03-10T00:00:00")


def test_the_design_of_5_3_gives_contiguous_test_spans_and_the_expected_folds():
    fs = wf.folds(START, END)
    # §5.3 estimaba «≈ 11»; con la ventana exacta (2023-01-01 → 2026-08-16) caben 10 enteros: el
    # siguiente probaría 2026-07 → 2026-10 y se saldría del periodo, así que no se usa.
    assert len(fs) == 10
    assert fs[0].fit_from == START and fs[0].test_to == ms("2024-04-01T00:00:00")
    for a, b in zip(fs, fs[1:], strict=False):
        assert b.fit_from == wf.add_months(a.fit_from, 3)
        assert b.test_from == a.test_to       # las pruebas son contiguas: cubren todo el periodo
    assert all(f.fit_to == f.test_from for f in fs)
    assert fs[-1].test_to <= END
    assert "embargo_hours" in fs[0].to_json()


def test_an_incomplete_fold_is_not_used():
    assert wf.folds(START, wf.add_months(START, 14)) == []     # no caben 12 + 3


def test_the_embargo_is_the_longest_of_the_p99_duration_and_the_feature_window():
    long = ([trade(0.0, day=d, hours=1.0) for d in range(97)]
            + [trade(0.0, day=97 + k, hours=500.0) for k in range(3)])
    assert wf.embargo_for(long, feature_ms=0) == pytest.approx(500 * H, rel=0.02)
    assert wf.embargo_for(long, feature_ms=1000 * H) == 1000 * H
    assert wf.embargo_for([], feature_ms=7 * H) == 7 * H
    # el p99 es un cuantil, no el máximo: una sola operación larguísima no fija el embargo
    short = [trade(0.0, day=d, hours=1.0) for d in range(99)] + [trade(0.0, day=99, hours=500.0)]
    assert wf.embargo_for(short, feature_ms=0) < 10 * H


def test_no_fit_trade_reaches_its_test_span_or_its_embargo():
    f = fold()
    rows = [
        at(trade(0.0, tid="ok", hours=1), f.fit_from + 10 * DAY),
        at(trade(0.0, tid="emb"), f.fit_to - DAY, f.fit_cut + DAY // 2),   # cae en el embargo
        at(trade(0.0, tid="test"), f.fit_to - DAY, f.test_from + DAY),     # cae en la prueba
        at(trade(0.0, tid="after", hours=1), f.test_from + 20 * DAY),      # ya es de la prueba
    ]
    fit = wf.fit_trades(rows, f)
    assert [t.id for t in fit] == ["ok"]
    assert wf.leaks(fit, f) == []
    assert len(wf.leaks(rows[:3], f)) == 2, "tiene que detectar las dos fugas a propósito"
    assert wf.purged(rows, f) == {"in_window": 3, "kept": 1, "purged_into_test": 1,
                                  "embargoed": 1}


def test_a_trade_decided_outside_the_fit_window_is_a_leak_too():
    f = fold()
    before = at(trade(0.0, tid="x", hours=1), f.fit_from - 10 * DAY)
    assert any("fuera del ajuste" in m for m in wf.leaks([before], f))
    assert wf.fit_trades([before], f) == []


def test_the_test_span_only_takes_decisions_inside_it():
    f = fold()
    rows = [at(trade(0.0, tid="a"), f.test_from + DAY),
            at(trade(0.0, tid="b"), f.test_to + DAY),
            at(trade(0.0, tid="c"), f.fit_from + DAY)]
    assert [t.id for t in wf.test_trades(rows, f)] == ["a"]
    assert [len(x) for x in wf.slices_by_fold(rows, [f])] == [1]


def test_a_zero_embargo_still_purges_what_closes_inside_the_test():
    f = fold(embargo_ms=0)
    crosses = at(trade(0.0, tid="x"), f.fit_to - DAY, f.test_from + DAY)
    assert wf.fit_trades([crosses], f) == []
    assert wf.leaks([crosses], f)
