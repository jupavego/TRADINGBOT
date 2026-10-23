"""Broker de testnet contra el exchange simulado: flujo completo, seguridad y fallos."""

import pytest

from eim.execution.binance_testnet import (
    ENV_KEY,
    ENV_SECRET,
    BinanceTestnetBroker,
    Credentials,
)
from eim.execution.broker import STOP, TAKE_PROFIT, BrokerError, OrderRejected
from eim.execution.service import CLOSED, FAILED, OPEN, PENDING, ExecutionError
from tests.execution.fake_binance import KEY, SECRET, FakeBinance
from tests.execution.helpers import PX, SYM, rig
from tests.risk.helpers import NOW, decide, plan

ORDER, ALGO = "/fapi/v1/order", "/fapi/v1/algoOrder"


# --- seguridad ----------------------------------------------------------------
@pytest.mark.parametrize("url", ["https://fapi.binance.com", "http://testnet.binancefuture.com",
                                 "https://testnet.binancefuture.com.evil.io"])
def test_non_testnet_host_blocked(url):
    with pytest.raises(BrokerError, match="bloqueado"):
        BinanceTestnetBroker(Credentials(KEY, SECRET), base_url=url)


def test_injected_client_with_real_host_blocked():
    import httpx
    c = httpx.Client(base_url="https://fapi.binance.com")
    with pytest.raises(BrokerError, match="bloqueado"):
        BinanceTestnetBroker(Credentials(KEY, SECRET), client=c)


def test_keys_only_from_env(monkeypatch):
    monkeypatch.delenv(ENV_KEY, raising=False)
    monkeypatch.delenv(ENV_SECRET, raising=False)
    with pytest.raises(BrokerError, match=ENV_KEY):
        BinanceTestnetBroker()
    monkeypatch.setenv(ENV_KEY, KEY)
    monkeypatch.setenv(ENV_SECRET, SECRET)
    b = BinanceTestnetBroker(client=FakeBinance().client())
    assert SECRET not in repr(b) and KEY not in repr(b)


def test_secret_never_travels_nor_appears_in_errors():
    r = rig()
    r.fx.fault("POST", ORDER, "after")
    r.fx.fault("GET", ORDER, "before", times=10)
    r.open()
    r.fx.fault("POST", ALGO, "reject", code=-2010, msg="x")
    with pytest.raises(ExecutionError) as e:
        r.open(plan_id="plan:2")
    texts = r.fx.raw + [str(e.value)] + [ev for t in r.svc.trades.values() for ev in t.events]
    assert all(SECRET not in t for t in texts)
    assert "signature=" not in str(e.value)


def test_bad_signature_rejected():
    fx = FakeBinance()
    b = BinanceTestnetBroker(Credentials(KEY, "otro"), client=fx.client())
    with pytest.raises(OrderRejected, match="Signature"):
        b.equity()


# --- flujo completo -------------------------------------------------------------
def test_open_protect_then_take_profit():
    r = rig()
    key = r.open()
    tr = r.svc.trades[key]
    assert tr.status == OPEN and r.pos() == pytest.approx(tr.qty) and tr.qty == 0.025
    paths = [p for m, p, _ in r.fx.log if m == "POST" and p in (ORDER, ALGO)]
    assert paths == [ALGO, ALGO, ORDER]               # SL y TP antes que la entrada
    kinds = {o.kind: o for o in r.orders()}
    assert kinds[STOP].trigger == 98_000 and kinds[STOP].close_position
    assert kinds[TAKE_PROFIT].trigger == 104_000 and kinds[STOP].side == -1
    assert r.fx.sim.leverage[SYM] == 3
    assert r.recon.run((SYM,), NOW).ok
    r.fx.sim.set_price(SYM, 104_500.0)
    rep = r.recon.run((SYM,), NOW + 1)
    assert tr.status == CLOSED and tr.exit_reason == "TP"
    assert r.pos() == 0 and r.orders() == [] and rep.ok


def test_stop_loss_closes_and_cancels_tp():
    r = rig()
    tr = r.svc.trades[r.open()]
    r.fx.sim.set_price(SYM, 97_000.0)
    r.recon.run((SYM,), NOW)
    assert tr.status == CLOSED and tr.exit_reason == "SL"
    assert r.pos() == 0 and r.orders() == []


def test_same_decision_twice_is_idempotent():
    r = rig()
    d = r.decision()
    assert r.gw.submit(d, NOW) == r.gw.submit(d, NOW)
    assert len(r.fx.posts(ORDER)) == 1 and r.pos() == 0.025


def test_testnet_requires_testnet_decision():
    r = rig()
    d = decide(r.eng, plan())                          # decisión SIMULADA
    with pytest.raises(PermissionError, match="modo"):
        r.gw.submit(d, NOW)
    assert r.fx.posts(ORDER) == []


