"""Evaluación de líderes (T41, I/O sin red): servicio con ejecuciones reales grabadas →
precio del seguidor; almacén → veredictos → tablero → snapshot → agente `smart_money`."""

from __future__ import annotations

import asyncio
import json

from eim.agents.smart_money import SmartMoneyAgent
from eim.data.leader_board import BoardStore
from eim.data.leader_eval import evaluate
from eim.data.leader_quotes import QuoteBook
from eim.data.leader_service import LeaderService
from eim.data.leader_store import LeaderStore
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.leaders.cli import _toggle_watch
from eim.operation.watchdog import heartbeat_t
from tests.copytrading import helpers as H
from tests.leaders.helpers import ACTIVE, FakeInfo, load
from tests.leaders.helpers import leader as hl_leader

OFFSET = 1_200
REC_NOW = 1_792_097_100_000


def _bbo(coin: str, px: float, t: int) -> dict:
    return {"channel": "bbo", "data": {"coin": coin, "time": t, "bbo": [
        {"px": str(px * 0.9999), "sz": "1", "n": 1}, {"px": str(px * 1.0001), "sz": "1", "n": 1}]}}


def test_service_records_follower_price_for_recorded_live_fills(tmp_path):
    info = FakeInfo([load("active_state0"), load("active_state1")],
                    funding=load("active_funding"), offset=OFFSET)
    store = LeaderStore.at_root(tmp_path)
    store.upsert_leader(hl_leader(ACTIVE), 0)
    svc = LeaderService(store, info, store.leaders(), root=tmp_path,
                        clock=lambda: REC_NOW, quote_coins=["ETH"])
    asyncio.run(svc.bootstrap(ACTIVE))
    live = [m for m in load("active_ws_user_fills") if not m["data"].get("isSnapshot")]
    for m in live:
        obs = m["_observed_at"] + OFFSET
        px = float(m["data"]["fills"][0]["px"])
        svc.on_quote(_bbo("ETH", px, obs - 5), obs - 5)  # vigente cuando el seguidor actúa
        svc.on_quote({"channel": "allMids", "data": {"mids": {"BTC": "80000.0"}}}, obs - 5)
        svc.on_message(m, obs)
        svc.on_quote(_bbo("ETH", px * 1.001, obs + 2_000), obs + 2_000)  # llega después
    svc.store.add_follow(svc.quotes.flush(10**13))
    lid = svc.books[ACTIVE].leader.id
    got = store.follow_quotes(lid)
    n_live = sum(1 for m in live for f in m["data"]["fills"] if f["coin"] in ("ETH", "BTC"))
    assert len(got) == n_live and all(q.follow_at == q.observed_at + 300 for q in got.values())
    assert {q.src for q in got.values() if q.symbol == "ETH"} == {"bbo"}
    assert all(q.quote_t < q.follow_at for q in got.values())  # la previa, no la posterior
    board = evaluate(store, REC_NOW + 60_000)
    (card,) = board.leaders
    assert card.copyability.live_fills > 0 and card.copyability.latency_ms["p50"] < 1_500
    assert card.verdict in ("watch", "rejected") and card.reasons  # 35 min no aprueban a nadie
    assert board.weights == [] and board.positions[lid]


def test_service_heartbeat_feeds_the_process_watchdog(tmp_path):
    store = LeaderStore.at_root(tmp_path)
    svc = LeaderService(store, FakeInfo([]), [], root=tmp_path, clock=lambda: REC_NOW,
                        quote_coins=[])
    asyncio.run(svc._safe("tareas extra", svc.extra_jobs()))  # cada tarea terminada late
    hb = tmp_path / "leaders" / "heartbeat.json"
    assert heartbeat_t(hb) == REC_NOW
    assert json.loads(hb.read_text(encoding="utf-8"))["state"] == "capturando"  # 0 de 0 listos
    assert BoardStore(tmp_path).latest() is None  # el latido no es un tablero
    store.close()


