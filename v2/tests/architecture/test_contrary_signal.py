"""T114 · Una señal contraria no cierra una posición cuya regla de salida exige mantenerla.

Lo que T109 prohíbe en el bróker, medido aquí para todas las fuentes. Ninguna fuente puede
pedir un cierre (`TradeProposal` no tiene campo para eso): cada posición sale solo por la regla
de salida que se le concedió (`authority.EXIT_RULES`) o por una salvaguarda.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from eim.core import TradeProposal
from eim.paper.ladder_audit import ALLOWED_CLOSE
from eim.risk import authority
from tests.copytrading.copy_helpers import engine as copy_engine
from tests.copytrading.copy_helpers import feed
from tests.copytrading.helpers import T0 as CT0
from tests.execution.helpers import SYM, rig
from tests.execution.test_arb_runner import _pilot
from tests.paper.helpers import tp_mode
from tests.paper.test_ladder_stop_only_book import E, P, book, btc, mirror
from tests.risk.helpers import account, decide, market, plan


def test_no_exit_rule_accepts_a_contrary_signal():
    assert authority.CONTRARY_SIGNAL
    for mode, allowed in authority.EXIT_RULES.items():
        assert not any("señal" in a or "agente" in a.lower() for a in allowed), mode
    # la escalera del bróker y el registro dicen lo mismo (T109)
    assert set(ALLOWED_CLOSE) == set(authority.EXIT_RULES["stop_only"])


def test_a_proposal_has_no_way_to_ask_for_a_close():
    fields = set(TradeProposal.model_fields)
    assert not fields & {"close", "reduce", "qty", "size", "quantity", "leverage", "api_key"}
    with pytest.raises(ValidationError):
        TradeProposal(proposal_id="x", source="agents.plan", source_version="1", symbol="BTCUSDT",
                      side=-1, timeframe="1h", entry=1.0, data_asof=0, expires_at=1, close=True)


# --- bróker simulado: escalera y modo «tp» -------------------------------------------------
ROWS = [(E, E + 50, E - 20, E + 30)] + [(E + 30, E + 60, E + 10, E + 40)] * 8


@pytest.mark.parametrize("exit_mode", ["ladder", "tp"])
@pytest.mark.parametrize("side", [1, -1])
def test_paper_contrary_idea_does_not_close_the_open_position(exit_mode, side):
    p = P["moderado"] if exit_mode == "ladder" else tp_mode(P["moderado"])
    a = btc(side, strategy="a")
    b = replace(btc(-side, t=a.t + 3_600_000, strategy="b"), entry=mirror(ROWS, side).o[4])
    b = replace(b, sl=b.entry + side * 1400, tp=b.entry - side * 2200)
    alone = book("moderado", [a], ROWS, side, p=p)
    both = book("moderado", [a, b], ROWS, side, p=p)
    assert a.id in alone.slots and a.id in both.slots
    assert both.slots[a.id].o == alone.slots[a.id].o           # mismo camino y mismo stop
    assert not any(t["id"] == a.id for t in both.trades)


# --- plan de los agentes (testnet T30) -----------------------------------------------------
def test_agents_contrary_plan_is_vetoed_and_the_position_stays():
    r = rig()
    r.open()
    held = r.pos()
    contrary = plan(side=-1, sl=102_000.0, tp=(96_000.0, 94_000.0), plan_id="plan:2")
    d = decide(r.eng, contrary, account(open_symbols=(SYM,)), market(last_price=100_000.0))
    assert not d.approved and "operaciones abiertas" in {c.rule for c in d.checks if not c.ok}
    with pytest.raises(PermissionError):
        r.gw.submit(d, d.decided_at)
    assert r.pos() == held != 0


# --- copia de líderes -----------------------------------------------------------------------
def test_copy_signal_from_another_leader_neither_closes_nor_opens():
    e = copy_engine()
    feed(e, "BTC", 0.0, 4.0, 50_000.0, CT0 + 1_000, 1)
    held = e.account.size("BTC")
    out = feed(e, "BTC", 4.0, -4.0, 49_000.0, CT0 + 5_000, 2, lid="hyperliquid:0xotro")
    assert out == [] and e.account.size("BTC") == held > 0
    assert e.journal[-1].code == "ajena"
    (close,) = feed(e, "BTC", 4.0, 0.0, 50_100.0, CT0 + 9_000, 3)      # SU líder sí manda
    assert close.kind == "close" and e.account.size("BTC") == 0


# --- arbitraje ------------------------------------------------------------------------------
def test_arb_new_opportunities_do_not_touch_the_open_position(tmp_path):
    r, pilot, _ = _pilot(tmp_path)
    first = pilot.cycle()["opened"]
    pos = r.ex.positions[first]
    qty, status = pos.approved_qty, pos.status
    for _ in range(3):                      # el escáner sigue proponiendo: nada cambia lo abierto
        pilot.cycle(r.clock())
    assert r.ex.positions[first].status == status and r.ex.positions[first].approved_qty == qty


# --- bots -----------------------------------------------------------------------------------
def test_bot_stance_is_only_information():
    from tests.agents.bots.test_bots_agent import sig
    s = sig(stance=-1.0)
    with pytest.raises(ValidationError):
        type(s)(**{**s.model_dump(), "close": True})
    p = s.as_proposal(price=100.0, ttl_ms=60_000)
    assert p.source == "bots.squad" and p.side == -1
    assert authority.route_reason(p.source, "risk.engine") is not None
