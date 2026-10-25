"""Motor base: validez, semilla, horizonte, evaluación y Kronos opcional (sin red)."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from eim.forecast import BaseEngine, BaseParams, valid_candles
from eim.forecast.eval import evaluate, format_report
from eim.forecast.kronos_engine import KronosEngine
from tests.agents.conftest import make_snapshot


@pytest.fixture(scope="module")
def snap():
    return make_snapshot()


def test_candles_valid_and_shape(snap):
    paths = BaseEngine().sample(snap, 25, 200)
    assert paths.shape == (200, 25, 4)
    assert valid_candles(paths)


@pytest.mark.perf
def test_fast(snap):
    BaseEngine().sample(snap, 25, 200)                       # calentamiento, descartado
    t = time.perf_counter()
    BaseEngine().sample(snap, 25, 200)
    took = time.perf_counter() - t
    assert took < 3, f"200 trayectorias de 25 velas tardaron {took:.2f} s"


def test_seed_reproducible(snap):
    a = BaseEngine(BaseParams(seed=7)).sample(snap, 20, 50)
    b = BaseEngine(BaseParams(seed=7)).sample(snap, 20, 50)
    c = BaseEngine(BaseParams(seed=8)).sample(snap, 20, 50)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


@pytest.mark.parametrize("h", [19, 31])
def test_horizon_out_of_range(snap, h):
    with pytest.raises(ValueError):
        BaseEngine().sample(snap, h, 10)


@pytest.mark.parametrize("h", [20, 30])
def test_horizon_bounds_ok(snap, h):
    assert BaseEngine().sample(snap, h, 10).shape == (10, h, 4)


def test_starts_near_last_close(snap):
    paths = BaseEngine().sample(snap, 20, 100)
    assert abs(np.median(paths[:, 0, 0]) / snap.candles[-1].c - 1) < 0.02


def test_drift_shifts_median(snap):
    up = BaseEngine(BaseParams(drift=0.002)).sample(snap, 20, 300)
    dn = BaseEngine(BaseParams(drift=-0.002)).sample(snap, 20, 300)
    assert np.median(up[:, -1, 3]) > np.median(dn[:, -1, 3])


def test_too_few_candles():
    with pytest.raises(ValueError):
        BaseEngine().sample(make_snapshot(50), 20, 10)


def test_eval_coverage_reasonable(snap):
    r = evaluate(BaseEngine(), snap.candles, window=700, stride=30, n=200)
    assert r.origins >= 10
    assert abs(r.coverage_50 - 0.5) < 0.15
    assert abs(r.coverage_80 - 0.8) < 0.12
    assert "base" in format_report([r])


def test_kronos_omitted_without_deps(snap):
    if not KronosEngine.available():
        with pytest.raises(RuntimeError):
            KronosEngine().sample(snap, 20, 2)


def test_kronos_contract_with_stub_predictor(snap):
    def stub(df, x_timestamp, y_timestamp, pred_len, **kw):
        c = float(df["close"].iloc[-1])
        return pd.DataFrame(
            {"open": [c] * pred_len, "high": [c * 1.01] * pred_len,
             "low": [c * 0.99] * pred_len, "close": [c] * pred_len}
        )

    paths = KronosEngine(predictor=stub).sample(snap, 25, 5)
    assert paths.shape == (5, 25, 4) and valid_candles(paths)
