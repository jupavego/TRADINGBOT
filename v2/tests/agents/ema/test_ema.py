"""Agente ema: las 44 variables FRM coinciden con el golden del legado."""
from __future__ import annotations

import json
import math

from eim.agents.ema import EMAAgent
from eim.agents.ema.params import VARIABLES
from tests.agents.conftest import make_snapshot
from tests.legacy import _runner as r


def test_exposes_44_variables_equal_to_golden(snapshot):
    assert len(VARIABLES) == 44 and len(set(VARIABLES)) == 44
    rep = EMAAgent().run(snapshot)
    assert rep.metrics["n_variables"] == 44
    g = json.loads((r.GOLDEN / "frm_brm_irm.json").read_text(encoding="utf-8"))["data"]
    for k in VARIABLES:
        exp, act = g[k][-1], rep.metrics["variables"][k]
        if isinstance(exp, float):
            assert math.isclose(act, exp, rel_tol=1e-9, abs_tol=1e-9), k
        else:
            assert act == exp, k


def test_contract_and_overlays(snapshot):
    rep = EMAAgent().run(snapshot)
    assert -1 <= rep.bias <= 1 and 0 <= rep.confidence <= 1
    levels = [o for o in rep.overlays if o.kind == "level"]
    assert {o.geometry["span"] for o in levels} == {9, 21, 55, 100, 200}
    assert all(o.kind in {"level", "marker"} for o in rep.overlays)
    json.dumps(rep.model_dump())  # serializable (sin NaN/numpy)


def test_warmup_degraded_and_no_data(snapshot):
    assert EMAAgent().run(make_snapshot(5)).status == "no_data"
    assert EMAAgent().run(make_snapshot(100)).status == "degraded"
    assert EMAAgent().run(snapshot) == EMAAgent().run(snapshot)
