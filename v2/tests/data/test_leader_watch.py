"""Vigilante de líderes (T40) sin red, con respuestas reales grabadas: seguimiento por WS,
reconexión con hueco, evento duplicado, reconciliación con relleno o resincronización."""

from __future__ import annotations

import asyncio

from eim.core.leaders import Leader, leader_id
from eim.data.leader_report import render, summary
from eim.data.leader_store import LeaderStore
from eim.data.leader_watch import LeaderWatch
from eim.leaders.parse import order_fills
from tests.leaders.helpers import (
    ACTIVE,
    TEST,
    FakeInfo,
    FakeWS,
    fake_connect,
    fill,
    leader,
    load,
    no_sleep,
    state,
)

NOW = 1_792_097_100_000
OFFSET = 1_200  # el reloj de la máquina de la grabación iba ≈1,2 s por detrás del servidor


def _live() -> list[dict]:
    return [m for m in load("active_ws_user_fills") if not m["data"].get("isSnapshot")]


def _watch(tmp_path, info, leaders=None, clock=lambda: NOW, **kw
           ) -> tuple[LeaderWatch, LeaderStore]:
    store = LeaderStore.at_root(tmp_path)
    return LeaderWatch(store, info, leaders or [leader(ACTIVE)], clock=clock, **kw), store


def test_follows_recorded_wallet_and_measures_corrected_latency(tmp_path):
    info = FakeInfo([load("active_state0"), load("active_state1")],
                    funding=load("active_funding"), offset=OFFSET)
    w, store = _watch(tmp_path, info)
    asyncio.run(w.bootstrap(ACTIVE))
    booted = len(info.calls)
    for m in load("active_ws_user_fills"):
        w.on_message(m, m["_observed_at"] + OFFSET)  # lo que entrega el stream (reloj alineado)
    rec = asyncio.run(w.reconcile(ACTIVE))
    assert rec.match and len(rec.checked) == 6
    assert not any(c[0] == "fills" for c in info.calls[booted:])  # sin relleno: no hizo falta
    s = summary(store, 0)
    assert s["fills_by_channel"]["ws"] == sum(len(m["data"]["fills"]) for m in _live())
    assert 0 < s["latency_ms"]["p50"] < 1_500 and s["latency_ms"]["min"] > -300
    assert s["funding"][0] == len(load("active_funding"))
    assert s["recon"][0]["size_ok"] == 1 and s["clock_offset_ms"] == OFFSET
    assert "Latencia WS" in render(s)


def test_reconnect_gap_is_backfilled_and_duplicates_dropped(tmp_path):
    live = _live()
    snap = next(m for m in load("active_ws_user_fills") if m["data"].get("isSnapshot"))
    missed = [f for m in live[20:30] for f in m["data"]["fills"]]
    seen_again = [f for m in live[18:20] for f in m["data"]["fills"]]
    resent = {"channel": "userFills",  # instantánea parcial al reconectar + repetidos
              "data": {"isSnapshot": True, "user": ACTIVE, "fills": seen_again + missed[-3:]}}
    c1 = FakeWS([{"channel": "subscriptionResponse", "data": {}}, snap, *live[:20],
                 ConnectionResetError("corte de red")])
    c2 = FakeWS([resent, *live[30:]])
    info = FakeInfo([load("active_state0"), load("active_state0"), load("active_state1")],
                    offset=OFFSET)
    sim = {"t": snap["_observed_at"]}  # reloj local simulado: avanza con la grabación
    w, store = _watch(tmp_path, info, clock=lambda: sim["t"],
                      stream_kw={"connect": fake_connect([c1, c2]), "sleep": no_sleep,
                                 "recv_timeout": 0.01})
    stop, last = asyncio.Event(), live[-1]["data"]["fills"][-1]["tid"]
    original = w.on_message

    def on_message(m, t):
        original(m, t)
        sim["t"] = m.get("_observed_at", sim["t"])
        if any(f["tid"] == last for f in (m.get("data") or {}).get("fills", [])):
            stop.set()

    w.on_message = on_message
    asyncio.run(w.bootstrap(ACTIVE))  # estado inicial antes del corte (el WS va en paralelo)
    info.fills = load("active_fills_by_time")  # desde aquí el REST conoce todo
    asyncio.run(asyncio.wait_for(w.run(stop), 20))
    t0 = load("active_state0")["time"]
    n_live = sum(1 for r in order_fills(load("active_fills_by_time")) if r["time"] > t0)
    assert store.query("SELECT count(*), count(DISTINCT (tid, oid)) FROM leader_fills "
                       "WHERE t > ?", [t0])[0] == (n_live, n_live)
    gaps = store.query("SELECT cause, recovered FROM leader_gaps")
    assert any(c == "ws" and r > 0 for c, r in gaps)
    final = store.query("SELECT size_ok, match, resynced FROM leader_recon "
                        "ORDER BY observed_at DESC, t DESC LIMIT 1")[0]
    assert final == (True, True, False)
    assert len([m for m in c2.sent if m["method"] == "subscribe"]) == 1


def test_divergence_resolved_by_backfill_without_resync(tmp_path):
    info = FakeInfo([load("active_state0"), load("active_state1")],
                    fills=load("active_fills_by_time"))
    w, store = _watch(tmp_path, info)
    info_fills, info.fills = info.fills, []  # el arranque no ve nada nuevo
    asyncio.run(w.bootstrap(ACTIVE))
    info.fills = info_fills  # luego se pierde todo el WS: solo REST lo sabe
    rec = asyncio.run(w.reconcile(ACTIVE))
    assert rec.match
    assert store.query("SELECT resynced, size_ok FROM leader_recon")[0] == (False, True)
    assert store.query("SELECT count(*) FROM leader_fills WHERE channel = 'rest_backfill'")[0][0]


