"""Agente calendar: ventanas antes/durante/después, calidad del calendario, nunca direccional."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from eim.agents.calendar import CalendarAgent, CalendarParams
from eim.agents.registry import default_registry
from eim.core import Candle, EconEvent, MarketSnapshot

MIN = 60_000
H = 60 * MIN
DAY = 24 * H
CPI = int(datetime(2026, 10, 14, 12, 30, tzinfo=UTC).timestamp() * 1000)  # 08:30 ET (EDT)
FOMC = int(datetime(2026, 10, 20, 18, 0, tzinfo=UTC).timestamp() * 1000)  # ficticia, 14:00 ET


def _ev(src: str, name: str, t: int, impact: str, **kw) -> EconEvent:
    return EconEvent(id=f"{src}:{name.lower().replace(' ', '-')}:{t}", t_utc=t, name=name,
                     country="US", impact=impact, source=f"fixture {src}", fetched_at=CPI - DAY,
                     **kw)


EVENTS = [
    _ev("bls", "Real Earnings", CPI, "bajo"),
    _ev("bls", "Consumer Price Index", CPI, "alto"),
    _ev("bls", "Producer Price Index", CPI + DAY, "medio"),
    _ev("fed_fomc", "Decisión de tipos FOMC", FOMC, "alto"),
]


def _snap(asof: int, events=EVENTS, fetched_age_h: float = 6, known_days: float = 60,
          missing: tuple[str, ...] = ()) -> MarketSnapshot:
    fetched = asof - int(fetched_age_h * H)
    cov = {f"events:{s}": (fetched, asof + int(known_days * DAY))
           for s in ("fed_fomc", "bls", "bea") if s not in missing}
    cov["events"] = (asof - DAY, asof + 7 * DAY)
    win = [e for e in events if asof - DAY <= e.t_utc <= asof + 7 * DAY] if events else events
    return MarketSnapshot(
        symbol="ETHUSDT", timeframe="1h", asof=asof, events=win,
        candles=[Candle(t=asof - H, o=2500, h=2510, l=2490, c=2505, v=1)],
        sources={"events": "bea, binance_expiry, bls, fed_fomc"}, coverage=cov)


# Lógica de ventanas por impacto (sin las ventanas por evidencia de T37: ver test_t37_windows).
AGENT = CalendarAgent(CalendarParams(event_windows={}))


def test_well_before_event_no_window():
    rep = AGENT.run(_snap(CPI - 5 * H))
    m = rep.metrics
    assert rep.status == "ok" and rep.bias == 0 and rep.confidence == 1
    assert m["next_high_impact"]["name"] == "Consumer Price Index"
    assert m["minutes_to_next_high"] == 300
    assert m["window"] is None and m["blackout"] is False
    assert [u["name"] for u in m["upcoming"]] == [
        "Consumer Price Index", "Producer Price Index", "Decisión de tipos FOMC"]  # sin "bajo"
    assert "en 5 h 0 min" in rep.evidence[0]
    json.dumps(rep.model_dump())


def test_just_before_high_impact_opens_blackout():
    rep = AGENT.run(_snap(CPI - 25 * MIN))
    m = rep.metrics
    assert m["window"] == "pre" and m["blackout"] is True
    assert "Consumer Price Index" in m["blackout_reason"] and "en 25 min" in m["blackout_reason"]
    assert rep.warnings[0].startswith("Riesgo de evento")
    assert rep.bias == 0


def test_at_release_and_after_post_window():
    at = AGENT.run(_snap(CPI))
    assert at.metrics["window"] == "post" and at.metrics["blackout"] is True
    assert at.metrics["next_high_impact"]["name"] == "Decisión de tipos FOMC"
    after = AGENT.run(_snap(CPI + 61 * MIN))
    assert after.metrics["window"] is None and after.metrics["blackout"] is False
    assert [r["name"] for r in after.metrics["recent"]] == ["Consumer Price Index"]


def test_fomc_post_window_is_longer():
    assert AGENT.run(_snap(FOMC + 90 * MIN)).metrics["blackout"] is True
    assert AGENT.run(_snap(FOMC + 121 * MIN)).metrics["blackout"] is False


def test_medium_impact_window_warns_without_blackout():
    rep = AGENT.run(_snap(CPI + DAY - 10 * MIN))
    assert rep.metrics["window"] == "pre" and rep.metrics["blackout"] is False
    assert "impacto medio" in rep.warnings[0]


def test_surprise_without_consensus_is_not_invented():
    ev = [_ev("bls", "Consumer Price Index", CPI, "alto", actual=0.4, previous=0.3,
              unit="IPC general m/m %")]
    s = AGENT.run(_snap(CPI + 2 * H, ev)).metrics["surprise"]
    assert s["actual"] == 0.4 and s["forecast"] is None and s["z"] is None
    assert "consenso no disponible" in s["note"]
    no_actual = AGENT.run(_snap(CPI + 2 * H, ev[:0] + [_ev("bls", "Consumer Price Index", CPI,
                                                           "alto")])).metrics["surprise"]
    assert no_actual["actual"] is None and "no disponible" in no_actual["note"]


def test_surprise_standardized_with_history():
    ev = [_ev("bls", "Consumer Price Index", CPI, "alto", actual=0.5, forecast=0.3)]
    agent = CalendarAgent(CalendarParams(surprise_sd={"Consumer Price Index": 0.1}))
    assert agent.run(_snap(CPI + H, ev)).metrics["surprise"]["z"] == pytest.approx(2.0)
    raw = AGENT.run(_snap(CPI + H, ev)).metrics["surprise"]
    assert raw["z"] is None and raw["diff"] == pytest.approx(0.2)


def test_stale_calendar_is_degraded():
    rep = AGENT.run(_snap(CPI - 5 * H, fetched_age_h=72))
    assert rep.status == "degraded" and rep.confidence == 0 and rep.bias == 0
    assert any("obsoleta" in w for w in rep.warnings)


def test_missing_source_and_short_horizon_lower_confidence():
    rep = AGENT.run(_snap(CPI - 5 * H, missing=("bea",)))
    assert rep.status == "degraded" and rep.confidence == pytest.approx(2 / 3, abs=1e-4)
    short = AGENT.run(_snap(CPI - 5 * H, known_days=3.5))
    assert short.status == "degraded" and short.confidence == pytest.approx(0.5, abs=1e-4)
    assert any("cobertura parcial" in w for w in short.warnings)


def test_no_events_field_is_no_data():
    rep = AGENT.run(_snap(CPI, events=None))
    assert rep.status == "no_data" and rep.bias == 0 and rep.confidence == 0


def test_empty_but_fresh_calendar_is_ok():
    rep = AGENT.run(_snap(CPI, events=[]))
    assert rep.status == "ok" and rep.metrics["next_high_impact"] is None
    assert rep.evidence[0].startswith("Sin eventos de alto impacto")


def test_markers_per_relevant_event_and_determinism():
    snap = _snap(CPI - 5 * H)
    a, b = AGENT.run(snap), AGENT.run(snap)
    assert a == b
    assert [o.kind for o in a.overlays] == ["marker"] * 3
    o = a.overlays[0]
    assert o.geometry["t"] == CPI and o.geometry["p"] == 2505 and o.t_from == CPI


@pytest.mark.parametrize("offset", [-3 * DAY, -2 * H, -30 * MIN, 0, 30 * MIN, 3 * H, 2 * DAY])
def test_never_directional(offset):
    assert AGENT.run(_snap(CPI + offset)).bias == 0


def test_registered():
    assert default_registry().get("calendar").version == "1.1.0"


def test_blackout_covers_next_bar_and_reaches_risk_engine():
    from eim.risk.inputs import market_context

    def two_bars(asof: int) -> MarketSnapshot:
        s = _snap(asof)
        c = [Candle(t=asof - 2 * H, o=1, h=1, l=1, c=1, v=1), *s.candles]
        return s.model_copy(update={"candles": c})

    soon = AGENT.run(two_bars(CPI - 90 * MIN))  # la ventana abre 30 min después del cierre
    assert soon.metrics["window"] is None and soon.metrics["blackout"] is True
    assert soon.bias == 0
    far = AGENT.run(two_bars(CPI - 2 * H))
    assert far.metrics["blackout"] is False
    assert {w["name"] for w in far.metrics["risk_windows"]} >= {"Consumer Price Index"}
    ctx = market_context([soon], last_close_t=CPI - 150 * MIN, now=CPI - 90 * MIN, bar_ms=H)
    assert ctx.blackout and "Consumer Price Index" in ctx.blackout_reason
