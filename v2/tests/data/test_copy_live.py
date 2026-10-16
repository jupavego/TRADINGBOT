"""Copia simulada EN VIVO dentro del servicio de líderes (T42), sin red: ejecuciones reales
grabadas de Hyperliquid (`tests/fixtures/leaders/active_*`, 2026-10-15) → señales que esperan
la cotización del seguidor → órdenes simuladas, bitácora en la base, resumen JSON,
reconciliación con la foto real y reinicio que conserva la subcuenta."""

from __future__ import annotations

import asyncio

import pytest

from eim.copytrading.copy_params import CopyParams
from eim.data.copy_store import read_summary, request_resume
from eim.data.leader_service import LeaderService
from eim.data.leader_store import LeaderStore
from eim.leaders.parse import parse_positions
from tests.copytrading import helpers as H
from tests.leaders.helpers import ACTIVE, FakeInfo, load
from tests.leaders.helpers import leader as hl_leader

OFFSET = 1_200
META = {"universe": [{"name": c, "szDecimals": d} for c, d in
                     (("BTC", 5), ("ETH", 4), ("HYPE", 2), ("LINK", 1), ("ARB", 1), ("SUI", 1))]}


class MetaInfo(FakeInfo):
    def meta(self) -> dict:
        return META

    def portfolio(self, user: str) -> list:
        return H.portfolio(60, av=1_638_000.0, t_end=1_792_096_000_000)


def _service(tmp_path, clock, p: CopyParams | None = None):
    info = MetaInfo([load("active_state0"), load("active_state1")],
                    funding=load("active_funding"), offset=OFFSET)
    store = LeaderStore.at_root(tmp_path)
    store.upsert_leader(hl_leader(ACTIVE), 0)
    lid = hl_leader(ACTIVE).id
    store.save_portfolio(lid, 0, H.portfolio(60, av=1_638_000.0, t_end=1_792_096_000_000))
    svc = LeaderService(store, info, store.leaders(), root=tmp_path, clock=clock,
                        quote_coins=["ETH"], copy_mode="tracked", copy_params=p)
    alerts: list = []
    svc.copy.alert = lambda *a: alerts.append(a)
    return svc, store, lid, alerts


def _settle(svc, name: str, obs: int) -> None:
    book = svc.books[ACTIVE]
    t, pos = parse_positions(book.leader, load(name), obs)
    svc._settle(ACTIVE, t, pos, book.compare(t, pos), obs, 0)


def _play(svc, cur: list[int]) -> int:
    """Mensajes en vivo con el reloj avanzando: el libro antes, la cotización que llega 2 s
    después (la vigente a los 300 ms es la anterior) y `allMids` del resto de monedas."""
    live = [m for m in load("active_ws_user_fills") if not m["data"].get("isSnapshot")]
    for m in live:
        obs = m["_observed_at"] + OFFSET
        mids = {f["coin"]: f["px"] for f in m["data"]["fills"]}
        cur[0] = obs - 5 - OFFSET
        eth = float(mids.get("ETH", 2_460.0))
        svc.on_quote({"channel": "bbo", "data": {"coin": "ETH", "time": obs - 5, "bbo": [
            {"px": str(eth * 0.9999)}, {"px": str(eth * 1.0001)}]}}, obs - 5)
        svc.on_quote({"channel": "allMids", "data": {"mids": mids}}, obs - 5)
        cur[0] = obs - OFFSET
        svc.on_message(m, obs)
        cur[0] = obs + 2_000 - OFFSET
        svc.on_quote({"channel": "allMids", "data": {"mids": mids}}, obs + 2_000)
        svc.on_quote({"channel": "bbo", "data": {"coin": "ETH", "time": obs + 2_000, "bbo": [
            {"px": str(eth * 0.9998)}, {"px": str(eth * 1.0002)}]}}, obs + 2_000)
    return live[-1]["_observed_at"] + OFFSET


def test_live_copy_follows_recorded_fills_and_does_not_copy_preexisting(tmp_path, monkeypatch):
    monkeypatch.setenv("EIM_NOTIFY", "0")
    cur = [load("active_state0")["time"]]
    svc, store, lid, alerts = _service(tmp_path, lambda: cur[0])
    asyncio.run(svc.bootstrap(ACTIVE))
    _settle(svc, "active_state0", cur[0] + OFFSET)  # primera foto: arranca la subcuenta
    end = _play(svc, cur)
    cur[0] = end + 60_000
    asyncio.run(svc.extra_jobs())  # vence colas, guarda estado y resumen
    eng = svc.copy.engines[lid]
    assert eng.counts["signals"] > 50 and "orders" not in eng.counts  # todo era preexistente
    assert eng.counts["rechazo:excluido"] == eng.counts["signals"]
    _settle(svc, "active_state1", end + 30_000)  # foto real tras las ejecuciones
    assert eng.last_recon.ok and not alerts and eng.paused is None
    j = store.journal(lid)
    assert {e.kind for e in j} >= {"start", "signal", "decision", "reject"}
    s = read_summary(tmp_path)
    assert s["mode"] == "SIMULADO" and s["accounts"][0]["measure"] is True
    store.close()


