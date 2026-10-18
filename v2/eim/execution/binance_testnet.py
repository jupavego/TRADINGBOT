"""`BinanceTestnetBroker`: Binance USDⓈ-M Futures **testnet** por REST firmado (modo TESTNET).

Seguridad:
- Solo hosts de testnet (`TESTNET_HOSTS`); cualquier otro host se bloquea al construir, también
  si se inyecta un cliente. No existe camino a la API real desde aquí.
- Claves solo por entorno (`EIM_TESTNET_API_KEY` / `EIM_TESTNET_API_SECRET`): nunca en el
  repositorio, en `repr` ni en mensajes de error. La testnet no tiene retiros; aun así la clave
  debe crearse sin ese permiso. Firma y transporte: `binance_rest.SignedRest` (común con el
  broker spot de T45).
- SL/TP van por la API de órdenes algorítmicas (`/fapi/v1/algoOrder`): desde 2025-12 Binance
  no acepta STOP_MARKET/TAKE_PROFIT_MARKET en `/fapi/v1/order`.
- T45 (arbitraje): mejor precio, profundidad, riesgo de la posición (margen aislado y
  liquidación), añadir margen y funding cobrado (`/fapi/v1/income`).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from eim.core import Mode
from eim.execution.binance_rest import ENV_KEY, ENV_SECRET, Credentials, SignedRest, check_host
from eim.execution.broker import (
    CANCELED,
    EXPIRED,
    LIMIT,
    MARKET,
    NEW,
    STOP,
    TAKE_PROFIT,
    TRIGGERED,
    BrokerError,
    OrderRejected,
    OrderSpec,
    OrderState,
    Position,
)

__all__ = ["ENV_KEY", "ENV_SECRET", "BinanceTestnetBroker", "Credentials"]

TESTNET_HOSTS = frozenset({"testnet.binancefuture.com", "demo-fapi.binance.com"})
DEFAULT_URL = "https://testnet.binancefuture.com"
ENV_URL = "EIM_TESTNET_URL"
_NOT_FOUND = {-2011, -2013}
_STATUS = {"NEW": NEW, "PARTIALLY_FILLED": "PARTIALLY_FILLED", "FILLED": "FILLED",
           "CANCELED": CANCELED, "REJECTED": "REJECTED", "EXPIRED": EXPIRED,
           "EXPIRED_IN_MATCH": EXPIRED, "TRIGGERING": TRIGGERED, "TRIGGERED": TRIGGERED,
           "FINISHED": TRIGGERED}
_KIND = {"STOP_MARKET": STOP, "STOP": STOP, "TAKE_PROFIT_MARKET": TAKE_PROFIT,
         "TAKE_PROFIT": TAKE_PROFIT, "MARKET": MARKET, "LIMIT": LIMIT}


def _num(x: float | Decimal) -> str:
    return format(Decimal(str(x)).normalize(), "f")


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


class BinanceTestnetBroker:
    mode = Mode.TESTNET

    def __init__(self, creds: Credentials | None = None, base_url: str | None = None,
                 client: httpx.Client | None = None, recv_window: int = 5000,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        url = base_url or os.environ.get(ENV_URL, DEFAULT_URL)
        check_host(url, TESTNET_HOSTS)
        self._client = client or httpx.Client(base_url=url, timeout=10.0)
        self._creds = creds or Credentials.from_env()
        self._rest = SignedRest(self._client, self._creds, TESTNET_HOSTS, "/fapi/v1/time",
                                recv_window, clock)
        self._clock = clock
        self._filters: dict[str, tuple[Decimal, Decimal, Decimal]] = {}

    def __repr__(self) -> str:
        return f"BinanceTestnetBroker({self._client.base_url}, {self._creds!r})"

    @property
    def last_ok(self) -> int | None:
        """ms de la última respuesta del exchange."""
        return self._rest.last_ok

    def _call(self, method: str, path: str, params: dict[str, Any] | None = None,
              signed: bool = True) -> Any:
        return self._rest.call(method, path, params, signed)

    # --- símbolo -----------------------------------------------------------
    def _filter(self, symbol: str) -> tuple[Decimal, Decimal, Decimal]:
        if symbol not in self._filters:
            info = self._call("GET", "/fapi/v1/exchangeInfo", signed=False)
            for s in info["symbols"]:
                f = {x["filterType"]: x for x in s["filters"]}
                self._filters[s["symbol"]] = (Decimal(f["LOT_SIZE"]["stepSize"]),
                                              Decimal(f["PRICE_FILTER"]["tickSize"]),
                                              Decimal(f["LOT_SIZE"]["minQty"]))
            if symbol not in self._filters:
                raise BrokerError(f"símbolo desconocido en testnet: {symbol}")
        return self._filters[symbol]

    def round_qty(self, symbol: str, qty: float) -> float:
        step, _, min_qty = self._filter(symbol)
        q = (Decimal(str(qty)) / step).to_integral_value(ROUND_DOWN) * step
        return float(q) if q >= min_qty else 0.0

    def round_price(self, symbol: str, price: float) -> float:
        tick = self._filter(symbol)[1]
        return float((Decimal(str(price)) / tick).to_integral_value(ROUND_HALF_UP) * tick)

    def prepare(self, symbol: str, leverage: int) -> None:
        if self._call("GET", "/fapi/v1/positionSide/dual").get("dualSidePosition"):
            raise BrokerError("la cuenta está en modo cobertura (hedge): se exige one-way")
        try:
            self._call("POST", "/fapi/v1/marginType", {"symbol": symbol,
                                                       "marginType": "ISOLATED"})
        except OrderRejected as e:
            if e.code in (-4047, -4048):              # órdenes/posición abiertas: ¿ya aislado?
                rows = self._call("GET", "/fapi/v3/positionRisk", {"symbol": symbol})
                if not rows or any(str(r.get("marginType", "")).lower() != "isolated"
                                   for r in rows):
                    raise BrokerError(f"{symbol}: no se puede pasar a margen aislado con "
                                      "órdenes o posición abiertas") from None
            elif e.code != -4046:                     # -4046: ya es aislado
                raise
        self._call("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": int(leverage)})

    # --- órdenes -----------------------------------------------------------
    def post_order(self, spec: OrderSpec) -> OrderState:
        side = "BUY" if spec.side > 0 else "SELL"
        if spec.conditional:
            data = self._call("POST", "/fapi/v1/algoOrder", {
                "algoType": "CONDITIONAL", "symbol": spec.symbol, "side": side,
                "type": "STOP_MARKET" if spec.kind == STOP else "TAKE_PROFIT_MARKET",
                "triggerPrice": _num(spec.trigger or 0), "workingType": "MARK_PRICE",
                "closePosition": "true" if spec.close_position else None,
                "quantity": None if spec.close_position else _num(spec.qty or 0),
                "reduceOnly": "true" if spec.reduce_only and not spec.close_position else None,
                "clientAlgoId": spec.client_id})
            return self._algo_state(data)
        data = self._call("POST", "/fapi/v1/order", {
            "symbol": spec.symbol, "side": side, "type": spec.kind,
            "quantity": _num(spec.qty or 0),
            "price": _num(spec.price) if spec.kind == LIMIT and spec.price else None,
            "timeInForce": spec.tif if spec.kind == LIMIT else None,
            "reduceOnly": "true" if spec.reduce_only else None,
            "newClientOrderId": spec.client_id, "newOrderRespType": "RESULT"})
        return self._order_state(data)

    def get_order(self, symbol: str, client_id: str, conditional: bool) -> OrderState | None:
        try:
            if conditional:
                return self._algo_state(self._call("GET", "/fapi/v1/algoOrder",
                                                   {"clientAlgoId": client_id}))
            return self._order_state(self._call("GET", "/fapi/v1/order", {
                "symbol": symbol, "origClientOrderId": client_id}))
        except OrderRejected as e:
            if e.code in _NOT_FOUND:
                return None
            raise

    def cancel(self, symbol: str, client_id: str, conditional: bool) -> None:
        try:
            if conditional:
                self._call("DELETE", "/fapi/v1/algoOrder", {"clientAlgoId": client_id})
            else:
                self._call("DELETE", "/fapi/v1/order", {"symbol": symbol,
                                                        "origClientOrderId": client_id})
        except OrderRejected:
            o = self.get_order(symbol, client_id, conditional)
            if o is not None and o.is_open:           # sigue viva: el rechazo es real
                raise

    def open_orders(self, symbol: str) -> list[OrderState]:
        normal = self._call("GET", "/fapi/v1/openOrders", {"symbol": symbol})
        algo = self._call("GET", "/fapi/v1/openAlgoOrders", {"symbol": symbol})
        algo = algo.get("orders", algo) if isinstance(algo, dict) else algo
        return [self._order_state(o) for o in normal] + [self._algo_state(o) for o in algo]

    def position(self, symbol: str) -> Position:
        rows = self._call("GET", "/fapi/v3/positionRisk", {"symbol": symbol})
        qty = sum(_f(r.get("positionAmt")) or 0.0 for r in rows if r.get("symbol") == symbol)
        entry = next((_f(r.get("entryPrice")) for r in rows if _f(r.get("positionAmt"))), None)
        return Position(symbol, qty, entry if qty else None)

    def last_price(self, symbol: str) -> float:
        return float(self._call("GET", "/fapi/v1/ticker/price", {"symbol": symbol},
                                signed=False)["price"])

    def equity(self) -> float:
        return float(self._call("GET", "/fapi/v2/account")["totalMarginBalance"])

    # --- arbitraje (T45) ---------------------------------------------------
    def book_top(self, symbol: str) -> tuple[float, float] | None:
        """(mejor compra, mejor venta); None si el libro está vacío."""
        d = self._call("GET", "/fapi/v1/ticker/bookTicker", {"symbol": symbol}, signed=False)
        bid, ask = _f(d.get("bidPrice")) or 0.0, _f(d.get("askPrice")) or 0.0
        return (bid, ask) if bid > 0 and ask > 0 else None

    def depth(self, symbol: str, limit: int = 20) -> tuple[list, list]:
        d = self._call("GET", "/fapi/v1/depth", {"symbol": symbol, "limit": limit}, signed=False)
        return ([(float(p), float(q)) for p, q in d.get("bids", [])],
                [(float(p), float(q)) for p, q in d.get("asks", [])])

    def account_summary(self) -> dict[str, float]:
        """Capital, disponible, margen inicial y exposición bruta de TODA la cuenta (también lo
        que abrió el carril direccional: el arbitraje cuenta contra el total)."""
        d = self._call("GET", "/fapi/v2/account")
        gross = sum(abs(_f(p.get("notional")) or 0.0) for p in d.get("positions", []))
        return {"equity": float(d["totalMarginBalance"]),
                "available": _f(d.get("availableBalance")) or 0.0,
                "initial_margin": _f(d.get("totalInitialMargin")) or 0.0, "gross": gross}

    def position_risk(self, symbol: str) -> dict[str, float | None]:
        """Margen aislado, marca y precio de liquidación de la posición del símbolo."""
        rows = [r for r in self._call("GET", "/fapi/v3/positionRisk", {"symbol": symbol})
                if r.get("symbol") == symbol and _f(r.get("positionAmt"))]
        if not rows:
            return {"qty": 0.0, "mark": None, "liq": None, "margin": None, "upnl": None}
        r = rows[0]
        return {"qty": _f(r.get("positionAmt")), "mark": _f(r.get("markPrice")),
                "liq": _f(r.get("liquidationPrice")) or None,
                "margin": _f(r.get("isolatedWallet")) or _f(r.get("isolatedMargin")),
                "upnl": _f(r.get("unRealizedProfit"))}

    def add_margin(self, symbol: str, amount: float) -> None:
        """Añade margen a la posición aislada (rebalanceo sin tocar las patas)."""
        self._call("POST", "/fapi/v1/positionMargin", {"symbol": symbol,
                                                       "amount": _num(amount),
                                                       "type": 1})

    def funding_income(self, symbol: str, start: int) -> list[tuple[int, float]]:
        """Pagos de funding realmente cobrados (+) o pagados (−) desde `start` (ms)."""
        rows = self._call("GET", "/fapi/v1/income", {"symbol": symbol,
                                                     "incomeType": "FUNDING_FEE",
                                                     "startTime": start, "limit": 1000})
        return [(int(r["time"]), float(r["income"])) for r in rows]

    # --- respuestas --------------------------------------------------------
    @staticmethod
    def _order_state(d: dict) -> OrderState:
        filled = _f(d.get("executedQty")) or 0.0
        return OrderState(
            client_id=d["clientOrderId"], symbol=d["symbol"],
            side=1 if d["side"] == "BUY" else -1, kind=_KIND.get(d.get("origType") or d["type"],
                                                                 d["type"]),
            status=_STATUS.get(d["status"], d["status"]), qty=_f(d.get("origQty")),
            filled=filled, avg_price=(_f(d.get("avgPrice")) or None) if filled else None,
            trigger=_f(d.get("stopPrice")) or None, close_position=bool(d.get("closePosition")),
            reduce_only=bool(d.get("reduceOnly")), exchange_id=str(d.get("orderId", "")))

    @staticmethod
    def _algo_state(d: dict) -> OrderState:
        close = bool(d.get("closePosition"))
        return OrderState(
            client_id=d["clientAlgoId"], symbol=d["symbol"],
            side=1 if d["side"] == "BUY" else -1, kind=_KIND.get(d.get("orderType", ""), STOP),
            status=_STATUS.get(d.get("algoStatus", ""), d.get("algoStatus", "")),
            qty=None if close else _f(d.get("quantity")), trigger=_f(d.get("triggerPrice")),
            close_position=close, reduce_only=bool(d.get("reduceOnly")),
            exchange_id=str(d.get("algoId", "")))
