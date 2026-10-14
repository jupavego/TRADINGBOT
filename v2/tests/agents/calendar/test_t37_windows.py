"""Ventanas por evidencia (T37) en el agente `calendar` y su paso al motor de riesgo."""
from __future__ import annotations

from eim.agents.calendar import CalendarAgent
from eim.agents.calendar.params import T37_WINDOWS
from eim.core import Candle, MarketSnapshot
from eim.risk.inputs import market_context
from tests.agents.calendar.test_calendar import CPI, DAY, FOMC, MIN, H, _ev, _snap

AGENT = CalendarAgent()
TRADE = "U.S. International Trade in Goods and Services"
EVENTS = [
    _ev("bls", "Consumer Price Index", CPI, "alto"),
    _ev("bls", "Producer Price Index", CPI + DAY, "medio"),
    _ev("bea", TRADE, CPI + 2 * DAY, "medio"),
    _ev("bls", "Employment Cost Index", CPI + 3 * DAY, "medio"),
    _ev("fed_fomc", "Decisión de tipos FOMC", FOMC, "alto"),
]


def _m(asof: int, bars: int = 1) -> dict:
    s = _snap(asof, EVENTS)
    if bars == 2:
        s = s.model_copy(update={"candles": [Candle(t=asof - 2 * H, o=1, h=1, l=1, c=1, v=1),
                                             *s.candles]})
    return AGENT.run(s).metrics


def test_every_window_cites_n_and_significance():
    for name, w in T37_WINDOWS.items():
        assert "n=" in w.evidence and "p Holm" in w.evidence, name
        assert w.blackout == bool(w.pre or w.post), name


def test_cpi_window_from_evidence():
    assert _m(CPI - 25 * MIN)["blackout"] is False            # pre = 15 min, no 60
    m = _m(CPI - 10 * MIN)
    assert m["blackout"] is True and m["window"] == "pre"
    w = next(r for r in m["risk_windows"] if r["name"] == "Consumer Price Index")
    assert w["blackout"] and w["basis"].startswith("evidencia T37") and "n=21" in w["basis"]
    assert _m(CPI + 25 * MIN)["blackout"] is True
    assert _m(CPI + 31 * MIN)["blackout"] is False             # post = 30 min


def test_medium_event_with_evidence_blocks():
    assert _m(CPI + DAY + 10 * MIN)["blackout"] is True        # IPP: ×2.1 en t0


def test_no_effect_event_has_no_window():
    m = _m(CPI + 2 * DAY)
    assert m["blackout"] is False and m["window"] is None
    assert TRADE not in {w["name"] for w in m["risk_windows"]}


def test_without_evidence_falls_back_to_impact():
    m = _m(CPI + 3 * DAY - 10 * MIN)                           # ECI: n=7, ventana por defecto
    assert m["window"] == "pre" and m["blackout"] is False
    assert m["window_event"]["name"] == "Employment Cost Index"


def test_fomc_long_post_window():
    assert _m(FOMC + 220 * MIN)["blackout"] is True
    assert _m(FOMC + 226 * MIN)["blackout"] is False


def test_pre_zero_still_blocks_previous_bar_and_reaches_risk():
    m = _m(CPI + DAY - 30 * MIN, bars=2)                       # IPP pre = 0; vela de 1 h
    assert m["window"] is None and m["blackout"] is True
    snap: MarketSnapshot = _snap(CPI + DAY - 30 * MIN, EVENTS)
    rep = AGENT.run(snap.model_copy(update={"candles": [
        Candle(t=snap.asof - 2 * H, o=1, h=1, l=1, c=1, v=1), *snap.candles]}))
    ctx = market_context([rep], last_close_t=snap.asof - H, now=snap.asof, bar_ms=H)
    assert ctx.blackout and "Producer Price Index" in ctx.blackout_reason
