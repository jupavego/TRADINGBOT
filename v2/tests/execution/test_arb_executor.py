"""Ejecutor de arbitraje (T45) contra el exchange simulado: dos patas, orden, unwind, fallos."""

import pytest

from eim.execution.arb_book import CLOSED, FAILED, OPEN, UNHEDGED
from eim.execution.arb_legs import ExecParams
from eim.execution.service import ExecutionError
from tests.execution.arb_helpers import PERP, QTR, SPOT, arb_rig

ORDER_S, ORDER_F = "/api/v3/order", "/fapi/v1/order"


def test_open_carry_is_hedged_on_both_exchanges():
    r = arb_rig()
    pos = r.open()
    assert pos.status == OPEN and pos.opened_at
    assert pos.spot.held == pytest.approx(0.01) and pos.fut.held == pytest.approx(-0.01)
    assert r.btc() == pytest.approx(0.01) and r.short() == pytest.approx(-0.01)
    assert r.net() == 0 and r.fv.leverage[PERP] == 3
    assert [o.role for o in pos.orders] == ["abrir", "cubrir"]
    assert all(o.cid.startswith("eia-") for o in pos.orders)   # T30 no las toca
    assert not r.kill.active


@pytest.mark.parametrize("thin, first", [(SPOT, "spot"), (PERP, "usdm")])
def test_less_liquid_leg_goes_first(thin, first):
    r = arb_rig()
    (r.sv if thin == SPOT and first == "spot" else r.fv).liquidity[thin] = 0.02
    pos = r.open()
    assert pos.orders[0].market == first and pos.status == OPEN


def test_same_decision_twice_is_idempotent():
    r = arb_rig()
    d = r.decision()
    k1 = r.gw.submit(d, r.clock())
    k2 = r.gw.submit(d, r.clock())
    assert k1 == k2 and len(r.ex.positions) == 1
    assert len(r.sh.posts(ORDER_S)) == 1 and len(r.fh.posts(ORDER_F)) == 1


def test_second_leg_rejected_unwinds_first_to_net_zero():
    r = arb_rig()
    r.sv.liquidity[SPOT] = 5.0                               # spot primero (menos líquido)
    r.fh.fault("POST", ORDER_F, "reject", times=5, code=-2019, msg="Margin is insufficient.")
    pos = r.open()
    assert pos.status == FAILED and "neta cero" in pos.exit_reason
    assert r.btc() == pytest.approx(0.0, abs=1e-9) and r.short() == 0
    assert [o.role for o in pos.orders][-1] == "deshacer"
    assert 0 <= pos.incident_loss <= pos.max_leg_loss and not r.kill.active
    with pytest.raises(ExecutionError, match="ya falló"):
        r.gw.submit(r.engine.evaluate(r.plan(arb_id=pos.arb_id), r.account(), r.clock()),
                    r.clock())


def test_first_leg_partial_hedges_only_what_filled():
    r = arb_rig()
    r.sv.liquidity[SPOT] = 0.006                             # solo hay 0,006 BTC en el libro
    pos = r.open()
    assert pos.orders[0].market == "spot"
    assert pos.status == OPEN and pos.hedged == pytest.approx(0.006)
    assert r.short() == pytest.approx(-0.006) and r.net() == 0


def test_second_leg_partial_unwinds_the_excess():
    r = arb_rig()
    r.sv.liquidity[SPOT] = 5.0                               # spot primero (menos líquido)
    r.fv.fill_cap[PERP] = 0.004                              # el futuro llena 0,004 …

    def dry(v, o):
        v.liquidity[PERP] = 0.0                              # … y su libro se agota
    r.fv.hooks.append(dry)
    pos = r.open()
    assert pos.orders[0].market == "spot"
    assert pos.status == OPEN and pos.hedged == pytest.approx(0.004)
    assert r.btc() == pytest.approx(0.004) and r.net() == pytest.approx(0.0, abs=1e-9)
    assert any(o.role == "deshacer" for o in pos.orders)


def test_empty_book_sends_nothing():
    r = arb_rig()
    r.fv.empty.add(PERP)
    pos = r.open()
    assert pos.status == FAILED and "libro vacío" in pos.exit_reason
    assert r.sh.posts(ORDER_S) == [] and r.fh.posts(ORDER_F) == []


def test_book_that_empties_after_first_leg_is_unwound():
    r = arb_rig()
    r.sv.liquidity[SPOT] = 5.0

    def vanish(v, o):
        if o["symbol"] == SPOT and o["side"] == "BUY":
            r.fv.empty.add(PERP)
    r.sv.hooks.append(vanish)
    pos = r.open()
    assert pos.status == FAILED and r.net() == pytest.approx(0.0, abs=1e-9)
    assert r.fh.posts(ORDER_F) == []


