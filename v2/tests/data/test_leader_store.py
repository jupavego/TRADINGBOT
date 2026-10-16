"""Almacén de historial de líderes (T40): deduplicación, fotos de posiciones e historial."""

from __future__ import annotations

from eim.data.leader_store import LeaderStore
from eim.leaders.book import LeaderBook
from eim.leaders.parse import order_fills, parse_funding, parse_positions
from tests.leaders.helpers import ACTIVE, TEST, fill, leader, load, state


def _store(tmp_path) -> LeaderStore:
    return LeaderStore.at_root(tmp_path)


def test_leader_upsert_keeps_status_and_first_discovery(tmp_path):
    s = _store(tmp_path)
    found = leader(TEST, status="candidate", t=1).model_copy(update={"evidence": {"trades": 3.0}})
    assert s.upsert_leader(found, 10)
    assert s.set_status(leader(TEST).id, "watch", 11)
    assert not s.upsert_leader(leader(TEST, status="candidate", t=50), 12)
    [ld] = s.leaders()
    assert ld.status == "watch" and ld.discovered_at == 1 and ld.evidence == {"trades": 3.0}
    assert s.leaders(("approved",)) == [] and not s.set_status("hyperliquid:0x1", "watch", 1)


def test_fills_and_funding_are_deduplicated(tmp_path):
    s, ld = _store(tmp_path), leader(ACTIVE)
    b = LeaderBook(ld)
    b.load(*parse_positions(ld, load("active_state0"), 0))
    fills = [f for r in order_fills(load("active_fills_by_time"))
             for f in [b.apply(r, 1, "rest_backfill")[0]] if f]
    assert s.add_fills(fills) == len(fills)
    assert s.add_fills(fills[:10]) == 0  # evento repetido (p. ej. instantánea del WS)
    fund = parse_funding(ld, load("active_funding"), 5)
    assert s.add_funding(fund) == len(fund) and s.add_funding(fund) == 0
    assert s.last_fill_t(ld.id) == max(f.t for f in fills)
    assert s.last_funding_t(ld.id) == max(r.t for r in fund)


def test_history_merges_fills_funding_and_leverage(tmp_path):
    s, ld = _store(tmp_path), leader(TEST)
    b = LeaderBook(ld)
    b.load(*parse_positions(ld, state(1000, ("BTC", "1.0", "100", 5, "cross")), 0))
    f, _ = b.apply(fill("BTC", "A", "0.4", "110", "1.0", 1100, 1, closedPnl="4.0"), 1200, "ws")
    s.add_fills([f])
    s.add_funding(parse_funding(ld, [{"time": 1050, "hash": "0x0", "delta": {
        "type": "funding", "coin": "BTC", "usdc": "-0.5", "szi": "1.0",
        "fundingRate": "0.0001"}}], 1300))
    t, pos = parse_positions(ld, state(1150, ("BTC", "0.6", "100", 10, "cross")), 0)
    s.add_leverage(ld.id, b.compare(t, pos), 1400)
    kinds = [(e["kind"], e["t"]) for e in s.history(ld.id)]
    assert kinds == [("funding", 1050), ("reduce", 1100), ("leverage", 1150)]
    ev = s.history(ld.id)[1]
    assert ev["closed_pnl"] == 4.0 and ev["fee"] == 0.01 and ev["position"] == 0.6


def test_positions_saved_on_change_and_read_point_in_time(tmp_path):
    s, ld = _store(tmp_path), leader(TEST, status="approved")
    s.upsert_leader(ld, 0)
    _, p1 = parse_positions(ld, state(1000, ("BTC", "1.0", "100", 5, "cross")), 1000)
    _, p2 = parse_positions(ld, state(2000, ("BTC", "2.0", "105", 5, "cross")), 2000)
    assert s.save_positions(ld.id, 1000, 1000, p1)
    assert not s.save_positions(ld.id, 1500, 1500, p1)  # sin cambios: no se repite
    assert s.save_positions(ld.id, 2000, 2000, p2)
    assert s.save_positions(ld.id, 400_000, 400_000, p2)  # sin cambios pero vieja: se renueva
    assert s.positions_at(999) == []  # nunca posterior a asof
    assert s.positions_at(1800)[0].size == 1.0
    assert s.positions_at(2500)[0].size == 2.0
    assert s.positions_at(400_000 + 11 * 60_000, max_age_ms=10 * 60_000) == []  # foto vieja
    assert s.positions_at(2500, statuses=("watch",)) == []  # solo líderes aprobados
