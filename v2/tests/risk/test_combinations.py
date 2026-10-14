"""Combinaciones: todas las reglas se evalúan, el veto lista todos los motivos y nunca hay
tamaño sin aprobación."""

import itertools

import pytest

from eim.core import Mode
from tests.risk.helpers import CFG, NOW, account, engine, failed, market, plan

BREAKERS = {
    "kill-switch": ("kill", None),
    "modo": ("plan", {"mode": Mode.REAL}),
    "plan": ("plan", {"rr": 0.5}),
    "datos": ("market", {"last_close_t": None}),
    "evento": ("market", {"blackout": True}),
    "pérdida diaria": ("account", {"equity": 9_790.0, "week_start_equity": 9_790.0}),
    "operaciones abiertas": ("account", {"open_symbols": ("BTCUSDT",)}),
    "enfriamiento": ("account", {"consecutive_losses": 5, "last_loss_t": NOW}),
}


def _apply(combo):
    kw: dict = {"plan": {}, "account": {}, "market": {}}
    kill = False
    for rule in combo:
        target, changes = BREAKERS[rule]
        if target == "kill":
            kill = True
        else:
            kw[target].update(changes)
    return kw, kill


@pytest.mark.parametrize("combo", [c for n in (1, 2, 3) for c in
                                   itertools.combinations(sorted(BREAKERS), n)])
def test_every_combination_vetoes_with_all_reasons(combo):
    eng, sink, ks = engine()
    kw, kill = _apply(combo)
    if kill:
        ks.activate("prueba", NOW)
    d = eng.evaluate(plan(**kw["plan"]), account(**kw["account"]), market(**kw["market"]))
    assert not d.approved
    assert failed(d) == set(combo)
    assert d.size == d.notional == d.leverage == d.risk_amount == 0.0
    assert len(d.reasons) == len(combo)
    assert sink.decisions == [d]                           # siempre registrada


def test_all_breakers_at_once():
    eng, _, ks = engine()
    kw, _ = _apply(BREAKERS)
    ks.activate("todo", NOW)
    d = eng.evaluate(plan(**kw["plan"]), account(**kw["account"]), market(**kw["market"]))
    assert failed(d) == set(BREAKERS)


def test_deterministic():
    a, _, _ = engine()
    b, _, _ = engine()
    da = a.evaluate(plan(), account(), market())
    db = b.evaluate(plan(), account(), market())
    assert da.model_dump(exclude={"seal"}) == db.model_dump(exclude={"seal"})


def test_approved_decisions_logged_too():
    eng, sink, _ = engine()
    for eq in (10_000.0, 12_000.0):
        eng.evaluate(plan(), account(equity=eq, day_start_equity=eq, week_start_equity=eq,
                                     peak_equity=eq), market())
    assert [d.approved for d in sink.decisions] == [True, True]
    assert sink.decisions[1].risk_amount == pytest.approx(12_000 * CFG.risk_per_trade)
