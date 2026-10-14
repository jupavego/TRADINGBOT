"""Script de IC del agente `technical`: Spearman, Holm y veredicto honesto (sin red)."""
from __future__ import annotations

import numpy as np

from eim.analytics.technical_ic import AGG, adjust, measure, report, spearman
from tests.agents.conftest import make_snapshot


def test_spearman_known_values():
    x = np.arange(50, dtype=float)
    ic, n, p = spearman(x, x ** 3)
    assert abs(ic - 1.0) < 1e-12 and n == 50 and p < 1e-6
    ic, _, p = spearman(x, np.full(50, 1.0))
    assert np.isnan(ic) and np.isnan(p)


def test_measure_on_fixture_reports_every_indicator_and_aggregate():
    rows = adjust(measure(make_snapshot().candles, [1, 6], "ETH fixture"))
    names = {r["indicator"] for r in rows}
    assert AGG in names and "RSI" in names
    assert all(r["p_holm"] >= r["p"] or np.isnan(r["p"]) for r in rows)
    flow = [r for r in rows if r["indicator"] == "CVD"]
    assert all(np.isnan(r["ic"]) for r in flow)  # sin taker_buy_v: no se inventa
    text = report(rows, ["- fixture"])
    assert "Veredicto" in text and "| ETH fixture |" in text


def test_report_says_when_nothing_beats_chance():
    rows = adjust([{"asset": "X", "indicator": "RSI", "h": 1, "ic": 0.01, "n": 100, "p": 0.9}])
    assert "ningún indicador" in report(rows, [])
