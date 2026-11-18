"""Cómo se guarda una foto de posiciones (T178): el formato compacto no pierde ningún campo,
el de antes se sigue leyendo y recodificar no cambia nada de lo que leen el almacén, la
evaluación ni la copia simulada."""

from __future__ import annotations

import json

from eim.data import leader_photos as photos
from eim.data.leader_retention import recode_photos
from eim.data.leader_store import LeaderStore
from tests.copytrading import helpers as H

T0 = 10 * 86_400_000


def _positions(n: int = 3, t: int = T0) -> list:
    return [H.position(c, "long" if i % 2 == 0 else "short", 1.0 + i, 100.0 + i, t,
                       upnl=float(i))
            for i, c in enumerate(("BTC", "ETH", "SOL")[:n])]


def _store(root) -> LeaderStore:
    store = LeaderStore.at_root(root)
    store.upsert_leader(H.leader(), 0)
    store.set_status(H.LID, "approved", 0)
    return store


def test_the_compact_photo_keeps_every_field():
    ps = _positions()
    raw = photos.encode(ps)
    assert photos.is_compact(raw)
    assert [p.model_dump() for p in photos.decode(raw)] == [p.model_dump() for p in ps]


def test_the_old_format_is_still_read_and_gives_the_same_shape():
    ps = _positions()
    old = json.dumps([p.model_dump() for p in ps])
    assert [p.model_dump() for p in photos.decode(old)] == [p.model_dump() for p in ps]
    assert photos.shape(old) == photos.shape(photos.encode(ps))
    assert photos.recode(old) == photos.encode(ps)
    assert photos.recode(photos.encode(ps)) is None      # ya está compacta


def test_the_compact_photo_is_smaller():
    ps = _positions()
    old = json.dumps([p.model_dump() for p in ps])
    assert len(photos.encode(ps)) < 0.6 * len(old)


def test_positions_that_do_not_share_a_header_stay_in_the_old_format():
    a, b = _positions(1, T0)[0], _positions(1, T0 + 5)[0]   # distinto `t`
    raw = photos.encode([a, b.model_copy(update={"symbol": "ETH"})])
    assert not photos.is_compact(raw)
    assert len(photos.decode(raw)) == 2


def test_an_empty_photo_round_trips():
    assert photos.decode(photos.encode([])) == []
    assert photos.shape(photos.encode([])) == "[]"


def test_recoding_the_stored_photos_changes_nothing_that_is_read(tmp_path):
    store = _store(tmp_path)
    for i in range(5):                                   # guardadas en el formato de antes
        t = T0 + i * 60_000
        raw = json.dumps([p.model_dump() for p in _positions(3, t)])
        store.query("INSERT INTO leader_positions VALUES (?,?,?,?)", [H.LID, t, t, raw])
    want = [p.model_dump() for p in store.positions_at(T0 + 4 * 60_000)]
    out = recode_photos(store, budget=None)
    assert out.photos_recoded == 5 and out.bytes_saved > 0
    assert [p.model_dump() for p in store.positions_at(T0 + 4 * 60_000)] == want
    assert store.query("SELECT count(*) FROM leader_positions WHERE positions NOT LIKE '{%'"
                       )[0][0] == 0
    assert recode_photos(store, budget=None).photos_recoded == 0      # idempotente
    store.close()


def test_recoding_respects_its_budget(tmp_path):
    store = _store(tmp_path)
    for i in range(10):
        t = T0 + i * 60_000
        raw = json.dumps([p.model_dump() for p in _positions(3, t)])
        store.query("INSERT INTO leader_positions VALUES (?,?,?,?)", [H.LID, t, t, raw])
    assert recode_photos(store, budget=4, max_rows=2).photos_recoded == 4
    assert store.query("SELECT count(*) FROM leader_positions WHERE positions NOT LIKE '{%'"
                       )[0][0] == 6
    store.close()


def test_what_the_store_writes_now_is_compact(tmp_path):
    store = _store(tmp_path)
    assert store.save_positions(H.LID, T0, T0, _positions(), keep_ms=0)
    raw = store.query("SELECT positions FROM leader_positions")[0][0]
    assert photos.is_compact(raw)
    assert store.positions_at(T0)[0].symbol == "BTC"
    store.close()
