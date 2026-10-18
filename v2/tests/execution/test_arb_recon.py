"""Reconciliación del arbitraje (T45): cortes de red, desconexión, liquidación y funding."""

import pytest

from eim.execution.arb_book import CLOSED, FAILED, GONE, OPEN, UNHEDGED
from eim.execution.reconcile import Reconciler
from eim.execution.service import ExecutionService
from tests.execution.arb_helpers import CFG, PERP, SPOT, arb_rig

ORDER_F = "/fapi/v1/order"
MIN = 60_000


def _faults(r, mode: str) -> None:
    """Spot primero; después falla la red de futuros de tres formas distintas."""
    r.sv.liquidity[SPOT] = 5.0
    if mode == "cut":                                         # cae justo tras comprar spot

        def cut(v, o):
            if o["side"] == "BUY":
                r.fh.down = True
        r.sv.hooks.append(cut)
    elif mode == "never":                                     # la orden nunca llega
        r.fh.fault("POST", ORDER_F, "before", times=50)
    else:                                                     # llega y se llena, sin respuesta
        r.fh.fault("POST", ORDER_F, "after")
        r.fh.fault("GET", ORDER_F, "before", times=50)


@pytest.mark.parametrize("mode", ["cut", "never", "after"])
def test_network_cut_mid_open_leaves_no_orphan(mode):
    r = arb_rig()
    _faults(r, mode)
    pos = r.open()
    assert pos.status == UNHEDGED and r.btc() == pytest.approx(0.01)
    r.fh.down = False
    r.fh.faults.clear()
    rep = r.recon.run(r.clock() + MIN)
    if mode == "after":                                       # llegó: se adopta, queda cubierta
        assert pos.status == OPEN and r.short() == pytest.approx(-0.01)
    else:                                                     # sin futuros: se vende el spot
        assert pos.status == FAILED and r.btc() == pytest.approx(0.0, abs=1e-9)
        assert pos.orders[-1].role == "recortar" and r.short() == 0
    if mode == "never":
        assert pos.orders[1].status == GONE
        assert any("nunca llegó" in a for a in rep.actions)
    assert r.net() == pytest.approx(0.0, abs=1e-9) and not r.kill.active


def test_disconnection_with_open_position_trips_kill_and_flattens():
    r = arb_rig()
    pos = r.open()
    t0 = r.clock()
    assert r.recon.run(t0).ok
    r.fh.down = r.sh.down = True
    assert not r.recon.run(t0 + MIN).connected and not r.kill.active
    r.recon.run(t0 + CFG.kill_max_disconnect_ms + MIN)
    assert r.kill.active and "desconectado" in r.kill.state()["reason"]
    assert pos.status == OPEN                                 # sin red no se toca nada
    r.fh.down = r.sh.down = False
    rep = r.recon.run(t0 + CFG.kill_max_disconnect_ms + 2 * MIN)
    assert pos.status == CLOSED and r.net() == 0 and r.short() == 0
    assert any("kill-switch" in a for a in rep.actions)


def test_external_liquidation_is_adopted_and_spot_sold():
    r = arb_rig()
    pos = r.open()
    r.fv.pos[PERP] = [0.0, 0.0, 0.0]                          # el corto desaparece (liquidado)
    rep = r.recon.run(r.clock())
    assert any("exchange" in i for i in rep.issues)
    assert pos.status == CLOSED and r.btc() == pytest.approx(0.0, abs=1e-9)


def test_tracks_margin_liquidation_and_real_vs_expected_funding():
    r = arb_rig()
    pos = r.open()
    t_open = pos.opened_at
    r.fv.income += [{"symbol": PERP, "time": t_open + h * 3_600_000, "income": "0.10",
                     "incomeType": "FUNDING_FEE"} for h in (1, 9)]
    r.recon.run(t_open + 17 * 3_600_000)                       # cruza 2 liquidaciones de 8 h
    assert pos.funding_received == pytest.approx(0.20) and pos.funding_n == 2
    expected = 1e-4 * 0.01 * r.fv.mids[PERP] * 2
    assert pos.funding_expected == pytest.approx(expected, rel=1e-6)
    assert pos.liq_price > r.fv.mids[PERP] and 0.3 < pos.liq_move < 0.34   # ×3 aislado
    assert pos.margin_equity == pytest.approx(0.01 * r.fv.mids[PERP] / 3, rel=0.01)


def test_spot_sold_outside_is_adopted():
    r = arb_rig()
    pos = r.open()
    r.sv.balances["BTC"] -= 0.004                             # alguien vendió spot fuera
    r.recon.run(r.clock())
    assert pos.status == OPEN and pos.hedged == pytest.approx(0.006)
    assert r.short() == pytest.approx(-0.006)


def test_directional_reconciler_respects_arbitrage_futures():
    """T30 no cierra la pata de futuros de un arbitraje como «posición desconocida sin SL»."""
    r = arb_rig()
    r.open()
    svc = ExecutionService(r.fut, r.kill, sleep=lambda _: None, clock=r.clock)
    from tests.risk.helpers import CFG as RISK
    plain = Reconciler(svc, RISK, external=r.ex.futures_qty).run((PERP,), r.clock())
    assert plain.ok and r.short() == pytest.approx(-0.01)
    r.kill.activate("prueba", r.clock())
    Reconciler(svc, RISK, external=r.ex.futures_qty).run((PERP,), r.clock())
    assert r.short() == pytest.approx(-0.01)                  # la cierra su ejecutor, no T30
    r.recon.run(r.clock())
    assert r.short() == 0 and r.net() == 0
