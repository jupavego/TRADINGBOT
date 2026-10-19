"""Operaciones intradía sugeridas: modelo de probabilidad, selección y ruta de la API."""

from __future__ import annotations

import pytest

from eim.core import AgentReport, Overlay, Synthesis
from eim.synthesis.setups import (
    Level,
    SetupParams,
    confluence,
    hit_first,
    levels_of,
    suggest,
    touch_prob,
)
from tests.api.test_api import client  # noqa: F401  (fixture de la API)

CLOSE, SIGMA, ATR = 1000.0, 5.0, 8.0   # σ por hora y ATR de 1 h, en USDT


def _syn(bias: float, conf: float = 0.8) -> Synthesis:
    return Synthesis(bias=bias, confidence=conf, agreement=0.8, contributions={}, thesis="")


def test_hit_first_driftless_is_geometric_and_drift_helps():
    assert hit_first(20, 10, 0.0, SIGMA) == pytest.approx(10 / 30)
    assert hit_first(20, 10, 0.5, SIGMA) > 10 / 30 > hit_first(20, 10, -0.5, SIGMA)


def test_touch_prob_bounds_and_monotone():
    assert touch_prob(0, 0, SIGMA, 12) == 1
    near, far = touch_prob(5, 0, SIGMA, 12), touch_prob(30, 0, SIGMA, 12)
    assert 0 < far < near <= 1
    assert touch_prob(30, 1.0, SIGMA, 12) > far  # deriva a favor acerca el nivel


def test_levels_and_confluence_from_agent_overlays():
    ov = [Overlay(id="z", agent_id="levels", kind="zone", t_from=0, label="soporte",
                  geometry={"p_low": 985, "p_high": 990}, confidence=0.5),
          Overlay(id="l", agent_id="vwap", kind="level", t_from=0, label="VWAP",
                  geometry={"p": 989}, confidence=0.5)]
    reps = [AgentReport(agent_id=o.agent_id, version="1", asof=1, bias=0, confidence=0.5,
                        horizon_bars=1, overlays=[o]) for o in ov]
    lv = levels_of(reps)
    assert {x.agent for x in lv} == {"levels", "vwap"}
    assert confluence(990, lv, 2) == 2 and confluence(970, lv, 2) == 0


def test_suggest_follows_the_agents_and_respects_the_rules():
    lv = [Level(988, 992, "levels: soporte", "levels"), Level(990, 990, "vwap: VWAP", "vwap"),
          Level(975, 978, "levels: soporte inferior", "levels"),
          Level(1015, 1020, "levels: resistencia", "levels")]
    p = SetupParams()
    out = suggest(CLOSE, SIGMA, ATR, lv, _syn(0.6), p)
    assert 1 <= len(out) <= p.top
    assert out[0].side == "long" and out[0].aligned
    for s in out:
        d = 1 if s.side == "long" else -1
        assert (s.entry - s.sl) * d > 0 and (s.tp - s.entry) * d > 0       # SL y TP en su lado
        assert (CLOSE - s.entry) * d > 0                                    # límite: retroceso
        assert s.rr >= p.min_rr and p.min_hours <= s.hours <= p.max_hours
        assert 0 <= s.p_fill <= 1 and 0 < s.p_tp < 1
    longs = [s.entry for s in out if s.side == "long"]
    assert all(abs(a - b) >= p.dedupe_atr * ATR for i, a in enumerate(longs) for b in longs[i + 1:])
    # con la síntesis bajista manda el corto
    assert suggest(CLOSE, SIGMA, ATR, lv, _syn(-0.6), p)[0].side == "short"


def test_suggest_without_volatility_is_empty():
    assert suggest(CLOSE, 0, ATR, [], None) == []


def test_setups_route(client):  # noqa: F811
    """T50: la ruta ya no publica la salida cruda de `suggest()` (solo validadas, ver T50)."""
    r = client.get("/v2/setups", params={"symbol": "ETHUSDT"})
    assert r.status_code == 200
    j = r.json()
    assert j["mode"] == "ANALISIS" and j["horizon_hours"] == [0, 36.0]
    assert j["setups"] == [] and j["status"] in ("sin_validadas", "datos_viejos")
    assert "no garantiza rentabilidad" in j["note"] and "p_fill" not in j
    assert client.get("/v2/setups", params={"symbol": "XXX"}).status_code == 400
