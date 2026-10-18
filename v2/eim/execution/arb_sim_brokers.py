"""Brokers del exchange de arbitraje simulado (modo SIMULADO): misma interfaz que
`BinanceSpotTestnetBroker` y `BinanceTestnetBroker`, sobre un `SimVenue` en memoria."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from eim.core import Mode
from eim.execution.arb_sim import QUOTE, SimVenue
from eim.execution.broker import (
    LIMIT,
    MARKET,
    BrokerError,
    OrderRejected,
    OrderSpec,
    OrderState,
    Position,
)


class _SimBroker:
    mode = Mode.SIMULADO
    market = ""
    step = tick = 0.0

    def __init__(self, venue: SimVenue) -> None:
        self.v = venue

    def round_qty(self, symbol: str, qty: float) -> float:
        s = Decimal(str(self.step))
        q = (Decimal(str(qty)) / s).to_integral_value(ROUND_DOWN) * s
        return float(q)

    def round_price(self, symbol: str, price: float) -> float:
        t = Decimal(str(self.tick))
        return float((Decimal(str(price)) / t).to_integral_value(ROUND_HALF_UP) * t)

    def post_order(self, spec: OrderSpec) -> OrderState:
        if spec.kind not in (MARKET, LIMIT):
            raise BrokerError(f"el simulador de arbitraje no admite órdenes {spec.kind}")
        return self.v.book_order(self.market, spec, self.step)

    def get_order(self, symbol: str, client_id: str,
                  conditional: bool = False) -> OrderState | None:
        self.v.net()
        o = self.v.orders.get(client_id)
        return o[0] if o is not None and o[0].symbol == symbol else None

    def cancel(self, symbol: str, client_id: str, conditional: bool = False) -> None:
        if client_id in self.v.orders:
            self.v.cancel(client_id)

    def open_orders(self, symbol: str) -> list[OrderState]:
        self.v.net()
        return [s for s, _, m in self.v.orders.values()
                if s.symbol == symbol and m == self.market and s.is_open]

    def book_top(self, symbol: str) -> tuple[float, float] | None:
        self.v.net()
        return self.v.top(symbol)

    def depth(self, symbol: str, limit: int = 20) -> tuple[list, list]:
        t = self.book_top(symbol)
        d = self.v.depth.get(symbol, 10.0)
        return ([(t[0], d)], [(t[1], d)]) if t else ([], [])


class SimSpotBroker(_SimBroker):
    market, step, tick = "spot", 0.00001, 0.01

    def base_asset(self, symbol: str) -> str:
        return symbol.removesuffix(QUOTE)

    def min_notional(self, symbol: str) -> float:
        return 5.0

    def prepare(self, symbol: str, leverage: int) -> None:
        """Spot: sin margen ni apalancamiento."""

    def balances(self) -> dict[str, float]:
        self.v.net()
        return dict(self.v.balances)

    def free(self, asset: str) -> float:
        return self.balances().get(asset, 0.0)

    def position(self, symbol: str) -> Position:
        return Position(symbol, self.free(self.base_asset(symbol)))

    def equity(self) -> float:
        return self.free(QUOTE)


class SimFuturesBroker(_SimBroker):
    market, step, tick = "usdm", 0.001, 0.1

    def prepare(self, symbol: str, leverage: int) -> None:
        self.v.net()
        self.v.leverage[symbol] = int(leverage)

    def position(self, symbol: str) -> Position:
        self.v.net()
        q, e, _ = self.v.pos.get(symbol, [0.0, 0.0, 0.0])
        return Position(symbol, q, e or None)

    def _upnl(self, sym: str) -> float:
        q, e, _ = self.v.pos.get(sym, [0.0, 0.0, 0.0])
        return q * (self.v.mids.get(sym, e) - e)

    def equity(self) -> float:
        return self.account_summary()["equity"]

    def account_summary(self) -> dict[str, float]:
        self.v.net()
        upnl = sum(self._upnl(s) for s in self.v.pos)
        used = sum(m for _, _, m in self.v.pos.values())
        gross = sum(abs(q) * self.v.mids.get(s, e) for s, (q, e, _) in self.v.pos.items())
        im = sum(abs(q) * self.v.mids.get(s, e) / self.v.leverage.get(s, 1)
                 for s, (q, e, _) in self.v.pos.items())
        return {"equity": self.v.wallet + upnl, "available": self.v.wallet - used + min(upnl, 0),
                "initial_margin": im, "gross": gross}

    def position_risk(self, symbol: str) -> dict[str, float | None]:
        self.v.net()
        q, _, margin = self.v.pos.get(symbol, [0.0, 0.0, 0.0])
        if not q:
            return {"qty": 0.0, "mark": None, "liq": None, "margin": None, "upnl": None}
        return {"qty": q, "mark": self.v.mids.get(symbol), "liq": self.v.liq_price(symbol),
                "margin": margin, "upnl": self._upnl(symbol)}

    def add_margin(self, symbol: str, amount: float) -> None:
        if self.account_summary()["available"] < amount or symbol not in self.v.pos:
            raise OrderRejected("Margin is insufficient.", -2019)
        self.v.pos[symbol][2] += amount

    def funding_income(self, symbol: str, start: int) -> list[tuple[int, float]]:
        self.v.net()
        return [(t, a) for t, s, a in self.v.income if s == symbol and t >= start]
