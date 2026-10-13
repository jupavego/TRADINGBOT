"""Agente seasonality: equivalencia con el golden y manejo de huecos/mes en curso."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from eim.agents.seasonality import SeasonalityAgent
from eim.agents.seasonality.compute import build_matrix, monthly_closes
from eim.core import Candle, MarketSnapshot
from tests.legacy import _runner as r


def _ms(ts) -> int:
    return int(ts.timestamp() * 1000)


def _snapshot(df, asof=None) -> MarketSnapshot:
    candles = [Candle(t=_ms(t), o=c, h=c, l=c, c=c, v=1.0) for t, c in df.itertuples(index=False)]
    return MarketSnapshot(symbol="ETHUSDT", timeframe="1M", candles=candles,
                          asof=asof or candles[-1].t + 32 * 86_400_000,
                          sources={"candles": "sintético"})


def test_matrix_equals_legacy_golden():
    g = json.loads((r.GOLDEN / "seasonality.json").read_text(encoding="utf-8"))
    df = r.synthetic_monthly_closes()
    got = build_matrix(df, strict_gaps=False)
    for k in ("rows", "months", "monthly_average_pct", "real_data_range"):
        assert got[k] == g["all"][k], k
    rng = build_matrix(df, 2023, 2024, strict_gaps=False)
    assert rng["rows"] == g["range"]["rows"]


def test_strict_gaps_leave_nan_after_missing_month():
    df = r.synthetic_monthly_closes()  # falta un mes (jun-2023)
    loose = build_matrix(df, strict_gaps=False)["rows"]
    strict = build_matrix(df, strict_gaps=True)["rows"]
    y23_l = next(x for x in loose if x["year"] == 2023)
    y23_s = next(x for x in strict if x["year"] == 2023)
    assert y23_l["Jul"] is not None and y23_s["Jul"] is None
    assert y23_l["Jun"] is None and y23_s["Jun"] is None


def test_current_month_excluded_and_daily_candles_resample():
    day = 86_400_000
    t0 = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
    candles = [Candle(t=t0 + i * day, o=1, h=1 + i, l=1, c=1 + i, v=1) for i in range(45)]
    asof = candles[-1].t + day  # 15-feb → febrero en curso
    m = monthly_closes(candles, "1d", asof)
    assert len(m) == 1 and m["close"].iloc[0] == 31.0  # solo enero, cierre 31-ene


def test_agent_contract(snapshot):
    df = r.synthetic_monthly_closes()
    snap = _snapshot(df)
    rep = SeasonalityAgent().run(snap)
    assert -1 <= rep.bias <= 1 and 0 <= rep.confidence <= 0.4
    assert rep.metrics["matrix"]["real_data_range"]["start"] == "2022-01"
    assert any("cobertura real" in w for w in rep.warnings)
    json.dumps(rep.model_dump())
    assert SeasonalityAgent().run(snap) == rep
    assert SeasonalityAgent().run(snapshot).status == "no_data"  # CSV de ~6 semanas, 1 mes


def test_few_samples_no_bias():
    df = r.synthetic_monthly_closes().iloc[:14]
    rep = SeasonalityAgent().run(_snapshot(df))
    assert rep.status == "ok" and rep.bias == 0 and rep.confidence == 0
    assert any("sin sesgo" in w for w in rep.warnings)
