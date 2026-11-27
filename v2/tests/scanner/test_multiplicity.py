"""T95 — intentos y multiplicidad: todo intento cuenta, la familia se amplía (841 previos de T49 +
los del escáner), Holm/BH/DSR sobre ella y nada se llama «validada» sin la puerta v1 de T49."""

from __future__ import annotations

import math

import numpy as np
import pytest

from eim.scanner import multiplicity as mu

RESULT = {"instrument_id": "crypto.binance.usdm.AUSDT", "symbol": "AUSDT", "timeframe": "1d",
          "ran": [{"agent_id": "ema", "version": "1.2", "status": "ok", "bias": 0.4},
                  {"agent_id": "vwap", "version": "2.0", "status": "degraded", "bias": -0.1},
                  {"agent_id": "regime", "version": "1.0", "status": "no_data", "bias": 0.0}],
          "synthesis": {"bias": 0.3}, "opportunity": {"side": "largo"}}


def test_every_evaluated_hypothesis_is_an_attempt_with_its_full_key():
    a = mu.attempts_of(RESULT, horizon_bars=25, close0=10.0, sigma_h=0.1, cost=0.002,
                       synthesis_version="v1-d1-s1", scores={"quality": 0.5})
    assert [x.key for x in a] == [
        "crypto.binance.usdm.AUSDT|ema@1.2|1d|h25", "crypto.binance.usdm.AUSDT|vwap@2.0|1d|h25",
        "crypto.binance.usdm.AUSDT|regime@1.0|1d|h25",
        "crypto.binance.usdm.AUSDT|sintesis@v1-d1-s1|1d|h25"]
    assert [x.side for x in a] == [1, -1, 0, 1]          # sin datos: cuenta, sin lado
    assert a[-1].scores == {"quality": 0.5} and a[0].scores is None
    neutral = dict(RESULT, opportunity=None)
    assert mu.attempts_of(neutral, horizon_bars=25, close0=10, sigma_h=0.1, cost=0.0,
                          synthesis_version="v")[-1].side == 0


def test_outcome_is_net_of_cost_in_sigma_and_the_flip_pays_the_same_cost():
    o, f = mu.outcome(1, 100.0, 110.0, 0.2, 0.004)
    assert o == pytest.approx((math.log(1.1) - 0.004) / 0.2)
    assert f == pytest.approx((-math.log(1.1) - 0.004) / 0.2)
    o2, _ = mu.outcome(-1, 100.0, 110.0, 0.2, 0.004)
    assert o2 == pytest.approx(f)


def test_pvalue_needs_matured_observations_and_detects_a_real_edge():
    assert mu.pvalue([1.0] * (mu.MIN_OBS - 1), [-1.0] * (mu.MIN_OBS - 1), 900, "x") is None
    rng = np.random.default_rng(0)
    r = rng.normal(0.8, 0.5, 40)
    p = mu.pvalue(r, -r - 0.02, 900, "fuerte")
    assert p is not None and p < 1e-3
    noise = rng.normal(0, 1, 40)
    assert mu.pvalue(noise, -noise, 900, "ruido") > 0.01
    assert mu.pvalue(r, -r - 0.02, 900, "fuerte") == p                  # reproducible


def test_correction_runs_over_the_whole_family_not_just_the_scanner():
    pv = {"k1": 1e-4, "k2": None, "k3": 0.5}
    adj = mu.adjust(pv)
    m = mu.PRIOR_FAMILY + 3
    assert adj["k1"][0] == pytest.approx(min(1.0, 1e-4 * m))            # Holm sobre 844
    assert adj["k1"][1] == pytest.approx(min(1.0, 1e-4 * m))            # BH: el menor, ×m
    assert adj["k2"] == (1.0, 1.0)                                       # sin p = 1
    alone = mu.adjust(pv, prior_family=0)
    assert alone["k1"][0] < adj["k1"][0]                                 # reiniciar sería trampa
    assert mu.family_size(3) == m and mu.adjust({}) == {}


def test_presentation_and_never_validated_without_the_t49_gate():
    adj = mu.adjust({"k": 1e-9})
    s = {"n_obs": 40, "n_matured": 30, "p_raw": 1e-9, "dsr": 0.99}
    out = mu.present("k", s, adj, mu.family_size(1), 0.05)
    assert out["n_family"] == mu.PRIOR_FAMILY + 1 and out["p_holm"] < 0.05
    assert "NO validada" in out["verdict"] and out["validation"] == mu.NOT_VALIDATED
    few = mu.present("k", {"n_obs": 3, "n_matured": 2}, adj, 900, 0.05)
    assert "sin resultados suficientes" in few["verdict"]
    assert mu.validation_status("k") == mu.NOT_VALIDATED
    assert mu.validation_status("k", frozenset({"k"})) == mu.VALIDATED   # solo vía T49


def test_deflated_sharpe_uses_the_family_size():
    rng = np.random.default_rng(2)
    r = list(rng.normal(0.3, 1, 60))
    assert mu.dsr(r, 1) > mu.dsr(r, 5000)
    assert mu.dsr(r[:2], 10) is None
