"""Registro de intentos y linaje (T49): versiones nuevas, ventanas heredadas y declaraciones."""

from __future__ import annotations

import pytest

from eim.data.paper_store import PaperStore
from eim.data.validation_store import ValidationStore
from eim.validation.lineage import (
    AUTO_ORIGIN,
    LINEAGE_FILE,
    Declaration,
    Window,
    declare,
    find_declaration,
    load_declarations,
    out_of_sample,
    tuning_windows,
)
from tests.validation.helpers import DAY, T0


@pytest.fixture
def vs():
    ps = PaperStore(":memory:")
    yield ValidationStore(ps)
    ps.close()


DECL = Declaration("T48b", "60 días", (Window(T0, T0 + 60 * DAY, None, "ajuste"),),
                   {"s@1h": "aaa"})


def test_declared_version_gets_its_windows(vs):
    v = vs.ensure("s@1h", "s", "1h", "aaa", T0 + 70 * DAY, [DECL])
    assert (v.n, v.origin, v.parent, v.retired_ms) == (1, "T48b", None, None)
    assert v.windows == DECL.windows and v.label == "s@1h@v1"
    assert vs.ensure("s@1h", "s", "1h", "aaa", T0 + 80 * DAY, [DECL]) == v   # idempotente


def test_new_fingerprint_is_new_version_with_ancestor_windows(vs):
    v1 = vs.ensure("s@1h", "s", "1h", "aaa", T0 + 70 * DAY, [DECL])
    now = T0 + 90 * DAY
    v2 = vs.ensure("s@1h", "s", "1h", "bbb", now, [DECL])
    assert (v2.n, v2.parent, v2.origin) == (2, 1, AUTO_ORIGIN)
    assert v2.windows == (Window(0, now, None, v2.windows[0].note),)   # todo lo anterior al alta
    fam = vs.versions("s@1h")
    assert [x.retired_ms for x in fam] == [now, None]
    wins = tuning_windows(v2, fam)
    assert set(wins) == set(v1.windows) | set(v2.windows)
    # una decisión dentro de la ventana del padre no es fuera de muestra para el hijo
    assert not out_of_sample(T0 + 10 * DAY, "X", wins)
    assert out_of_sample(now + DAY, "X", wins)


def test_revert_to_old_fingerprint_reuses_version(vs):
    vs.ensure("s@1h", "s", "1h", "aaa", T0, [DECL])
    vs.ensure("s@1h", "s", "1h", "bbb", T0 + DAY, [DECL])
    back = vs.ensure("s@1h", "s", "1h", "aaa", T0 + 2 * DAY, [DECL])
    assert back.n == 1 and back.retired_ms is None
    assert [(x.n, x.retired_ms) for x in vs.versions("s@1h")] == [(1, None), (2, T0 + 2 * DAY)]


def test_verdict_history_and_last_p(vs):
    row = {"sid": "s@1h", "n": 1, "fingerprint": "aaa", "verdict": "RECHAZADA", "n_oos": 10,
           "p_raw": 0.3, "p_holm": 0.9, "id": "s@1h@v1"}
    vs.save_verdicts("validation_v1", "X", T0, T0, [row])
    vs.save_verdicts("validation_v1", "X", T0 + DAY, T0 + DAY, [{**row, "p_raw": 0.2}])
    assert vs.last_pvalues("validation_v1") == {("X", "s@1h", 1): 0.2}
    asof, computed, rows = vs.latest("validation_v1", "X")
    assert asof == computed == T0 + DAY and rows[0]["p_raw"] == 0.2
    assert [h["asof"] for h in vs.history("validation_v1", "X", "s@1h")] == [T0 + DAY, T0]


def test_lineage_file_is_append_only_and_lookup_takes_latest(tmp_path):
    p = tmp_path / "lineage.json"
    declare(p, "a", "uno", [Window(T0, T0 + DAY)], {"s@1h": "aaa"}, "2026-10-18")
    declare(p, "b", "dos", [Window(T0, T0 + 2 * DAY)], {"s@1h": "aaa"}, "2026-10-19")
    ds = load_declarations(p)
    assert [d.origin for d in ds] == ["a", "b"]
    assert find_declaration(ds, "s@1h", "aaa").origin == "b"
    assert find_declaration(ds, "s@1h", "zzz") is None


def test_repo_lineage_declares_t48b_window():
    ds = load_declarations(LINEAGE_FILE)
    t48 = [d for d in ds if d.origin == "T48b"]
    assert t48 and len(t48[0].versions) == 87
    w = t48[0].windows[0]
    assert w.symbol is None and (w.to_ms - w.from_ms) >= 60 * DAY
