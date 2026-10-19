"""Estrategias «literatura» (T54): ideas con aciertos sintéticos, versiones y puerta T49."""

from __future__ import annotations

import pytest

from eim.core import Candle
from eim.paper import strategies_lit as sl
from eim.paper import versioning
from eim.paper.catalog import CATALOG, generate_ideas
from eim.paper.ideas import Draft, to_idea
from eim.paper.params import FAMILIES, PROFILES, ExecParams
from eim.paper.strategies_ind import Ind
from tests.paper.helpers import H1, T0, bar

N = 120
CLOSE, ATR = 100.0, 1.0
LIT_IDS = {s.id for s in sl.LIT}


def candles(step: int = H1, **last: tuple[float, float, float, float]) -> list[Candle]:
    """N velas planas (100 ± 0,2); `mK` = OHLC de la K-ésima vela desde el final (m1 = última)."""
    cs = [bar(T0 + i * step, 100.0, 100.2, 99.8, 100.0) for i in range(N)]
    for k, ohlc in last.items():
        i = N + int(k.lstrip("m")) * -1 if k.startswith("m") else int(k)
        cs[i] = bar(cs[i].t, *ohlc)
    return cs


def ctx(cs: list[Candle], card: str | None, direction: int = 1, strength: float = 0.8) -> dict:
    c = cs[-1]
    out = {"v": 2, "t": c.t + (cs[1].t - cs[0].t), "close": CLOSE, "atr": ATR, "regime": "range",
           "syn": {"bias": 0.0, "conf": 0.0, "agree": 0.0}, "agents": {}}
    if card:
        out["lit"] = {"v": "0.1.0", "hits": [[card, direction, strength]],
                      "net": {"bull": 0.5, "neutral": -0.5, "bear": 0.0}, "n": 9}
    return out


def ideas(cs, c, sid, tf="1h"):
    bar_ms = cs[1].t - cs[0].t
    return [i for i in generate_ideas([c], cs, "X", bar_ms, timeframe=tf) if i.strategy == sid]


def test_every_strategy_emits_a_cited_idea_with_valid_geometry():
    cs = candles(step=4 * H1)
    cases = {"lit_canal_4sem": "murphy_weekly_rule", "lit_rsi_recruce": "murphy_rsi",
             "lit_envolvente": "nison_engulfing", "lit_vela_cola": "nison_hammer",
             "lit_estrella_3v": "nison_morning_star"}
    assert set(cases) == LIT_IDS
    for sid, card in cases.items():
        got = ideas(cs, ctx(cs, card), sid, tf="4h")
        assert len(got) == 1, sid
        i = got[0]
        assert i.family == "literatura" and i.version and i.vid.endswith(i.version)
        assert i.side == 1 and (i.entry - i.sl) > 0 and (i.tp - i.entry) > 0
        assert sl.CITE[card] in i.why[0] and "no es una señal validada" in i.why[1]
        assert i.key.startswith(card + ":")


def test_hammer_and_shooting_star_use_the_pattern_extreme_as_stop():
    lo = 98.8
    cs = candles(m1=(99.7, 100.05, lo, 100.0))
    d = ideas(cs, ctx(cs, "nison_hammer", +1), "lit_vela_cola")[0]
    risk = CLOSE - (lo - sl.SL_BUFFER_ATR * ATR)
    assert d.sl == pytest.approx(lo - 0.25) and d.tp == pytest.approx(CLOSE + 2 * risk)
    hi = 101.3
    cs = candles(m1=(100.3, hi, 99.95, 100.0))
    s = ideas(cs, ctx(cs, "nison_shooting_star", -1), "lit_vela_cola")[0]
    risk = (hi + 0.25) - CLOSE
    assert s.side == -1 and s.sl == pytest.approx(hi + 0.25)
    assert s.tp == pytest.approx(CLOSE - 2 * risk)


