"""Validación y serialización de los contratos."""

import pytest
from pydantic import ValidationError

from eim.core import (
    Agent,
    AgentReport,
    Candle,
    ForecastSet,
    MarketSnapshot,
    Mode,
    Overlay,
    Scenario,
    Synthesis,
)


def candle(t: int, c: float = 100.0) -> Candle:
    return Candle(t=t, o=100.0, h=max(101.0, c), l=min(99.0, c), c=c, v=1.0)


def scenario(sid: str, p: float) -> Scenario:
    return Scenario(
        id=sid, probability=p, path=[(1, 100.0)], band_low=[(1, 99.0)], band_high=[(1, 101.0)],
        candles=[candle(1)], invalidation={"level": 95.0, "condition": "cierre < 95"},
        narrative="n", n_paths=100, engine="mc",
    )


def forecast(probs=(0.3, 0.4, 0.3)) -> ForecastSet:
    ids = ("bull", "neutral", "bear")
    return ForecastSet(
        symbol="ETHUSDT", timeframe="1h", made_at=1, horizon_bars=24,
        scenarios=[scenario(i, p) for i, p in zip(ids, probs, strict=True)],
        engine="mc", baseline_engine="gbm",
    )


def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="ETHUSDT", timeframe="1h", candles=[candle(1), candle(2)],
        forming=candle(3), funding=[(1, 0.0001)], asof=3,
        sources={"candles": "fixture"}, coverage={"candles": (1, 2)},
    )


def test_candles_must_be_ordered():
    with pytest.raises(ValidationError):
        MarketSnapshot(symbol="X", timeframe="1h", candles=[candle(2), candle(1)], asof=2)


def test_forming_must_follow_last_closed():
    with pytest.raises(ValidationError):
        MarketSnapshot(symbol="X", timeframe="1h", candles=[candle(2)], forming=candle(2), asof=2)


def test_candle_ohlc_consistency():
    with pytest.raises(ValidationError):
        Candle(t=1, o=100, h=99, l=98, c=100, v=1)


@pytest.mark.parametrize("bias", [-1.01, 1.01])
def test_bias_range(bias):
    with pytest.raises(ValidationError):
        AgentReport(agent_id="a", version="1", asof=1, bias=bias, confidence=0.5, horizon_bars=5)


def test_probabilities_must_sum_to_one():
    with pytest.raises(ValidationError):
        forecast((0.5, 0.4, 0.3))


def test_exactly_three_distinct_scenarios():
    with pytest.raises(ValidationError):
        ForecastSet(
            symbol="X", timeframe="1h", made_at=1, horizon_bars=24,
            scenarios=[scenario("bull", 0.5), scenario("bull", 0.5)],
            engine="mc", baseline_engine="gbm",
        )


def test_horizon_range():
    with pytest.raises(ValidationError):
        ForecastSet(**{**forecast().model_dump(), "horizon_bars": 10})


def test_frozen():
    with pytest.raises(ValidationError):
        snapshot().candles[0].c = 1.0  # type: ignore[misc]


def test_json_roundtrip():
    overlay = Overlay(
        id="o1", agent_id="a", kind="level", t_from=1, geometry={"p": 100.0},
        label="S", confidence=0.7,
    )
    report = AgentReport(
        agent_id="a", version="1", asof=1, bias=0.4, confidence=0.6, horizon_bars=10,
        overlays=[overlay], metrics={"x": 1},
    )
    synth = Synthesis(
        bias=0.2, confidence=0.5, agreement=0.8, contributions={"a": 0.4}, thesis="t"
    )
    for obj in (snapshot(), report, forecast(), synth):
        assert type(obj).model_validate_json(obj.model_dump_json()) == obj


def test_mode_values():
    assert {m.value for m in Mode} == {"ANALISIS", "SIMULADO", "TESTNET", "REAL"}


def test_agent_protocol():
    class Dummy:
        id = "dummy"
        version = "1"
        requires = {"candles"}

        def run(self, snapshot):
            return AgentReport(
                agent_id=self.id, version=self.version, asof=snapshot.asof,
                bias=0, confidence=0, horizon_bars=0, status="no_data",
            )

    assert isinstance(Dummy(), Agent)
