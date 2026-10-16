"""Servicio de líderes (T41): vigilante de T40 + precio del seguidor + evaluación periódica.

- Segunda conexión WS (no cuenta en el límite de 10 usuarios): `bbo` de las monedas que
  operan los líderes y `allMids` para el resto → `leader_follow` (copiabilidad).
- `portfolio` de cada líder capturado cada 6 h (dos líderes por minuto para no gastar el
  presupuesto de peso) → preselección.
- Cada `score_every_s` evalúa a todos (en un hilo) y guarda el tablero en `data/leaders/`;
  también al cerrar. Solo lectura de datos públicos: no hay órdenes.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from eim.copytrading import ScoreParams
from eim.core.leaders import Leader
from eim.data.leader_board import BoardStore
from eim.data.leader_eval import evaluate, refresh_portfolios
from eim.data.leader_quotes import QuoteBook
from eim.data.leader_store import LeaderStore
from eim.data.leader_watch import LeaderWatch
from eim.data.providers.leaders import HyperliquidInfo, HyperliquidStream
from eim.leaders import params as P
from eim.leaders.parse import is_perp

QUOTE_COINS_MAX = 60  # suscripciones `bbo` (el límite oficial por IP es 1000)
PORTFOLIO_PER_TICK = 2  # `portfolio` pesa 20: dos por minuto no compiten con la captura
DAY_MS = 86_400_000


class LeaderService(LeaderWatch):
    def __init__(self, store: LeaderStore, info: HyperliquidInfo, leaders: list[Leader], *,
                 root: str | Path, params: ScoreParams | None = None,
                 quote_coins: list[str] | None = None, score_every_s: float = 300.0,
                 first_score_s: float = 60.0, portfolio_every_s: float = 60.0,
                 **kw) -> None:
        super().__init__(store, info, leaders, **kw)
        self.p = params or ScoreParams()
        self.boards = BoardStore(root)
        coins = quote_coins if quote_coins is not None else self._coins()
        self.quotes = QuoteBook(coins, self.p.exec_delay_ms, self.p.live_max_latency_ms)
        self.score_every_s, self.portfolio_every_s = score_every_s, portfolio_every_s
        start = time.monotonic()
        self._next = {"score": start + first_score_s, "portfolio": start}
        self.boards_saved = 0

    def _coins(self) -> list[str]:
        """Monedas operadas por los capturados en el último día + BTC/ETH."""
        recent = self.store.recent_coins(self.now() - DAY_MS)
        coins = sorted(c for c in recent if is_perp(c))
        base = [c for c in P.DISCOVERY_COINS if c not in coins]
        return (base + coins)[:QUOTE_COINS_MAX]

    # --- ganchos del vigilante ----------------------------------------------------------------
    def on_fills(self, fills: list) -> None:
        self.quotes.expect(fills)

    def on_quote(self, msg: dict, observed_at: int) -> None:
        ch = msg.get("channel")
        if ch == "bbo":
            got = self.quotes.on_bbo(msg.get("data") or {}, observed_at)
        elif ch == "allMids":
            got = self.quotes.on_mids((msg.get("data") or {}).get("mids") or {}, observed_at)
        else:
            return
        if got:
            self.store.add_follow(got)

    def extra_streams(self) -> list[HyperliquidStream]:
        subs = [{"type": "bbo", "coin": c} for c in sorted(self.quotes.bbo_coins)]
        subs.append({"type": "allMids"})
        return [HyperliquidStream(subs, self.on_quote, clock=self.now, **self.stream_kw)]

    async def extra_jobs(self) -> None:
        got = self.quotes.flush(self.now())
        if got:
            self.store.add_follow(got)
        now = time.monotonic()
        if now >= self._next["portfolio"]:
            self._next["portfolio"] = now + self.portfolio_every_s
            await self._safe("portfolio", asyncio.to_thread(
                refresh_portfolios, self.store, self.info, self.now(), PORTFOLIO_PER_TICK))
        if now >= self._next["score"]:
            self._next["score"] = now + self.score_every_s
            await self._safe("evaluación", self.score_now())

    async def score_now(self) -> None:
        board = await asyncio.to_thread(evaluate, self.store, self.now(), self.p)
        self.boards.save(board)
        self.boards_saved += 1

    async def run(self, stop: asyncio.Event, minutes: float | None = None) -> None:
        await super().run(stop, minutes)
        await self._safe("evaluación final", self.score_now())
