"""Cada regla por separado: la entrada base aprueba y solo cambia lo que se prueba."""

import pytest

from eim.core import Mode
from tests.risk.helpers import CFG, NOW, H, account, engine, failed, market, plan


def run(p=None, a=None, m=None):
    eng, _, _ = engine()
    return eng.evaluate(p or plan(), a or account(), m or market())


def test_base_case_approved():
    d = run()
    assert d.approved and d.size > 0 and not failed(d)
    assert d.risk_frac == pytest.approx(CFG.risk_per_trade)
    assert d.config_version == CFG.version and d.config_sha256 == CFG.sha256


@pytest.mark.parametrize("kw,needle", [
    ({"side": 0}, "sin lado"),
    ({"sl": 101_000.0}, "SL del lado equivocado"),
    ({"tp": (99_000.0,)}, "TP del lado equivocado"),
    ({"sl": 99_950.0}, "ruido"),
    ({"sl": 90_000.0, "tp": (130_000.0,), "rr": 3.0}, "SL a 10.00%"),
    ({"rr": 1.2}, "R:R 1.20"),
    ({"rr": None, "tp": (101_000.0,)}, "R:R 0.50"),
    ({"entry": float("nan")}, "no finitos"),
])
def test_plan_geometry(kw, needle):
    d = run(p=plan(**kw))
    assert not d.approved and failed(d) == {"plan"}
    assert any(needle in r for r in d.reasons)


def test_short_mirror_ok():
    d = run(p=plan(side=-1, sl=102_000.0, tp=(96_000.0,)))
    assert d.approved and d.side == -1
    assert d.liquidation_price > 102_000.0


def test_mode_real_vetoed():
    d = run(p=plan(mode=Mode.REAL))
    assert not d.approved and "modo" in failed(d)


@pytest.mark.parametrize("mode", [Mode.ANALISIS, Mode.SIMULADO, Mode.TESTNET])
def test_allowed_modes(mode):
    assert run(p=plan(mode=mode)).approved


def test_daily_loss_limit():
    assert run(a=account(equity=9_801.0)).approved                    # −1.99 %
    d = run(a=account(equity=9_800.0))                                # −2.00 %
    assert not d.approved and failed(d) == {"pérdida diaria"}


def test_weekly_loss_limit():
    d = run(a=account(equity=9_500.0, day_start_equity=9_500.0, week_start_equity=10_000.0))
    assert not d.approved and failed(d) == {"pérdida semanal"}


def test_max_open_trades_and_per_symbol():
    assert run(a=account(open_symbols=("ETHUSDT",))).approved
    d = run(a=account(open_symbols=("ETHUSDT", "ETHUSDT")))
    assert failed(d) == {"operaciones abiertas"} and "máx. 2" in d.reasons[0]
    d = run(a=account(open_symbols=("BTCUSDT",)))
    assert failed(d) == {"operaciones abiertas"} and "en BTCUSDT" in d.reasons[0]


def test_cooldown_after_consecutive_losses():
    n = CFG.max_consecutive_losses
    assert run(a=account(consecutive_losses=n - 1, last_loss_t=NOW)).approved
    d = run(a=account(consecutive_losses=n, last_loss_t=NOW - H))
    assert failed(d) == {"enfriamiento"} and "pausa" in d.reasons[0]
    later = account(consecutive_losses=n, last_loss_t=NOW - CFG.cooldown_ms)
    assert run(a=later).approved


@pytest.mark.parametrize("kw,needle", [
    ({"blackout": True, "blackout_reason": "FOMC 18:00 UTC"}, "FOMC"),
    ({"event_pause": True}, "contexto"),
])
def test_event_windows(kw, needle):
    d = run(m=market(**kw))
    assert failed(d) == {"evento"} and needle in d.reasons[0]


def test_context_cannot_lift_calendar_blackout():
    assert not run(m=market(blackout=True, event_pause=False)).approved


@pytest.mark.parametrize("kw,needle", [
    ({"last_close_t": None}, "sin velas"),
    ({"last_close_t": NOW - 3 * H}, "obsoletos"),
    ({"agent_status": {"structure": "ok", "levels": "degraded", "plan": "ok"}}, "críticos"),
    ({"agent_status": {"structure": "ok", "levels": "ok"}}, "plan"),
    ({"agent_status": {"structure": "ok", "levels": "ok", "plan": "ok", "vwap": "degraded",
                       "ema": "degraded"}}, "2 agentes degradados"),
])
def test_data_quality(kw, needle):
    d = run(m=market(**kw))
    assert failed(d) == {"datos"} and needle in d.reasons[0]


def test_one_degraded_non_critical_tolerated():
    st = {"structure": "ok", "levels": "ok", "plan": "ok", "vwap": "degraded"}
    assert run(m=market(agent_status=st)).approved


def test_zero_equity_vetoed():
    d = run(a=account(equity=0.0, day_start_equity=0.0, week_start_equity=0.0))
    assert not d.approved and d.size == 0