def test_stars_use_the_three_candle_extreme_and_fall_back_when_stop_is_absurd():
    cs = candles(m3=(101.0, 101.3, 99.2, 99.4), m2=(99.4, 99.6, 99.3, 99.5),
                 m1=(99.5, 101.0, 99.4, 100.9))
    m = ideas(cs, ctx(cs, "nison_morning_star", +1), "lit_estrella_3v")[0]
    assert m.sl == pytest.approx(99.2 - 0.25)                # mínimo de las tres velas
    far = candles(m3=(101.0, 101.3, 90.0, 99.4), m1=(99.5, 101.0, 99.4, 100.9))
    f = ideas(far, ctx(far, "nison_morning_star", +1), "lit_estrella_3v")[0]
    assert f.sl == pytest.approx(CLOSE - 1.5 * ATR) and f.tp == pytest.approx(CLOSE + 2.5 * ATR)
    e = candles(m3=(99.0, 100.5, 98.7, 100.4), m1=(100.5, 100.6, 99.0, 99.1))
    ev = ideas(e, ctx(e, "nison_evening_star", -1), "lit_estrella_3v")[0]
    assert ev.side == -1 and ev.sl == pytest.approx(100.6 + 0.25)


def test_no_hit_or_old_context_means_no_idea():
    cs = candles()
    for sid in LIT_IDS:
        assert ideas(cs, ctx(cs, None), sid) == []                  # contexto sin `lit`
    old = {k: v for k, v in ctx(cs, "murphy_rsi").items() if k != "lit"}
    assert ideas(cs, old, "lit_rsi_recruce") == []
    assert ideas(cs, ctx(cs, "nison_engulfing"), "lit_rsi_recruce") == []   # otra ficha
    nolit = {**ctx(cs, None), "lit": None}                                    # agente sin datos
    assert ideas(cs, nolit, "lit_envolvente") == []


def test_timeframes_canal_only_4h_and_others_1h_4h():
    cs = candles()
    c = ctx(cs, "murphy_weekly_rule")
    assert ideas(cs, c, "lit_canal_4sem", tf="1h") == []
    assert len(ideas(cs, c, "lit_canal_4sem", tf="4h")) == 1       # el marco manda, no el paso
    for sid in LIT_IDS - {"lit_canal_4sem"}:
        assert CATALOG[sid].runs_in("1h") and CATALOG[sid].runs_in("4h")
        assert not CATALOG[sid].runs_in("15m")
    assert CATALOG["lit_canal_4sem"].timeframes == ("4h",)
    assert CATALOG["consenso_sintesis"].runs_in("15m")           # el resto no cambia


@pytest.fixture
def fresh_cache():
    versioning.rules_fingerprint.cache_clear()
    yield
    versioning.rules_fingerprint.cache_clear()


def test_changing_a_parameter_creates_a_new_version(monkeypatch, fresh_cache):
    ep = ExecParams()
    before = {s: CATALOG[s].version("1h", ep) for s in LIT_IDS | {"consenso_sintesis"}}
    monkeypatch.setattr(sl, "SL_BUFFER_ATR", 0.5)
    versioning.rules_fingerprint.cache_clear()
    after = {s: CATALOG[s].version("1h", ep) for s in before}
    assert after["lit_vela_cola"] != before["lit_vela_cola"]
    assert after["lit_estrella_3v"] != before["lit_estrella_3v"]
    assert after["lit_envolvente"] == before["lit_envolvente"]    # no usa ese parámetro
    assert after["consenso_sintesis"] == before["consenso_sintesis"]
    assert CATALOG["lit_vela_cola"].version("1h", ep) != CATALOG["lit_vela_cola"].version("4h", ep)


def test_family_is_registered_but_not_traded_by_profiles():
    assert "literatura" in FAMILIES
    assert all("literatura" not in p.families for p in PROFILES)


def test_pure_strategy_functions_do_not_read_the_future():
    cs = candles(m1=(99.7, 100.05, 98.8, 100.0))
    x = Ind(cs)
    c = ctx(cs, "nison_hammer")
    i = x.index(cs[-1].t)
    a = sl._tail(c, x, i)
    cs2 = cs + [bar(cs[-1].t + H1, 50.0, 200.0, 1.0, 150.0)]      # una vela posterior distinta
    b = sl._tail(c, Ind(cs2), Ind(cs2).index(cs[-1].t))
    assert isinstance(a, Draft) and a == b


def test_to_idea_rejects_wrong_side_geometry():
    info = CATALOG["lit_vela_cola"]
    bad = Draft(side=1, sl=101.0, tp=103.0, conf=0.5, why=("x",), entry=100.0)
    assert to_idea(info, bad, {"t": T0, "close": 100.0}, "X", "backtest") is None
