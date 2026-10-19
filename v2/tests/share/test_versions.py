"""T61: versiones de validación (remapeo por huella), ventanas, Holm y procedencia."""

from eim.data.paper_store import PaperStore
from eim.data.validation_store import ValidationStore
from eim.validation.service import Validator
from tests.share.helpers import T0, apply, build, publish, rows

S1, S2 = "trend@15m", "trend@1h"


def _machines(tmp_path):
    a = build(tmp_path, "a", versions=[(S1, 1, "aaa", None, 5), (S1, 2, "bbb", 1, None)],
              windows=[(S1, 1, 0, 10), (S1, 2, 20, 30)])
    b = build(tmp_path, "b", versions=[(S1, 1, "aaa", None, 5), (S1, 2, "ccc", 1, 7),
                                       (S1, 3, "ddd", 2, None), (S2, 1, "eee", None, None)],
              windows=[(S1, 1, 5, 15), (S1, 3, 40, 50), (S2, 1, 0, 1)])
    return a, b


def _by_fp(d):
    return {(r[0], r[1]): r[2:] for r in rows(
        d, "paper.duckdb", "SELECT sid, fingerprint, n, parent, retired_ms FROM val_versions")}


def test_versions_remapped_by_fingerprint(tmp_path):
    a, b = _machines(tmp_path)
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    rep = apply(a, shared, "a")
    got = _by_fp(a)
    assert got[(S1, "aaa")][0] == 1 and got[(S1, "bbb")][0] == 2          # lo local no cambia
    assert got[(S1, "ccc")][:2] == (3, 1)                                  # n nuevo, padre = aaa
    assert got[(S1, "ddd")][:2] == (4, 3)                                  # padre remapeado (2→3)
    assert got[(S2, "eee")][:2] == (1, None)
    assert got[(S1, "bbb")][2] is None                                     # la vigente local sigue
    assert all(got[k][2] is not None for k in [(S1, "ccc"), (S1, "ddd"), (S2, "eee")])
    assert rep.totals()["val_versions"] == {"new": 3, "dup": 1, "conflict": 0, "incompatible": 0}


def test_windows_are_unioned(tmp_path):
    a, b = _machines(tmp_path)
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    publish(a, shared, "a")
    apply(a, shared, "a")
    apply(b, shared, "b")
    q = ("SELECT v.sid, v.fingerprint, w.from_ms, w.to_ms FROM val_windows w JOIN val_versions v "
         "USING (sid, n) ORDER BY 1, 2, 3, 4")
    wa, wb = rows(a, "paper.duckdb", q), rows(b, "paper.duckdb", q)
    assert wa == wb                                                          # conmutativa
    assert (S1, "aaa", 0, 10) in wa and (S1, "aaa", 5, 15) in wa            # ventana de B en aaa
    assert (S1, "bbb", 20, 30) in wa and (S1, "ddd", 40, 50) in wa and (S2, "eee", 0, 1) in wa
    assert len(wa) == 5


def test_holm_counts_union_of_attempts(tmp_path):
    a, b = _machines(tmp_path)
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    apply(a, shared, "a")
    ps = PaperStore(a / "paper.duckdb")
    try:
        p = Validator(None, ValidationStore(ps)).payload("BTCUSDT", T0, T0, [])
    finally:
        ps.close()
    assert p["attempts"] == 5                       # {aaa, bbb, ccc, ddd, eee}: unión por huella
    prov = p["provenance"]["machines"]["b"]
    assert prov["val_versions"]["imported"] == 3 and prov["val_versions"]["duplicates"] == 1


def test_derived_verdicts_not_imported(tmp_path):
    a, b = _machines(tmp_path)
    shared = tmp_path / "cloud"
    out = publish(b, shared, "b")
    assert "val_verdicts" not in (out / "manifest.json").read_text(encoding="utf-8")
    apply(a, shared, "a")
    assert rows(a, "paper.duckdb", "SELECT count(*) FROM val_verdicts")[0][0] == 1   # solo el local
