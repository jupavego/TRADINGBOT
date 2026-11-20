"""Balance de la cantera (2026-11-20): ganadas frente a perdidas y capital por agente."""

from __future__ import annotations

from types import SimpleNamespace as NS

from fastapi import FastAPI
from fastapi.testclient import TestClient

from eim.api.nursery import OFF, build_nursery_router
from eim.nursery.balance import WINDOWS, stats
from tests.nursery.test_panel_t171 import desk  # noqa: F401 — fixture compartida


def _e(pnl: float, r: float, reason: str = "SL") -> NS:
    return NS(pnl_usd=pnl, qty=1.0, trade=NS(r=r, reason=reason, fill=100.0, cost=0.001))


def test_stats_split_wins_and_losses_like_the_broker():
    s = stats([_e(30, 0.3, "SLD"), _e(10, 0.1, "SLD"), _e(-50, -1.0), _e(0.0, 0.0)])
    assert s["n"] == 4 and s["wins"]["n"] == 2 and s["losses"]["n"] == 2   # 0 cuenta como perdida
    assert s["win_rate"] == 0.5 and s["net"] == -10.0
    assert s["payoff"] == round(20 / 25, 3) and s["breakeven"] == round(1 / 1.8, 4)
    assert s["pf"] == round(40 / 50, 3) and s["costs"] == 0.4
    assert s["wins"]["by_reason"] == {"SLD": 2}


def test_stats_without_trades_says_nothing():
    s = stats([])
    assert s["n"] == 0 and s["win_rate"] is None and s["breakeven"] is None and s["pf"] is None


def test_balance_travels_in_the_nursery_payload(desk):  # noqa: F811
    b = desk.summary()["balance"]
    assert set(b["windows"]) == {k for k, _, _ in WINDOWS}
    todo = b["windows"]["todo"]["all"]
    book = desk._book
    prospects = {a.id for a in book.accounts if a.kind == "prospecto"}
    closed = [e for e in book.entries if e.account in prospects and e.booked
              and e.trade.status == "CERRADA"]
    assert todo["n"] == len(closed) and todo["wins"]["n"] + todo["losses"]["n"] == todo["n"]
    assert abs(todo["net"] - round(sum(e.pnl_usd for e in closed), 2)) < 0.05
    # el capital de cada agente es la suma de las cuentas de sus prospectos
    for a in b["agents"]:
        accs = [x for x in book.accounts if x.kind == "prospecto" and x.agent_id == a["agent_id"]]
        assert a["accounts"] == len(accs)
        assert abs(a["equity"] - sum(book.balance(x.id) for x in accs)) < 0.05
        assert a["curve"][0]["pct"] == 0.0 and a["curve"][-1]["equity"] == a["equity"]
    app = FastAPI()
    app.include_router(build_nursery_router(desk))
    assert "balance" in TestClient(app).get("/v2/nursery").json()


def test_off_message_does_not_say_t170_is_pending():
    app = FastAPI()
    app.include_router(build_nursery_router(None))
    j = TestClient(app).get("/v2/nursery").json()
    assert j == OFF and j["enabled"] is False and "se enciende en T170" not in j["reason"]
    assert "juanpablo-cpu" in j["reason"]
