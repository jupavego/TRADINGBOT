"""Compactación de la microestructura: une horas cerradas sin perder ni duplicar filas."""

import duckdb

from eim.data.collectors.compact import compact_closed, compact_dir
from eim.data.collectors.writer import SCHEMAS


def _part(d, name, rows):
    d.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE x ({SCHEMAS['trades']})")
    con.executemany("INSERT INTO x VALUES (?, ?, ?, ?, ?)", rows)
    con.execute(f"COPY x TO '{(d / name).as_posix()}' (FORMAT parquet)")


def _rows(root):
    g = (root / "micro" / "trades" / "symbol=BTCUSDT").as_posix() + "/date=*/hour=*/part-*.parquet"
    return duckdb.connect().execute(
        f"SELECT t, id, p, q, maker FROM read_parquet('{g}', hive_partitioning=false) ORDER BY t"
    ).fetchall()


def test_compacts_closed_hours_only_and_keeps_every_row(tmp_path):
    now = 1_792_558_800_000                                   # 2026-10-21 05:00 UTC
    old = tmp_path / "micro/trades/symbol=BTCUSDT/date=2026-10-21/hour=01"
    cur = tmp_path / "micro/trades/symbol=BTCUSDT/date=2026-10-21/hour=04"
    base = now - 4 * 3_600_000
    _part(old, "part-1.parquet",
          [(base + 5, 1, 100.0, 1.0, True), (base + 1, 2, 101.0, 2.0, False)])
    _part(old, "part-2.parquet", [(base + 9, 3, 102.0, 3.0, False)])
    _part(cur, "part-3.parquet", [(now - 3_000, 4, 103.0, 1.0, True)])
    _part(cur, "part-4.parquet", [(now - 2_000, 5, 104.0, 1.0, True)])
    before = _rows(tmp_path)
    done = compact_closed(tmp_path, now)
    assert [(n, r) for _, n, r in done] == [(2, 3)]            # solo la hora cerrada
    assert len(list(old.glob("part-*.parquet"))) == 1 and not list(old.glob("*.old"))
    assert len(list(cur.glob("part-*.parquet"))) == 2          # la hora en curso no se toca
    assert _rows(tmp_path) == before
    assert [r[0] for r in _rows(tmp_path)] == sorted(r[0] for r in _rows(tmp_path))
    assert compact_closed(tmp_path, now) == []                 # idempotente


def test_single_file_is_left_alone(tmp_path):
    d = tmp_path / "micro/trades/symbol=BTCUSDT/date=2026-10-20/hour=01"
    _part(d, "part-1.parquet", [(1, 1, 1.0, 1.0, True)])
    assert compact_dir(d) is None
