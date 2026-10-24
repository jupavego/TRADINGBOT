"""Estadística del banco de latencia (T77): sin red, con relojes sintéticos conocidos."""

from __future__ import annotations

import numpy as np
import pytest

from eim.hft.latency import (
    ClockSample,
    Hist,
    clock_anchors,
    clock_summary,
    event_times,
    stream_kind,
    stream_stats,
)
from eim.hft.latency_report import budget, merge, render

T0_US = 1_792_000_000_000_000          # época en µs


def test_hist_quantiles_merge_and_roundtrip():
    h = Hist.of(range(1, 101))                       # 1..100 ms, bins de 1 ms
    assert h.n == 100
    assert h.quantile(0.5) == 50.5 and h.quantile(0.99) == 99.5
    assert h.summary()["max"] == 100.5
    both = h.merge(Hist.of([200.0] * 100))
    assert both.n == 200 and both.quantile(0.5) == 100.5 and both.quantile(0.99) == 200.5
    assert Hist.from_json(both.to_json()).counts == both.counts
    with pytest.raises(ValueError):
        h.merge(Hist(0.1))


def test_hist_ignores_non_finite_and_handles_negatives():
    h = Hist.of([float("nan"), float("inf"), -2.5, 3.0])
    assert h.n == 2 and h.quantile(0.01) == -2.5
    assert Hist().quantile(0.5) is None and Hist().summary() == {"n": 0}


def _sample(t_s: float, offset_ms: float, rtt_ms: float) -> ClockSample:
    send = T0_US + int(t_s * 1e6)
    recv = send + int(rtt_ms * 1000)
    mid_ms = (send + recv) / 2000
    return ClockSample(send, recv, round(mid_ms + offset_ms))


def test_clock_offset_uses_min_rtt_per_window_and_measures_drift():
    # desfase real 40 ms que crece 100 ppm (0,1 ms/s); una muestra lenta por ventana con error
    samples = []
    for i in range(0, 600, 5):
        true = 40 + 0.1 * i
        samples.append(_sample(i, true, 200))
        samples.append(_sample(i + 1, true + 0.1 + 80, 900))   # RTT alto y desfase falso
    a = clock_anchors(samples, win_s=60)
    assert a.t_ms.size == 10
    assert np.all(a.rtt_ms == 200)
    s = clock_summary(samples, a)
    assert s["drift_ppm"] == pytest.approx(100, abs=2)
    assert s["uncertainty_ms"] == 100 and s["resid_max_ms"] <= 1


def test_clock_step_is_tracked_by_interpolation():
    samples = [_sample(i, 0 if i < 300 else 500, 100) for i in range(0, 600, 10)]
    a = clock_anchors(samples, win_s=60)
    assert a.offset_at(T0_US / 1000 + 100_000) == pytest.approx(0, abs=1)
    assert a.offset_at(T0_US / 1000 + 500_000) == pytest.approx(500, abs=1)
    assert clock_summary(samples, a)["resid_max_ms"] > 100        # el salto se delata


def test_stream_kind_and_event_times():
    assert stream_kind("btcusdt@depth@100ms") == "depth"
    assert stream_kind("btcusdt@markPrice@1s") == "markPrice"
    assert stream_kind("") is None
    assert event_times("markPrice", {"E": 10, "T": 99}) == (10, -1)   # T = próximo funding
    assert event_times("aggTrade", {"E": 10, "T": 8}) == (10, 8)


def test_stream_stats_recovers_known_age():
    # reloj local 30 ms por detrás del servidor; el evento llega 120 ms después de E, E = T + 2
    offset, age = 30.0, 120.0
    samples = [_sample(i, offset, 50) for i in range(0, 180, 5)]
    a = clock_anchors(samples)
    e = np.arange(200) * 100 + T0_US / 1000 + 1_000
    loc_us = ((e + age - offset) * 1000).astype(np.int64)
    proc = Hist.of([10, 20, 30])
    out, hists = stream_stats(loc_us, e.astype(np.int64), (e - 2).astype(np.int64), a, 20.0,
                              proc)
    assert out["msgs"] == 200 and out["msg_per_s"] == 10
    assert hists["age_E"].quantile(0.5) == pytest.approx(age, abs=1)
    assert hists["age_T"].quantile(0.5) == pytest.approx(age + 2, abs=1)
    assert hists["E_minus_T"].quantile(0.99) == pytest.approx(2, abs=1)
    assert hists["interarrival"].quantile(0.5) == pytest.approx(100, abs=1)
    assert out["jitter_ms"] <= 1 and out["stalls_5s"] == 0 and out["proc_us"]["n"] == 3


def test_stream_stats_counts_stalls_and_empty_stream():
    a = clock_anchors([_sample(0, 0, 10)])
    loc = np.array([0, 100, 7_000_100], dtype=np.int64) + T0_US
    out, _ = stream_stats(loc, [1, 1, 1], [-1, -1, -1], a, 10.0)
    assert out["stalls_5s"] == 1 and "age_T" not in out
    assert stream_stats([], [], [], a, 10.0) == ({"msgs": 0}, {})


def _run(run_id: str, hour: int, age: float) -> dict:
    hj = {"age_T": Hist.of([age] * 100).to_json(), "age_E": Hist.of([age] * 100).to_json()}
    return {"run_id": run_id, "started_utc": f"2026-10-23T{hour:02d}:00:00+00:00",
            "duration_s": 3600, "minutes": 60, "label": "x",
            "clock": {"offset_ms_first": 1.0, "offset_ms_last": 2.0, "drift_ppm": 3.0,
                      "uncertainty_ms": 100.0},
            "connections": {"public": {"reconnects": 1}},
            "streams": {"bookTicker": {"msgs": 1000, "stalls_5s": 0}},
            "hists": {"bookTicker": hj, "depth": {"proc_us": Hist.of([500] * 100).to_json()},
                      "rest_rtt": Hist.of([250] * 10).to_json(),
                      "ws_api_ping": Hist.of([240] * 10).to_json(),
                      "loop_lag": Hist(0.1, {20: 100}).to_json()}}


def test_report_merges_runs_and_derives_budget():
    runs = [_run("b", 22, 200.0), _run("a", 21, 100.0)]
    m = merge(runs)
    assert m["bookTicker.age_T"].n == 200
    b = budget(m)
    # p99: datos 200,5 + proceso 0,5005 + bucle 2,05 + ida 240,5/2
    assert b["p99"]["total"] == pytest.approx(200.5 + 0.5005 + 2.05 + 120.25, abs=0.01)
    assert budget(m, "depth")["p99"]["datos"] == 0            # sin `depth`: la vista no inventa
    md = render(runs)
    assert md.index("| a |") < md.index("| b |")            # ordenadas por hora
    assert "horas de inicio UTC: 21, 22" in md and "Python basta" in md
    assert "menor presupuesto p99" in md                     # la regla usa la vista más exigente
