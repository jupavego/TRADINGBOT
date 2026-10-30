"""Flujo sintético e irregular de un líder muy activo (evaluación incremental, T41): giros,
cierres, huecos, varias ejecuciones en el mismo milisegundo con `tid` desordenado, rellenos
tardíos (`observed_at` muy posterior a `t`) y cotizaciones que llegan tarde, viejas o nunca."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from eim.core.leaders import FollowQuote, LeaderFill, LeaderFunding
from tests.copytrading import helpers as H

HOUR = 3_600_000


@dataclass
class Stream:
    fills: list[LeaderFill] = field(default_factory=list)
    held: list[LeaderFill] = field(default_factory=list)  # huecos: llegarían por otra vía
    quotes: list[tuple[int, FollowQuote]] = field(default_factory=list)  # (grabada en, cot.)
    funding: list[LeaderFunding] = field(default_factory=list)
    end: int = 0


def _next_position(rng: random.Random, start: float) -> float:
    if start == 0:
        return rng.choice([-1.0, 1.0]) * rng.randint(1, 5)
    sign, r = math.copysign(1.0, start), rng.random()
    if r < 0.2 or (r < 0.6 and abs(start) <= 1):
        return 0.0  # cierre
    if r < 0.3:
        return -sign * rng.randint(1, 5)  # giro
    if r < 0.6:
        return start - sign * rng.randint(1, int(abs(start)) - 1)  # reducción
    return start + sign * rng.randint(1, 3)  # aumento


def _quote(rng: random.Random, f: LeaderFill) -> tuple[int, FollowQuote]:
    follow = f.observed_at + 300
    src = rng.choice(["bbo", "bbo", "allMids"])
    px = f.price * (1 + rng.gauss(0, 3e-4))
    q = FollowQuote(leader_id=f.leader_id, tid=f.tid, oid=f.oid, symbol=f.symbol,
                    observed_at=f.observed_at, follow_at=follow,
                    quote_t=follow - rng.choice([50, 400, 2_000, 16_000]),  # 16 s: vieja
                    bid=px * 0.9999 if src == "bbo" else None,
                    ask=px * 1.0001 if src == "bbo" else None, mid=px, src=src)
    return f.observed_at + rng.randint(300, 65_000), q


def stream(n: int = 700, seed: int = 3, t0: int = H.T0, symbols=("BTC", "ETH", "SOL"),
           step_ms: int = 20_000) -> Stream:
    rng = random.Random(seed)
    pos = dict.fromkeys(symbols, 0.0)
    px = {"BTC": 60_000.0, "ETH": 3_000.0, "SOL": 150.0}
    out, t, tid = Stream(), t0, 1
    for i in range(n):
        t += rng.randint(1, step_ms)
        sym = rng.choice(symbols)
        k = 1 if rng.random() > 0.12 else rng.randint(2, 3)  # mismo milisegundo
        tids = list(range(tid, tid + k))
        rng.shuffle(tids)  # el `tid` no sigue la cadena de posiciones
        tid += k
        for j in range(k):
            start = pos[sym]
            end = pos[sym] = _next_position(rng, start)
            px[sym] *= 1 + rng.gauss(0, 0.002)
            r = rng.random()
            channel, delay = "ws", rng.randint(50, 1_500)
            if i < 5:
                channel = "ws_snapshot"
            elif r < 0.06:
                channel, delay = "rest_backfill", rng.randint(30_000, 900_000)  # relleno tardío
            elif r < 0.08:
                delay = rng.randint(121_000, 300_000)  # vista tarde: no es «en vivo»
            f = H.fill(sym, start, end, px[sym], t, tids[j], pnl=rng.gauss(0, 50),
                       fee=abs(end - start) * px[sym] * rng.choice([2e-4, 4.5e-4, -1e-4]),
                       lev=rng.choice([None, 3.0, 5.0, 10.0]), delay=delay, channel=channel,
                       crossed=rng.random() < 0.6, liquidated=rng.random() < 0.01)
            if i > 5 and rng.random() < 0.03:
                out.held.append(f)  # hueco en la captura
                continue
            out.fills.append(f)
            if channel != "ws_snapshot" and delay <= 120_000 and rng.random() < 0.9:
                out.quotes.append(_quote(rng, f))
    out.end = t + HOUR
    for h in range(t0 - t0 % HOUR + HOUR, out.end, HOUR):
        for sym in symbols:
            out.funding.append(LeaderFunding(
                leader_id=H.LID, address=H.ADDR, symbol=sym, usdc=rng.gauss(0, 3), rate=1e-5,
                size=1.0, t=h, observed_at=h + rng.randint(1_000, 900_000), source="test"))
    return out
