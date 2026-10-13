"""Escenarios: 3 siempre, probabilidades suman 1, velas válidas, semilla, deriva y API."""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from eim.api.config import Settings
from eim.api.main import create_app
from eim.core import Candle, ForecastSet
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.forecast import BaseEngine, BaseParams
from eim.forecast.scenarios import ScenarioParams, build_forecast, classify
from tests.agents.conftest import make_snapshot


@pytest.fixture(scope="module")
def snap():
    return make_snapshot()


@pytest.fixture(scope="module")
def fs(snap):
    return build_forecast(snap, 25, 300, BaseEngine(BaseParams(seed=1)))


def test_three_scenarios_probabilities_sum_one(fs):
    assert isinstance(fs, ForecastSet)
    assert sorted(s.id for s in fs.scenarios) == ["bear", "bull", "neutral"]
    assert sum(s.probability for s in fs.scenarios) == pytest.approx(1.0)
    assert sum(s.n_paths for s in fs.scenarios) == 300  # proporción = n_paths / n


def test_candles_valid_and_future(fs, snap):
    step = tf_ms(snap.timeframe)
    for s in fs.scenarios:
        assert len(s.candles) == len(s.path) == len(s.band_low) == 25
        assert s.candles[0].t == snap.candles[-1].t + step
        for c in s.candles:
            assert c.h >= max(c.o, c.c) and c.l <= min(c.o, c.c) and c.l > 0
        for (_, lo), (_, p), (_, hi) in zip(s.band_low, s.path, s.band_high, strict=True):
            assert lo <= p <= hi
        assert "simulad" in s.narrative and s.engine == "base"
        assert s.invalidation["condition"]


def test_invalidation_sides(fs, snap):
    last = snap.candles[-1].c
    by = {s.id: s for s in fs.scenarios}
    assert by["bull"].invalidation["level"] < last < by["bear"].invalidation["level"]


def test_reproducible_with_seed(snap):
    eng = lambda: BaseEngine(BaseParams(seed=5))  # noqa: E731
    a = build_forecast(snap, 20, 100, eng())
    b = build_forecast(snap, 20, 100, eng())
    assert a.model_dump() == b.model_dump()


def test_empty_group_still_three_with_zero_probability(snap):
    # umbral enorme: todo cae en neutral; bull/bear presentes con prob. 0 y aviso
    out = build_forecast(snap, 20, 100, BaseEngine(BaseParams(seed=2)),
                         ScenarioParams(neutral_atr=1e6))
    probs = {s.id: s.probability for s in out.scenarios}
    assert probs == {"bull": 0.0, "neutral": 1.0, "bear": 0.0}
    assert len(out.warnings) == 2
    assert all(s.n_paths >= 1 for s in out.scenarios)


def test_external_drift_tilts_probabilities(snap):
    base = BaseEngine(BaseParams(seed=3))
    up = build_forecast(snap, 25, 300, base, drift=0.003)
    dn = build_forecast(snap, 25, 300, base, drift=-0.003)
    p = lambda f, i: next(s.probability for s in f.scenarios if s.id == i)  # noqa: E731
    assert p(up, "bull") > p(dn, "bull") and p(dn, "bear") > p(up, "bear")
    assert any("deriva" in w for w in up.warnings)


def test_classify_threshold():
    paths = np.ones((3, 2, 4))
    paths[:, -1, 3] = [110.0, 100.5, 90.0]
    assert list(classify(paths, 100.0, 1.0, 2.0)) == [0, 1, 2]


def test_api_forecast_btcusdt(tmp_path):
    step = tf_ms("1h")
    t0 = 1_700_000_000_000 // step * step
    rng = np.random.default_rng(0)
    price = 30000 * np.exp(np.cumsum(rng.normal(0, 0.004, 400)))
    candles = [Candle(t=t0 + i * step, o=float(p), h=float(p * 1.003), l=float(p * 0.997),
                      c=float(p * 1.001), v=10.0) for i, p in enumerate(price)]
    Store(tmp_path).upsert_candles("BTCUSDT", "1h", candles, "test")
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        r = client.get("/v2/forecast", params={"symbol": "BTCUSDT", "tf": "1h", "h": 25})
        assert r.status_code == 200
        fs = ForecastSet.model_validate(r.json())
        assert fs.symbol == "BTCUSDT" and fs.horizon_bars == 25
        assert client.get("/v2/forecast", params={"h": 5}).status_code == 422
        assert client.get("/v2/forecast", params={"symbol": "XXX"}).status_code == 400
        assert client.get("/v2/forecast", params={"symbol": "ETHUSDT"}).status_code == 404
        saved = app.state.forecaster.db.query("BTCUSDT", "1h")
        assert [s.model_dump() for s in saved] == [fs.model_dump()]


def test_each_scenario_has_ceiling_and_floor(fs):
    for s in fs.scenarios:
        roles = {lv["role"]: lv for lv in s.levels}
        assert set(roles) == {"techo", "piso"}
        assert roles["techo"]["price"] > roles["piso"]["price"]
        for lv in roles.values():
            assert lv["source"] == "estadístico" and lv["note"] and lv["price"] == lv["stat_price"]
            assert lv["context"] is None or lv["context"]["methods"]
