"""Reconciliación: divergencia → kill-switch y cierre; SL perdido → reposición; huérfanas."""

import pytest

from eim.execution.broker import MARKET, STOP, OrderSpec, client_id
from eim.execution.reconcile import drift_of
from eim.execution.service import CLOSED
from tests.execution.helpers import SYM, rig
from tests.risk.helpers import CFG, NOW


def test_drift_definition():
    assert drift_of(0, 0) == 0 and drift_of(0.02, 0) == 1 and drift_of(0, 0.01) == 1
    assert drift_of(0.02, 0.019) == pytest.approx(0.05)


def test_divergence_activates_kill_switch_and_flattens():
    r = rig()
    tr = r.svc.trades[r.open()]
    r.fx.sim.post_order(OrderSpec("manual-1", SYM, 1, MARKET, qty=0.01))   # mano ajena
    rep = r.recon.run((SYM,), NOW)
    assert not rep.ok and rep.kill and r.ks.active
    assert "reconciliación" in r.ks.state()["reason"]
    assert r.pos() == 0 and r.orders() == [] and tr.status == CLOSED
    d = r.decision(plan_id="plan:2")
    assert not d.approved and any("kill-switch" in x for x in d.reasons)


def test_lost_stop_is_replaced():
    r = rig()
    tr = r.svc.trades[r.open()]
    r.fx.sim.cancel(SYM, tr.cid("s"), True)          # el SL desaparece del exchange
    rep = r.recon.run((SYM,), NOW)
    assert any("sin SL" in i for i in rep.issues) and not r.ks.active
    sl = [o for o in r.orders() if o.kind == STOP]
    assert [o.client_id for o in sl] == [tr.cid("s2")] and sl[0].trigger == 98_000
    assert r.recon.run((SYM,), NOW).ok
    r.fx.sim.set_price(SYM, 97_000.0)
    r.recon.run((SYM,), NOW)
    assert r.pos() == 0 and tr.status == CLOSED and r.orders() == []


def test_stop_beyond_price_closes_at_market():
    r = rig()
    tr = r.svc.trades[r.open()]
    r.fx.sim.cancel(SYM, tr.cid("s"), True)
    r.fx.sim._px[SYM] = 97_500.0                      # el precio ya cruzó el SL (sin casar)
    r.recon.run((SYM,), NOW)
    assert r.pos() == 0 and tr.status == CLOSED


def test_unknown_position_without_stop_is_closed():
    r = rig()
    r.fx.sim.post_order(OrderSpec("manual-1", SYM, -1, MARKET, qty=0.01))
    rep = r.recon.run((SYM,), NOW)
    assert r.pos() == 0 and r.ks.active and rep.actions


def test_orphan_orders_cancelled():
    r = rig()
    orphan = client_id("plan:viejo", SYM, "s")
    r.fx.sim.post_order(OrderSpec(orphan, SYM, -1, STOP, trigger=90_000, close_position=True))
    r.fx.sim.post_order(OrderSpec("ajena-1", SYM, -1, STOP, trigger=90_000,
                                  close_position=True))
    rep = r.recon.run((SYM,), NOW)
    assert [o.client_id for o in r.orders()] == ["ajena-1"]    # solo toca las suyas
    assert any(orphan in a for a in rep.actions)


def test_disconnection_triggers_kill_after_threshold():
    r = rig()
    r.open()
    assert r.recon.run((SYM,), NOW).ok
    r.fx.down = True
    rep = r.recon.run((SYM,), NOW + 60_000)
    assert not rep.ok and not r.ks.active             # corte corto: aún no
    rep = r.recon.run((SYM,), NOW + CFG.kill_max_disconnect_ms)
    assert r.ks.active and "desconectado" in r.ks.state()["reason"]
    assert r.pos() == 0.025 and any(o.kind == STOP for o in r.orders())   # SL sigue en el exchange
    r.fx.down = False
    rep = r.recon.run((SYM,), NOW + CFG.kill_max_disconnect_ms + 1)
    assert r.pos() == 0 and r.orders() == []          # al volver la red: cierre ordenado


def test_entry_never_reached_exchange_is_failed():
    r = rig()
    r.fx.fault("POST", "/fapi/v1/order", "before", times=99)
    r.fx.fault("GET", "/fapi/v1/order", "before", times=4)    # consultas sin respuesta firme
    tr = r.svc.trades[r.open()]
    r.fx.faults.clear()
    r.recon.run((SYM,), NOW)
    assert tr.status == "FALLIDA" and r.orders() == [] and r.pos() == 0


def test_disconnected_from_first_pass_still_triggers_kill():
    r = rig()
    r.fx.down = True
    r.recon.run((SYM,), NOW)                          # primer contacto ya falla
    r.recon.run((SYM,), NOW + CFG.kill_max_disconnect_ms)
    assert r.ks.active and "desconectado" in r.ks.state()["reason"]


def test_fill_between_reads_is_not_divergence():
    r = rig(fill_cap=0.01)
    tr = r.svc.trades[r.open()]
    real = r.broker.position
    calls = {"n": 0}

    def racing(symbol):                               # un fill llega justo antes de leer
        calls["n"] += 1
        if calls["n"] == 1:
            r.fx.sim.set_price(SYM, 100_000.0)
        return real(symbol)

    r.broker.position = racing
    rep = r.recon.run((SYM,), NOW)
    assert not r.ks.active and rep.ok and tr.filled == 0.02
