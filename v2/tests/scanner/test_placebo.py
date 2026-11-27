"""T95 — control placebo: las réplicas conservan volatilidad y correlación y destruyen la
estructura temporal; el umbral controla los hallazgos falsos y un universo sin estructura no
muestra nada por encima de él."""

from __future__ import annotations

import numpy as np
import pytest

from eim.scanner import deep, placebo, rank
from eim.scanner import placebo_eval as pe
from tests.scanner._helpers import DAY, T0, candles, perp
from tests.scanner.test_deep import FakeAgent

CUT = T0 + 101 * DAY
ASOF = CUT + 3_600_000


def universe(n=6, width=200, trend=False, short=None):
    insts = {perp(f"S{i}USDT").id: perp(f"S{i}USDT") for i in range(n)}
    ser = {}
    for k, iid in enumerate(sorted(insts)):
        m = short if (short and k == 0) else width
        ser[iid] = candles(m, seed=k, end_t=CUT - DAY, drift=0.004 if trend else 0.0)
    return insts, placebo.stack(ser, width)


def logret(s, i):
    a = s.width - int(s.n[i])
    return np.diff(np.log(s.c[i, a:]))


def test_permutation_keeps_volatility_and_correlation_but_kills_time_structure():
    rng = np.random.default_rng(0)
    w = 300
    f = np.cumsum(rng.normal(0, 1, w)) * 0.002            # deriva persistente: momentum
    ar = np.zeros(w)
    for t in range(1, w):
        ar[t] = 0.8 * ar[t - 1] + rng.normal(0, 0.01)
    base = {"A": ar + f * 0, "B": 0.7 * ar + rng.normal(0, 0.005, w)}
    from eim.core import Candle
    ser = {}
    for k, r in base.items():
        c = 100 * np.exp(np.cumsum(r))
        o = np.r_[100, c[:-1]]
        ser[k] = [Candle(t=T0 + j * DAY, o=float(o[j]), h=float(max(o[j], c[j]) * 1.01),
                         l=float(min(o[j], c[j]) * 0.99), c=float(c[j]), v=1e5 + j,
                         taker_buy_v=5e4) for j in range(w)]
    s = placebo.stack(ser, w)
    p = placebo.permuted(s, np.random.default_rng(1))
    for i in range(2):
        assert np.sort(logret(p, i)) == pytest.approx(np.sort(logret(s, i)))   # misma σ y forma
    corr = lambda x: float(np.corrcoef(logret(x, 0), logret(x, 1))[0, 1])  # noqa: E731
    assert corr(p) == pytest.approx(corr(s), abs=1e-9)                      # misma ρ
    ac = lambda x: float(np.corrcoef(logret(x, 0)[1:], logret(x, 0)[:-1])[0, 1])  # noqa: E731
    assert ac(s) > 0.6 and abs(ac(p)) < 0.2                                  # sin memoria
    assert np.all(p.h >= np.maximum(p.o, p.c) - 1e-9) and np.all(p.l <= np.minimum(p.o, p.c) + 1e-9)
    assert sorted(p.v[0]) == sorted(s.v[0]) and np.array_equal(p.t, s.t)


def test_short_histories_stay_finite_and_keep_their_first_bar():
    _, s = universe(n=3, width=120, short=70)
    for kind in placebo.KINDS.values():
        p = kind(s, np.random.default_rng(2))
        a = s.width - int(s.n[0])
        assert int(p.n[0]) == 70 and np.all(np.isfinite(p.c[0, a:]))
        assert p.c[0, a] == s.c[0, a] and np.all(np.isnan(p.c[0, :a]))


def test_gaussian_keeps_sigma_and_correlation_without_drift():
    rng = np.random.default_rng(3)
    w = 600
    z = rng.normal(0, 1, (2, w))
    r = np.vstack([0.02 * z[0], 0.04 * (0.8 * z[0] + 0.6 * z[1])])
    from eim.core import Candle
    ser = {}
    for k, rr in zip("AB", r, strict=True):
        c = 100 * np.exp(np.cumsum(rr))
        o = np.r_[100, c[:-1]]
        ser[k] = [Candle(t=T0 + j * DAY, o=float(o[j]), h=float(max(o[j], c[j]) * 1.01),
                         l=float(min(o[j], c[j]) * 0.99), c=float(c[j]), v=1e5)
                  for j in range(w)]
    s = placebo.stack(ser, w)
    g = placebo.gaussian(s, np.random.default_rng(4))
    for i in range(2):
        assert np.std(logret(g, i)) == pytest.approx(np.std(logret(s, i)), rel=0.12)
    assert float(np.corrcoef(logret(g, 0), logret(g, 1))[0, 1]) == pytest.approx(0.8, abs=0.08)
    assert np.all(g.h >= np.maximum(g.o, g.c) - 1e-9)


