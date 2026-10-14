"""`SimBroker`: exchange en memoria con la misma interfaz que la testnet (modo SIMULADO).

Casa órdenes contra el precio que se le da con `set_price` (sin libro): MARKET al precio
actual, LIMIT al cruzar su precio, STOP/TAKE_PROFIT al tocar el disparo. `fill_cap` limita la
cantidad que se llena por evento para reproducir fills parciales. Imita las reglas de Binance
que importan a la ejecución: id de cliente duplicado entre órdenes abiertas → rechazo,
reduce-only sin posición → rechazo, condicional que dispararía al instante → rechazo,
`close_position` sin posición al disparar → expira.
"""

from __future__ import annotations

import math
from dataclasses import replace

from eim.core import Mode
from eim.execution.broker import (
    CANCELED,
    EXPIRED,
    FILLED,
    LIMIT,
    MARKET,
    NEW,
    PARTIAL,
    STOP,
    TRIGGERED,
    OrderRejected,
    OrderSpec,
    OrderState,
    Position,
)


class SimBroker:
    mode = Mode.SIMULADO

    def __init__(self, balance: float = 10_000.0, fee_rate: float = 0.0004,
                 step: float = 0.001, tick: float = 0.1, min_qty: float = 0.001,
                 fill_cap: float | None = None) -> None:
        self.balance, self.fee_rate = balance, fee_rate
        self.step, self.tick, self.min_qty, self.fill_cap = step, tick, min_qty, fill_cap
        self.leverage: dict[str, int] = {}
        self._orders: dict[str, OrderState] = {}
        self._pos: dict[str, tuple[float, float | None]] = {}
        self._px: dict[str, float] = {}
        self._limit_px: dict[str, float | None] = {}
        self._seq = 0

    # --- mercado -----------------------------------------------------------
    def set_price(self, symbol: str, price: float) -> None:
        self._px[symbol] = price
        for o in list(self._orders.values()):
            if o.symbol == symbol and o.is_open:
                self._match(o)

    def price(self, symbol: str) -> float | None:
        return self._px.get(symbol)

    # --- interfaz Broker ---------------------------------------------------
    def prepare(self, symbol: str, leverage: int) -> None:
        self.leverage[symbol] = leverage

    def round_qty(self, symbol: str, qty: float) -> float:
        q = round(math.floor(qty / self.step + 1e-9) * self.step, 10)
        return q if q >= self.min_qty else 0.0

    def round_price(self, symbol: str, price: float) -> float:
        return round(round(price / self.tick) * self.tick, 10)

    def post_order(self, spec: OrderSpec) -> OrderState:
        old = self._orders.get(spec.client_id)
        if old is not None and old.is_open:
            raise OrderRejected("ClientOrderId is duplicated", -4116, duplicate=True)
        px = self._px.get(spec.symbol)
        if px is None:
            raise OrderRejected(f"sin precio para {spec.symbol}", -1121)
        if not spec.close_position and (spec.qty is None or self.round_qty(spec.symbol,
                                                                        spec.qty) != spec.qty):
            raise OrderRejected("cantidad inválida para el paso del símbolo", -1111)
        if spec.reduce_only and not self._reduces(spec.symbol, spec.side):
            raise OrderRejected("ReduceOnly Order is rejected", -2022)
        if spec.conditional and self._triggers(spec.kind, spec.side, spec.trigger, px):
            raise OrderRejected("Order would immediately trigger.", -2021)
        if spec.kind == LIMIT and not spec.price:
            raise OrderRejected("LIMIT sin precio", -1102)
        self._seq += 1
        o = OrderState(client_id=spec.client_id, symbol=spec.symbol, side=spec.side,
                       kind=spec.kind, status=NEW, qty=spec.qty, trigger=spec.trigger,
                       close_position=spec.close_position, reduce_only=spec.reduce_only,
                       exchange_id=str(self._seq))
        self._orders[spec.client_id] = o
        self._limit_px[spec.client_id] = spec.price
        self._match(o)
        return self._orders[spec.client_id]

    def get_order(self, symbol: str, client_id: str, conditional: bool) -> OrderState | None:
        o = self._orders.get(client_id)
        return o if o is not None and o.symbol == symbol and o.conditional == conditional \
            else None

    def order_by_id(self, client_id: str) -> OrderState | None:
        return self._orders.get(client_id)

    def cancel(self, symbol: str, client_id: str, conditional: bool) -> None:
        o = self.get_order(symbol, client_id, conditional)
        if o is not None and o.is_open:
            self._orders[client_id] = replace(o, status=CANCELED)

    def open_orders(self, symbol: str) -> list[OrderState]:
        return [o for o in self._orders.values() if o.symbol == symbol and o.is_open]

    def position(self, symbol: str) -> Position:
        q, e = self._pos.get(symbol, (0.0, None))
        return Position(symbol, q, e)

    def equity(self) -> float:
        upnl = sum(q * (self._px.get(s, e or 0.0) - (e or 0.0)) for s, (q, e) in self._pos.items())
        return self.balance + upnl

    # --- casación ----------------------------------------------------------
    def _reduces(self, symbol: str, side: int) -> bool:
        q = self._pos.get(symbol, (0.0, None))[0]
        return q * side < 0

    @staticmethod
    def _triggers(kind: str, side: int, trigger: float | None, px: float) -> bool:
        if trigger is None:
            return False
        # STOP de venta dispara al bajar; TAKE_PROFIT de venta al subir (y al revés en compra)
        down = (kind == STOP) == (side < 0)
        return px <= trigger if down else px >= trigger

    def _match(self, o: OrderState) -> None:
        px = self._px[o.symbol]
        if o.conditional:
            if not self._triggers(o.kind, o.side, o.trigger, px):
                return
            q = abs(self._pos.get(o.symbol, (0.0, None))[0]) if o.close_position else (o.qty or 0)
            if o.close_position and not self._reduces(o.symbol, o.side):
                q = 0.0
            if q <= 0:
                self._orders[o.client_id] = replace(o, status=EXPIRED)
                return
            self._fill(o.symbol, o.side, q, px)
            self._orders[o.client_id] = replace(o, status=TRIGGERED, filled=q, avg_price=px)
            return
        limit = self._limit_px.get(o.client_id)
        if o.kind == LIMIT and (px - (limit or 0)) * o.side > 0:
            return                                    # no cruza
        fill_px = px if o.kind == MARKET else float(limit or px)
        rest = (o.qty or 0) - o.filled
        if o.reduce_only:
            rest = min(rest, abs(self._pos.get(o.symbol, (0.0, None))[0]))
        q = min(rest, self.fill_cap) if self.fill_cap else rest
        if q <= 0:
            self._orders[o.client_id] = replace(o, status=EXPIRED)
            return
        self._fill(o.symbol, o.side, q, fill_px)
        filled = o.filled + q
        avg = ((o.avg_price or 0) * o.filled + fill_px * q) / filled
        done = filled >= (o.qty or 0) - 1e-12
        self._orders[o.client_id] = replace(o, filled=round(filled, 10), avg_price=avg,
                                            status=FILLED if done else PARTIAL)

    def _fill(self, symbol: str, side: int, q: float, px: float) -> None:
        cur, entry = self._pos.get(symbol, (0.0, None))
        new = round(cur + side * q, 10)
        if cur * side >= 0:                           # abre o aumenta
            entry = ((entry or 0) * abs(cur) + px * q) / abs(new)
        else:                                         # reduce (reduce-only: nunca invierte)
            self.balance += (px - (entry or px)) * min(q, abs(cur)) * (1 if cur > 0 else -1)
            if new == 0:
                entry = None
        self.balance -= px * q * self.fee_rate
        self._pos[symbol] = (new, entry)
