"""Vigilante de líderes (T40): WS + REST de Hyperliquid → libro esperado, historial,
reconciliación periódica y relleno de huecos. Solo lectura: no envía órdenes.

- ≤ 10 líderes por WS (`userFills`, límite oficial por IP); el resto por consulta REST.
- Al empezar: estado real (`clearinghouseState`) + ejecuciones del último día. El WS arranca
  en paralelo: lo que llegue de un líder aún sin estado se descarta y lo cubre su arranque.
- Huecos: (a) `startPosition` que no cuadra con el libro, (b) corte del WS, (c) divergencia en
  la reconciliación. (a) y (b) se rellenan con `userFillsByTime`; si tras rellenar y
  re-comprobar (5/10/15 s) el libro sigue sin cuadrar, (c) resincroniza con el estado real.
- Todo el estado se muta en el hilo del bucle asyncio; el REST va en hilos (`to_thread`).
- `observed_at` = reloj local + desfase medido contra el servidor (`clock_offset_ms`), para
  que `observed_at − t` sea la latencia real y no el error del reloj de la máquina.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from eim.core.leaders import Channel, Leader, LeaderPosition
from eim.data.leader_store import LeaderStore
from eim.data.providers.leaders import HyperliquidInfo, HyperliquidStream, now_ms
from eim.leaders import params as P
from eim.leaders.book import Gap, LeaderBook, Recon
from eim.leaders.parse import order_fills, parse_funding, parse_positions
from eim.observability import hooks_service

log = logging.getLogger(__name__)


@dataclass
class _Suspect:
    """Estado real que no cuadró tras rellenar: se re-compara cada `RECON_RETRY_S`."""

    t: int
    pos: list[LeaderPosition]
    obs: int
    since: int
    tries: int
    due: float  # monotonic


class LeaderWatch:
    def __init__(self, store: LeaderStore, info: HyperliquidInfo, leaders: list[Leader], *,
                 clock: Callable[[], int] = now_ms, ws_max: int = P.WS_MAX_USERS,
                 stream_kw: dict | None = None) -> None:
        self.store, self.info, self.clock = store, info, clock
        self.stream_kw = stream_kw or {}  # inyección en tests (conexión WS falsa)
        hl = sorted((ld for ld in leaders if ld.venue == "hyperliquid" and ld.tracked),
                    key=lambda ld: (ld.status != "approved", ld.discovered_at, ld.id))
        self.manual_only = [ld.id for ld in leaders if ld.venue != "hyperliquid"]
        self.books = {ld.address: LeaderBook(ld) for ld in hl}
        self.ws_users = [ld.address for ld in hl[:ws_max]]
        self.poll_users = [ld.address for ld in hl[ws_max:]]
        self.pending: dict[str, int] = {}  # dirección → relleno pendiente desde t
        self.open_gaps: dict[str, list[Gap]] = {}
        self.ready: set[str] = set()  # con estado inicial cargado
        self.suspect: dict[str, _Suspect] = {}  # desajuste en observación por dirección
        self.boot_retry: dict[str, tuple[float, float]] = {}  # arranque fallido: (cuándo, espera)
        self.errors: deque[str] = deque(maxlen=200)

    def now(self) -> int:
        """Reloj local alineado con el del exchange."""
        return self.clock() + self.offset()

    def offset(self) -> int:
        fn = getattr(self.info, "clock_offset_ms", None)
        return int(fn()) if fn else 0

    # --- ingesta (síncrona) -------------------------------------------------------------------
    def ingest(self, address: str, raws: list[dict], observed_at: int, channel: Channel) -> int:
        """Aplica ejecuciones al libro y las guarda; devuelve cuántas eran nuevas."""
        book = self.books.get(address)
        if book is None or address not in self.ready:
            return 0
        fills, gaps = [], []
        for raw in order_fills(raws):
            f, g = book.apply(raw, observed_at, channel)
            if f is not None:
                fills.append(f)
            if g is not None:
                gaps.append(g)
        n = self.store.add_fills(fills)
        self.on_fills(fills)
        for g in gaps:
            log.warning("hueco %s %s: %s", g.leader_id, g.symbol, g.detail)
            self._open_gap(address, g, g.start - P.BACKFILL_MARGIN_MS)
        return n

    def _open_gap(self, address: str, gap: Gap, since: int) -> None:
        self.open_gaps.setdefault(address, []).append(gap)
        self.pending[address] = min(self.pending.get(address, since), since)

    def on_message(self, msg: dict, observed_at: int) -> None:
        ch = msg.get("channel")
        if ch == "userFills":
            d = msg.get("data") or {}
            channel: Channel = "ws_snapshot" if d.get("isSnapshot") else "ws"
            self.ingest(str(d.get("user", "")).lower(), d.get("fills") or [], observed_at,
                        channel)
        elif ch == "error":
            self.errors.append(str(msg.get("data"))[:200])
            log.error("WS: %s", msg.get("data"))

    def on_down(self, since: int, reason: str) -> None:
        log.warning("WS caído desde %s: %s", since, reason)
        for a in self.ws_users:
            if a in self.ready:
                lid = self.books[a].leader.id
                self._open_gap(a, Gap(lid, None, since, since, "ws", reason),
                               since - P.BACKFILL_MARGIN_MS)

    def on_up(self, since: int) -> None:
        now = self.now()
        log.info("WS reconectado (%d ms caído)", now - since)
        for gaps in self.open_gaps.values():
            gaps[:] = [dataclasses.replace(g, end=now) if g.cause == "ws" and g.end == since
                       else g for g in gaps]

    # --- REST (asíncrono, en hilos) -----------------------------------------------------------
    async def bootstrap(self, address: str) -> None:
        book = self.books[address]
        obs = self.now()
        state = await asyncio.to_thread(self.info.clearinghouse_state, address)
        t, pos = parse_positions(book.leader, state, obs)
        book.load(t, pos)
        self.ready.add(address)
        self.store.save_positions(book.leader.id, t, obs, pos)
        since = max(self.store.last_fill_t(book.leader.id) or 0, obs - P.BOOT_LOOKBACK_MS)
        n = await self._fill_since(address, t - P.BACKFILL_MARGIN_MS)  # lo que mueve el libro
        if since < t - P.BACKFILL_MARGIN_MS:  # historial: paginado desde lo más antiguo, con tope
            n += await self._fill_since(address, since)
        self.boot_retry.pop(address, None)
        log.info("%s: %d posiciones, %d ejecuciones nuevas en el historial", book.leader.id,
                 len(pos), n)
        await self.funding(address)

    async def backfill(self, address: str) -> int:
        """Rellena los huecos abiertos; si la consulta falla siguen abiertos (se reintenta)."""
        since, k = self.pending[address], len(self.open_gaps.get(address, []))
        n = await self._fill_since(address, since)
        gaps = self.open_gaps.pop(address, [])
        if gaps[k:]:  # huecos abiertos durante la consulta: quedan para la próxima vuelta
            self.open_gaps[address] = gaps[k:]
        elif self.pending.get(address) == since:
            del self.pending[address]
        for g in gaps[:k]:
            self.store.add_gap(g, self.now(), n)
        return n

    async def poll(self, address: str) -> int:
        book = self.books[address]
        since = max(book.last_fill_t, book.as_of or 0) - P.BACKFILL_MARGIN_MS
        return await self._fill_since(address, since, "rest_poll")

    async def funding(self, address: str) -> int:
        lid = self.books[address].leader.id
        last = self.store.last_funding_t(lid)
        since = last + 1 if last is not None else self.now() - P.BOOT_LOOKBACK_MS
        rows = await asyncio.to_thread(self.info.user_funding, address, since)
        return self.store.add_funding(parse_funding(self.books[address].leader, rows,
                                                    self.now()))

    async def _fill_since(self, address: str, since: int,
                          channel: Channel = "rest_backfill") -> int:
        raws = await asyncio.to_thread(self.info.user_fills_by_time, address, since)
        return self.ingest(address, raws, self.now(), channel)

    async def reconcile(self, address: str, retries: int = 0, final: bool = False
                        ) -> Recon:
        """Estado real vs esperado. Si el tamaño no cuadra, rellena por REST desde la última
        ejecución de esas monedas. Si aún no cuadra, queda en observación: el endpoint de
        ejecuciones puede ir varios segundos por detrás del estado (medido en vivo), así que
        `recheck` vuelve a comparar ESE estado; con `final` se resincroniza al exchange."""
        book = self.books[address]
        obs = self.now()
        state = await asyncio.to_thread(self.info.clearinghouse_state, address)
        t, pos = parse_positions(book.leader, state, obs)
        rec = book.compare(t, pos)
        if not rec.size_ok:
            bad = [d.symbol for d in rec.diffs if d.field == "size"]
            since = min(book.touched.get(s, book.as_of or t) for s in bad) - P.BACKFILL_MARGIN_MS
            await self._fill_since(address, since)
            rec = book.compare(t, pos)
            if not rec.size_ok and not final:
                self.suspect[address] = _Suspect(t, pos, obs, since, 0,
                                                 time.monotonic() + P.RECON_RETRY_S)
                return rec
        self._settle(address, t, pos, rec, obs, retries)
        return rec

    async def recheck(self, address: str) -> Recon | None:
        """Vuelve a comparar el estado en observación tras rellenar otra vez; agotados los
        intentos, reconcilia con un estado fresco y resincroniza si sigue sin cuadrar."""
        s = self.suspect[address]
        s.tries += 1
        await self._fill_since(address, s.since)
        rec = self.books[address].compare(s.t, s.pos)
        if rec.size_ok:
            del self.suspect[address]
            self._settle(address, s.t, s.pos, rec, s.obs, s.tries)
            return rec
        if s.tries < P.RECON_RETRIES:
            s.due = time.monotonic() + P.RECON_RETRY_S
            return None
        del self.suspect[address]
        return await self.reconcile(address, s.tries + 1, final=True)

    async def settle_now(self, address: str) -> None:
        """Reconciliación completa, esperando los reintentos (cierre del servicio)."""
        self.suspect.pop(address, None)
        await self.reconcile(address)
        while address in self.suspect:
            await asyncio.sleep(max(0.0, self.suspect[address].due - time.monotonic()))
            await self.recheck(address)

    def _settle(self, address: str, t: int, pos: list[LeaderPosition], rec: Recon, obs: int,
                retries: int) -> None:
        book = self.books[address]
        resynced = not rec.size_ok
        if resynced:
            detail = "; ".join(f"{d.symbol} esperado {d.expected} real {d.actual}"
                               for d in rec.diffs if d.field == "size")
            log.warning("divergencia %s: %s → resincronizado", book.leader.id, detail)
            self.store.add_gap(Gap(book.leader.id, ",".join(sorted({d.symbol for d in rec.diffs})),
                                   book.as_of or t, t, "reconciliación", detail[:500]), obs, 0)
            book.load(t, pos)
        else:
            book.refresh(pos, rec)
        if rec.leverage:
            self.store.add_leverage(book.leader.id, rec, obs)
        self.store.add_recon(book.leader.id, rec, obs, resynced, self.offset(), retries)
        self.store.save_positions(book.leader.id, t, obs, pos)

    # --- ganchos (T41: cotizaciones del seguidor y evaluación, en `leader_service.py`) --------
    def on_fills(self, fills: list) -> None: ...

    async def extra_jobs(self) -> None: ...

    def extra_streams(self) -> list[HyperliquidStream]:
        return []

    # --- bucle --------------------------------------------------------------------------------
    async def _safe(self, what: str, coro) -> None:
        try:
            await coro
        except Exception as exc:  # un líder o una consulta fallida no detiene al resto
            self.errors.append(f"{what}: {type(exc).__name__}: {exc}"[:300])
            hooks_service.service_error("leaders.service", exc, detail={"what": what[:60]})
            log.error("%s: %s", what, exc)

    async def _periodic(self, stop: asyncio.Event) -> None:
        nxt = {"recon": 0.0, "poll": 0.0, "funding": time.monotonic() + P.FUNDING_EVERY_S}
        every = {"recon": P.RECON_EVERY_S, "poll": P.POLL_EVERY_S, "funding": P.FUNDING_EVERY_S}
        while not stop.is_set():
            for a in [a for a in list(self.pending) if a in self.ready]:
                await self._safe(f"relleno {a}", self.backfill(a))
            now = time.monotonic()
            for a in [a for a, s in list(self.suspect.items()) if s.due <= now]:
                await self._safe(f"recomprobación {a}", self.recheck(a))
            for addr in [a for a in self.books if a not in self.ready
                         and self.boot_retry.get(a, (0.0, 0.0))[0] <= now]:
                wait = self.boot_retry.get(addr, (0.0, 2.5))[1] * 2  # 5 s, 10 s… hasta 5 min
                self.boot_retry[addr] = (now + wait, min(wait, 300.0))
                await self._safe(f"arranque {addr}", self.bootstrap(addr))
            calm = [a for a in self.ready if a not in self.suspect]
            for job, fn, users in (("recon", self.reconcile, calm),
                                   ("poll", self.poll, [a for a in self.poll_users
                                                        if a in self.ready]),
                                   ("funding", self.funding, list(self.ready))):
                if now >= nxt[job]:
                    nxt[job] = now + every[job]
                    for a in users:
                        await self._safe(f"{job} {a}", fn(a))
            await self._safe("tareas extra", self.extra_jobs())
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.0)
            except TimeoutError:
                pass

    async def run(self, stop: asyncio.Event, minutes: float | None = None) -> None:
        tasks = [asyncio.create_task(self._periodic(stop))]  # arranca cada líder
        if self.ws_users:
            subs = [{"type": "userFills", "user": a} for a in self.ws_users]
            stream = HyperliquidStream(subs, self.on_message, on_down=self.on_down,
                                       on_up=self.on_up, clock=self.now, **self.stream_kw)
            tasks.append(asyncio.create_task(stream.run(stop)))
        tasks += [asyncio.create_task(s.run(stop)) for s in self.extra_streams()]
        if minutes:
            await asyncio.wait({asyncio.create_task(stop.wait())}, timeout=minutes * 60)
            stop.set()
        await asyncio.gather(*tasks)
        for a in [a for a in list(self.pending) if a in self.ready]:  # huecos aún abiertos
            await self._safe(f"relleno {a}", self.backfill(a))
        for a in list(self.ready):  # cierre: última comparación con el exchange
            await self._safe(f"recon final {a}", self.settle_now(a))

