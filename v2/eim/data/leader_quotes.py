"""Precio del seguidor (T41): cotizaciones vivas → `FollowQuote` por ejecución del líder.

WS oficial `bbo` (mejor compra/venta, cada cambio) para las monedas que operan los líderes y
`allMids` (precio medio de todo, cada pocos segundos) para el resto. Cada ejecución vista en
vivo queda pendiente hasta `due = observed_at + retraso de orden`; se le asigna la cotización
**vigente en `due`**: la última recibida antes. Por eso se liquida justo antes de aplicar
una cotización nueva (la vieja era la vigente) o cuando pasa un rato sin mensajes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from eim.core.leaders import FollowQuote, LeaderFill
from eim.leaders.parse import is_perp

DROP_AFTER_MS = 60_000  # pendiente sin ninguna cotización en este tiempo: se descarta


@dataclass(frozen=True)
class _Pending:
    fill: LeaderFill
    due: int


@dataclass(frozen=True)
class _Bbo:
    t: int  # hora del exchange
    bid: float | None
    ask: float | None


def _px(level: dict | None) -> float | None:
    return float(level["px"]) if level else None


class QuoteBook:
    def __init__(self, bbo_coins: Iterable[str], delay_ms: int, live_max_ms: int) -> None:
        self.bbo_coins = set(bbo_coins)
        self.delay_ms, self.live_max_ms = delay_ms, live_max_ms
        self.bbo: dict[str, _Bbo] = {}
        self.mids: dict[str, tuple[int, float]] = {}  # moneda → (recibido, medio)
        self.pending: dict[str, list[_Pending]] = defaultdict(list)
        self.dropped = 0

    def expect(self, fills: Iterable[LeaderFill]) -> int:
        """Registra las ejecuciones vistas en vivo (no el historial reenviado ni el relleno
        de algo viejo: un seguidor no las habría podido copiar)."""
        n = 0
        for f in fills:
            if f.channel == "ws_snapshot" or not 0 <= f.latency_ms <= self.live_max_ms:
                continue
            if not is_perp(f.symbol):
                continue
            self.pending[f.symbol].append(_Pending(f, f.observed_at + self.delay_ms))
            n += 1
        return n

    def on_bbo(self, data: dict, observed_at: int) -> list[FollowQuote]:
        coin = str(data.get("coin", ""))
        levels = data.get("bbo") or [None, None]
        out = self._settle(coin, observed_at)
        self.bbo[coin] = _Bbo(int(data.get("time") or observed_at), _px(levels[0]),
                              _px(levels[1]))
        return out

    def on_mids(self, mids: dict, observed_at: int) -> list[FollowQuote]:
        out = []
        for coin in [c for c in self.pending if c not in self.bbo_coins]:
            out += self._settle(coin, observed_at)
        for coin, v in mids.items():
            if not coin.startswith("@"):
                self.mids[coin] = (observed_at, float(v))
        return out

    def flush(self, now: int, quiet_ms: int = 1_000) -> list[FollowQuote]:
        """Pendientes vencidos hace `quiet_ms` sin cotización nueva: la última sigue vigente."""
        out = []
        for coin in list(self.pending):
            out += self._settle(coin, now - quiet_ms)
        return out

    def _quote(self, coin: str, p: _Pending) -> FollowQuote | None:
        f = p.fill
        base = {"leader_id": f.leader_id, "tid": f.tid, "oid": f.oid, "symbol": coin,
                "observed_at": f.observed_at, "follow_at": p.due}
        b = self.bbo.get(coin)
        if coin in self.bbo_coins and b is not None and (b.bid or b.ask):
            mid = (b.bid + b.ask) / 2 if b.bid and b.ask else (b.bid or b.ask)
            return FollowQuote(**base, quote_t=b.t, bid=b.bid, ask=b.ask, mid=mid, src="bbo")
        m = self.mids.get(coin)
        if m is not None:
            return FollowQuote(**base, quote_t=m[0], mid=m[1], src="allMids")
        return None

    def _settle(self, coin: str, upto: int) -> list[FollowQuote]:
        ps = self.pending.get(coin)
        if not ps:
            return []
        out, keep = [], []
        for p in ps:
            if p.due > upto:
                keep.append(p)
                continue
            q = self._quote(coin, p)
            if q is not None:
                out.append(q)
            elif upto - p.due > DROP_AFTER_MS:
                self.dropped += 1
            else:
                keep.append(p)
        if keep:
            self.pending[coin] = keep
        else:
            del self.pending[coin]
        return out
