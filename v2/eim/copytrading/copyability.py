"""Copiabilidad (puro): lo que habría obtenido un seguidor, no el líder.

El seguidor se entera de cada ejecución en `observed_at` (latencia de captura medida) y su
orden llega `exec_delay_ms` después: compra al `ask` y vende al `bid` vigentes en ese
instante (`FollowQuote`, grabado en vivo por el vigilante) y paga comisión de tomador.
Solo cuentan operaciones adelante con **todas** sus patas cotizadas.
"""

from __future__ import annotations

from collections import defaultdict

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


def _q(xs: list[float]) -> dict[str, float | None]:
    return {"p50": quantile(xs, 0.5), "p90": quantile(xs, 0.9), "p99": quantile(xs, 0.99),
            "max": max(xs) if xs else None}


def _price(leg: Leg, q: FollowQuote, p: ScoreParams) -> float:
    if q.bid is not None and q.ask is not None:
        return q.ask if leg.buy else q.bid
    return q.mid * (1 + p.allmids_half_spread if leg.buy else 1 - p.allmids_half_spread)


def latency(fills: list[LeaderFill], p: ScoreParams) -> tuple[int, dict, dict]:
    """Latencia de captura de las ejecuciones vistas en vivo (no el historial reenviado)."""
    live = [f for f in fills if f.channel != "ws_snapshot"
            and 0 <= f.latency_ms <= p.live_max_latency_ms]
    by: dict[str, list[float]] = defaultdict(list)
    for f in live:
        by[f.channel].append(float(f.latency_ms))
    per = {ch: {"n": float(len(xs)), "p50": quantile(xs, 0.5), "p90": quantile(xs, 0.9)}
           for ch, xs in sorted(by.items())}
    return len(live), _q([float(f.latency_ms) for f in live]), per


def copy_stats(fwd: list[Trip], fills: list[LeaderFill],
               quotes: dict[tuple[int, int], FollowQuote], p: ScoreParams) -> CopyStats:
    n_live, lat, per = latency(fills, p)
    slips: list[float] = []
    src: dict[str, int] = defaultdict(int)
    stale = quoted = unquoted = 0
    trades = 0
    l_net = f_net = f_fees = notional = 0.0
    for tr in (t for t in fwd if t.closed and t.complete):
        cash = fees = 0.0
        ok = True
        for leg in tr.legs:
            q = quotes.get((leg.fill.tid, leg.fill.oid))
            if q is None:
                ok = False
                continue
            if q.follow_at - q.quote_t > p.quote_timeout_ms:
                stale += 1
                ok = False
                continue
            quoted += 1
            src[q.src] += 1
            px = _price(leg, q, p)
            slips.append((px - leg.fill.price) / leg.fill.price * 1e4 * (1 if leg.buy else -1))
            cash += -leg.qty * px if leg.buy else leg.qty * px
            fees += leg.qty * px * p.follower_taker_fee
        if not ok:
            unquoted += 1
            continue
        trades += 1
        l_net += tr.net
        f_net += cash - fees + tr.funding
        f_fees += fees
        notional += tr.notional_max
    taker = [f.crossed for f in fills if f.channel != "ws_snapshot"]
    return CopyStats(
        delay_ms=p.exec_delay_ms, live_fills=n_live, latency_ms=lat, latency_by_channel=per,
        quoted_fills=quoted, stale_quotes=stale, quote_src=dict(src),
        slip_bps={"p50": quantile(slips, 0.5), "p90": quantile(slips, 0.9),
                  "mean": sum(slips) / len(slips) if slips else None},
        trades=trades, unquoted_trades=unquoted, leader_net=l_net, follower_net=f_net,
        follower_fees=f_fees, retention=f_net / l_net if trades and l_net > 0 else None,
        follower_mean=f_net / trades if trades else None,
        follower_bps=f_net / notional * 1e4 if notional else None,
        taker_share=sum(taker) / len(taker) if taker else None)