def test_threshold_controls_false_findings_familywise():
    rng = np.random.default_rng(5)
    mk = lambda: {"priorities": list(rng.random(20) * 0.6),  # noqa: E731
                  "n_candidates": 20}
    nulls = [dict(m, max=max(m["priorities"])) for m in (mk() for _ in range(200))]
    ev = pe.evaluate(dict(nulls[0]), nulls, alpha=0.05)
    fresh = [mk() for _ in range(2000)]
    rate = np.mean([max(m["priorities"]) >= ev["threshold"] for m in fresh])
    assert rate <= 0.08                                  # ≈ α: el panel casi nunca muestra ruido
    assert ev["null_rate_per_candidate"] <= 0.01
    real = {"priorities": [0.99, 0.3], "n_candidates": 2, "max": 0.99}
    ev2 = pe.evaluate(real, nulls, alpha=0.05)
    assert ev2["real_above"] == 1 and ev2["p_global"] < 0.01 and ev2["beats_chance"]
    assert ev2["fdr_estimate"] == pytest.approx(ev2["false_per_pass"])


def test_a_structureless_universe_shows_nothing_above_the_threshold(monkeypatch):
    fakes = [FakeAgent("ema", 0.6), FakeAgent("structure", 0.5)]
    monkeypatch.setattr(deep, "_AGENTS", fakes)
    insts, s = universe(n=5, width=200)

    def scan(x):
        return placebo.scan(x, insts, n_bars=90, shortlist_size=3, timeframe="1d", cut=CUT,
                            asof=ASOF, run_many=lambda ps: [placebo.safe_analyze(p) for p in ps])

    real = scan(s)
    assert real["n_candidates"] == 3 and len(real["priorities"]) == 3
    nulls = [scan(placebo.permuted(s, np.random.default_rng([95, k]))) for k in range(20)]
    ev = pe.evaluate(real, nulls, alpha=0.05)
    assert not ev["beats_chance"] and ev["replicas"] == 20
    assert all(m["n_candidates"] == 3 for m in nulls)


def test_threshold_file_is_only_valid_for_the_same_versions(tmp_path):
    fp = pe.fingerprint(rank.DEFAULT_WEIGHTS, "agentes", {"deep": "1"})
    assert pe.load_threshold(tmp_path, fp)["status"] == "sin_placebo"
    ev = {"threshold": 0.61, "replicas": 30, "alpha": 0.05, "fdr_estimate": None}
    pe.write_threshold(tmp_path, ev, fp, {"kind": "permuted", "computed_at": 1})
    ok = pe.load_threshold(tmp_path, fp)
    assert ok["status"] == "vigente" and ok["value"] == 0.61 and ok["replicas"] == 30
    w = rank.Weights({"quality": 1, "viability": 0, "risk": 0, "edge": 0})
    other = pe.fingerprint(w, "agentes", {"deep": "1"})
    stale = pe.load_threshold(tmp_path, other)
    assert stale["status"] == "desactualizado" and stale["value"] is None
    assert pe.fingerprint(rank.DEFAULT_WEIGHTS, "otros", {"deep": "1"}) != fp


def test_rebuilt_bars_stay_valid_candles_when_high_equals_close():
    """En la corrida real falló una vela con h == c: el redondeo dejaba h bajo c (T95)."""
    from eim.core import Candle
    rng = np.random.default_rng(7)
    w = 400
    c = 37.123456789 * np.exp(np.cumsum(rng.normal(0, 0.03, w)))
    o = np.r_[c[0], c[:-1]] * np.exp(rng.normal(0, 0.002, w))
    ser = {"A": [Candle(t=T0 + j * DAY, o=float(o[j]), h=float(max(o[j], c[j])),
                        l=float(min(o[j], c[j])), c=float(c[j]), v=1e5, taker_buy_v=4e4)
                 for j in range(w)]}                      # h y l exactamente en el cuerpo
    s = placebo.stack(ser, w)
    for k in range(20):
        for kind in placebo.KINDS.values():
            p = kind(s, np.random.default_rng(k))
            assert len(placebo.candles_of(p, 0)) == w       # Candle valida cada vela
