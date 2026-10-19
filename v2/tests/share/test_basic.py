"""T61: unión sin duplicados, idempotencia, conmutatividad, conflictos y simulacro."""

import hashlib

from eim.data.share_import import import_all
from tests.share.helpers import M15, T0, apply, build, publish, rows

KEYS = {
    "paper.duckdb": "SELECT asof_ms FROM paper_ctx ORDER BY 1",
    "leaders.duckdb": "SELECT tid FROM leader_fills ORDER BY 1",
}


def _pair(tmp_path, tag=""):
    a = build(tmp_path, "a" + tag, asofs=[T0 + i * M15 for i in range(1, 7)],
              conflict_at=T0 + 6 * M15, fills=[1, 2, 3], photos=[T0 + 10, T0 + 20])
    b = build(tmp_path, "b" + tag, asofs=[T0 + i * M15 for i in range(4, 10)], fills=[3, 4],
              photos=[T0 + 15])
    return a, b


def _sig(d):
    return {db: rows(d, db, q) for db, q in KEYS.items()} | {
        "pos": rows(d, "leaders.duckdb", "SELECT observed_at FROM leader_positions ORDER BY 1")}


def _hashes(d):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.iterdir())
            if p.is_file()}


def test_union_without_duplicates(tmp_path):
    a, b = _pair(tmp_path)
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    rep = apply(a, shared, "a")
    tot = rep.totals()
    assert tot["paper_ctx"] == {"new": 3, "dup": 2, "conflict": 1, "incompatible": 0}
    assert tot["leader_fills"]["new"] == 1 and tot["leader_fills"]["dup"] == 1
    assert len(rows(a, "paper.duckdb", "SELECT * FROM paper_ctx")) == 9    # únicas de ambas
    assert [r[0] for r in rows(a, "leaders.duckdb", "SELECT tid FROM leader_fills ORDER BY 1")
            ] == [1, 2, 3, 4]
    assert len(rows(a, "leaders.duckdb", "SELECT * FROM leader_positions")) == 3
    assert rep.backup and "pre-import" in rep.backup


def test_idempotent(tmp_path):
    a, b = _pair(tmp_path)
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    apply(a, shared, "a")
    first = _sig(a)
    again = apply(a, shared, "a")
    assert _sig(a) == first
    assert all(r.new == 0 for r in again.results)
    assert rows(a, "paper.duckdb", "SELECT count(*) FROM share_origin")[0][0] == 3
    assert rows(a, "leaders.duckdb", "SELECT count(*) FROM share_origin")[0][0] == 2


def test_commutative(tmp_path):
    a, b = _pair(tmp_path)
    shared = tmp_path / "cloud"
    publish(a, shared, "a")
    publish(b, shared, "b")
    apply(a, shared, "a")
    apply(b, shared, "b")
    sa, sb = _sig(a), _sig(b)
    assert sa == sb
    assert len(sa["paper.duckdb"]) == 9


def test_conflict_is_reported_not_overwritten(tmp_path):
    a, b = _pair(tmp_path)
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    rep = apply(a, shared, "a")
    assert rep.totals()["paper_ctx"]["conflict"] == 1
    kept = rows(a, "paper.duckdb", "SELECT ctx FROM paper_ctx WHERE asof_ms = ?"
                .replace("?", str(T0 + 6 * M15)))
    assert '"x":99' in kept[0][0]                                    # lo local se conserva
    got = rows(a, "paper.duckdb", "SELECT tbl, src_machine, differs FROM share_conflicts")
    assert got and got[0][0] == "paper_ctx" and "ctx" in got[0][2]
    assert "conflicto" in rep.render()


def test_dry_run_writes_nothing(tmp_path):
    a, b = _pair(tmp_path)
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    before = _hashes(a)
    sim = import_all(a, shared, "a", apply=False, backup_dir=tmp_path / "bk")
    assert _hashes(a) == before and not (a / "share").exists() and not (tmp_path / "bk").exists()
    assert "SIMULACRO" in sim.render()
    real = apply(a, shared, "a")
    assert sim.totals() == real.totals()                  # el simulacro es lo que haría --apply


def test_separate_empty_machine_gets_everything(tmp_path):
    """Colaborador nuevo: primera importación completa sobre una carpeta de datos vacía."""
    a, _ = _pair(tmp_path)
    shared = tmp_path / "cloud"
    publish(a, shared, "a")
    new = tmp_path / "n" / "data"
    new.mkdir(parents=True)
    rep = apply(new, shared, "n")
    assert rep.totals()["paper_ctx"]["new"] == 6
    assert len(rows(new, "leaders.duckdb", "SELECT * FROM leader_fills")) == 3
