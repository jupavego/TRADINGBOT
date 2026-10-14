"""Fábricas de entradas válidas para el motor de riesgo (cada test cambia solo lo que prueba)."""

from __future__ import annotations

from eim.core import Mode
from eim.risk import (
    AccountState,
    KillSwitch,
    MarketContext,
    MemorySink,
    PlanRequest,
    RiskEngine,
    load_config,
)

H = 3_600_000
NOW = 1_760_000_000_000 // H * H + 5 * 60_000      # 5 min tras el cierre de una vela 1h
CFG = load_config()
OK_AGENTS = {"structure": "ok", "levels": "ok", "plan": "ok", "vwap": "ok"}


def plan(**kw) -> PlanRequest:
    base = dict(symbol="BTCUSDT", timeframe="1h", plan_id="plan:1", side=1, entry=100_000.0,
                sl=98_000.0, tp=(104_000.0, 106_000.0), rr=2.0, mode=Mode.SIMULADO,
                asof=NOW - 5 * 60_000)
    return PlanRequest(**{**base, **kw})


def account(**kw) -> AccountState:
    base = dict(equity=10_000.0, day_start_equity=10_000.0, week_start_equity=10_000.0,
                peak_equity=10_000.0, source="test")
    return AccountState(**{**base, **kw})


def market(**kw) -> MarketContext:
    base = dict(now=NOW, bar_ms=H, last_close_t=NOW - 5 * 60_000, agent_status=OK_AGENTS)
    return MarketContext(**{**base, **kw})


def engine(cfg=CFG) -> tuple[RiskEngine, MemorySink, KillSwitch]:
    sink, ks = MemorySink(), KillSwitch()
    return RiskEngine(cfg, sink, ks), sink, ks


def failed(decision) -> set[str]:
    return {c.rule for c in decision.checks if not c.ok}
