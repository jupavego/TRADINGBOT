"""Compactado de una base DuckDB que nadie tiene abierta (T128, entregable 2)."""

from __future__ import annotations

import duckdb
import pytest

from eim.data import duck_compact
from eim.data.duck_compact import CompactError, compact


def _db(path, n=200_000, keep=10_000):
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE f (lid VARCHAR, tid BIGINT, v DOUBLE, PRIMARY KEY (lid, tid))")
    con.execute("CREATE TABLE s (k VARCHAR PRIMARY KEY)")
    con.execute(f"INSERT INTO f SELECT 'líder-' || (i % 7), i, i * 0.5 FROM range({n}) t(i)")
    con.execute("INSERT INTO s VALUES ('a'), ('b')")
    con.execute(f"DELETE FROM f WHERE tid >= {keep}")     # deja bloques libres
    con.execute("CHECKPOINT")
    con.close()


def test_compacts_keeps_rows_and_keys_and_then_has_nothing_to_do(tmp_path):
    p = tmp_path / "leaders.duckdb"
    _db(p)
    before = p.stat().st_size
    done = compact(p, min_free=0.2, min_bytes=0)
    assert done and done["tables"] == 2 and p.stat().st_size < before
    con = duckdb.connect(str(p))
    try:
        assert con.execute("SELECT count(*), sum(tid) FROM f").fetchone() == (10_000,
                                                                              sum(range(10_000)))
        with pytest.raises(duckdb.ConstraintException):             # la clave sigue ahí
            con.execute("INSERT INTO f VALUES ('líder-0', 0, 1.0)")
    finally:
        con.close()
    assert compact(p, min_free=0.2, min_bytes=0) is None            # ya no hay hueco
    assert not list(tmp_path.glob("*.old")) and not list(tmp_path.glob("*.compact*"))


def test_small_or_tidy_bases_are_left_alone(tmp_path):
    p = tmp_path / "leaders.duckdb"
    _db(p)
    assert compact(p) is None                                       # < 256 MB
    assert compact(tmp_path / "no_existe.duckdb", min_bytes=0) is None


def test_a_copy_that_does_not_match_leaves_the_original(tmp_path, monkeypatch):
    p = tmp_path / "leaders.duckdb"
    _db(p)
    size = p.stat().st_size
    monkeypatch.setattr(duck_compact, "copy_db_cold", lambda src, dst: {"f": 1, "s": 2})
    with pytest.raises(CompactError):
        compact(p, min_free=0.2, min_bytes=0)
    assert p.stat().st_size == size and not list(tmp_path.glob("*.compact*"))


def test_a_swap_cut_in_half_is_undone(tmp_path):
    p = tmp_path / "leaders.duckdb"
    _db(p, n=20_000, keep=20_000)
    p.replace(tmp_path / "leaders.duckdb.old")                      # se cortó entre los dos pasos
    assert compact(p, min_bytes=0) is None and p.exists()
    con = duckdb.connect(str(p), read_only=True)
    assert con.execute("SELECT count(*) FROM f").fetchone() == (20_000,)
    con.close()