def test_lagging_fills_endpoint_resolved_by_recheck(tmp_path):
    """Medido en vivo: `userFillsByTime` puede ir segundos por detrás del estado."""
    late = fill("BTC", "B", "2.0", "102", "1.0", NOW - 2000, 5)
    info = FakeInfo([state(NOW - 5000, ("BTC", "1.0", "100", 5, "cross")),
                     state(NOW - 1000, ("BTC", "3.0", "101.333", 5, "cross"))])
    w, store = _watch(tmp_path, info, [leader(TEST)])
    asyncio.run(w.bootstrap(TEST))
    assert not asyncio.run(w.reconcile(TEST)).size_ok and TEST in w.suspect
    assert store.query("SELECT count(*) FROM leader_recon")[0][0] == 0  # aún sin veredicto
    assert asyncio.run(w.recheck(TEST)) is None  # sigue sin llegar
    info.fills.append(late)  # el endpoint se pone al día
    rec = asyncio.run(w.recheck(TEST))
    assert rec.match and TEST not in w.suspect
    assert store.query("SELECT size_ok, resynced, retries FROM leader_recon") == [
        (True, False, 2)]
    assert store.query("SELECT count(*) FROM leader_gaps")[0][0] == 0


def test_unexplained_divergence_resyncs_to_exchange(tmp_path):
    info = FakeInfo([state(NOW - 5000, ("BTC", "1.0", "100", 5, "cross")),
                     state(NOW - 1000, ("BTC", "3.0", "102", 5, "cross"))])
    w, store = _watch(tmp_path, info, [leader(TEST)])
    asyncio.run(w.bootstrap(TEST))
    asyncio.run(w.reconcile(TEST))
    for _ in range(3):  # 3 re-comprobaciones y luego estado fresco → resincroniza
        asyncio.run(w.recheck(TEST))
    assert TEST not in w.suspect
    assert store.query("SELECT cause FROM leader_gaps") == [("reconciliación",)]
    assert asyncio.run(w.reconcile(TEST)).match  # libro resincronizado con el exchange
    assert store.query("SELECT resynced, retries FROM leader_recon ORDER BY observed_at, t, "
                       "retries DESC") == [(True, 4), (False, 0)]


def test_leverage_change_recorded_in_history(tmp_path):
    info = FakeInfo([state(1000, ("ETH", "-2.0", "2500", 10, "cross")),
                     state(2000, ("ETH", "-2.0", "2500", 25, "cross"))])
    w, store = _watch(tmp_path, info, [leader(TEST)])
    asyncio.run(w.bootstrap(TEST))
    asyncio.run(w.reconcile(TEST))
    asyncio.run(w.reconcile(TEST))
    ev = [e for e in store.history(leader(TEST).id) if e["kind"] == "leverage"]
    assert [(e["old"], e["new"]) for e in ev] == [(10, 25)]


def test_ws_limit_split_polling_and_manual_binance(tmp_path):
    addrs = [f"0x{i:040x}" for i in range(1, 13)]
    leaders = [leader(a, t=i) for i, a in enumerate(addrs)]
    leaders.append(Leader(id=leader_id("binance", "P1"), venue="binance", address="P1",
                          origin="manual", status="watch", discovered_at=0, source="manual"))
    leaders.append(leader("0x" + "ee" * 20, status="candidate"))  # no seguido
    info = FakeInfo([state(NOW - 5000)],
                    fills=[fill("BTC", "B", "1.0", "100", "0.0", NOW - 4000, 7)])
    w, store = _watch(tmp_path, info, leaders)
    assert w.ws_users == addrs[:10] and w.poll_users == addrs[10:]
    assert w.manual_only == ["binance:P1"] and len(w.books) == 12
    asyncio.run(w.bootstrap(addrs[11]))
    assert store.query("SELECT channel FROM leader_fills") == [("rest_backfill",)]
    info.fills.append(fill("BTC", "A", "0.4", "101", "1.0", NOW - 3000, 8))
    assert asyncio.run(w.poll(addrs[11])) == 1
    assert store.query("SELECT action, channel FROM leader_fills WHERE tid = 8") == [
        ("reduce", "rest_poll")]


def test_failed_backfill_keeps_gap_open(tmp_path):
    info = FakeInfo([state(NOW - 5000)])
    w, store = _watch(tmp_path, info, [leader(TEST)])
    asyncio.run(w.bootstrap(TEST))
    w.on_down(NOW - 3000, "corte")
    real = info.user_fills_by_time

    def boom(*a, **k):
        raise ConnectionError("sin red")

    info.user_fills_by_time = boom
    asyncio.run(w._safe("relleno", w.backfill(TEST)))
    assert TEST in w.pending and len(w.open_gaps[TEST]) == 1  # sigue abierto
    assert store.query("SELECT count(*) FROM leader_gaps")[0][0] == 0
    info.user_fills_by_time = real
    asyncio.run(w.backfill(TEST))
    assert TEST not in w.pending and store.query("SELECT cause FROM leader_gaps") == [("ws",)]


def test_failed_bootstrap_backs_off(tmp_path):
    info = FakeInfo([state(NOW - 5000)])
    calls = []

    def boom(user):
        calls.append(user)
        raise ConnectionError("422")

    info.clearinghouse_state = boom
    w, _ = _watch(tmp_path, info, [leader(TEST)])
    stop = asyncio.Event()

    async def go():
        task = asyncio.create_task(w._periodic(stop))
        await asyncio.sleep(2.5)  # ~3 vueltas del bucle de 1 s
        stop.set()
        await task

    asyncio.run(go())
    assert len(calls) == 1 and TEST in w.boot_retry and w.errors
