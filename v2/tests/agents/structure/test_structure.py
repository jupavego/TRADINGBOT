"""Regresión del agente `structure` contra el golden de T02 + comportamiento del agente."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from eim.agents.structure import StructureAgent
from eim.agents.structure.agent import snapshot_frame, structure_frame
from eim.core import Candle, MarketSnapshot
from tests.legacy import _runner as r
from tests.legacy.test_golden import assert_same


def _snapshot(n: int | None = None) -> MarketSnapshot:
    df = pd.read_csv(r.CSV, parse_dates=["timestamp"])
    if n:
        df = df.tail(n)
    candles = [
        Candle(t=int(row.timestamp.timestamp() * 1000), o=row.open, h=row.high, l=row.low,
               c=row.close, v=row.volume)
        for row in df.itertuples()
    ]
    return MarketSnapshot(
        symbol="ETHUSDT", timeframe="1h", candles=candles, asof=candles[-1].t + 3_600_000,
        sources={"candles": "fixture"}, coverage={"candles": (candles[0].t, candles[-1].t)},
    )


def test_matches_legacy_golden():
    golden = json.loads((r.GOLDEN / "frm_brm_irm.json").read_text(encoding="utf-8"))
    out = structure_frame(snapshot_frame(_snapshot()))
    assert_same(r.canon(out), golden)


def test_report_is_valid_and_traceable():
    rep = StructureAgent().run(_snapshot())
    assert rep.agent_id == "structure" and rep.status == "ok"
    assert -1 <= rep.bias <= 1 and 0 <= rep.confidence <= 0.95
    assert rep.metrics["source"] == "fixture"
    assert any("Estado estructural" in e for e in rep.evidence)


def test_deterministic():
    snap = _snapshot()
    assert StructureAgent().run(snap) == StructureAgent().run(snap)


def test_no_data_when_few_bars():
    rep = StructureAgent().run(_snapshot(30))
    assert rep.status == "no_data" and rep.bias == 0 and rep.confidence == 0 and rep.warnings


def test_degraded_below_warmup():
    rep = StructureAgent().run(_snapshot(100))
    assert rep.status == "degraded" and any("warmup" in w for w in rep.warnings)


@pytest.mark.parametrize("n", [100, 400, 1000])
def test_bias_bounds(n):
    assert -1 <= StructureAgent().run(_snapshot(n)).bias <= 1
