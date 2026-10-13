"""Agente derivatives: una serie sintética por cada combinación precio/OI/funding."""
from __future__ import annotations

import json
import math

import pytest

from eim.agents.derivatives import DerivativesAgent
from eim.core import Candle, MarketSnapshot

H = 3_600_000
N = 100
T0 = 1_700_000_000_000


def _snap(price_dir: int, oi_dir: int, funding_last: float, *, with_oi=True, with_funding=True,
          ls=None, basis=None) -> MarketSnapshot:
    """Base plana con ruido; en las últimas 12 barras el precio y el OI se mueven ±."""
    candles = []
    for i in range(N):
        c = 100.0 + 0.05 * math.sin(i)
        if i >= N - 12:
            c += price_dir * 0.5 * (i - (N - 13))  # ±6 % en 12 barras
        candles.append(Candle(t=T0 + i * H, o=c, h=c, l=c, c=c, v=1))
    oi = []
    for i in range(N):
        v = 1000.0 + 5 * math.sin(i)
        if i >= N - 12:
            v *= 1 + oi_dir * 0.01 * (i - (N - 13))
        oi.append((T0 + i * H, v))
    funding = [(T0 + i * 8 * H, 0.0001 + 0.00002 * math.sin(i)) for i in range(29)]
    funding.append((T0 + 29 * 8 * H, funding_last))
    return MarketSnapshot(
        symbol="ETHUSDT", timeframe="1h", candles=candles, asof=T0 + N * H,
        funding=funding if with_funding else None, open_interest=oi if with_oi else None,
        long_short_ratio=ls, basis=basis, sources={"funding": "fixture"},
    )


@pytest.mark.parametrize(("price", "oi", "fund", "rule", "sign"), [
    (1, 1, 0.0010, "largos_saturados", -1),
    (1, 1, 0.0001, "tendencia_alcista_con_oi", 1),
    (-1, 1, -0.0010, "cortos_saturados", 1),
    (-1, 1, 0.0001, "tendencia_bajista_con_oi", -1),
    (-1, -1, 0.0001, "cierre_de_posiciones", 0),
    (1, -1, 0.0001, "cobertura_de_cortos", 1),
])
def test_each_combination(price, oi, fund, rule, sign):
    rep = DerivativesAgent().run(_snap(price, oi, fund))
    assert rep.status == "ok" and rep.metrics["rule"] == rule
    assert (rep.bias > 0) - (rep.bias < 0) == sign
    assert -1 <= rep.bias <= 1 and rep.evidence
    json.dumps(rep.model_dump())


def test_crowded_positions_warn():
    rep = DerivativesAgent().run(_snap(1, 1, 0.0010))
    assert any("squeeze" in w for w in rep.warnings)


@pytest.mark.parametrize("kw", [{"with_oi": False}, {"with_funding": False}])
def test_missing_series_is_no_data(kw):
    rep = DerivativesAgent().run(_snap(1, 1, 0.0001, **kw))
    assert rep.status == "no_data" and rep.bias == 0 and rep.confidence == 0 and rep.warnings


def test_optional_series_warn_and_adjust():
    plain = DerivativesAgent().run(_snap(1, 1, 0.0001))
    assert any("long/short" in w for w in plain.warnings)
    assert any("basis" in w for w in plain.warnings)
    ls = [(T0 + i * H, 1.0 + 0.01 * math.sin(i)) for i in range(40)] + [(T0 + 40 * H, 3.0)]
    rep = DerivativesAgent().run(_snap(1, 1, 0.0001, ls=ls))
    assert rep.bias < plain.bias and rep.metrics["long_short_z"] > 1


def test_deterministic():
    s = _snap(1, 1, 0.0010)
    assert DerivativesAgent().run(s) == DerivativesAgent().run(s)