def test_quote_book_waits_for_order_delay_and_drops_old_fills():
    qb = QuoteBook(["BTC"], delay_ms=300, live_max_ms=120_000)
    live = H.fill("BTC", 0.0, 1.0, 100.0, 1_000_000, 1, delay=200)
    late = H.fill("BTC", 1.0, 0.0, 100.0, 1_000_000, 2, delay=500_000)  # historial: no se copia
    assert qb.expect([live, late]) == 1
    assert qb.on_bbo({"coin": "BTC", "time": 1_000_150, "bbo": [{"px": "99"}, {"px": "101"}]},
                     1_000_250) == []  # aún no vence (due = 1 000 500)
    (q,) = qb.on_bbo({"coin": "BTC", "time": 1_000_600, "bbo": [{"px": "98"}, {"px": "102"}]},
                     1_000_700)
    assert (q.bid, q.ask, q.quote_t, q.follow_at) == (99.0, 101.0, 1_000_150, 1_000_500)


def _approved_store(tmp_path) -> tuple[LeaderStore, int]:
    store = LeaderStore.at_root(tmp_path)
    store.upsert_leader(H.leader(), 0)
    store.set_status(H.LID, "watch", 0)
    fills = H.series(300, H.T0 + 1000, 10 * H.DAY, edge=0.002, noise=0.004)
    store.add_fills(fills)
    store.add_follow(list(H.quotes(fills).values()))
    now = H.T0 + 10 * H.DAY + 60_000
    pos = json.dumps([H.position("BTC", "long", 5.0, 60_000.0, now - 30_000).model_dump()])
    photos = [(H.LID, t, t, "[]") for t in range(H.T0, now - 60_000, 600_000)]
    store._insert("leader_positions", "leader_id, t, observed_at, positions",
                  photos + [(H.LID, now - 30_000, now - 30_000, pos)])
    store.save_portfolio(H.LID, H.T0, H.portfolio(120, t_end=H.T0))
    return store, now


def test_evaluate_approves_records_verdict_and_feeds_the_agent(tmp_path):
    store, now = _approved_store(tmp_path)
    board = evaluate(store, now)
    (card,) = board.leaders
    assert card.verdict == "approved" and card.forward_days > 9.9, card.reasons
    assert [ld.status for ld in store.leaders()] == ["approved"]
    assert [m.verdict for m in store.verdicts()] == ["approved"]
    assert {(c.symbol, c.window_h, c.to_size) for c in board.changes[H.LID]} == {
        ("BTC", h, 5.0) for h in (1.0, 4.0, 24.0)}
    evaluate(store, now + 1000)
    assert len(store.verdicts()) == 1  # sin cambio de veredicto no se repite
    BoardStore(tmp_path).save(board)
    snap = build_snapshot(Store(tmp_path), "BTCUSDT", "1h", 10, asof=now + 60_000)
    assert [w.leader_id for w in snap.leader_weights] == [H.LID] and len(snap.leaders) == 1
    assert snap.sources["leaders"] and snap.coverage["leaders"][1] == now
    rep = SmartMoneyAgent().run(snap)
    assert rep.status == "ok" and 0 < rep.bias <= 0.4 and rep.metrics["n_in_coin"] == 1
    assert build_snapshot(Store(tmp_path), "BTCUSDT", "1h", 10, asof=now - 1).leaders is None
    late = build_snapshot(Store(tmp_path), "BTCUSDT", "1h", 10, asof=now + 11 * 60_000)
    assert late.leaders is None and late.leader_weights is None


def test_rejected_stays_captured_until_unwatched(tmp_path):
    store = LeaderStore.at_root(tmp_path)
    store.upsert_leader(H.leader(status="rejected"), 0)
    assert store.leaders()[0].tracked  # grupo de control
    assert "sin cambios" in _toggle_watch(store, H.LID, True, 1)
    assert _toggle_watch(store, H.LID, False, 2).endswith("ok")
    assert store.leaders()[0].status == "candidate" and not store.leaders()[0].tracked


def test_changes_need_a_photo_near_the_window_start(tmp_path):
    store = LeaderStore.at_root(tmp_path)
    store.upsert_leader(H.leader(), 0)
    store.set_status(H.LID, "watch", 0)
    now = H.T0 + 2 * H.DAY
    old = json.dumps([H.position("BTC", "short", 1.0, 60_000.0, H.T0).model_dump()])
    cur = json.dumps([H.position("BTC", "long", 2.0, 60_000.0, now - 1000).model_dump()])
    store._insert("leader_positions", "leader_id, t, observed_at, positions",
                  [(H.LID, H.T0, H.T0, old), (H.LID, now - 1000, now - 1000, cur)])
    board = evaluate(store, now)  # vigilante apagado 2 días: no hay «cambio en 1 h» contra ayer
    assert board.changes[H.LID] == [] and board.positions[H.LID][0].side == "long"
