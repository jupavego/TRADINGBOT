"""Captura HFT (T78): convierte mensajes ya sellados en filas de `micro_hft/` y marca los tramos
dudosos. Testeable sin red: el proceso `hft_ws` le pasa tuplas de su cola (`handle`) y ella
escribe en un almacén con `add(tipo, hora, fila)`.

- Guarda TODO lo recibido (también los diffs que llegan sin libro), con los dos relojes.
- Mantiene un `VerifiedBook` y escribe el libro completo (`book`) al arrancar, en cada cambio de
  hora y cada vez que se rehace: el conversor parte de ahí y reproduce exactamente este libro.
- Marca (tabla `gaps`), nunca rellena: secuencia rota (`pu`), tramos sin libro, silencios de un
  flujo continuo, desconexiones, mensajes descartados por cola llena, divergencias con el
  snapshot REST e ids de `aggTrade` que faltan. Los reordenamientos se cuentan.
"""

from __future__ import annotations

import json
from collections import Counter

from eim.data.collectors.hft_book import Diff, VerifiedBook, book_hash
from eim.data.collectors.hft_schema import HOUR_NS, kind_of, levels, market_row

# un flujo continuo callado más que esto es un hueco (BTCUSDT: depth 10/s, bbo decenas/s, mark 1/s)
SILENCE_NS = {"depth": 2_000_000_000, "bbo": 5_000_000_000, "mark": 3_000_000_000}
ID_FIELD = {"depth": "u", "bbo": "u", "trades": "a"}


def _split(items) -> tuple[list[float], list[float]]:
    return [p for p, _ in items], [q for _, q in items]


