"""Ajuste bibliográfico de escenarios (T54): forma, apagado, evaluación y sin anticipación."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from eim.core import Candle, ForecastSet
from eim.forecast.calibration import IDS, Outcome
from eim.forecast.lit_tilt import CONFIG_FILE, STATE_FILE, apply_tilt, load_config, tilt_probs
from eim.forecast.scenarios import build_forecast
from eim.literature import tilt_eval
from eim.literature.tilt_eval import Row, evaluate_tilt, literature_net, run_backfill
from tests.paper.helpers import H1, T0, bar
from tests.paper.test_strategies import walk

CFG = load_config()
PROBS = {"bull": 0.5, "neutral": 0.3, "bear": 0.2}


def test_committed_config_is_off_and_matches_the_preregistration():
    assert CFG.version == "lit_tilt_v1" and CFG.enabled is False and CFG.k == 0.5
    assert "enabled" not in json.loads(CONFIG_FILE.read_text(encoding="utf-8"))   # inmutable
    assert CFG.criteria.boot_reps >= 5000 and CFG.criteria.min_forecasts == 300
    assert (CFG.sample.horizon, CFG.sample.stride, CFG.sample.agent_bars) == (25, 25, 500)


def test_activation_lives_in_the_state_file_and_must_match_the_version(tmp_path):
    st = tmp_path / "state.json"
    assert load_config(state=st).enabled is False                       # sin archivo: apagado
    st.write_text(json.dumps({"version": "lit_tilt_v1", "enabled": True}), encoding="utf-8")
    assert load_config(state=st).enabled is True
    st.write_text(json.dumps({"version": "lit_tilt_v0", "enabled": True}), encoding="utf-8")
    assert load_config(state=st).enabled is False                       # otra versión: apagado
    shipped = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    assert shipped["enabled"] is False and shipped["version"] == "lit_tilt_v1"


def test_zero_net_leaves_probabilities_unchanged_and_always_sum_to_one():
    zero = {"bull": 0.0, "neutral": 0.0, "bear": 0.0}
    assert tilt_probs(PROBS, zero, 0.5) == pytest.approx(PROBS)
    assert tilt_probs(PROBS, {}, 0.5) == pytest.approx(PROBS)
    assert tilt_probs(PROBS, {"bull": 1, "neutral": -1, "bear": 0.3}, 0.0) == pytest.approx(PROBS)
    rng = np.random.default_rng(1)
    for _ in range(200):
        p = rng.dirichlet(np.ones(3))
        net = rng.uniform(-1, 1, 3)
        out = tilt_probs(dict(zip(IDS, p, strict=True)), dict(zip(IDS, net, strict=True)), 0.5)
        assert sum(out.values()) == pytest.approx(1.0) and all(v >= 0 for v in out.values())


def test_tilt_moves_mass_toward_supported_scenario_and_keeps_zero_at_zero():
    out = tilt_probs(PROBS, {"bull": 1.0, "neutral": -0.5, "bear": -1.0}, 0.5)
    assert out["bull"] > PROBS["bull"] and out["bear"] < PROBS["bear"]
    z = tilt_probs({"bull": 0.0, "neutral": 0.6, "bear": 0.4}, {"bull": 1.0}, 0.5)
    assert z["bull"] == 0.0 and sum(z.values()) == pytest.approx(1.0)
    one = math.exp(0.5 * 1.0)
    assert out["bull"] == pytest.approx(0.5 * one / (0.5 * one + 0.3 * math.exp(-0.25)
                                                    + 0.2 * math.exp(-0.5)))


@pytest.fixture(scope="module")
def forecast() -> ForecastSet:
    cs = walk(400)
    from eim.core import MarketSnapshot
    snap = MarketSnapshot(symbol="X", timeframe="1h", candles=cs, asof=cs[-1].t + H1,
                          sources={}, coverage={})
    return build_forecast(snap, 25, 100)


def test_apply_tilt_is_off_by_default_and_declares_itself_when_on(forecast):
    net = {"bull": 0.8, "neutral": -0.8, "bear": 0.0}
    assert apply_tilt(forecast, net, CFG) is forecast               # apagado: nada cambia
    on = CFG.model_copy(update={"enabled": True})
    assert apply_tilt(forecast, {i: 0.0 for i in IDS}, on) is forecast   # neto 0: intacto
    fs = apply_tilt(forecast, net, on)
    assert sum(s.probability for s in fs.scenarios) == pytest.approx(1.0)
    assert fs.adjustments and fs.adjustments[0]["id"] == "lit_tilt_v1"
    assert "ajuste bibliográfico" in fs.adjustments[0]["label"]
    base = {s.id: s.probability for s in forecast.scenarios}
    assert fs.adjustments[0]["base_probability"] == pytest.approx(base)
    assert all("ajuste bibliográfico" in s.narrative for s in fs.scenarios)
    assert [s.path for s in fs.scenarios] == [s.path for s in forecast.scenarios]  # bandas igual
    assert forecast.adjustments == []


# --- evaluación -----------------------------------------------------------------------------
def outcome(made_at: int, probs: dict, realized: str) -> Outcome:
    return Outcome(made_at=made_at, realized=realized, ret=0.0, probs=probs,
                   top=max(probs, key=probs.get), brier=0.0, brier_rw=0.0, pinball=None,
                   pinball_rw=None, dir_pred=0, dir_real=0,
                   in_band_terminal={"50": True, "80": True, "90": True},
                   in_band_pooled={"50": 0.5, "80": 0.8, "90": 0.9})


def rows(n: int, informative: bool, seed: int = 0) -> list[Row]:
    """`n` pronósticos (uno por día); con `informative` el neto apunta al escenario realizado."""
    rng = np.random.default_rng(seed)
    out = []
    for k in range(n):
        real = IDS[int(rng.integers(0, 3))]
        net = {i: 0.0 for i in IDS}
        if rng.random() < 0.5:
            tgt = real if informative else IDS[int(rng.integers(0, 3))]
            net = {i: (0.8 if i == tgt else -0.4) for i in IDS}
        out.append(Row(outcome(T0 + k * 86_400_000, dict(PROBS), real), net))
    return out


def test_informative_net_is_accepted_only_when_all_criteria_hold():
    cfg = CFG.model_copy(update={"k": 1.0})
    res = evaluate_tilt(rows(1200, True), cfg)
    assert res["verdict"] == "ACEPTA", res["checks"]
    assert [c["id"] for c in res["checks"]] == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert res["brier"]["gain"] > 0 and res["brier"]["ci"][0] > 0


def test_uninformative_net_is_not_accepted_and_small_sample_is_inconclusive():
    res = evaluate_tilt(rows(1200, False, seed=3), CFG.model_copy(update={"k": 1.0}))
    assert res["verdict"] == "NO ACEPTA" and "falla" in res["reason"]
    small = evaluate_tilt(rows(50, True), CFG)
    assert small["verdict"] == "SIN EVIDENCIA" and "T1" in small["reason"]
    assert evaluate_tilt([], CFG)["verdict"] == "SIN EVIDENCIA"


def test_net_zero_everywhere_gives_zero_gain():
    zero = [Row(r.out, {i: 0.0 for i in IDS}) for r in rows(400, True)]
    res = evaluate_tilt(zero, CFG)
    assert res["brier"]["gain"] == pytest.approx(0.0, abs=1e-12) and res["n_active"] == 0
    assert res["verdict"] == "SIN EVIDENCIA"
    assert res["coverage"]["base"] == res["coverage"]["tilt"]


# --- sin anticipación ------------------------------------------------------------------------
def with_hammer() -> list[Candle]:
    """Descenso limpio y, en la última vela, un martillo: el agente debe apoyar `bull`."""
    cs, p = [], 1000.0
    for k in range(120):
        cs.append(Candle(t=T0 + k * H1, o=p, h=p + 0.2, l=p - 0.7, c=p - 0.5, v=1000.0))
        p -= 0.5
    cs.append(Candle(t=T0 + 120 * H1, o=p - 0.1, h=p + 0.11, l=p - 0.8, c=p + 0.1, v=1000.0))
    return cs


def test_net_uses_only_candles_before_the_origin():
    cs = with_hammer()
    asof = cs[-1].t + H1
    a = literature_net(cs, "1h", asof, 500)
    assert a["bull"] > 0 and a["neutral"] < 0                       # el patrón está activo
    later = [bar(asof + k * H1, 1.0, 9999.0, 0.5, 5000.0) for k in range(30)]
    assert literature_net(cs + later, "1h", asof, 500) != a       # control: lo posterior sí pesa
    assert literature_net((cs + later)[:len(cs)], "1h", asof, 500) == a   # el origen no lo ve


def test_backfill_rows_do_not_depend_on_what_happens_after_the_horizon():
    cfg = CFG.model_copy(update={"sample": CFG.sample.model_copy(
        update={"n_paths": 60, "context": 400, "stride": 25})})
    cs = walk(900, seed=5)
    base = run_backfill(cs, cfg, "X")
    cut = 700
    h = cfg.sample.horizon
    twisted = cs[:cut] + [bar(c.t, c.o * 2, c.h * 2, c.l * 2, c.c * 2, ) for c in cs[cut:]]
    again = run_backfill(twisted, cfg, "X")
    early = [r for r in base if r.out.made_at + (h + 1) * H1 <= cs[cut].t]
    assert early and len(early) <= len(again)
    for r, q in zip(early, again, strict=False):
        assert (r.out.made_at, r.net, r.out.probs, r.out.realized) == (
            q.out.made_at, q.net, q.out.probs, q.out.realized)
    assert tilt_eval.LOG_FLOOR > 0
