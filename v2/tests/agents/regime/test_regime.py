"""Agente regime: series sintéticas con cambios conocidos (retraso acotado, sin falsas alarmas)."""
from __future__ import annotations

import numpy as np

from eim.agents.regime import RegimeAgent
from eim.agents.regime.bocpd import bocpd, change_points, standardize
from eim.core import Candle, MarketSnapshot

H = 3_600_000
T0 = 1_700_000_000_000


def _snap(rets: np.ndarray) -> MarketSnapshot:
    close = 100 * np.exp(np.concatenate(([0.0], np.cumsum(rets))))
    cs = [Candle(t=T0 + i * H, o=x, h=x, l=x, c=x, v=1) for i, x in enumerate(close)]
    return MarketSnapshot(symbol="ETHUSDT", timeframe="1h", candles=cs, asof=cs[-1].t + H)


def _series(seed=1):
    rng = np.random.default_rng(seed)
    # calma -> tendencia alcista -> alta volatilidad (cambios en 300 y 600)
    return np.concatenate([rng.normal(0, 0.002, 300), rng.normal(0.003, 0.002, 300),
                           rng.normal(0, 0.008, 300)])


def _detect(rets):
    _, run = bocpd(standardize(rets), 1 / 800)
    return change_points(run, 8, 12)


def test_detects_known_changes_with_bounded_delay():
    cps = _detect(_series())
    for true in (300, 600):
        hits = [(loc, det) for loc, det in cps if abs(loc - true) <= 15]
        assert hits, f"sin detección cerca de {true}: {cps}"
        assert min(det for _, det in hits) - true <= 40


def test_few_false_alarms_on_stationary_noise():
    total = sum(len(_detect(np.random.default_rng(s).normal(0, 0.003, 900))) for s in range(5))
    assert total <= 1


def test_report_regime_and_neutral_bias():
    rep = RegimeAgent().run(_snap(_series()))
    assert rep.status == "ok" and rep.bias == 0 and 0 <= rep.confidence <= 1
    assert rep.metrics["regime"] == "volatile"
    assert rep.metrics["stability"]["entropy"] >= 0
    for row in rep.metrics["stability"]["transition"]:
        assert abs(sum(row) - 1) < 1e-3 or sum(row) == 0
    assert rep.overlays and all(o.agent_id == "regime" for o in rep.overlays)


def test_trend_label():
    rng = np.random.default_rng(3)
    rets = np.concatenate([rng.normal(0, 0.002, 200), rng.normal(0.004, 0.002, 200)])
    assert RegimeAgent().run(_snap(rets)).metrics["regime"] == "trend_up"


def test_flickering_scheme_is_flagged_unstable():
    rng = np.random.default_rng(5)
    rets = rng.normal(0, 0.003, 600) * np.where(np.arange(600) // 6 % 2 == 0, 1, 4)
    rep = RegimeAgent().run(_snap(rets))
    assert rep.metrics["stability"]["dwell_overall"] >= 0


def test_no_data_and_determinism():
    assert RegimeAgent().run(_snap(np.zeros(20))).status == "no_data"
    s = _snap(_series())
    assert RegimeAgent().run(s) == RegimeAgent().run(s)