def test_live_copy_executes_at_the_follower_quote_and_survives_a_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("EIM_NOTIFY", "0")
    cur = [load("active_state0")["time"]]
    p = CopyParams(copy_existing=True, initial_equity=100_000.0)
    svc, store, lid, alerts = _service(tmp_path, lambda: cur[0], p)
    asyncio.run(svc.bootstrap(ACTIVE))
    _settle(svc, "active_state0", cur[0] + OFFSET)
    end = _play(svc, cur)
    cur[0] = end + 60_000
    asyncio.run(svc.extra_jobs())
    eng = svc.copy.engines[lid]
    (arb,) = [f for f in eng.fills if f.coin == "ARB"]  # el único aumento del líder
    assert arb.kind == "open" and arb.src == "allMids" and arb.latency_ms > 300
    assert arb.qty * arb.price >= 10.0  # sobre el mínimo del exchange
    _settle(svc, "active_state1", end + 30_000)
    assert eng.last_recon.ok, eng.last_recon
    svc.copy.save(cur[0])
    eq = eng.account.equity()
    svc2, *_ = _service(tmp_path, lambda: cur[0], p)  # mismo almacén: reinicio del servicio
    eng2 = svc2.copy.engines[lid]
    assert eng2.account.equity() == pytest.approx(eq) and eng2.account.size("ARB") == arb.qty
    request_resume(tmp_path, [lid], cur[0])
    eng2.pause("prueba", cur[0])
    svc2.copy._refresh()
    assert eng2.paused is None and eng2.journal[-1].kind == "resume"
    store.close()


def test_a_copy_failure_never_stops_the_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("EIM_NOTIFY", "0")
    cur = [load("active_state0")["time"]]
    svc, store, lid, _ = _service(tmp_path, lambda: cur[0])

    def boom(*_a):
        raise RuntimeError("fallo de prueba")

    svc.copy.on_fills = boom
    asyncio.run(svc.bootstrap(ACTIVE))
    _settle(svc, "active_state0", cur[0] + OFFSET)
    _play(svc, cur)  # el vigilante sigue: ejecuciones guardadas y precio del seguidor
    assert store.fills_fast(lid) and store.follow_quotes(lid)
    assert any("copia señales: RuntimeError" in e for e in svc.errors)
    store.close()


def test_restart_after_a_crash_rereads_what_the_subaccount_had_not_saved(tmp_path, monkeypatch):
    """Caída a la fuerza: la subcuenta pierde lo procesado desde su último guardado y T40 no lo
    re-entrega (ya está en la base). Al restaurar se relee de la base: sin divergencia."""
    monkeypatch.setenv("EIM_NOTIFY", "0")
    cur = [load("active_state0")["time"]]
    svc, store, lid, alerts = _service(tmp_path, lambda: cur[0])
    asyncio.run(svc.bootstrap(ACTIVE))
    _settle(svc, "active_state0", cur[0] + OFFSET)
    svc.copy.save(cur[0])  # último guardado: antes de todas las ejecuciones en vivo
    end = _play(svc, cur)  # procesadas y guardadas en la base por T40, no en la subcuenta
    cur[0] = end + 60_000
    svc2, *_ = _service(tmp_path, lambda: cur[0])  # «reinicio» sin cierre ordenado
    alerts2: list = []
    svc2.copy.alert = lambda *a: alerts2.append(a)
    asyncio.run(svc2.bootstrap(ACTIVE))
    eng = svc2.copy.engines[lid]
    # T40 reconcilia ANTES de la primera vuelta de tareas: la relectura no debe esperarla
    _settle(svc2, "active_state1", end + 10_000)
    assert eng.counts["signals"] > 50 and eng.last_recon.ok, eng.last_recon
    asyncio.run(svc2.extra_jobs())
    for k in range(3):
        _settle(svc2, "active_state1", end + 30_000 * (k + 1))
        assert eng.last_recon.ok, eng.last_recon
    assert not alerts2 and eng.paused is None
    store.close()
