"""`BinanceSpotTestnetBroker`: Binance **Spot testnet** por REST firmado (modo TESTNET, T45).

Pata spot del arbitraje (carry y base): compra/venta del activo contra USDT. Misma seguridad que
el broker de futuros (`binance_rest`): solo hosts de testnet, claves solo por entorno
(`EIM_SPOT_TESTNET_API_KEY/SECRET`; si faltan, las de futuros, que valen en la cuenta demo),
firma en el cuerpo. En spot no hay apalancamiento ni posición: la «posición» es el saldo total
(libre + bloqueado) de la moneda base y la comisión de una compra puede cobrarse en esa moneda
(`OrderState.fee`/`fee_asset`: de los `fills` de la respuesta FULL o de `myTrades`).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import replace
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from eim.core import Mode
from eim.execution.binance_rest import ENV_KEY as FUT_KEY
from eim.execution.binance_rest import ENV_SECRET as FUT_SECRET
from eim.execution.binance_rest import Credentials, SignedRest, check_host
from eim.execution.broker import (
    CANCELED,
    EXPIRED,
    FILLED,
    LIMIT,
    MARKET,
    NEW,
    PARTIAL,
    REJECTED,
    BrokerError,
    OrderRejected,
    OrderSpec,
    OrderState,
    Position,
)

TESTNET_HOSTS = frozenset({"testnet.binance.vision", "demo-api.binance.com"})
DEFAULT_URL = "https://testnet.binance.vision"
ENV_KEY, ENV_SECRET = "EIM_SPOT_TESTNET_API_KEY", "EIM_SPOT_TESTNET_API_SECRET"
ENV_URL = "EIM_SPOT_TESTNET_URL"
QUOTE = "USDT"
_NOT_FOUND = {-2011, -2013}
_STATUS = {"NEW": NEW, "PARTIALLY_FILLED": PARTIAL, "FILLED": FILLED, "CANCELED": CANCELED,
           "PENDING_CANCEL": CANCELED, "REJECTED": REJECTED, "EXPIRED": EXPIRED,
           "EXPIRED_IN_MATCH": EXPIRED}
_TERMINAL = {FILLED, CANCELED, EXPIRED, REJECTED}


def _num(x: float | Decimal) -> str:
    return format(Decimal(str(x)).normalize(), "f")


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _env_creds() -> Credentials:
    if os.environ.get(ENV_KEY) or os.environ.get(ENV_SECRET):
        return Credentials.from_env(ENV_KEY, ENV_SECRET)
    return Credentials.from_env(FUT_KEY, FUT_SECRET)


class BinanceSpotTestnetBroker:
    mode = Mode.TESTNET
    market = "spot"

    def __init__(self, creds: Credentials | None = None, base_url: str | None = None,
                 client: httpx.Client | None = None, recv_window: int = 5000,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        url = base_url or os.environ.get(ENV_URL, DEFAULT_URL)
        check_host(url, TESTNET_HOSTS, "la testnet spot de Binance")
        self._client = client or httpx.Client(base_url=url, timeout=10.0)
        self._creds = creds or _env_creds()
        self._rest = SignedRest(self._client, self._creds, TESTNET_HOSTS, "/api/v3/time",
                                recv_window, clock)
        self._info: dict[str, dict[str, Any]] = {}

    def __repr__(self) -> str:
        return f"BinanceSpotTestnetBroker({self._client.base_url}, {self._creds!r})"

    @property
    def last_ok(self) -> int | None:
        return self._rest.last_ok

    def _call(self, method: str, path: str, params: dict[str, Any] | None = None,
              signed: bool = True) -> Any:
        return self._rest.call(method, path, params, signed)

    # --- símbolo -----------------------------------------------------------
    def _symbol(self, symbol: str) -> dict[str, Any]:
        if symbol not in self._info:
            try:
                d = self._call("GET", "/api/v3/exchangeInfo", {"symbol": symbol}, signed=False)
            except OrderRejected as e:
                raise BrokerError(f"símbolo desconocido en la testnet spot: {symbol}") from e
            for s in d.get("symbols", []):
                f = {x["filterType"]: x for x in s["filters"]}
                notional = f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {}
                self._info[s["symbol"]] = {
                    "base": s["baseAsset"], "quote": s["quoteAsset"],
                    "step": Decimal(f["LOT_SIZE"]["stepSize"]),
                    "min_qty": Decimal(f["LOT_SIZE"]["minQty"]),
                    "tick": Decimal(f["PRICE_FILTER"]["tickSize"]),
                    "min_notional": _f(notional.get("minNotional"))}
            if symbol not in self._info:
                raise BrokerError(f"símbolo desconocido en la testnet spot: {symbol}")
        return self._info[symbol]

    def base_asset(self, symbol: str) -> str:
        return str(self._symbol(symbol)["base"])

    def min_notional(self, symbol: str) -> float:
        return float(self._symbol(symbol)["min_notional"])

    def prepare(self, symbol: str, leverage: int) -> None:
        """Spot: sin margen ni apalancamiento; solo valida el símbolo."""
        self._symbol(symbol)

    def round_qty(self, symbol: str, qty: float) -> float:
        i = self._symbol(symbol)
        q = (Decimal(str(qty)) / i["step"]).to_integral_value(ROUND_DOWN) * i["step"]
        return float(q) if q >= i["min_qty"] else 0.0

    def round_price(self, symbol: str, price: float) -> float:
        tick = self._symbol(symbol)["tick"]
        return float((Decimal(str(price)) / tick).to_integral_value(ROUND_HALF_UP) * tick)

    # --- órdenes -----------------------------------------------------------
    def post_order(self, spec: OrderSpec) -> OrderState:
        if spec.kind not in (MARKET, LIMIT):
            raise BrokerError(f"spot no admite órdenes {spec.kind}")
        data = self._call("POST", "/api/v3/order", {
            "symbol": spec.symbol, "side": "BUY" if spec.side > 0 else "SELL",
            "type": spec.kind, "quantity": _num(spec.qty or 0),
            "price": _num(spec.price) if spec.kind == LIMIT and spec.price else None,
            "timeInForce": spec.tif if spec.kind == LIMIT else None,
            "newClientOrderId": spec.client_id, "newOrderRespType": "FULL"})
        return self._state(data)

    def get_order(self, symbol: str, client_id: str,
                  conditional: bool = False) -> OrderState | None:
        try:
            st = self._state(self._call("GET", "/api/v3/order", {
                "symbol": symbol, "origClientOrderId": client_id}))
        except OrderRejected as e:
            if e.code in _NOT_FOUND:
                return None
            raise
        if st.filled > 0 and st.status in _TERMINAL and not st.fee_asset:
            fee, asset = self._fees(symbol, st.exchange_id)
            st = replace(st, fee=fee, fee_asset=asset)
        return st

    def _fees(self, symbol: str, order_id: str) -> tuple[float, str]:
        rows = self._call("GET", "/api/v3/myTrades", {"symbol": symbol, "orderId": order_id})
        assets = {r.get("commissionAsset", "") for r in rows}
        return sum(_f(r.get("commission")) for r in rows), ",".join(sorted(a for a in assets if a))

    def cancel(self, symbol: str, client_id: str, conditional: bool = False) -> None:
        try:
            self._call("DELETE", "/api/v3/order", {"symbol": symbol,
                                                   "origClientOrderId": client_id})
        except OrderRejected:
            o = self.get_order(symbol, client_id)
            if o is not None and o.is_open:           # sigue viva: el rechazo es real
                raise

    def open_orders(self, symbol: str) -> list[OrderState]:
        return [self._state(o) for o in self._call("GET", "/api/v3/openOrders",
                                                   {"symbol": symbol})]

    # --- cuenta y mercado ----------------------------------------------------
    def balances(self) -> dict[str, float]:
        """Saldo total (libre + bloqueado) por moneda."""
        rows = self._call("GET", "/api/v3/account", {"omitZeroBalances": "true"})["balances"]
        return {r["asset"]: _f(r.get("free")) + _f(r.get("locked")) for r in rows}

    def free(self, asset: str) -> float:
        rows = self._call("GET", "/api/v3/account", {"omitZeroBalances": "true"})["balances"]
        return next((_f(r.get("free")) for r in rows if r["asset"] == asset), 0.0)

    def position(self, symbol: str) -> Position:
        return Position(symbol, self.balances().get(self.base_asset(symbol), 0.0))

    def equity(self) -> float:
        """Capital spot disponible para el arbitraje = saldo en USDT."""
        return self.balances().get(QUOTE, 0.0)

    def book_top(self, symbol: str) -> tuple[float, float] | None:
        d = self._call("GET", "/api/v3/ticker/bookTicker", {"symbol": symbol}, signed=False)
        bid, ask = _f(d.get("bidPrice")), _f(d.get("askPrice"))
        return (bid, ask) if bid > 0 and ask > 0 else None

    def depth(self, symbol: str, limit: int = 20) -> tuple[list, list]:
        d = self._call("GET", "/api/v3/depth", {"symbol": symbol, "limit": limit}, signed=False)
        return ([(float(p), float(q)) for p, q in d.get("bids", [])],
                [(float(p), float(q)) for p, q in d.get("asks", [])])

    # --- respuestas --------------------------------------------------------
    @staticmethod
    def _state(d: dict) -> OrderState:
        filled = _f(d.get("executedQty"))
        quote = _f(d.get("cummulativeQuoteQty"))
        fills = d.get("fills") or []
        assets = sorted({x.get("commissionAsset", "") for x in fills} - {""})
        return OrderState(
            client_id=d["clientOrderId"], symbol=d["symbol"],
            side=1 if d["side"] == "BUY" else -1, kind=d.get("type", MARKET),
            status=_STATUS.get(d["status"], d["status"]), qty=_f(d.get("origQty")),
            filled=filled, avg_price=quote / filled if filled > 0 and quote > 0 else None,
            exchange_id=str(d.get("orderId", "")),
            fee=sum(_f(x.get("commission")) for x in fills), fee_asset=",".join(assets))
