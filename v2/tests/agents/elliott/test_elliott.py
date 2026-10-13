"""Agente elliott: equivalencia con el golden del legado + contrato."""
from __future__ import annotations

import json
import math

from eim.agents.elliott import ElliottAgent
from tests.agents.conftest import make_snapshot
from tests.legacy import _runner as r


def test_matches_golden(snapshot):
    g = json.loads((r.GOLDEN / "elliott.json").read_text(encoding="utf-8"))
    m = ElliottAgent().run(snapshot).metrics
    assert len(m["pivots"]) == len(g["pivots"])
    for a, e in zip(m["pivots"], g["pivots"], strict=True):
        assert (a["index"], a["type"], a["wave_label"]) == (e["index"], e["type"], e["wave_label"])
        assert math.isclose(a["price"], e["price"], rel_tol=1e-9)
        assert a["t"] == int(snapshot.candles[e["index"]].t)
    for k in ("threshold_pct", "rule_violations", "valid_count", "prob_up_pct", "prob_down_pct",
              "next_expected_label", "wave_note"):
        assert m[k] == g[k], k


def test_contract_and_overlays(snapshot):
    rep = ElliottAgent().run(snapshot)
    assert -1 <= rep.bias <= 1 and 0 <= rep.confidence <= 1 and rep.status == "ok"
    kinds = {o.kind for o in rep.overlays}
    assert kinds <= {"marker", "level"} and "marker" in kinds
    assert sum(o.kind == "marker" for o in rep.overlays) == len(rep.metrics["pivots"])
    assert any("heurística" in w for w in rep.warnings)
    assert all(v in rep.warnings for v in rep.metrics["rule_violations"])
    json.dumps(rep.model_dump())
    assert ElliottAgent().run(snapshot) == rep


def test_no_data(snapshot):
    assert ElliottAgent().run(make_snapshot(5)).status == "no_data"