# --- fallos de red y rechazos ------------------------------------------------------
def test_lost_response_does_not_duplicate_entry():
    r = rig()
    r.fx.fault("POST", ORDER, "after")
    tr = r.svc.trades[r.open()]
    assert len(r.fx.posts(ORDER)) == 1 and r.pos() == 0.025 and tr.status == OPEN


def test_lost_request_is_resent_once():
    r = rig()
    r.fx.fault("POST", ORDER, "before")
    tr = r.svc.trades[r.open()]
    assert len(r.fx.posts(ORDER)) == 1 and tr.status == OPEN


def test_server_error_on_stop_is_retried():
    r = rig()
    r.fx.fault("POST", ALGO, "503")
    tr = r.svc.trades[r.open()]
    assert tr.status == OPEN and len(r.fx.posts(ALGO)) == 2


def test_network_cut_mid_trade_leaves_position_with_sl():
    r = rig()
    r.fx.fault("POST", ORDER, "after")               # la entrada se llena, la respuesta no llega
    r.fx.fault("GET", ORDER, "before", times=99)     # y la red no vuelve durante el envío
    tr = r.svc.trades[r.open()]
    assert tr.status == PENDING and r.pos() == 0.025
    sl = [o for o in r.orders() if o.kind == STOP]
    assert sl and sl[0].close_position and sl[0].side == -1
    r.fx.faults.clear()                               # vuelve la red: se reconcilia
    rep = r.recon.run((SYM,), NOW)
    assert rep.ok and tr.status == OPEN and tr.filled == 0.025


def test_entry_rejected_cancels_protection():
    r = rig()
    r.fx.fault("POST", ORDER, "reject", code=-2019, msg="Margin is insufficient.")
    with pytest.raises(ExecutionError, match="insufficient"):
        r.open()
    tr = next(iter(r.svc.trades.values()))
    assert tr.status == FAILED and r.orders() == [] and r.pos() == 0


def test_stop_rejected_means_no_entry():
    r = rig()
    r.fx.fault("POST", ALGO, "reject", code=-2021, msg="Order would immediately trigger.")
    with pytest.raises(ExecutionError, match="sin SL"):
        r.open()
    assert r.fx.posts(ORDER) == [] and r.pos() == 0 and r.orders() == []


def test_partial_fills_are_protected_and_tracked():
    r = rig(fill_cap=0.01)
    tr = r.svc.trades[r.open()]
    assert tr.status == OPEN and tr.filled == 0.01 and r.pos() == 0.01
    assert any(o.kind == STOP for o in r.orders())
    assert r.recon.run((SYM,), NOW).ok                # parcial ≠ divergencia
    r.fx.sim.set_price(SYM, PX)
    r.fx.sim.set_price(SYM, PX)
    r.recon.run((SYM,), NOW)
    assert tr.filled == 0.025 and r.pos() == 0.025
    r.fx.sim.set_price(SYM, 97_000.0)                 # el SL cierra todo lo llenado
    r.recon.run((SYM,), NOW)
    assert r.pos() == 0 and tr.status == CLOSED and r.orders() == []


def test_limit_entry_partial_then_stop_cancels_rest():
    r = rig(fill_cap=0.01)
    r.fx.sim.set_price(SYM, PX + 50)
    tr = r.svc.trades[r.open(entry_kind="LIMIT")]
    assert tr.status == PENDING and tr.filled == 0
    r.fx.sim.set_price(SYM, PX)                       # cruza: llena 0.01
    r.recon.run((SYM,), NOW)
    assert tr.status == OPEN and tr.filled == 0.01
    # el SL cierra lo llenado, pero la límite que sigue viva vuelve a llenarse al mismo
    # precio: la reconciliación ve una posición sin operación → la cierra y activa el
    # kill-switch (conservador)
    r.fx.sim.set_price(SYM, 97_000.0)
    rep = r.recon.run((SYM,), NOW)
    assert tr.status == CLOSED and r.orders() == [] and r.pos() == 0
    assert r.ks.active and rep.kill


def test_failed_plan_is_not_reported_as_sent_again():
    r = rig()
    r.fx.fault("POST", ORDER, "reject", code=-2019, msg="Margin is insufficient.")
    d = r.decision()
    with pytest.raises(ExecutionError):
        r.gw.submit(d, NOW)
    with pytest.raises(ExecutionError, match="ya falló"):
        r.gw.submit(d, NOW)


def test_limit_entry_rests_at_plan_entry():
    r = rig()
    tr = r.svc.trades[r.open(entry_kind="LIMIT", entry=99_500.0, sl=97_500.0)]
    entry = r.fx.sim.order_by_id(tr.cid("e"))
    assert entry.is_open and r.fx.sim._limit_px[tr.cid("e")] == 99_500.0 and r.pos() == 0
