"""Piezas de I/O de la copia simulada (T42): instantánea a pedido, reanudaciones y caché de
velas de Hyperliquid (sin red)."""

from __future__ import annotations

import json

from eim.data.copy_store import (
    request_resume,
    request_snapshot,
    take_control,
    take_snapshot_request,
)
from eim.data.hl_market import candles_1m
from eim.data.leader_store import LeaderStore

MIN = 60_000


def test_snapshot_per_request_does_not_hold_the_store_lock(tmp_path):
    store = LeaderStore.at_root(tmp_path)
    store.save_copy_state("a", 1, {"x": 1})
    target = request_snapshot(tmp_path, 123)
    assert take_snapshot_request(tmp_path) == target and take_snapshot_request(tmp_path) is None
    locked: list[bool] = []

    class Cur:  # registra si el candado está tomado mientras se ejecuta la copia
        def __init__(self, cur) -> None:
            self.cur = cur

        def execute(self, q):
            locked.append(store._lock.locked())
            return self.cur.execute(q)

        def close(self) -> None:
            self.cur.close()

    class Con:
        def __init__(self, con) -> None:
            self.con = con

        def cursor(self):
            return Cur(self.con.cursor())

        def __getattr__(self, name):
            return getattr(self.con, name)

    real = store._con
    store._con = Con(real)
    out = store.snapshot(target)
    store._con = real
    assert locked and not any(locked)  # la captura puede seguir escribiendo
    copy = LeaderStore(out)
    assert copy.copy_states() == {"a": {"x": 1}}
    copy.close()
    nxt = request_snapshot(tmp_path, 456)  # la anterior sigue abierta o no: otro archivo
    assert nxt != target and take_snapshot_request(tmp_path) == nxt
    store.close()


def test_resume_requests_accumulate_until_the_service_takes_them(tmp_path):
    request_resume(tmp_path, ["a"], 1)
    request_resume(tmp_path, ["b", "a"], 2)
    assert take_control(tmp_path)["resume"] == ["a", "b"] and take_control(tmp_path) is None


class _Info:
    def __init__(self, bars: dict[str, list[dict]]) -> None:
        self.bars, self.calls = bars, 0

    def candles(self, coin, interval, start, end):
        self.calls += 1
        return [b for b in self.bars.get(coin, []) if start <= b["t"] <= end]


def _bar(t: int) -> dict:
    return {"t": t, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "10"}


def test_candle_cache_only_claims_the_coverage_it_really_has(tmp_path):
    t0 = 1_790_000_000_000
    info = _Info({"BTC": [_bar(t0 + k * MIN) for k in range(10, 20)]})  # sin lo más viejo
    got = candles_1m(info, "BTC", t0, t0 + 20 * MIN, tmp_path)
    assert len(got) == 10
    cache = json.loads((tmp_path / "BTC.json").read_text(encoding="utf-8"))
    assert cache["from"] == t0 + 10 * MIN and cache["to"] == t0 + 19 * MIN
    assert candles_1m(info, "BTC", t0 + 12 * MIN, t0 + 15 * MIN, tmp_path, offline=True) == \
        [tuple(float(x) if i else int(x) for i, x in enumerate(
            (t0 + k * MIN, 1, 2, 0.5, 1.5, 10))) for k in range(12, 16)]
