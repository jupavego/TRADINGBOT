"""Constructores de escenarios sintéticos para el scorecard (T41): sin red, deterministas."""

from __future__ import annotations

import random

from eim.core.leaders import FollowQuote, Leader, LeaderFill, LeaderPosition, leader_id

ADDR = "0x" + "ab" * 20
LID = leader_id("hyperliquid", ADDR)
DAY = 86_400_000
T0 = 1_790_000_000_000


def leader(addr: str = ADDR, status: str = "watch") -> Leader:
    return Leader(id=leader_id("hyperliquid", addr), venue="hyperliquid", address=addr,
                  origin="manual", status=status, discovered_at=0, source="test")


def fill(symbol: str, start: float, end: float, price: float, t: int, tid: int, *,
         pnl: float = 0.0, fee: float = 0.0, lid: str = LID, lev: float | None = 5.0,
         delay: int = 200, channel: str = "ws", liquidated: bool = False,
         crossed: bool = True) -> LeaderFill:
    """Ejecución que lleva la posición firmada de `start` a `end`."""
    if start == 0:
        action, side = "open", "long" if end > 0 else "short"
    elif end == 0:
        action, side = "close", "long" if start > 0 else "short"
    elif (start > 0) != (end > 0):
        action, side = "flip", "long" if end > 0 else "short"
    elif abs(end) > abs(start):
        action, side = "increase", "long" if end > 0 else "short"
    else:
        action, side = "reduce", "long" if start > 0 else "short"
    size = abs(end - start)
    return LeaderFill(leader_id=lid, address=lid.split(":")[1], symbol=symbol, side=side,
                      action=action, size=size, price=price, start_position=start,
                      end_position=end, fee=fee, closed_pnl=pnl, crossed=crossed,
                      liquidated=liquidated, leverage=lev, tid=tid, oid=tid, t=t,
                      observed_at=t + delay, channel=channel, source="test")


def trip(symbol: str, side: str, size: float, entry: float, exit_: float, t: int, hold: int,
         tid: int, fee_rate: float = 0.0002, **kw) -> list[LeaderFill]:
    """Operación completa de apertura y cierre con su PnL cerrado."""
    s = size if side == "long" else -size
    pnl = (exit_ - entry) * s
    return [fill(symbol, 0.0, s, entry, t, tid, fee=size * entry * fee_rate, **kw),
            fill(symbol, s, 0.0, exit_, t + hold, tid + 1, pnl=pnl,
                 fee=size * exit_ * fee_rate, **kw)]


def series(n: int, start: int, span_ms: int, edge: float, noise: float, seed: int = 7,
           symbols: tuple[str, ...] = ("BTC", "ETH"), size_usd: float = 10_000.0,
           tid0: int = 1, **kw) -> list[LeaderFill]:
    """`n` operaciones repartidas en `span_ms`, retorno por operación ~ N(edge, noise)."""
    rng = random.Random(seed)
    out: list[LeaderFill] = []
    step = span_ms // n
    for i in range(n):
        sym = symbols[i % len(symbols)]
        px = 50_000.0 if sym == "BTC" else 2_500.0
        side = "long" if i % 2 == 0 else "short"
        r = rng.gauss(edge, noise)
        exit_ = px * (1 + r) if side == "long" else px * (1 - r)
        out += trip(sym, side, size_usd / px, px, exit_, start + i * step, step // 2,
                    tid0 + 2 * i, **kw)
    return out


def quotes(fills: list[LeaderFill], adverse_bps: float = 1.0, delay: int = 300,
           src: str = "bbo") -> dict[tuple[int, int], FollowQuote]:
    """Cotización del seguidor alrededor del precio del líder, `adverse_bps` en su contra."""
    out = {}
    for f in fills:
        buy = (f.side == "long") == (f.action in ("open", "increase", "flip"))
        px = f.price * (1 + adverse_bps / 1e4 * (1 if buy else -1))
        bid, ask = (px * 0.99999, px) if buy else (px, px * 1.00001)
        out[(f.tid, f.oid)] = FollowQuote(
            leader_id=f.leader_id, tid=f.tid, oid=f.oid, symbol=f.symbol,
            observed_at=f.observed_at, follow_at=f.observed_at + delay,
            quote_t=f.observed_at + delay - 50, bid=bid if src == "bbo" else None,
            ask=ask if src == "bbo" else None, mid=(bid + ask) / 2, src=src)
    return out


def portfolio(days: int, av: float = 1_000_000.0, daily: float = 0.002, dd_at: int | None = None,
              dd: float = 0.0, t_end: int = T0) -> list:
    """Respuesta `portfolio` con `perpAllTime` semanal: crece `daily` por día (compuesto)."""
    pts_av, pts_pnl, pnl, v = [], [], 0.0, av
    for k in range(0, days + 1, 7):
        t = t_end - (days - k) * DAY
        if k:
            g = v * ((1 + daily) ** 7 - 1)
            if dd_at is not None and k // 7 == dd_at:
                g = -v * dd
            pnl += g
            v += g
        pts_av.append([t, str(v)])
        pts_pnl.append([t, str(pnl)])
    return [["perpAllTime", {"accountValueHistory": pts_av, "pnlHistory": pts_pnl,
                             "vlm": "1000000.0"}]]


def position(symbol: str, side: str, size: float, entry: float, t: int, *, upnl: float = 0.0,
             lid: str = LID, lev: float = 5.0) -> LeaderPosition:
    return LeaderPosition(leader_id=lid, address=lid.split(":")[1], symbol=symbol, side=side,
                          size=size, entry=entry, leverage=lev, unrealized_pnl=upnl, t=t,
                          observed_at=t + 100, source="test")