class HftCapture:
    def __init__(self, symbol: str, sink, run_ns: int) -> None:
        self.symbol, self.sink, self.run = symbol.upper(), sink, run_ns
        self.vb = VerifiedBook()
        self.seq = 0
        self.hour: int | None = None
        self.counts: Counter[str] = Counter()
        self.gaps: Counter[str] = Counter()
        self.reorders: Counter[str] = Counter()
        self.last_recv: dict[str, int] = {}
        self.last_id: dict[str, int] = {}
        self.last_e: dict[str, int] = {}
        self.unsynced_since: int | None = run_ns
        self.last_depth_ok = run_ns
        self.checks = Counter()
        self.snaps_handled = 0
        self.last_msg_ms: int | None = None

    # --- utilidades ----------------------------------------------------------
    def _add(self, kind: str, recv: int, mono: int, *fields) -> None:
        self.seq += 1
        self.sink.add(kind, self.hour, (recv, mono, self.run, self.seq, *fields))

    def gap(self, stream: str, cause: str, start: int, end: int, recv: int, mono: int,
            n: int = 1, detail: str = "") -> None:
        self.gaps[cause] += 1
        self._add("gaps", recv, mono, stream, cause, start, end, n, detail[:300])

    def _tick(self, recv: int, mono: int) -> None:
        """Al empezar la corrida o una hora nueva: cierra el tramo sin libro y fija el libro."""
        h = recv // HOUR_NS
        if self.hour is not None and h <= self.hour:
            return
        first = self.hour is None
        self.hour = h
        if not first and self.unsynced_since is not None:
            self.gap("depth", "sin_libro", self.unsynced_since, recv, recv, mono)
            self.unsynced_since = recv
        self._book_row("arranque" if first else "hora", recv, mono)

    def _book_row(self, purpose: str, recv: int, mono: int) -> None:
        bk = self.vb.book
        bp, bq = _split(sorted(bk.bids.items(), reverse=True))
        ap, aq = _split(sorted(bk.asks.items()))
        self._add("book", recv, mono, purpose, bk.last_id,
                  -1 if bk.last_u is None else bk.last_u, bk.synced, bp, bq, ap, aq)

    # --- entrada -------------------------------------------------------------
    def handle(self, item: tuple) -> None:
        """Una tupla de la cola del proceso (ver `hft_ws.Inbox`)."""
        tag = item[0]
        if tag == "msg":
            _, _conn, raw, recv, mono = item
            msg = json.loads(raw)
            self.on_message(msg.get("data", msg), recv, mono)
        elif tag == "snap":
            _, purpose, snap, req, recv, mono = item
            self.on_snapshot(snap, purpose, req, recv, mono)
        elif tag == "close":
            _, conn, err, recv, mono = item
            self._tick(recv, mono)
            self.gap(conn, "desconexion", recv, recv, recv, mono, detail=err)
        elif tag == "overflow":
            _, conn, n, start, end, recv, mono = item
            self._tick(recv, mono)
            self.gap(conn, "cola_llena", start, end, recv, mono, n=n,
                     detail=f"{n} mensajes descartados")
        elif tag == "clock":
            _, kind, jump, wall, recv, mono = item
            self._tick(recv, mono)
            self._add("clock", recv, mono, kind, jump, wall)
        elif tag == "open":
            self.counts["conexiones"] += 1

    def on_message(self, d: dict, recv: int, mono: int) -> None:
        kind = kind_of(d, self.symbol)
        if kind is None:
            return
        self._tick(recv, mono)
        self.counts[kind] += 1
        self.last_msg_ms = recv // 1_000_000
        self._watch(kind, d, recv, mono)
        self.seq += 1
        self.sink.add(kind, self.hour, market_row(kind, d, (recv, mono, self.run, self.seq)))
        if kind == "depth":
            self._depth(d, recv, mono)

    def _watch(self, kind: str, d: dict, recv: int, mono: int) -> None:
        """Silencios, reordenamientos e ids de trades que faltan (antes de guardar la fila)."""
        last = self.last_recv.get(kind)
        if kind in SILENCE_NS and last is not None and recv - last > SILENCE_NS[kind]:
            self.gap(kind, "silencio", last, recv, recv, mono,
                     detail=f"{(recv - last) / 1e9:.1f} s sin mensajes")
        e = int(d.get("E", -1))
        back = e < self.last_e.get(kind, -1)
        self.last_e[kind] = max(e, self.last_e.get(kind, -1))
        f = ID_FIELD.get(kind)
        if f is not None:
            i, prev = int(d[f]), self.last_id.get(kind)
            back |= prev is not None and i <= prev
            if kind == "trades" and prev is not None and i > prev + 1:
                self.gap("trades", "ids_trades", last if last is not None else recv, recv,
                         recv, mono, n=i - prev - 1, detail=f"esperado {prev + 1}, llegó {i}")
            self.last_id[kind] = i if prev is None else max(i, prev)
        self.reorders[kind] += back
        self.last_recv[kind] = recv

    def _depth(self, d: dict, recv: int, mono: int) -> None:
        bp, bq = levels(d["b"])
        ap, aq = levels(d["a"])
        diff = Diff(int(d["U"]), int(d["u"]), int(d["pu"]), list(zip(bp, bq, strict=True)),
                    list(zip(ap, aq, strict=True)))
        before = self.vb.book.last_u
        res = self.vb.on_diff(diff)
        if res == "gap":
            self.gap("depth", "secuencia", self.last_depth_ok, recv, recv, mono,
                     detail=f"pu {diff.prev} ≠ u previo {before}; libro descartado")
            self.unsynced_since = recv
        elif res == "ok":
            self.last_depth_ok = recv
        self._after_book(recv, mono)

    def on_snapshot(self, snap: dict, purpose: str, req: int, recv: int, mono: int) -> None:
        self._tick(recv, mono)
        bp, bq = levels(snap["bids"])
        ap, aq = levels(snap["asks"])
        last_id = int(snap["lastUpdateId"])
        self._add("snap", recv, mono, req, int(snap.get("E", -1)), int(snap.get("T", -1)),
                  last_id, purpose, bp, bq, ap, aq)
        res = self.vb.on_snapshot(last_id, snap["bids"], snap["asks"])
        self.snaps_handled += 1
        self.counts[f"snap_{res}"] += 1
        self._after_book(recv, mono)

    def _after_book(self, recv: int, mono: int) -> None:
        reset, self.vb.reset = self.vb.reset, None
        if reset is not None:
            self._book_row(reset, recv, mono)
            if reset == "sync" and self.unsynced_since is not None:
                self.gap("depth", "sin_libro", self.unsynced_since, recv, recv, mono)
                self.unsynced_since = None
                self.last_depth_ok = recv
            elif reset == "divergencia":
                self.gap("depth", "divergencia", recv, recv, recv, mono,
                         detail="el libro local no coincidía con el snapshot REST; rehecho")
            if self.vb.awaiting and self.unsynced_since is None:
                self.unsynced_since = recv
        if self.vb.checks:
            h = book_hash(self.vb.book.bids, self.vb.book.asks)
            for c in self.vb.checks:
                self.checks["total"] += 1
                self.checks["comparables"] += c.comparable
                self.checks["coinciden"] += c.match
                self._add("checks", recv, mono, c.snap_id, c.at_id, c.comparable, c.match,
                          c.n_diff, h, c.detail)
            self.vb.checks.clear()

    # --- estado --------------------------------------------------------------
    def wants_sync(self) -> bool:
        """Hace falta snapshot y ya hay diffs acumulados (procedimiento de Binance: primero el
        flujo, luego el snapshot; pedido antes, sería más viejo que el primer diff)."""
        return self.vb.awaiting and bool(self.vb.pending)

    def status(self) -> dict:
        """Resumen para el latido."""
        comp = self.checks["comparables"]
        return {"counts": dict(self.counts), "gaps": dict(self.gaps),
                "reorders": dict(self.reorders), "synced": self.vb.book.synced,
                "awaiting_snapshot": self.vb.awaiting, "pending_dropped": self.vb.pending_dropped,
                "checks": dict(self.checks),
                "match_rate": round(self.checks["coinciden"] / comp, 4) if comp else None,
                "ghosts_pruned": self.vb.book.ghosts_pruned, "last_msg_ms": self.last_msg_ms}
