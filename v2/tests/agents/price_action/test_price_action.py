"""Agente price_action: regresión contra golden del legado y contrato."""
from __future__ import annotations

import json

from eim.agents.price_action import PriceActionAgent
from eim.agents.price_action.compute import compute_price_action
from eim.agents.structure.agent import snapshot_frame
from tests.agents.conftest import make_snapshot
from tests.legacy import _runner as r
from tests.legacy.test_golden import assert_same


def test_matches_legacy_golden(snapshot):
    golden = json.loads((r.GOLDEN / "price_action.json").read_text(encoding="utf-8"))
    df, zones, _ = compute_price_action(snapshot_frame(snapshot))
    assert_same(r.canon({"frame": df, "sr_zones": zones}), golden)


def test_contract_and_zones(snapshot):
    rep = PriceActionAgent().run(snapshot)
    assert -1 <= rep.bias <= 1 and 0 <= rep.confidence <= 1
    assert rep.metrics["source"] and rep.metrics["structure_state"] in {
        "BULLISH", "BEARISH", "UNDEFINED"}
    assert rep.overlays
    for o in rep.overlays:
        assert o.kind == "zone" and o.geometry["p_low"] < o.geometry["p_high"]


def test_no_data_and_determinism(snapshot):
    assert PriceActionAgent().run(make_snapshot(5)).status == "no_data"
    assert PriceActionAgent().run(snapshot) == PriceActionAgent().run(snapshot)
