"""Exchange de arbitraje simulado (modo SIMULADO): spot + futuros USDⓈ-M en memoria.

Sus brokers (`arb_sim_brokers.py`) tienen la misma interfaz que los de testnet: el ejecutor de
arbitraje, su riesgo y su reconciliación (T45) corren sin cambios y sin cuenta de Binance.
Precios = los que se le dan (`set_mid`, p. ej. velas reales); libro = medio diferencial
alrededor del precio con profundidad fija por lado (`depth`). Casación con mejora de precio (una
LIMIT que cruza se llena al mejor precio contrario). Comisiones VIP 0 tomador: spot 0,10 %
(compra cobrada en la moneda base, venta en USDT, como Binance sin BNB) y futuros 0,05 %.
Futuros one-way con margen aislado, liquidación al cruzar su precio y funding
(`settle_funding`). Mínimo de orden de futuros 100 USDT (salvo reduce-only).
Fallos para las pruebas: `reject[símbolo]` (rechazo), `down` (red cortada: toda llamada lanza
`NetworkError`), `empty` (libro vacío) y `hooks` (tras cada orden).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from eim.execution.broker import (
    CANCELED,
    EXPIRED,
    FILLED,
    LIMIT,
    MARKET,
    NEW,
    PARTIAL,
    NetworkError,
    OrderRejected,
    OrderSpec,
    OrderState,
)

QUOTE = "USDT"


@dataclass
class SimVenue:
    spread_bps: float = 2.0
    depth: dict[str, float] = field(default_factory=dict)   # base visible por lado
    spot_fee: float = 0.001
    fut_fee: float = 0.0005
    mmr: float = 0.005
    min_fut_notional: float = 100.0
    mids: dict[str, float] = field(default_factory=dict)
    balances: dict[str, float] = field(default_factory=lambda: {QUOTE: 10_000.0})
    wallet: float = 10_000.0                                 # USDT de la cuenta de futuros
    empty: set[str] = field(default_factory=set)
    reject: dict[str, str] = field(default_factory=dict)
    down: bool = False
    hooks: list[Callable[[SimVenue, OrderState], None]] = field(default_factory=list)
    clock: Callable[[], int] = lambda: 0

    def __post_init__(self) -> None:
        self.orders: dict[str, tuple[OrderState, float, str]] = {}  # cid → (estado, USDT, mercado)
        self.pos: dict[str, list[float]] = {}           # símbolo → [qty, entrada, margen]
        self.leverage: dict[str, int] = {}
        self.income: list[tuple[int, str, float]] = []               # (t, símbolo, USDT)
        self.liquidations: list[tuple[int, str, float]] = []
        self.seq = 0

    # --- mercado ---------------------------------------------------------------
    def net(self) -> None:
        if self.down:
            raise NetworkError("red cortada (simulada)")

    def set_mid(self, sym: str, px: float) -> None:
        self.mids[sym] = px
        q, _, _ = self.pos.get(sym, [0.0, 0.0, 0.0])
        liq = self.liq_price(sym)
        if q and liq and ((q < 0 and px >= liq) or (q > 0 and px <= liq)):
            self.liquidations.append((self.clock(), sym, px))
            self.wallet -= self.pos[sym][2]                  # se pierde el margen aislado
            self.pos[sym] = [0.0, 0.0, 0.0]

    def top(self, sym: str) -> tuple[float, float] | None:
        if sym in self.empty or sym not in self.mids:
            return None
        m = self.mids[sym]
        h = m * self.spread_bps / 2e4
        return m - h, m + h

    def settle_funding(self, sym: str, rate: float, t: int) -> float:
        """Liquidación de funding: el corto cobra `rate × nocional` si `rate` > 0."""
        q, e, margin = self.pos.get(sym, [0.0, 0.0, 0.0])
        if not q:
            return 0.0
        amount = -q * rate * self.mids.get(sym, e)
        self.pos[sym][2] = margin + amount                   # margen aislado de la posición
        self.wallet += amount
        self.income.append((t, sym, amount))
        return amount

    def liq_price(self, sym: str) -> float | None:
        q, e, margin = self.pos.get(sym, [0.0, 0.0, 0.0])
        if q < 0:
            return (margin + abs(q) * e) / (abs(q) * (1 + self.mmr))
        if q > 0:
            return max((abs(q) * e - margin) / (abs(q) * (1 - self.mmr)), 0.0)
        return None

    # --- órdenes -----------------------------------------------------------------
    def book_order(self, market: str, spec: OrderSpec, step: float) -> OrderState:
        self.net()
        sym, side = spec.symbol, spec.side
        old = self.orders.get(spec.client_id)
        if old is not None and old[0].is_open:
            raise OrderRejected("Duplicate order sent.", -2010, duplicate=True)
        if sym in self.reject:
            raise OrderRejected(self.reject[sym], -2019)
        qty = spec.qty or 0.0
        if qty <= 0 or abs(qty / step - round(qty / step)) > 1e-6:
            raise OrderRejected("Precision is over the maximum defined for this asset.", -1111)
        t = self.top(sym)
        ref = spec.price or (t[1] if t and side > 0 else t[0] if t else self.mids.get(sym, 0.0))
        if market == "spot":
            base = sym.removesuffix(QUOTE)
            if side > 0 and self.balances.get(QUOTE, 0.0) < qty * ref:
                raise OrderRejected("Account has insufficient balance for requested action.", -2010)
            if side < 0 and self.balances.get(base, 0.0) < qty - 1e-12:
                raise OrderRejected("Account has insufficient balance for requested action.", -2010)
        else:
            q0 = self.pos.get(sym, [0.0])[0]
            if spec.reduce_only and q0 * side >= 0:
                raise OrderRejected("ReduceOnly Order is rejected.", -2022)
            if not spec.reduce_only and qty * ref < self.min_fut_notional:
                raise OrderRejected(f"Order's notional must be no smaller than "
                                    f"{self.min_fut_notional:g}", -4164)
        self.seq += 1
        st = OrderState(client_id=spec.client_id, symbol=sym, side=side, kind=spec.kind,
                        status=NEW, qty=qty, reduce_only=spec.reduce_only,
                        exchange_id=str(self.seq))
        self.orders[spec.client_id] = (st, 0.0, market)
        self._match(spec.client_id, spec.price)
        st = self.orders[spec.client_id][0]
        for h in list(self.hooks):
            h(self, st)
        return st

    def _match(self, cid: str, limit: float | None) -> None:
        st, quote, market = self.orders[cid]
        sym, side = st.symbol, st.side
        t = self.top(sym)
        if t is None:
            if st.kind == MARKET:
                self.orders[cid] = (replace(st, status=EXPIRED), quote, market)
            return
        px = t[1] if side > 0 else t[0]
        if st.kind == LIMIT and limit is not None and (px - limit) * side > 1e-9:
            return                                           # no cruza: queda abierta
        q = min((st.qty or 0.0) - st.filled, self.depth.get(sym, math.inf))
        if st.reduce_only:
            q = min(q, abs(self.pos.get(sym, [0.0])[0]))
        if q <= 1e-12:
            if st.kind == MARKET:
                self.orders[cid] = (replace(st, status=EXPIRED), quote, market)
            return
        fee, fee_asset = self._fill(market, sym, side, q, px)
        filled = round(st.filled + q, 10)
        quote += q * px
        done = filled >= (st.qty or 0.0) - 1e-12
        status = FILLED if done else (EXPIRED if st.kind == MARKET else PARTIAL)
        self.orders[cid] = (replace(st, filled=filled, avg_price=quote / filled, status=status,
                                    fee=st.fee + fee, fee_asset=fee_asset), quote, market)

    def _fill(self, market: str, sym: str, side: int, q: float, px: float) -> tuple[float, str]:
        if market == "spot":
            base = sym.removesuffix(QUOTE)
            if side > 0:                                     # compra: comisión en la base
                fee = q * self.spot_fee
                self.balances[base] = self.balances.get(base, 0.0) + q - fee
                self.balances[QUOTE] -= q * px
                return fee, base
            fee = q * px * self.spot_fee
            self.balances[base] -= q
            self.balances[QUOTE] += q * px - fee
            return fee, QUOTE
        qty, entry, margin = self.pos.get(sym, [0.0, 0.0, 0.0])
        lev = self.leverage.get(sym, 1)
        if qty == 0 or qty * side > 0:                       # abre o aumenta
            new = qty + side * q
            entry = (abs(qty) * entry + q * px) / abs(new)
            margin += q * px / lev
        else:                                                # reduce: realiza esa parte
            pnl = (px - entry) * q * (1 if qty > 0 else -1)
            self.wallet += pnl
            new = qty + side * q
            margin = margin * abs(new) / abs(qty) if abs(new) > 1e-12 else 0.0
            if abs(new) < 1e-12:
                new, entry = 0.0, 0.0
        fee = q * px * self.fut_fee
        self.wallet -= fee
        self.pos[sym] = [round(new, 10), entry, margin]
        return fee, QUOTE

    def cancel(self, cid: str) -> None:
        self.net()
        st, quote, market = self.orders[cid]
        if st.is_open:
            self.orders[cid] = (replace(st, status=CANCELED), quote, market)
