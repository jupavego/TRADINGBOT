"""Agente vwap: regresión contra golden del legado y contrato."""
from __future__ import annotations

import json

from eim.agents.base import no_data_report  # noqa: F401
from eim.agents.structure.agent import snapshot_frame
from eim.agents.vwap import VWAPAgent
from eim.agents.vwap.compute import compute_vwap
from tests.agents.conftest import make_snapshot
from tests.legacy import _runner as r
from tests.legacy.test_golden import assert_same


def test_matches_legacy_golden(snapshot):
    golden = json.loads((r.GOLDEN / "vwap.json").read_text(encoding="utf-8"))
    assert_same(r.canon(compute_vwap(snapshot_frame(snapshot))), golden)


def test_contract_and_overlays(snapshot):
    rep = VWAPAgent().run(snapshot)
    assert -1 <= rep.bias <= 1 and 0 <= rep.confidence <= 1
    assert rep.metrics["source"] and set(rep.metrics["periods"]) == {
        "daily", "weekly", "quincenal", "monthly"}
    assert rep.overlays and all(o.kind == "level" and "p" in o.geometry for o in rep.overlays)
    assert {o.geometry["period"] for o in rep.overlays} == set(rep.metrics["periods"])
    assert len({o.id for o in rep.overlays}) == len(rep.overlays)


def test_partial_period_warns(snapshot):
    rep = VWAPAgent().run(snapshot)
    assert rep.metrics["periods"]["monthly"]["partial"] or rep.status == "ok"
    if rep.metrics["periods"]["monthly"]["partial"]:
        assert rep.status == "degraded" and any("mensual" in w for w in rep.warnings)


def test_no_data_and_determinism(snapshot):
    assert VWAPAgent().run(make_snapshot(5)).status == "no_data"
    assert VWAPAgent().run(snapshot) == VWAPAgent().run(snapshot)
