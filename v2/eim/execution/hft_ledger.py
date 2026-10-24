"""Libro del carril HFT (T83): órdenes enviadas, posición por fills, resultado y tasas.

Se alimenta de tres fuentes que pueden llegar en cualquier orden: la respuesta del envío, los
eventos del flujo de usuario (`user_stream.py`, la vía principal) y las consultas de la
reconciliación (red de seguridad). Cada orden lleva la cantidad ya contabilizada (`acc_qty`):
un estado nuevo solo suma la diferencia de su llenado acumulado, así un fill nunca cuenta dos
veces aunque llegue por dos vías; un estado terminal no retrocede. De aquí sale la `HftAccount`
que lee el motor de riesgo en cada decisión.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from eim.execution.broker import (
    CANCELED,
    EXPIRED,
    FILLED,
    REJECTED,
    OrderSpec,
    OrderState,
    RateLimited,
)
from eim.execution.user_stream import UserEvent
from eim.risk.hft_models import HftAccount

SENT, UNKNOWN, REFUSED, NEVER = "ENVIADA", "DESCONOCIDA", "RECHAZADA", "NUNCA_LLEGO"
TERMINAL = (FILLED, CANCELED, EXPIRED, REJECTED, REFUSED, NEVER)
HOUR_MS, DAY_MS = 3_600_000, 86_400_000
KEEP_CLOSED_MS = 60_000                # órdenes cerradas que se recuerdan (doble envío, consultas)
_EPS = 1e-12


@dataclass
class LiveOrder:
    spec: OrderSpec
    sent_at: int
    status: str = SENT
    state: OrderState | None = None
    acc_qty: float = 0.0               # llenado ya contabilizado en la posición
    acc_cost: float = 0.0
    cancel_at: int | None = None       # última petición de cancelación
    updated_at: int = 0
    error: str = ""

    @property
    def live(self) -> bool:
        return self.status not in TERMINAL

    @property
    def remaining(self) -> float:
        return max((self.spec.qty or 0.0) - self.acc_qty, 0.0) if self.live else 0.0


class HftLedger:
    def __init__(self, clock: Callable[[], int] = lambda: int(time.time() * 1000),
                 fee_bps: float = 5.0, maker_bps: float = 2.0) -> None:
        self._clock = clock
        self.fee_bps, self.maker_bps = fee_bps, maker_bps   # si el evento no trae la comisión
        self.orders: dict[str, LiveOrder] = {}
        self.pos: dict[str, float] = {}
        self.entry: dict[str, float | None] = {}
        self.realized = 0.0                           # neto de comisiones (USD)
        self.fees = 0.0
        self._sent: deque[int] = deque()
        self._cancels: deque[int] = deque()
        self._mid: dict[str, float] = {}
        self._hour = self._day = -1
        self._hour_pnl = self._day_pnl = self._day_peak = 0.0
        self.consecutive_losses = 0
        self.last_loss_t: int | None = None
        self.rate_limited_until: int | None = None
        self.banned = False
        self.heartbeat_t: int | None = None
        self.user_stream_ok = True
        self.exchange_pos: dict[str, float] = {}      # última posición vista por evento

    # --- envíos y respuestas ---------------------------------------------------
    def note_sent(self, spec: OrderSpec, now: int) -> LiveOrder:
        o = self.orders[spec.client_id] = LiveOrder(spec, now, updated_at=now)
        self._sent.append(now)
        return o

    def note_cancel(self, cid: str, now: int) -> None:
        self._cancels.append(now)
        if (o := self.orders.get(cid)) is not None:
            o.cancel_at = now

    def on_reject(self, cid: str, why: str) -> None:
        if (o := self.orders.get(cid)) is not None and o.acc_qty <= 0:
            o.status, o.error = REFUSED, why

    def on_unknown(self, cid: str, why: str) -> None:
        if (o := self.orders.get(cid)) is not None and o.status == SENT:
            o.status, o.error = UNKNOWN, why

    def on_gone(self, cid: str) -> None:
        """El exchange confirma que no existe: si nunca se confirmó, no llegó."""
        if (o := self.orders.get(cid)) is not None and o.status in (SENT, UNKNOWN):
            o.status = NEVER

    def on_rate_limit(self, e: RateLimited) -> None:
        self.rate_limited_until = max(self.rate_limited_until or 0, e.until)
        self.banned = self.banned or e.banned

    def on_event(self, ev: UserEvent) -> None:
        if ev.kind == "order" and ev.state is not None:
            self.on_state(ev.state, ev.last_price, ev.fee if ev.last_qty else None)
        elif ev.kind == "account" and ev.position is not None:
            self.exchange_pos[ev.symbol] = ev.position

    def on_state(self, st: OrderState, last_px: float | None = None,
                 fee: float | None = None) -> None:
        o = self.orders.get(st.client_id)
        if o is None or (not o.live and st.status not in TERMINAL):
            return                                    # ajena o estado viejo
        dq = round(st.filled - o.acc_qty, 12)
        if dq > _EPS:
            px = last_px or ((st.avg_price or 0.0) * st.filled - o.acc_cost) / dq
            bps = self.maker_bps if o.spec.tif == "GTX" else self.fee_bps
            self._fill(st.symbol, st.side, dq, px, fee if fee is not None else dq * px * bps / 1e4)
            o.acc_qty, o.acc_cost = st.filled, o.acc_cost + dq * px
        o.state, o.status, o.updated_at = st, st.status, self._clock()

    def _fill(self, sym: str, side: int, q: float, px: float, fee: float) -> None:
        cur, entry = self.pos.get(sym, 0.0), self.entry.get(sym)
        new = round(cur + side * q, 12)
        pnl = -fee
        if cur * side >= 0:                           # abre o aumenta
            entry = ((entry or 0.0) * abs(cur) + px * q) / abs(new)
        else:                                         # reduce (y quizá invierte)
            pnl += (px - (entry or px)) * min(q, abs(cur)) * (1 if cur > 0 else -1)
            entry = None if abs(new) < _EPS else (px if new * cur < 0 else entry)
            if pnl < 0:
                self.consecutive_losses, self.last_loss_t = self.consecutive_losses + 1, \
                    self._clock()
            else:
                self.consecutive_losses = 0
        self.realized += pnl
        self.fees += fee
        self.pos[sym], self.entry[sym] = (0.0 if abs(new) < _EPS else new), entry

    # --- lectura -----------------------------------------------------------------
    def position(self, symbol: str) -> float:
        return self.pos.get(symbol, 0.0)

    def live(self, symbol: str | None = None) -> list[LiveOrder]:
        return [o for o in self.orders.values()
                if o.live and (symbol is None or o.spec.symbol == symbol)]

    def pnl(self) -> float:
        """Resultado neto: realizado + no realizado a precio medio."""
        return self.realized + sum(q * (self._mid.get(s, e or 0.0) - (e or 0.0))
                                   for s, q in self.pos.items() if q
                                   for e in (self.entry.get(s),))

    @staticmethod
    def _count(q: deque[int], now: int, win: int) -> int:
        while q and q[0] <= now - 60_000:
            q.popleft()
        n = 0
        for t in reversed(q):
            if t <= now - win:
                break
            n += 1
        return n

    def _prune(self, now: int) -> None:
        """Olvida las órdenes cerradas hace > `KEEP_CLOSED_MS`: el libro no crece sin fin."""
        old = [k for k, o in self.orders.items()
               if not o.live and o.updated_at < now - KEEP_CLOSED_MS]
        for k in old:
            del self.orders[k]

    def account(self, symbol: str, mid: float | None, now: int) -> HftAccount:
        if len(self.orders) > 256:
            self._prune(now)
        if mid:
            self._mid[symbol] = mid
        pnl = self.pnl()
        if now // HOUR_MS != self._hour:
            self._hour, self._hour_pnl = now // HOUR_MS, pnl
        if now // DAY_MS != self._day:
            self._day, self._day_pnl, self._day_peak = now // DAY_MS, pnl, pnl
        self._day_peak = max(self._day_peak, pnl)
        live = self.live(symbol)
        return HftAccount(
            position=self.position(symbol),
            live_buy_qty=sum(o.remaining for o in live if o.spec.side > 0),
            live_sell_qty=sum(o.remaining for o in live if o.spec.side < 0),
            live_orders=len(live), pnl_session=pnl, pnl_hour=pnl - self._hour_pnl,
            pnl_day=pnl - self._day_pnl, drawdown_day=self._day_peak - pnl,
            consecutive_losses=self.consecutive_losses, last_loss_t=self.last_loss_t,
            orders_10s=self._count(self._sent, now, 10_000),
            orders_60s=self._count(self._sent, now, 60_000),
            cancels_10s=self._count(self._cancels, now, 10_000),
            cancels_60s=self._count(self._cancels, now, 60_000),
            rate_limited_until=self.rate_limited_until,
            banned=self.banned and now < (self.rate_limited_until or 0),
            heartbeat_t=self.heartbeat_t, user_stream_ok=self.user_stream_ok,
            source="libro HFT (eventos + reconciliación)")
