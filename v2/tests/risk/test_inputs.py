"""Entradas del motor: plan desde reporte, cuenta desde el libro simulado, contexto de mercado."""

import pytest

from eim.core import AgentReport, Mode, Overlay
from eim.execution.sim_ledger import Trade
from eim.risk.inputs import DAY_MS, _week0, account_from_trades, market_context, plan_request

H = 3_600_000
MON = 1_760_313_600_000          # 2025-10-13 00:00 UTC, lunes


def _plan_report(status="VIGENTE", side="long"):
    geom = {"side": side, "entry": 100.0, "sl": 98.0, "tp": [104.0], "rr": 2.0,
            "mode": "ANALISIS", "status": status}
    ov = Overlay(id="plan:7", agent_id="plan", kind="trade_plan", t_from=0, geometry=geom,
                 label="Plan", confidence=0.5)
    return AgentReport(agent_id="plan", version="1", asof=123, bias=0.5, confidence=0.5,
                       horizon_bars=10, metrics={"plan": geom}, overlays=[ov])


def test_plan_request_from_report():
    req = plan_request(_plan_report(), "ETHUSDT", "1h")
    assert req is not None
    assert (req.side, req.entry, req.sl, req.tp, req.plan_id, req.asof) == \
        (1, 100.0, 98.0, (104.0,), "plan:7", 123)
    assert req.mode == Mode.SIMULADO
    assert plan_request(_plan_report(side="short"), "ETHUSDT", "1h").side == -1


@pytest.mark.parametrize("status", ["INVALIDADO", "CUMPLIDO", "EXPIRADO"])
def test_resolved_plan_not_sized(status):
    assert plan_request(_plan_report(status), "ETHUSDT", "1h") is None


def test_week_starts_monday():
    assert _week0(MON + 3 * DAY_MS + 5 * H) == MON
    assert _week0(MON) == MON


def _tr(i, r, entry_t, exit_t, symbol="BTCUSDT"):
    return Trade(id=str(i), symbol=symbol, timeframe="1h", plan_id=str(i), side=1,
                 entry_t=entry_t, entry=100.0, sl0=98.0, tp1=104.0, tp2=None,
                 status="SL" if r is not None and r < 0 else ("ABIERTA" if r is None else "TP1"),
                 exit_t=exit_t, r=r)


def test_account_equity_day_week_streak():
    now = MON + 2 * DAY_MS + 12 * H                     # miércoles 12:00
    trades = [
        _tr(1, 2.0, MON - 3 * DAY_MS, MON - 2 * DAY_MS),   # semana anterior: +1 %
        _tr(2, -1.0, MON + H, MON + 2 * H),                # lunes: −0.5 %
        _tr(3, -1.0, MON + 2 * DAY_MS, MON + 2 * DAY_MS + 2 * H),   # miércoles: −0.5 %
        _tr(4, -1.0, MON + 2 * DAY_MS + 3 * H, MON + 2 * DAY_MS + 5 * H),
        _tr(5, None, MON + 2 * DAY_MS + 6 * H, None, "ETHUSDT"),     # abierta
        _tr(6, 1.0, MON + 2 * DAY_MS + 11 * H, MON + 2 * DAY_MS + 12 * H),  # aún no cerró
    ]
    a = account_from_trades(trades, 10_000.0, 0.005, now, H, "test")
    e1 = 10_000 * 1.01
    assert a.week_start_equity == pytest.approx(e1)
    assert a.day_start_equity == pytest.approx(e1 * 0.995)
    assert a.equity == pytest.approx(e1 * 0.995 ** 3)
    assert a.peak_equity == pytest.approx(e1)
    assert a.consecutive_losses == 3 and a.last_loss_t == MON + 2 * DAY_MS + 6 * H
    assert a.open_symbols == ("ETHUSDT", "BTCUSDT")


def test_account_without_trades():
    a = account_from_trades([], 10_000.0, 0.005, MON, H, "test")
    assert a.equity == a.day_start_equity == a.week_start_equity == 10_000.0
    assert a.open_symbols == () and a.consecutive_losses == 0


def _rep(agent, status="ok", **metrics):
    return AgentReport(agent_id=agent, version="1", asof=1, bias=0, confidence=0,
                       horizon_bars=1, metrics=metrics, status=status)


def test_market_context_events_and_status():
    m = market_context([_rep("structure"), _rep("levels", "degraded"),
                        _rep("calendar", blackout=True, blackout_reason="CPI"),
                        _rep("context", event_pause=True, event_risk="alto")], 10, 20, H)
    assert m.agent_status == {"structure": "ok", "levels": "degraded", "calendar": "ok",
                              "context": "ok"}
    assert m.blackout and m.blackout_reason == "CPI"
    assert m.event_pause and "alto" in m.pause_reason


def test_market_context_no_events():
    m = market_context([_rep("context", event_pause=False)], 10, 20, H)
    assert not m.blackout and not m.event_pause
