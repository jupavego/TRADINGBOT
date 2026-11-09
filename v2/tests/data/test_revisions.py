"""T124: una vela guardada que cambia al sincronizar queda anotada y se sabe a quién afecta."""

from __future__ import annotations

import time

from eim.data import revisions
from eim.data.snapshots import SnapshotStore
from tests.data.test_snapshots import T0, H, candles, make_store


def test_same_values_or_gap_fill_are_not_revisions(tmp_path):
    store = make_store(tmp_path)
    cs = candles()
    store.upsert_candles("BTCUSDT", "1h", cs[5:15], "prueba")          # mismos valores
    store.upsert_candles("BTCUSDT", "1h", candles(60)[50:], "prueba")  # filas nuevas
    assert revisions.read(tmp_path) == []


def test_changed_candle_is_recorded_with_before_and_after(tmp_path):
    store = make_store(tmp_path)
    c = candles()[7]
    mid = (c.h + c.l) / 2
    store.upsert_candles("BTCUSDT", "1h", [c.model_copy(update={"c": mid, "v": 9.0})],
                         "binance-futures")
    (r,) = revisions.read(tmp_path)
    assert (r["kind"], r["symbol"], r["timeframe"], r["t"]) == ("candles", "BTCUSDT", "1h", c.t)
    assert r["before"]["c"] == c.c and r["after"]["c"] == mid and r["after"]["v"] == 9.0
    assert r["before"]["o"] == r["after"]["o"]
    assert (r["source_before"], r["source_after"]) == ("prueba", "binance-futures")
    assert abs(r["detected_ms"] - time.time() * 1000) < 60_000


def test_revised_funding_is_recorded(tmp_path):
    store = make_store(tmp_path)
    store.upsert_series("funding", "BTCUSDT", "-", [(T0 + 8 * H, 0.5)], "prueba")
    (r,) = revisions.read(tmp_path)
    assert r["kind"] == "funding" and r["before"]["x"] == 1e-4 and r["after"]["x"] == 0.5


def test_affected_snapshots_are_the_older_ones_covering_the_row(tmp_path):
    store, snaps = make_store(tmp_path), SnapshotStore(tmp_path)
    covers = snaps.create(store, "BTCUSDT", "1h", start=T0, end=T0 + 20 * H).info
    elsewhere = snaps.create(store, "BTCUSDT", "1h", start=T0 + 30 * H, end=T0 + 40 * H).info
    time.sleep(0.01)
    c = candles()[7]
    store.upsert_candles("BTCUSDT", "1h", [c.model_copy(update={"h": c.h * 2})], "prueba")
    time.sleep(0.01)
    after = snaps.create(store, "BTCUSDT", "1h", start=T0, end=T0 + 20 * H).info
    hit = revisions.affected(revisions.read(tmp_path), [covers, elsewhere, after])
    assert list(hit) == [covers.id]                 # la posterior ya vio la vela revisada


def test_a_failure_to_record_never_breaks_the_write(tmp_path, monkeypatch):
    store = make_store(tmp_path)

    def boom(*_a, **_k):
        raise OSError("disco lleno")
    monkeypatch.setattr(revisions, "write", boom)
    c = candles()[3]
    mid = (c.h + c.l) / 2
    n = store.upsert_candles("BTCUSDT", "1h", [c.model_copy(update={"c": mid})], "prueba")
    assert n == 50 and store.read_candles("BTCUSDT", "1h", start=c.t, end=c.t + 1)[0].c == mid
