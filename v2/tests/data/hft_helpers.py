"""Secuencias simuladas de Binance USDⓈ-M para los tests de la captura HFT (T78). Sin red.

`Exchange` lleva un libro «verdadero» y genera diffs encadenados (`U`/`u`/`pu`) y snapshots REST
coherentes con él, también a mitad de un diff (`U ≤ L ≤ u`), como hace Binance.
"""
from __future__ import annotations

import json
import random

from eim.data.collectors.hft_capture import HftCapture
from eim.data.collectors.hft_schema import HOUR_NS
from eim.data.collectors.hft_writer import HftStore

SYM = "BTCUSDT"
T0 = 1_800_000_000_000_000_000 // HOUR_NS * HOUR_NS        # comienzo de una hora UTC (ns)
MS = 1_000_000
CONN = {"depthUpdate": "depth", "bookTicker": "bbo"}


def lv(levels) -> list[list[str]]:
    return [[f"{p:.1f}", f"{q:.3f}"] for p, q in levels]


def depth(U: int, u: int, pu: int, b=(), a=(), e_ms: int = 0) -> dict:
    return {"e": "depthUpdate", "E": e_ms, "T": e_ms, "s": SYM, "U": U, "u": u, "pu": pu,
            "b": lv(b), "a": lv(a)}


def bbo(u: int, bid: float, ask: float, e_ms: int) -> dict:
    return {"e": "bookTicker", "u": u, "s": SYM, "b": f"{bid:.1f}", "B": "1.000",
            "a": f"{ask:.1f}", "A": "2.000", "T": e_ms, "E": e_ms}


def trade(a: int, e_ms: int, p: float = 100.0, q: float = 0.5, maker: bool = False) -> dict:
    return {"e": "aggTrade", "E": e_ms, "s": SYM, "a": a, "p": f"{p:.1f}", "q": f"{q:.3f}",
            "f": a * 2, "l": a * 2 + 1, "T": e_ms, "m": maker}


def mark(e_ms: int, p: float = 100.0) -> dict:
    return {"e": "markPriceUpdate", "E": e_ms, "s": SYM, "p": f"{p:.2f}", "i": f"{p - 0.05:.2f}",
            "P": f"{p:.2f}", "r": "0.00010000", "T": e_ms + 3_600_000}


def liq(e_ms: int, side: str = "SELL") -> dict:
    return {"e": "forceOrder", "E": e_ms, "o": {"s": SYM, "S": side, "o": "LIMIT", "f": "IOC",
                                                 "q": "0.010", "p": "99.0", "ap": "99.5",
                                                 "X": "FILLED", "l": "0.010", "z": "0.010",
                                                 "T": e_ms}}


class Exchange:
    """Libro verdadero de un perpetuo de juguete (bids 98–99.9, asks 100.1–102: nunca cruza)."""

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)
        self.u = 1000
        self.bids = {round(100 - 0.1 * i, 1): 1.0 + i for i in range(1, 21)}
        self.asks = {round(100 + 0.1 * i, 1): 1.0 + i for i in range(1, 21)}

    def _sub(self) -> tuple[str, float, float]:
        side = self.rng.choice("ba")
        book = self.bids if side == "b" else self.asks
        p = round((100 - 0.1 * self.rng.randint(1, 20)) if side == "b"
                  else (100 + 0.1 * self.rng.randint(1, 20)), 1)
        q = 0.0 if self.rng.random() < 0.2 else round(self.rng.uniform(0.1, 9.0), 3)
        if q == 0:
            book.pop(p, None)
        else:
            book[p] = q
        return side, p, q

    def step(self, k: int = 3, e_ms: int = 0, snap_at: int | None = None
             ) -> tuple[dict, dict | None]:
        """Diff de `k` actualizaciones; con `snap_at=j` también el snapshot tras la j-ésima."""
        U, pu = self.u + 1, self.u
        changed: dict[tuple[str, float], float] = {}
        snap = None
        for j in range(1, k + 1):
            side, p, q = self._sub()
            changed[(side, p)] = q
            self.u += 1
            if snap_at == j:
                snap = self.snapshot()
        b = [(p, q) for (s, p), q in changed.items() if s == "b"]
        a = [(p, q) for (s, p), q in changed.items() if s == "a"]
        return depth(U, self.u, pu, b, a, e_ms), snap

    def snapshot(self) -> dict:
        return {"lastUpdateId": self.u, "E": 0, "T": 0,
                "bids": lv(sorted(self.bids.items(), reverse=True)),
                "asks": lv(sorted(self.asks.items()))}


def capture(tmp_path, run: int = T0, flush_rows: int = 10**9) -> tuple[HftCapture, HftStore]:
    store = HftStore(tmp_path, SYM, threaded=False, flush_rows=flush_rows)
    return HftCapture(SYM, store, run), store


def send(cap: HftCapture, d: dict, recv: int, conn: str | None = None) -> None:
    conn = conn or CONN.get(d["e"], "market")
    cap.handle(("msg", conn, json.dumps({"stream": "x", "data": d}), recv, recv - T0))


def snap(cap: HftCapture, s: dict, recv: int, purpose: str = "sync") -> None:
    cap.handle(("snap", purpose, s, recv - 100 * MS, recv, recv - T0))


def full_hour(tmp_path, lose_at: int | None = None, seed: int = 0, flush_rows: int = 10**9):
    """Una hora entera: 1 diff, 1 bookTicker, 1 markPrice y 1 trade por segundo; verificación
    REST cada 10 min. Con `lose_at` se pierde el diff de ese segundo (y se resincroniza)."""
    cap, store = capture(tmp_path, flush_rows=flush_rows)
    ex = Exchange(seed)
    send(cap, ex.step(e_ms=T0 // MS)[0], T0 + MS)
    snap(cap, ex.snapshot(), T0 + 20 * MS)
    for s in range(3600):
        t = T0 + s * 10**9 + 100 * MS
        e = t // MS - 110
        m, mid = ex.step(k=3, e_ms=e, snap_at=2 if s % 600 == 300 else None)
        if s != lose_at:
            send(cap, m, t)
        if lose_at is not None and s == lose_at + 1:
            snap(cap, ex.snapshot(), t + 10 * MS)
        if mid is not None:
            snap(cap, mid, t + 40 * MS, "check")
        send(cap, bbo(s + 1, 99.9, 100.1, e), t + MS)
        send(cap, mark(e), t + 2 * MS)
        send(cap, trade(1000 + s, e), t + 3 * MS)
    store.flush()
    return cap, store
