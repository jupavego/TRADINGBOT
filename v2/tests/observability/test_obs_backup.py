"""T73: `obs.duckdb` entra en la copia diaria (caliente y fría), se verifica y se restaura."""

from __future__ import annotations

import json

import duckdb

from eim.data import backup as B
from eim.data.share_spec import NOT_SHARED
from eim.observability.indexer import Indexer
from eim.observability.store import ObsStore
from tests.observability.helpers import candle_trace, write


def _setup(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    con = duckdb.connect(str(data / B.DB_NAME))
    con.execute("CREATE TABLE t (x INT)")
    con.close()
    store = ObsStore(data / "obs" / B.OBS_NAME)
    ix = Indexer(store, data / "obs" / "spool")
    write(data / "obs" / "spool" / "api.20251001.1.jsonl", candle_trace())
    ix.run_once()
    return data, store


def test_hot_backup_includes_obs_and_verifies(tmp_path):
    data, store = _setup(tmp_path)
    out = B.create(data, tmp_path / "bk", extra_dbs={B.OBS_NAME: (store.con, store.lock)})
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["dbs"][B.OBS_NAME]["tables"]["events"] == 11
    assert B.OBS_NAME in m["files"] and B.verify(out) == []
    (out / B.OBS_NAME).write_bytes((out / B.OBS_NAME).read_bytes() + b"x")
    assert any("hash distinto" in p for p in B.verify(out))      # un cambio se detecta


def test_cold_backup_and_restore_keep_the_original(tmp_path):
    data, store = _setup(tmp_path)
    store.close()                                               # API detenida
    out = B.create(data, tmp_path / "bk")
    assert B.verify(out) == []
    # el equipo pierde el registro: se restaura, y lo que había queda a un lado
    (data / "obs" / B.OBS_NAME).write_bytes(b"corrupto")
    restored = B.restore(out, data)
    assert B.OBS_NAME in restored
    back = ObsStore(data / "obs" / B.OBS_NAME)
    assert back.counts()["events"] == 11
    assert list((data / "obs").glob(B.OBS_NAME + ".antes-de-restaurar-*"))
    back.close()


def test_registry_is_rebuildable_from_the_spool_alone(tmp_path):
    """Derivado de verdad: sin `obs.duckdb`, reindexar el spool devuelve lo mismo."""
    data, store = _setup(tmp_path)
    want = store.counts()
    store.close()
    (data / "obs" / B.OBS_NAME).unlink()
    again = ObsStore(data / "obs" / B.OBS_NAME)
    Indexer(again, data / "obs" / "spool").run_once()
    assert again.counts() == want
    again.close()


def test_obs_is_declared_as_not_shared():
    assert any("obs.duckdb" in k for k in NOT_SHARED)
