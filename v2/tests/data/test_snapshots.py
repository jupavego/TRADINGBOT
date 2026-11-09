"""T124: instantáneas inmutables con hash del contenido, copia congelada y corte en su fecha."""

from __future__ import annotations

import duckdb
import numpy as np
import pytest

from eim.calibration.cli import load_series
from eim.core import Candle
from eim.data.snapshots import (
    LookaheadError,
    SnapshotCorrupt,
    SnapshotScopeError,
    SnapshotStore,
    content_hash,
)
from eim.data.store import Store

H = 3_600_000
T0 = 1_700_000_000_000 // H * H


def candles(n: int = 50, seed: int = 3, t0: int = T0) -> list[Candle]:
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    out, prev = [], float(px[0])
    for i, c in enumerate(px):
        c = float(c)
        out.append(Candle(t=t0 + i * H, o=prev, h=max(prev, c) * 1.002, l=min(prev, c) * 0.998,
                          c=c, v=1000.0 + i))
        prev = c
    return out


def make_store(tmp_path, n: int = 50) -> Store:
    s = Store(tmp_path)
    s.upsert_candles("BTCUSDT", "1h", candles(n), "prueba")
    s.upsert_series("funding", "BTCUSDT", "-", [(T0 + k * 8 * H, 1e-4 * k) for k in range(7)],
                    "prueba")
    return s


def test_create_fixes_identity_and_is_idempotent(tmp_path):
    store, snaps = make_store(tmp_path), SnapshotStore(tmp_path)
    end = T0 + 40 * H
    a = snaps.create(store, "BTCUSDT", "1h", start=T0, end=end)
    b = snaps.create(store, "BTCUSDT", "1h", start=T0, end=end)
    i = a.info
    assert a.info.id == b.info.id and a.info.created_ms == b.info.created_ms
    assert (i.n_candles, i.first_t, i.last_t, i.gaps) == (40, T0, T0 + 39 * H, 0)
    assert i.n_funding == 5 and i.source == "prueba" and i.funding_source == "prueba"
    assert i.frozen and i.version == 1 and i.content_hash == content_hash(a.candles, a.funding)
    assert i.coverage()["expected"] == 40 and len(snaps.list()) == 1
    assert (tmp_path / "snapshots" / "frozen" / i.id / "candles.parquet").exists()


def test_snapshot_is_immutable_new_data_makes_a_new_one(tmp_path):
    store, snaps = make_store(tmp_path), SnapshotStore(tmp_path)
    old = snaps.create(store, "BTCUSDT", "1h", start=T0, end=T0 + 40 * H)
    c = candles()[10]
    store.upsert_candles("BTCUSDT", "1h", [c.model_copy(update={"c": (c.h + c.l) / 2})], "prueba")
    new = snaps.create(store, "BTCUSDT", "1h", start=T0, end=T0 + 40 * H)
    assert new.info.id != old.info.id and new.info.content_hash != old.info.content_hash
    back = snaps.load(old.info.id)               # la vieja sigue dando los datos de entonces
    assert back.candles == old.candles and back.candles[10].c == c.c
    assert len(snaps.list()) == 2


def test_cut_keeps_only_candles_closed_at_end(tmp_path):
    store, snaps = make_store(tmp_path), SnapshotStore(tmp_path)
    s = snaps.create(store, "BTCUSDT", "1h", start=T0, end=T0 + 10 * H + H // 2)
    assert s.info.last_t == T0 + 9 * H         # la de las 10 h aún no cerraba a ese corte
    assert all(t < s.info.end_ms for t, _ in s.funding)


def test_altered_frozen_copy_is_detected(tmp_path):
    store, snaps = make_store(tmp_path), SnapshotStore(tmp_path)
    s = snaps.create(store, "BTCUSDT", "1h", start=T0, end=T0 + 40 * H)
    p = (tmp_path / "snapshots" / "frozen" / s.info.id / "candles.parquet").as_posix()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE x AS SELECT * FROM read_parquet('{p}')")
    con.execute("UPDATE x SET c = (h + l) / 2 WHERE t = ?", [T0 + 5 * H])
    con.execute(f"COPY x TO '{p}' (FORMAT PARQUET)")
    with pytest.raises(SnapshotCorrupt):
        snaps.load(s.info.id)


def test_light_snapshot_keeps_identity_without_copy(tmp_path):
    store, snaps = make_store(tmp_path), SnapshotStore(tmp_path)
    s = snaps.create(store, "BTCUSDT", "1h", start=T0, end=T0 + 20 * H, freeze=False)
    assert not s.info.frozen and not (tmp_path / "snapshots" / "frozen" / s.info.id).exists()
    with pytest.raises(SnapshotScopeError):
        snaps.load(s.info.id)
    live = snaps.live(store, s.info)
    assert content_hash(live.candles, live.funding) == s.info.content_hash


def test_funding_only_snapshot(tmp_path):
    store, snaps = make_store(tmp_path), SnapshotStore(tmp_path)
    s = snaps.create(store, "BTCUSDT", "-", start=T0, end=T0 + 30 * H, kind="funding",
                     freeze=False)
    assert s.info.n_candles == 0 and s.info.n_funding == 4 and s.info.coverage()["expected"] == 0


def test_view_cuts_at_its_date_a_lookahead_read_fails(tmp_path):
    """Freno al lookahead: una vela posterior al corte no se puede leer."""
    store, snaps = make_store(tmp_path), SnapshotStore(tmp_path)
    end = T0 + 30 * H
    view = snaps.create(store, "BTCUSDT", "1h", start=T0, end=end).view()
    assert store.read_candles("BTCUSDT", "1h", start=end)        # el almacén sí la tiene
    assert len(view.read_candles("BTCUSDT", "1h")) == 30
    assert len(view.read_candles("BTCUSDT", "1h", end=end, last=5)) == 5
    with pytest.raises(LookaheadError):
        view.read_candles("BTCUSDT", "1h", start=end, end=end + H)   # la vela de después
    with pytest.raises(LookaheadError):
        view.read_series("funding", "BTCUSDT", end=end + 8 * H)
    with pytest.raises(SnapshotScopeError):
        view.read_candles("ETHUSDT", "1h")
    with pytest.raises(SnapshotScopeError):
        view.read_candles("BTCUSDT", "1h", start=T0 - H)
    with pytest.raises(SnapshotScopeError):
        view.read_series("open_interest", "BTCUSDT", "1h")


def test_producer_reads_through_the_view_and_never_sees_later_data(tmp_path):
    """Un productor que lee de la vista (como la puerta de edge) solo ve hasta el corte."""
    store, snaps = make_store(tmp_path), SnapshotStore(tmp_path)
    end = T0 + 30 * H
    s, _ = load_series(snaps.create(store, "BTCUSDT", "1h", start=T0, end=end).view(),
                       "BTCUSDT", "1h", 10, tmp_path / "cache")
    assert s.candles[-1].t + H <= end and len(s.candles) == 30
    assert s.funding and all(t < end for t, _ in s.funding) and s.source == "prueba"
