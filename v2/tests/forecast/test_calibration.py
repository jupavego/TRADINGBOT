"""Calibración (T19): evaluador, métricas, veredicto, backfill (≥500) y API."""
from __future__ import annotations

import pytest

from eim.api.config import Settings
from eim.api.main import create_app
from eim.data.store import Store
from eim.forecast import BaseEngine
from eim.forecast.backfill import backfill
from eim.forecast.calibration import evaluate_forecast, summarize, verdict
from eim.forecast.scenarios import build_forecast
from tests.agents.conftest import make_snapshot
from tests.local_client import LocalClient


@pytest.fixture(scope="module")
def candles():
    return make_snapshot().candles


def _closes_after(fs, fn):
    return {t: fn(i, p) for i, (t, p) in enumerate(fs.scenarios[0].path)}


def test_pending_until_horizon_observed(candles):
    fs = build_forecast(make_snapshot(500), 20, 100)
    assert evaluate_forecast(fs, {}) is None
    t = [t for t, _ in fs.scenarios[0].path]
    assert evaluate_forecast(fs, dict.fromkeys(t[:-1], 1.0)) is None


def test_realized_scenario_and_bands(candles):
    snap = make_snapshot(500)
    fs = build_forecast(snap, 20, 200)
    last = snap.candles[-1].c
    times = [t for t, _ in fs.scenarios[0].path]
    up = evaluate_forecast(fs, dict.fromkeys(times, last * 1.5))
    assert up.realized == "bull" and up.dir_real == 1
    assert not any(up.in_band_terminal.values())  # +50 % queda fuera de todas las bandas
    flat = evaluate_forecast(fs, dict.fromkeys(times, last))
    assert flat.realized == "neutral" and all(flat.in_band_terminal.values())
    assert 0 <= flat.brier <= 2 and flat.brier < up.brier


def test_backfill_500_and_metrics(candles):
    fcs = list(backfill(BaseEngine(), candles, symbol="ETHUSDT", timeframe="1h",
                        horizon=20, n=100, start=150, stride=1))
    assert len(fcs) >= 500, len(fcs)
    closes = {c.t: c.c for c in candles}
    outs = [o for f in fcs if (o := evaluate_forecast(f, closes))]
    assert len(outs) == len(fcs)  # todo origen tiene su horizonte completo en la historia
    # walk-forward: el origen nunca ve el futuro
    assert all(f.made_at > 0 and f.scenarios[0].path[0][0] >= f.made_at - 3_600_000 for f in fcs)
    rep = summarize(outs, 20)
    assert rep["n_evaluated"] == len(fcs)
    for k, c in rep["coverage"].items():
        assert 0 <= c["terminal"] <= 1 and 0 <= c["pooled"] <= 1, k
    assert sum(rep["realized_freq"].values()) == pytest.approx(1)
    assert rep["curve"] and rep["verdict"]


def test_verdict_small_sample_and_baseline():
    assert "insuficiente" in verdict({"n_evaluated": 10, "n_effective": 0.5})[0]
    assert "Sin pronósticos" in summarize([], 20)["verdict"][0]


def test_api_backfill_and_report(tmp_path, candles):
    Store(tmp_path).upsert_candles("ETHUSDT", "1h", candles, "test")
    app = create_app(Settings(data_dir=tmp_path))
    with LocalClient(app) as client:
        assert client.get("/v2/calibration", params={"h": 20}).json()["n_evaluated"] == 0
        url, q = "/v2/calibration/backfill", {"h": 20, "origins": 520}
        assert client.post(url, params=q).status_code == 403            # sin cabecera (CSRF)
        r = client.post(url, params=q, headers={"X-EIM-Confirm": "backfill"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["saved"] == 520 and j["n_evaluated"] >= 500 and j["n_backfill"] == 520
        assert j["verdict"] and "coverage" in j
        assert client.get("/v2/calibration", params={"symbol": "X"}).status_code == 400
