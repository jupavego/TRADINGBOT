"""Exchange simulado con libro para el arbitraje (T45): spot y futuros testnet por HTTP, sin red.

`Venue` casa órdenes contra un libro (mejor compra/venta alrededor de `mids`) con mejora de
precio: una LIMIT que cruza se llena al mejor precio contrario. Controles de prueba:
- `empty`: símbolos con el libro vacío · `liquidity[sym]`: base que queda (se agota al llenar)
- `fill_cap[sym]`: máximo por orden (fill parcial; el resto queda abierto hasta cancelarse)
- `hooks`: funciones `(venue, orden)` tras cada orden (mover el precio, vaciar un libro…)
La API REST que lo expone está en `fake_venue_http.FakeHTTP` (se reexporta aquí).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass


class VenueError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code, self.msg = code, msg


@dataclass
class Venue:
    mids: dict[str, float]
    futures: bool = False
    spread_bps: float = 2.0
    step: float = 0.001
    tick: float = 0.1
    min_notional: float = 5.0
    fee_rate: float = 0.0
    fee_in_base: bool = False
    mmr: float = 0.005

    def __post_init__(self) -> None:
        self.empty: set[str] = set()
        self.liquidity: dict[str, float] = {}
        self.fill_cap: dict[str, float] = {}
        self.hooks: list[Callable[[Venue, dict], None]] = []
        self.orders: dict[str, dict] = {}
        self.seq = 0
        self.balances = {"USDT": 50_000.0, "BTC": 1.0, "ETH": 10.0}
        self.wallet = 20_000.0
        self.pos: dict[str, list[float]] = {}           # símbolo → [qty, entrada, margen]
        self.leverage: dict[str, int] = {}
        self.income: list[dict] = []

    # --- libro -----------------------------------------------------------------
    def top(self, sym: str) -> tuple[float, float] | None:
        if sym in self.empty or sym not in self.mids:
            return None
        m = self.mids[sym]
        h = m * self.spread_bps / 2e4
        return m - h, m + h

    def base_of(self, sym: str) -> str:
        return sym.split("USDT")[0]

    # --- órdenes -----------------------------------------------------------------
    def place(self, p: dict) -> dict:
        sym, cid = p["symbol"], p.get("newClientOrderId", "")
        old = self.orders.get(cid)
        if old is not None and old["status"] in ("NEW", "PARTIALLY_FILLED"):
            raise VenueError(-4116 if self.futures else -2010,
                             "ClientOrderId is duplicated" if self.futures
                             else "Duplicate order sent.")
        qty = float(p["quantity"])
        if qty <= 0 or abs(qty / self.step - round(qty / self.step)) > 1e-6:
            raise VenueError(-1111, "Precision is over the maximum defined for this asset.")
        ref = self.mids.get(sym, 0.0)
        if not self.futures and qty * ref < self.min_notional:
            raise VenueError(-1013, "Filter failure: NOTIONAL")
        side = 1 if p["side"] == "BUY" else -1
        reduce = p.get("reduceOnly") == "true"
        if reduce and self.pos.get(sym, [0.0])[0] * side >= 0:
            raise VenueError(-2022, "ReduceOnly Order is rejected.")
        if not self.futures:
            t = self.top(sym)
            px = float(p.get("price") or (t[1] if t else ref))
            if side > 0 and self.balances.get("USDT", 0) < qty * px:
                raise VenueError(-2010, "Account has insufficient balance for requested action.")
            if side < 0 and self.balances.get(self.base_of(sym), 0) < qty - 1e-12:
                raise VenueError(-2010, "Account has insufficient balance for requested action.")
        self.seq += 1
        o = {"symbol": sym, "orderId": self.seq, "clientOrderId": cid, "side": p["side"],
             "type": p["type"], "origQty": qty, "price": float(p.get("price") or 0),
             "status": "NEW", "executedQty": 0.0, "quote": 0.0, "reduceOnly": reduce,
             "fills": []}
        self.orders[cid] = o
        self.match(o)
        for h in list(self.hooks):
            h(self, o)
        return o

    def match(self, o: dict) -> None:
        sym, side = o["symbol"], 1 if o["side"] == "BUY" else -1
        t = self.top(sym)
        if t is None:
            if o["type"] == "MARKET":
                o["status"] = "EXPIRED"
            return
        px = t[1] if side > 0 else t[0]
        if o["type"] == "LIMIT" and (px - o["price"]) * side > 1e-9:
            return                                        # no cruza
        q = min(o["origQty"] - o["executedQty"], self.fill_cap.get(sym, math.inf),
                self.liquidity.get(sym, math.inf))
        if o["reduceOnly"]:
            q = min(q, abs(self.pos.get(sym, [0.0])[0]))
        q = math.floor(q / self.step + 1e-9) * self.step
        if q > 0:
            self._fill(o, sym, side, round(q, 10), px)
        if o["type"] == "MARKET" and o["status"] in ("NEW", "PARTIALLY_FILLED"):
            o["status"] = "EXPIRED" if o["executedQty"] < o["origQty"] - 1e-12 else "FILLED"

    def _fill(self, o: dict, sym: str, side: int, q: float, px: float) -> None:
        if sym in self.liquidity:
            self.liquidity[sym] -= q
        o["executedQty"] = round(o["executedQty"] + q, 10)
        o["quote"] += q * px
        o["status"] = "FILLED" if o["executedQty"] >= o["origQty"] - 1e-12 else \
            "PARTIALLY_FILLED"
        if self.futures:
            self._futures_fill(sym, side, q, px)
            return
        base = self.base_of(sym)
        fee = self.fee_rate * (q if side > 0 and self.fee_in_base else q * px)
        fee_asset = base if side > 0 and self.fee_in_base else "USDT"
        self.balances[base] = self.balances.get(base, 0.0) + side * q - (
            fee if fee_asset == base else 0.0)
        self.balances["USDT"] -= side * q * px + (fee if fee_asset == "USDT" else 0.0)
        o["fills"].append({"price": str(px), "qty": str(q), "commission": str(fee),
                           "commissionAsset": fee_asset})

    def _futures_fill(self, sym: str, side: int, q: float, px: float) -> None:
        qty, entry, margin = self.pos.get(sym, [0.0, 0.0, 0.0])
        lev = self.leverage.get(sym, 1)
        if qty == 0 or qty * side > 0:                     # abre o aumenta
            new = qty + side * q
            entry = (abs(qty) * entry + q * px) / abs(new)
            margin += q * px / lev
        else:                                              # reduce
            self.wallet += (px - entry) * min(q, abs(qty)) * (1 if qty > 0 else -1)
            new = qty + side * q
            margin *= abs(new) / abs(qty) if qty else 0.0
            if abs(new) < 1e-12:
                new, entry, margin = 0.0, 0.0, 0.0
        self.pos[sym] = [round(new, 10), entry, margin]

    def cancel(self, cid: str) -> dict | None:
        o = self.orders.get(cid)
        if o is not None and o["status"] in ("NEW", "PARTIALLY_FILLED"):
            o["status"] = "CANCELED"
        return o

    # --- futuros: riesgo y cuenta --------------------------------------------------
    def risk_row(self, sym: str) -> dict:
        qty, entry, margin = self.pos.get(sym, [0.0, 0.0, 0.0])
        mark = self.mids.get(sym, entry)
        liq = 0.0
        if qty < 0:
            liq = (margin + abs(qty) * entry) / (abs(qty) * (1 + self.mmr))
        elif qty > 0:
            liq = max((abs(qty) * entry - margin) / (abs(qty) * (1 - self.mmr)), 0.0)
        return {"symbol": sym, "positionSide": "BOTH", "positionAmt": str(qty),
                "entryPrice": str(entry), "markPrice": str(mark), "liquidationPrice": str(liq),
                "isolatedWallet": str(margin), "unRealizedProfit": str(qty * (mark - entry)),
                "marginType": "isolated", "notional": str(qty * mark)}

    def account(self) -> dict:
        rows = [self.risk_row(s) for s in self.pos]
        upnl = sum(float(r["unRealizedProfit"]) for r in rows)
        used = sum(m for _, _, m in self.pos.values())
        im = sum(abs(q) * self.mids.get(s, e) / self.leverage.get(s, 1)
                 for s, (q, e, _) in self.pos.items())
        return {"totalMarginBalance": str(self.wallet + upnl),
                "availableBalance": str(self.wallet - used + min(upnl, 0.0)),
                "totalInitialMargin": str(im), "positions": rows}


from tests.execution.fake_venue_http import FakeHTTP  # noqa: E402

__all__ = ["FakeHTTP", "Venue", "VenueError"]
