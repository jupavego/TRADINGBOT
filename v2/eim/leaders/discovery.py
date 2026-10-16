"""Descubrimiento de candidatos (puro): muestra del WS oficial `trades` → direcciones activas.

Hyperliquid no tiene leaderboard oficial (T33 §1): cada operación del WS `trades` trae
`users = [comprador, vendedor]` y `side` = lado del agresor. Esto **no evalúa** al trader
(eso es T41); solo filtra ruido (poco volumen, creadores de mercado puros, direcciones del
sistema) y deja evidencia de lo visto.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from eim.core.leaders import Leader, leader_id
from eim.leaders import params as P


@dataclass
class TraderSample:
    address: str
    trades: int = 0
    taker: int = 0
    notional: float = 0.0
    coins: set[str] = field(default_factory=set)
    first_t: int = 0
    last_t: int = 0

    @property
    def taker_share(self) -> float:
        return self.taker / self.trades if self.trades else 0.0


def aggregate(messages: Iterable[dict], samples: dict[str, TraderSample] | None = None
              ) -> dict[str, TraderSample]:
    """Acumula mensajes `{"channel": "trades", "data": [...]}` por dirección."""
    out = samples if samples is not None else {}
    for msg in messages:
        if msg.get("channel") != "trades":
            continue
        for tr in msg.get("data") or []:
            users = [str(u).lower() for u in tr.get("users") or []]
            if len(users) != 2:
                continue
            aggressor = users[0] if tr.get("side") == "B" else users[1]
            notional, t = float(tr["px"]) * float(tr["sz"]), int(tr["time"])
            for u in set(users):
                s = out.setdefault(u, TraderSample(u, first_t=t, last_t=t))
                s.trades += 1
                s.taker += u == aggressor
                s.notional += notional
                s.coins.add(str(tr.get("coin", "")))
                s.first_t, s.last_t = min(s.first_t, t), max(s.last_t, t)
    return out


def rank(samples: dict[str, TraderSample], now: int, *, window_s: float,
         min_trades: int = P.DISCOVERY_MIN_TRADES,
         min_notional: float = P.DISCOVERY_MIN_NOTIONAL,
         min_taker_share: float = P.DISCOVERY_MIN_TAKER_SHARE,
         top: int = P.DISCOVERY_TOP, exclude: Iterable[str] = P.EXCLUDED) -> list[Leader]:
    """Candidatos ordenados por nocional visto (desc.), con la evidencia de la muestra."""
    skip = {a.lower() for a in exclude}
    ok = [s for s in samples.values()
          if s.address not in skip and s.address.startswith("0x") and len(s.address) == 42
          and s.trades >= min_trades and s.notional >= min_notional
          and s.taker_share >= min_taker_share]
    ok.sort(key=lambda s: (-s.notional, s.address))
    return [Leader(id=leader_id("hyperliquid", s.address), venue="hyperliquid",
                   address=s.address, origin="trades_ws", discovered_at=now,
                   source=f"{P.SOURCE}:ws.trades",
                   evidence={"trades": float(s.trades), "notional_usd": round(s.notional, 2),
                             "taker_share": round(s.taker_share, 4),
                             "coins": ",".join(sorted(s.coins)), "window_s": float(window_s),
                             "universe": float(len(samples))})  # direcciones vistas (T41)
            for s in ok[:top]]
