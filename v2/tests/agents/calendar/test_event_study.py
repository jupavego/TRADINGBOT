"""Estudio de eventos (T37) sobre velas sintéticas con efecto conocido (sin red)."""
from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from eim.analytics import event_report
from eim.analytics.event_study import (
    Bars,
    StudyParams,
    bootstrap_mean,
    by_surprise,
    control_times,
    run_study,
)
from eim.core import Candle
from eim.data.store import Store

M15 = 15 * 60_000
DAY = 96 * M15
T0 = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)
CPI, PPI = "Consumer Price Index", "Producer Price Index"


def _days(first: int, n: int, step: int) -> list[int]:
    """Días hábiles (índice desde T0) a partir de `first`, separados ≥ `step`."""
    out, d = [], first
    while len(out) < n:
        if datetime.fromtimestamp((T0 + d * DAY) / 1000, tz=UTC).weekday() < 5:
            out.append(d)
            d += step
        else:
            d += 1
    return out


CPI_T = [T0 + d * DAY + 12 * 4 * M15 + 2 * M15 for d in _days(40, 20, 6)]   # 12:30 UTC
PPI_T = [T0 + d * DAY + 19 * 4 * M15 for d in _days(43, 20, 6)]             # 19:00 UTC
EVENTS = [(t, CPI, "alto") for t in CPI_T] + [(t, PPI, "medio") for t in PPI_T]


def _candles(seed: int, n_days: int = 190, mult: float = 4.0) -> list[Candle]:
    """Paseo aleatorio; tras cada CPI las 4 primeras velas (1 h) tienen rango × `mult`."""
    rng = np.random.default_rng(seed)
    n = n_days * 96
    t = T0 + np.arange(n) * M15
    hot = np.zeros(n, dtype=bool)
    for e in CPI_T:
        i = (e - T0) // M15
        hot[i:i + 4] = True
    scale = np.where(hot, mult, 1.0) * 0.002
    r = rng.normal(0, 1, n) * scale
    c = 100 * np.exp(np.cumsum(r))
    o = np.concatenate([[100.0], c[:-1]])
    wick = np.abs(rng.normal(0, 1, n)) * scale * c
    return [Candle(t=int(t[i]), o=o[i], h=max(o[i], c[i]) + wick[i],
                   l=min(o[i], c[i]) - wick[i], c=c[i], v=1.0) for i in range(n)]


@pytest.fixture(scope="module")
def study() -> dict:
    bars = {"BTCUSDT": Bars.from_candles(_candles(1)), "ETHUSDT": Bars.from_candles(_candles(2))}
    return run_study(bars, EVENTS, StudyParams(n_boot=1000))


def test_detects_effect_and_window(study):
    rec = study["recommended"]["CPI"]
    assert rec["status"] == "efecto"
    assert rec["pre"] == 0 and rec["post"] == 60          # 4 velas de 15 m
    w = study["results"]["BTCUSDT"]["CPI"]["windows"]
    assert w["post_15"]["boot"]["significant"]
    assert math.exp(w["post_60"]["range"]["p50"]) > 2
    assert not w["pre_60"]["boot"]["significant"]


def test_no_effect_is_said(study):
    rec = study["recommended"]["PPI"]
    assert rec["status"] == "sin_efecto" and rec["pre"] == 0 and rec["post"] == 0
    for a in ("BTCUSDT", "ETHUSDT"):
        assert not study["results"][a]["PPI"]["windows"]["post_60"]["boot"]["significant"]


def test_sample_size_and_distribution_declared(study):
    r = study["results"]["ETHUSDT"]["CPI"]
    assert r["n"] == r["n_events"] == 20
    d = r["windows"]["post_240"]["range"]
    assert {"p10", "p25", "p50", "p75", "p90", "frac_pos", "sd"} <= d.keys()
    assert all("p_holm" in b for b in r["bars"]) and len(r["bars"]) == 20


def test_reproducible(study):
    bars = {"BTCUSDT": Bars.from_candles(_candles(1)), "ETHUSDT": Bars.from_candles(_candles(2))}
    again = run_study(bars, EVENTS, StudyParams(n_boot=1000))
    a = study["results"]["BTCUSDT"]["CPI"]["windows"]["post_60"]["boot"]
    b = again["results"]["BTCUSDT"]["CPI"]["windows"]["post_60"]["boot"]
    assert a == b


def test_insufficient_sample():
    bars = {"BTCUSDT": Bars.from_candles(_candles(3, n_days=80))}
    out = run_study(bars, [(t, CPI, "alto") for t in CPI_T[:5]], StudyParams(n_boot=200))
    assert out["recommended"]["CPI"]["status"] == "insuficiente"
    assert out["recommended"]["CPI"]["post"] is None


def test_controls_skip_weekends_and_event_days():
    t = CPI_T[5]
    blocked = np.array(sorted(CPI_T + PPI_T), dtype=np.int64)
    ctl = control_times(t, blocked, StudyParams())
    assert len(ctl) == 20
    for c in ctl:
        assert datetime.fromtimestamp(c / 1000, tz=UTC).weekday() < 5
        assert (c - t) % DAY == 0
        assert np.min(np.abs(blocked - c)) > 4 * 4 * M15


def test_bootstrap_p():
    rng = np.random.default_rng(0)
    assert bootstrap_mean(rng.normal(1, 1, 40), 2000, 1)["p"] < 0.01
    assert bootstrap_mean(rng.normal(0, 1, 40), 2000, 1)["p"] > 0.05
    assert bootstrap_mean([1.0, 2.0], 100, 1)["n"] == 2


def test_by_surprise_terciles(study):
    rows = study["results"]["BTCUSDT"]["CPI"]["rows"]
    s = {r["t0"]: i - 10.0 for i, r in enumerate(rows)}
    out = by_surprise(rows, s)
    assert out["available"] and sum(t["n"] for t in out["terciles"]) == len(rows)
    assert not by_surprise(rows, {})["available"]


def test_report_cli(tmp_path):
    store = Store(tmp_path / "data")
    store.upsert_candles("BTCUSDT", "15m", _candles(1), "fixture")
    ev = tmp_path / "reports" / "calendar" / "events.csv"
    event_report.save_events(ev, [(t, n, i, "fixture") for t, n, i in EVENTS])
    event_report.main(["--symbols", "BTCUSDT", "--data", str(tmp_path / "data"),
                       "--out", str(tmp_path / "reports")])
    md = (tmp_path / "reports" / "calendar_impact.md").read_text(encoding="utf-8")
    assert "| CPI | 20 | 0 | 60 | pausa −0 min / +60 min |" in md
    assert "**no mueve el mercado**" in md
    assert (tmp_path / "reports" / "calendar" / "results.json").exists()
