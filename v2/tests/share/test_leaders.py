"""T61: líderes — cobertura por unión de intervalos, bitácora con contador local, `machine`."""

import duckdb

from eim.copytrading.forward import covered_ms
from eim.data.leader_store import LeaderStore
from tests.share.helpers import LID, T0, apply, build, publish, rows

STEP = 300_000
MAX_STEP = 600_000


def _times(d):
    return [r[0] for r in rows(d, "leaders.duckdb",
                               "SELECT observed_at FROM leader_positions ORDER BY 1")]


def test_forward_coverage_is_union_not_sum(tmp_path):
    span = range(0, 12 * STEP + 1, STEP)               # 1 hora capturada por A
    a = build(tmp_path, "a", photos=[T0 + k for k in span])
    b = build(tmp_path, "b", photos=[T0 + k + 60_000 for k in span])    # misma hora, otra máquina
    sa, sb = covered_ms(_times(a), MAX_STEP), covered_ms(_times(b), MAX_STEP)
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    apply(a, shared, "a")
    union = covered_ms(_times(a), MAX_STEP)
    assert len(_times(a)) == 26
    assert union < sa + sb and union <= sa + 60_000          # la hora cubierta no se duplica


def test_forward_coverage_extends_with_new_interval(tmp_path):
    a = build(tmp_path, "a", photos=[T0, T0 + STEP, T0 + 2 * STEP])
    b = build(tmp_path, "b", photos=[T0 + 2 * STEP + 60_000, T0 + 3 * STEP, T0 + 4 * STEP])
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    apply(a, shared, "a")
    assert covered_ms(_times(a), MAX_STEP) == 4 * STEP       # tramo nuevo de B suma, sin hueco


def test_journal_counter_is_remapped_and_deduped(tmp_path):
    a = build(tmp_path, "a", journal=["x", "y"])
    b = build(tmp_path, "b", journal=["x", "z"])    # «x» tiene el mismo contenido en ambas
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    rep = apply(a, shared, "a")
    assert rep.totals()["copy_journal"]["new"] == 1      # solo «z»; «x» ya estaba
    got = rows(a, "leaders.duckdb", "SELECT seq, text FROM copy_journal ORDER BY seq")
    assert [t for _, t in got] == ["x", "y", "z"] and [s for s, _ in got] == [1, 2, 3]
    again = apply(a, shared, "a")
    assert again.totals()["copy_journal"]["new"] == 0


def test_recon_rows_keep_their_machine(tmp_path):
    a = build(tmp_path, "a", recon=2)
    b = build(tmp_path, "b", recon=3)
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    apply(a, shared, "a")
    got = rows(a, "leaders.duckdb",
               "SELECT machine, count(*) FROM leader_recon GROUP BY 1 ORDER BY 1")
    # t/observed_at coinciden entre a y b, pero la máquina forma parte de la identidad
    assert got == [("a", 2), ("b", 3)]


def test_legacy_db_without_machine_column_is_migrated(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "machine_id").write_text("viejo-1\n", encoding="utf-8")
    con = duckdb.connect(str(d / "leaders.duckdb"))
    con.execute("CREATE TABLE leader_recon (leader_id VARCHAR, t BIGINT, observed_at BIGINT, "
                "checked INTEGER, skipped INTEGER, size_ok BOOLEAN, match BOOLEAN, "
                "resynced BOOLEAN, diffs VARCHAR, clock_offset_ms INTEGER, retries INTEGER)")
    con.execute("INSERT INTO leader_recon VALUES (?,1,1,1,0,true,true,false,NULL,0,0)", [LID])
    con.close()
    LeaderStore(d / "leaders.duckdb").close()
    LeaderStore(d / "leaders.duckdb").close()                 # idempotente
    assert rows(d, "leaders.duckdb", "SELECT machine FROM leader_recon") == [("viejo-1",)]
