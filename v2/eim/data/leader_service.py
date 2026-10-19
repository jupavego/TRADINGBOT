"""Servicio de líderes (T41): vigilante de T40 + precio del seguidor + evaluación periódica.

- Segunda conexión WS (no cuenta en el límite de 10 usuarios): `bbo` de las monedas que
  operan los líderes y `allMids` para el resto → `leader_follow` (copiabilidad).
- `portfolio` de cada líder capturado cada 6 h (dos líderes por minuto para no gastar el
  presupuesto de peso) → preselección.
- Cada `score_every_s` evalúa a todos (en un hilo) y guarda el tablero en `data/leaders/`;
  también al cerrar. Solo lectura de datos públicos: no hay órdenes.
- Copia simulada en vivo (T42, `copy_mode` ≠ `off`): una subcuenta virtual por líder con
  las mismas ejecuciones, cotizaciones, marcas y reconciliaciones (`copy_live.py`).
- Latido en `data/leaders/heartbeat.json` (como mucho cada `HEARTBEAT_EVERY_S`) cada vez que
  termina una tarea, bien o mal: el vigilante de proceso (`python -m eim.leaders supervise`)
  relanza el servicio si nada termina en 15 min. Por tarea y no por vuelta del bucle: tras un
  apagado largo la primera vuelta (arranque de cada líder con relleno) puede tardar minutos.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from eim.copytrading import ScoreParams
from eim.copytrading.copy_models import ExecQuote
from eim.copytrading.copy_params import CopyParams
from eim.copytrading.copy_risk import copy_config
from eim.core.leaders import Leader
from eim.data.copy_live import CopyLive
from eim.data.copy_store import take_snapshot_request
from eim.data.hl_market import exchange_spec
from eim.data.leader_board import BoardStore
from eim.data.leader_eval import evaluate, refresh_portfolios
from eim.data.leader_quotes import QuoteBook
from eim.data.leader_store import LeaderStore
from eim.data.leader_watch import LeaderWatch
from eim.data.providers.leaders import HyperliquidInfo, HyperliquidStream
from eim.leaders import params as P
from eim.leaders.parse import is_perp
from eim.operation.alerts import Alert
from eim.operation.notify import JsonLog, WindowsToast

QUOTE_COINS_MAX = 60  # suscripciones `bbo` (el límite oficial por IP es 1000)
PORTFOLIO_PER_TICK = 2  # `portfolio` pesa 20: dos por minuto no compiten con la captura
DAY_MS = 86_400_000
HEARTBEAT_EVERY_S = 30.0
HEARTBEAT = "heartbeat.json"

log = logging.getLogger(__name__)


class LeaderService(LeaderWatch):
    def __init__(self, store: LeaderStore, info: HyperliquidInfo, leaders: list[Leader], *,
                 root: str | Path, params: ScoreParams | None = None,
                 quote_coins: list[str] | None = None, score_every_s: float = 300.0,
                 first_score_s: float = 60.0, portfolio_every_s: float = 60.0,
                 copy_mode: str = "off", copy_params: CopyParams | None = None,
                 **kw) -> None:
        super().__init__(store, info, leaders, **kw)
        self.root = root
        self.p = params or ScoreParams()
        self.boards = BoardStore(root)
        coins = quote_coins if quote_coins is not None else self._coins()
        self.quotes = QuoteBook(coins, self.p.exec_delay_ms, self.p.live_max_latency_ms)
        self.score_every_s, self.portfolio_every_s = score_every_s, portfolio_every_s
        start = time.monotonic()
        self._next = {"score": start + first_score_s, "portfolio": start, "heartbeat": start}
        self.boards_saved = 0
        self.share = None             # T61: `ShareAgent` (lo asigna la CLI `run` si hay nube)
        self.copy: CopyLive | None = None
        self._copy_logged: dict[str, float] = {}
        if copy_mode != "off":
            self._alerts = JsonLog(self.boards.dir / "logs")
            self._toast = WindowsToast()
            try:
                cp = copy_params or CopyParams()
                self.copy = CopyLive(store, root, cp, exchange_spec(info, root),
                                     copy_config(cp), [ld for ld in leaders if ld.tracked],
                                     mode=copy_mode, price_now=self._price_now,
                                     alert=self._copy_alert)
            except Exception as exc:  # sin copia, pero la captura sigue
                self.errors.append(f"copia: no arrancó: {type(exc).__name__}: {exc}"[:300])
                log.exception("copia simulada desactivada")

    def _coins(self) -> list[str]:
        """Monedas operadas por los capturados en el último día + BTC/ETH."""
        recent = self.store.recent_coins(self.now() - DAY_MS)
        coins = sorted(c for c in recent if is_perp(c))
        base = [c for c in P.DISCOVERY_COINS if c not in coins]
        return (base + coins)[:QUOTE_COINS_MAX]

    # --- ganchos del vigilante ----------------------------------------------------------------
    def on_fills(self, fills: list) -> None:
        self.quotes.expect(fills)
        if self.copy is not None and fills:
            self._copy_call("señales", self.copy.on_fills, fills, self.now())

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
        if self.copy is not None:
            self._copy_call("marcas", self._copy_marks, ch, msg.get("data") or {}, observed_at,
                            got)

    # --- copia simulada (T42) -----------------------------------------------------------------
    def _copy_call(self, what: str, fn, *args) -> None:
        """La copia nunca detiene la captura: un fallo queda en `errors` y en el registro
        (como mucho una traza por minuto y tipo, para no inundarlo)."""
        try:
            fn(*args)
        except Exception as exc:
            self.errors.append(f"copia {what}: {type(exc).__name__}: {exc}"[:300])
            now = time.monotonic()
            if now - self._copy_logged.get(what, -1e9) >= 60.0:
                self._copy_logged[what] = now
                log.exception("copia simulada (%s)", what)

    def _copy_marks(self, ch: str, data: dict, observed_at: int, got: list) -> None:
        if got:
            self.copy.on_quotes(got, self.now())
        if ch == "bbo":
            q = self._price_now(str(data.get("coin", "")), observed_at)
            if q is not None:
                self.copy.on_mark(str(data.get("coin")), observed_at, q.mid)
            return
        held = self.copy.coins()
        for coin, (_, mid) in list(self.quotes.mids.items()):
            if coin in held and coin not in self.quotes.bbo_coins:
                self.copy.on_mark(coin, observed_at, mid)

    def _price_now(self, coin: str, now: int) -> ExecQuote | None:
        b = self.quotes.bbo.get(coin)
        if coin in self.quotes.bbo_coins and b is not None and b.bid and b.ask:
            return ExecQuote(t=b.t, at=now, mid=(b.bid + b.ask) / 2, bid=b.bid, ask=b.ask,
                             src="bbo")
        m = self.quotes.mids.get(coin)
        return ExecQuote(t=m[0], at=now, mid=m[1], src="allMids") if m else None

    def _copy_alert(self, level: str, title: str, detail: str) -> None:
        a = Alert(t=self.now(), kind="copia", level=level, title=title, detail=detail,
                  key=f"copia:{title}")
        self._alerts.alert_sink(a)
        self._toast(a)

    def _settle(self, address, t, pos, rec, obs, retries) -> None:
        super()._settle(address, t, pos, rec, obs, retries)
        if self.copy is not None:
            self._copy_call("reconciliación", self.copy.on_recon, self.books[address].leader,
                            t, obs, pos)

    def on_down(self, since: int, reason: str) -> None:
        super().on_down(since, reason)
        if self.copy is not None:
            self._copy_call("flujo", self.copy.feed_down,
                            [self.books[a].leader.id for a in self.ws_users], since)

    def on_up(self, since: int) -> None:
        super().on_up(since)
        if self.copy is not None:
            self._copy_call("flujo", self.copy.feed_up,
                            [self.books[a].leader.id for a in self.ws_users])

    def extra_streams(self) -> list[HyperliquidStream]:
        subs = [{"type": "bbo", "coin": c} for c in sorted(self.quotes.bbo_coins)]
        subs.append({"type": "allMids"})
        return [HyperliquidStream(subs, self.on_quote, clock=self.now, **self.stream_kw)]

    async def extra_jobs(self) -> None:
        got = self.quotes.flush(self.now())
        if got:
            self.store.add_follow(got)
        if self.copy is not None:
            if got:
                self._copy_call("cotizaciones", self.copy.on_quotes, got, self.now())
            self._copy_call("vuelta", self.copy.tick, self.now())
        snap = take_snapshot_request(self.root)  # copia de la base pedida por `copy-sim` (T42)
        if snap is not None:
            await self._safe("instantánea", asyncio.to_thread(self.store.snapshot, snap))
        if self.share is not None and self.share.due():   # T61: exportar/importar experiencia
            await self._safe("compartir", asyncio.to_thread(self.share.tick))
        now = time.monotonic()
        if now >= self._next["portfolio"]:
            self._next["portfolio"] = now + self.portfolio_every_s
            await self._safe("portfolio", asyncio.to_thread(
                refresh_portfolios, self.store, self.info, self.now(), PORTFOLIO_PER_TICK))
        if now >= self._next["score"]:
            self._next["score"] = now + self.score_every_s
            await self._safe("evaluación", self.score_now())

    async def _safe(self, what: str, coro) -> None:
        await super()._safe(what, coro)
        now = time.monotonic()
        if now >= self._next["heartbeat"]:
            self._next["heartbeat"] = now + HEARTBEAT_EVERY_S
            self.heartbeat()

    def heartbeat(self) -> None:
        """Escritura atómica; `last_heartbeat` en reloj local (el del vigilante). Un fallo de
        disco no detiene la captura: sin latido, el vigilante acabará relanzando."""
        ready = len(self.ready)
        row = {"last_heartbeat": self.clock(), "pid": os.getpid(),
               "state": "capturando" if ready == len(self.books) else "arrancando",
               "leaders": len(self.books), "ready": ready, "boards_saved": self.boards_saved,
               "errors": len(self.errors)}
        try:
            self.boards.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.boards.dir / (HEARTBEAT + ".tmp")
            tmp.write_text(json.dumps(row), encoding="utf-8")
            tmp.replace(self.boards.dir / HEARTBEAT)
        except OSError as exc:
            log.error("latido: %s", exc)

    async def score_now(self) -> None:
        board = await asyncio.to_thread(evaluate, self.store, self.now(), self.p)
        self.boards.save(board)
        self.boards_saved += 1

    async def run(self, stop: asyncio.Event, minutes: float | None = None) -> None:
        self.heartbeat()
        await super().run(stop, minutes)
        await self._safe("evaluación final", self.score_now())
        if self.copy is not None:
            self._copy_call("cierre", self.copy.close, self.now())