def test_unwind_beyond_loss_cap_goes_to_market_and_trips_kill_switch():
    r = arb_rig()
    r.sv.liquidity[SPOT] = 5.0

    def crash(v, o):
        if o["symbol"] == SPOT and o["side"] == "BUY" and o["status"] == "FILLED":
            v.mids[SPOT] *= 0.98                             # −2 %: más que el tope de 50 pb
    r.sv.hooks.append(crash)
    r.fh.fault("POST", ORDER_F, "reject", times=5, code=-2019, msg="Margin is insufficient.")
    pos = r.open()
    assert pos.status == FAILED and r.btc() == pytest.approx(0.0, abs=1e-9)
    assert [o.role for o in pos.orders][-2:] == ["deshacer", "deshacer mercado"]
    assert pos.incident_loss > pos.max_leg_loss
    assert r.kill.active and "tope" in r.kill.state()["reason"]


def test_lost_response_on_second_leg_is_not_duplicated():
    r = arb_rig()
    r.fh.fault("POST", ORDER_F, "after")                     # llega, pero la respuesta se pierde
    pos = r.open()
    assert pos.status == OPEN and len(r.fh.posts(ORDER_F)) == 1 and r.net() == 0


def test_spot_fee_in_base_leaves_only_dust():
    r = arb_rig(fee_rate=0.001, fee_in_base=True)
    r.sv.liquidity[SPOT] = 5.0                               # spot primero: recibe 0,00999
    pos = r.open()
    assert pos.status == OPEN and r.short() == pytest.approx(-0.01)
    assert pos.spot.held == pytest.approx(0.00999)
    assert abs(pos.residual) <= ExecParams().hedge_tol * 0.01


def test_kill_switch_blocks_new_arbitrage():
    r = arb_rig()
    d = r.decision()
    r.kill.activate("prueba", r.clock())
    with pytest.raises(PermissionError, match="kill-switch"):
        r.gw.submit(d, r.clock())
    assert r.ex.positions == {}


def test_close_both_legs():
    r = arb_rig()
    pos = r.open()
    assert r.ex.close(pos, "prueba")
    assert pos.status == CLOSED and r.net() == 0 and r.short() == 0
    assert r.btc() == pytest.approx(0.0, abs=1e-9)


def test_close_with_second_book_empty_redoes_first_and_stays_hedged():
    r = arb_rig()
    pos = r.open()
    first = pos.order[0]

    def vanish(v, o):
        if o["clientOrderId"].split("-")[-1].startswith("c"):
            (r.fv if first == "spot" else r.sv).empty.add(PERP if first == "spot" else SPOT)
    (r.sv if first == "spot" else r.fv).hooks.append(vanish)
    assert not r.ex.close(pos, "rentabilidad agotada")
    assert pos.status == OPEN and pos.hedged == pytest.approx(0.01) and r.net() == 0


def test_partial_close_stays_hedged_and_retries():
    r = arb_rig()
    pos = r.open()
    r.fv.liquidity[PERP] = 0.004                             # futuros, ahora el menos líquido
    assert not r.ex.close(pos, "kill-switch", urgent=True)
    assert pos.status == OPEN and pos.hedged == pytest.approx(0.006) and r.net() == 0
    r.fv.liquidity.pop(PERP)
    assert r.ex.close(pos, "kill-switch", urgent=True) and pos.status == CLOSED


def test_urgent_close_never_undoes_and_reconciliation_finishes():
    r = arb_rig(params=ExecParams(chase_tries=0))
    pos = r.open()
    r.sv.liquidity[SPOT] = 0.02                              # spot primero
    r.fv.fill_cap[PERP] = 0.004                              # el futuro llena a cuentagotas
    assert not r.ex.close(pos, "kill-switch", urgent=True)
    roles = [(o.role, o.market) for o in pos.orders[2:]]
    assert roles == [("cerrar", "spot"), ("cerrar", "usdm"), ("mercado", "usdm")]
    assert pos.status == UNHEDGED and pos.fut.held == pytest.approx(-0.002)
    r.recon.run(r.clock())                                   # recompra el corto que sobra
    assert pos.status == CLOSED and r.net() == 0 and r.short() == 0


def test_basis_on_quarterly():
    r = arb_rig()
    pos = r.open(fut=QTR, strategy="basis", variant="largo spot / corto trimestral",
                 delivery_t=r.clock() + 70 * 86_400_000, funding_rate=None)
    assert pos.status == OPEN and r.short(QTR) == pytest.approx(-0.01)


def test_futures_min_notional_checked_before_any_order():
    r = arb_rig()
    pos = r.open(qty=0.0009)                                 # ~90 USD < 100 USDT de futuros
    assert pos.status == FAILED and "mínimo" in pos.exit_reason
    assert r.sh.posts(ORDER_S) == [] and r.fh.posts(ORDER_F) == []


def test_urgent_close_pushes_first_leg_to_market():
    r = arb_rig()
    pos = r.open()
    r.sv.liquidity[SPOT] = 0.02                              # spot primero
    r.sv.fill_cap[SPOT] = 0.004                              # la LIMIT solo llena 0,004
    r.sv.hooks.append(lambda v, o: v.fill_cap.pop(SPOT, None))
    assert r.ex.close(pos, "kill-switch", urgent=True)
    assert pos.status == CLOSED and r.net() == 0
    assert ("mercado", "spot") in [(o.role, o.market) for o in pos.orders]
