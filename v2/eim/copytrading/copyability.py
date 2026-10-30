"""Copiabilidad (puro): lo que habría obtenido un seguidor, no el líder.

El seguidor se entera de cada ejecución en `observed_at` (latencia de captura medida) y su
orden llega `exec_delay_ms` después: compra al `ask` y vende al `bid` vigentes en ese
instante (`FollowQuote`, grabado en vivo por el vigilante) y paga comisión de tomador.
Solo cuentan operaciones adelante con **todas** sus patas cotizadas. `TripFollow` acumula un
viaje pata a pata; la evaluación incremental (`trip_fold.py`) lo guarda y suelta las patas.
"""

from __future__ import annotations

from array import array
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from eim.copytrading.params import ScoreParams
from eim.copytrading.stats import quantile
from eim.copytrading.trades import Leg, Trip
from eim.core.leaders import FollowQuote, LeaderFill
from eim.core.market import Frozen


class CopyStats(Frozen):
    delay_ms: int
    live_fills: int = 0  # ejecuciones vistas en vivo (latencia ≤ máximo)
    latency_ms: dict[str, float | None] = {}  # p50, p90, p99, max
    latency_by_channel: dict[str, dict[str, float | None]] = {}
    quoted_fills: int = 0
    stale_quotes: int = 0
    quote_src: dict[str, int] = {}  # bbo / allMids
    slip_bps: dict[str, float | None] = {}  # p50, p90, mean (adverso > 0)
    trades: int = 0  # operaciones adelante con todas las patas cotizadas
    unquoted_trades: int = 0
    leader_net: float = 0.0  # neto del líder en esas mismas operaciones
    follower_net: float = 0.0
    follower_fees: float = 0.0
    retention: float | None = None  # neto del seguidor / neto del líder (si el líder gana)
    follower_mean: float | None = None
    follower_bps: float | None = None  # neto del seguidor / nocional
    taker_share: float | None = None  # del líder: un creador de mercado no se copia


def _q(xs: Sequence[float]) -> dict[str, float | None]:
    return {"p50": quantile(xs, 0.5), "p90": quantile(xs, 0.9), "p99": quantile(xs, 0.99),
            "max": max(xs) if xs else None}


def _price(leg: Leg, q: FollowQuote, p: ScoreParams) -> float:
    if q.bid is not None and q.ask is not None:
        return q.ask if leg.buy else q.bid
    return q.mid * (1 + p.allmids_half_spread if leg.buy else 1 - p.allmids_half_spread)


@dataclass
class TripFollow:
    """Lo que habría hecho un seguidor en las patas de UN viaje, en su orden. Basta una pata
    sin cotización (o con cotización vieja) para que el viaje no cuente (`ok` falso)."""

    ok: bool = True
    stale: int = 0
    quoted: int = 0
    src: dict[str, int] = field(default_factory=dict)
    slips: array = field(default_factory=lambda: array("d"))  # pb, adverso > 0
    cash: float = 0.0
    fees: float = 0.0

    def add(self, leg: Leg, q: FollowQuote | None, p: ScoreParams) -> None:
        if q is None:
            self.ok = False
            return
        if q.follow_at - q.quote_t > p.quote_timeout_ms:
            self.stale += 1
            self.ok = False
            return
        self.quoted += 1
        self.src[q.src] = self.src.get(q.src, 0) + 1
        px = _price(leg, q, p)
        self.slips.append((px - leg.fill.price) / leg.fill.price * 1e4 * (1 if leg.buy else -1))
        self.cash += -leg.qty * px if leg.buy else leg.qty * px
        self.fees += leg.qty * px * p.follower_taker_fee

    def copy(self) -> TripFollow:
        return TripFollow(self.ok, self.stale, self.quoted, dict(self.src), array("d", self.slips),
                          self.cash, self.fees)


def latency_stats(by: dict[str, Sequence[float]]) -> tuple[int, dict, dict]:
    """(n, cuantiles, por canal) de las latencias en vivo ya separadas por canal."""
    per = {}
    for ch, xs in sorted(by.items()):  # ordenadas una vez: `quantile` reordena en O(n)
        s = sorted(xs)
        per[ch] = {"n": float(len(s)), "p50": quantile(s, 0.5), "p90": quantile(s, 0.9)}
    every = sorted(x for xs in by.values() for x in xs)
    return len(every), _q(every), per


def latency(fills: list[LeaderFill], p: ScoreParams) -> tuple[int, dict, dict]:
    """Latencia de captura de las ejecuciones vistas en vivo (no el historial reenviado)."""
    by: dict[str, list[float]] = defaultdict(list)
    for f in fills:
        if f.channel != "ws_snapshot" and 0 <= f.latency_ms <= p.live_max_latency_ms:
            by[f.channel].append(float(f.latency_ms))
    return latency_stats(by)


def finish(follows: list[tuple[Trip, TripFollow]], lat: tuple[int, dict, dict],
           taker: tuple[int, int], p: ScoreParams) -> CopyStats:
    """Une las operaciones adelante cerradas (con su seguidor) en las cifras de copiabilidad.
    `taker` = (ejecuciones tomadoras, ejecuciones) fuera del historial reenviado."""
    slips: list[float] = []
    src: dict[str, int] = {}
    stale = quoted = unquoted = trades = 0
    l_net = f_net = f_fees = notional = 0.0
    for tr, acc in follows:
        stale += acc.stale
        quoted += acc.quoted
        for k, v in acc.src.items():
            src[k] = src.get(k, 0) + v
        slips.extend(acc.slips)
        if not acc.ok:
            unquoted += 1
            continue
        trades += 1
        l_net += tr.net
        f_net += acc.cash - acc.fees + tr.funding
        f_fees += acc.fees
        notional += tr.notional_max
    n_live, latency_ms, per = lat
    ordered = sorted(slips)  # una sola ordenación grande (retiene el GIL); la media, en orden
    return CopyStats(
        delay_ms=p.exec_delay_ms, live_fills=n_live, latency_ms=latency_ms,
        latency_by_channel=per, quoted_fills=quoted, stale_quotes=stale, quote_src=src,
        slip_bps={"p50": quantile(ordered, 0.5), "p90": quantile(ordered, 0.9),
                  "mean": sum(slips) / len(slips) if slips else None},
        trades=trades, unquoted_trades=unquoted, leader_net=l_net, follower_net=f_net,
        follower_fees=f_fees, retention=f_net / l_net if trades and l_net > 0 else None,
        follower_mean=f_net / trades if trades else None,
        follower_bps=f_net / notional * 1e4 if notional else None,
        taker_share=taker[0] / taker[1] if taker[1] else None)


def copy_stats(fwd: list[Trip], fills: list[LeaderFill],
               quotes: dict[tuple[int, int], FollowQuote], p: ScoreParams) -> CopyStats:
    follows = []
    for tr in (t for t in fwd if t.closed and t.complete):
        acc = TripFollow()
        for leg in tr.legs:
            acc.add(leg, quotes.get((leg.fill.tid, leg.fill.oid)), p)
        follows.append((tr, acc))
    live = [f.crossed for f in fills if f.channel != "ws_snapshot"]
    return finish(follows, latency(fills, p), (sum(live), len(live)), p)
