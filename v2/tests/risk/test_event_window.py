"""T44: el calendario no suma al sesgo; en ventana reduce el tamaño y con blackout veta."""

import pytest

from eim.core import AgentReport
from eim.risk import load_config
from eim.risk.inputs import market_context
from tests.risk.helpers import CFG, NOW, H, account, engine, failed, market, plan

EV = {"name": "Producer Price Index", "t_utc": NOW + 600_000, "impact": "medio"}


def cal(**metrics) -> AgentReport:
    return AgentReport(agent_id="calendar", version="1", asof=NOW, bias=0.0, confidence=0.9,
                       horizon_bars=1, metrics=metrics)


def test_market_context_window_without_blackout():
    m = market_context([cal(window="pre", window_event=EV, blackout=False)], NOW - H, NOW, H)
    assert m.event_window and not m.blackout
    assert "Producer Price Index" in m.event_reason and "medio" in m.event_reason


def test_market_context_blackout_is_not_a_size_window():
    m = market_context([cal(window="pre", window_event=EV, blackout=True,
                            blackout_reason="ventana pre-evento")], NOW - H, NOW, H)
    assert m.blackout and not m.event_window


def test_window_halves_the_size_with_risk_v2():
    eng, _, _ = engine()
    full = eng.evaluate(plan(), account(), market())
    half = eng.evaluate(plan(), account(), market(event_window=True,
                                                  event_reason="ventana pre-evento: IPP"))
    assert CFG.event_size_factor == 0.5
    assert full.approved and half.approved and not failed(half)
    assert half.size == pytest.approx(full.size * 0.5)
    assert half.risk_frac == pytest.approx(CFG.risk_per_trade * 0.5)
    assert any("×0.50" in r and "IPP" in r for r in half.reasons)


def test_blackout_vetoes_regardless_of_window():
    eng, _, _ = engine()
    d = eng.evaluate(plan(), account(), market(blackout=True, blackout_reason="FOMC"))
    assert not d.approved and failed(d) == {"evento"}


def test_risk_v1_keeps_full_size_in_window():
    v1 = load_config(version="risk_v1")
    eng, _, _ = engine(v1)
    full = eng.evaluate(plan(), account(), market())
    win = eng.evaluate(plan(), account(), market(event_window=True))
    assert win.size == pytest.approx(full.size)


# --- T36-1: ventanas evaluadas a la hora real de la decisión ------------------------------
def _win(start, end, blackout, name="Consumer Price Index", impact="alto"):
    return {"id": "x", "name": name, "impact": impact, "start": start, "end": end,
            "blackout": blackout, "basis": "test"}


def test_blackout_window_that_opens_after_the_close_is_seen_at_decision_time():
    r = cal(window=None, blackout=False,
            risk_windows=[_win(NOW - 60_000, NOW + 30 * 60_000, True)])
    m = market_context([r], NOW - 5 * 60_000, NOW, H)
    assert m.blackout and "a la hora de decidir" in m.blackout_reason
    assert not market_context([r], NOW - 5 * 60_000, NOW - 2 * 60_000, H).blackout


def test_size_window_at_decision_time_and_no_data_calendar_is_ignored():
    r = cal(risk_windows=[_win(NOW - 60_000, NOW + 60_000, False, "PPI", "medio")])
    m = market_context([r], NOW - H, NOW, H)
    assert m.event_window and not m.blackout and "PPI" in m.event_reason
    nod = AgentReport(agent_id="calendar", version="1", asof=NOW, bias=0, confidence=0,
                      horizon_bars=1, status="no_data", metrics={"blackout": True})
    assert not market_context([nod], NOW - H, NOW, H).blackout


def test_blackout_seen_at_close_is_not_lifted_by_finished_window():
    r = cal(blackout=True, blackout_reason="ventana pre-evento FOMC",
            risk_windows=[_win(NOW - H, NOW - 1, True, "FOMC")])
    m = market_context([r], NOW - H, NOW, H)
    assert m.blackout and m.blackout_reason == "ventana pre-evento FOMC"
