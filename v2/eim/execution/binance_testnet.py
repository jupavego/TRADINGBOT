"""`BinanceTestnetBroker`: Binance USDⓈ-M Futures **testnet** por REST firmado (modo TESTNET).

Seguridad:
- Solo hosts de testnet (`TESTNET_HOSTS`); cualquier otro host se bloquea al construir, también
  si se inyecta un cliente. No existe camino a la API real desde aquí.
- Claves solo por entorno (`EIM_TESTNET_API_KEY` / `EIM_TESTNET_API_SECRET`): nunca en el
  repositorio, en `repr` ni en mensajes de error. La testnet no tiene retiros; aun así la clave
  debe crearse sin ese permiso. Los parámetros firmados de POST/DELETE van en el cuerpo y el
  registro de `httpx` se sube a WARNING para que ninguna URL firmada llegue a los logs.
- SL/TP van por la API de órdenes algorítmicas (`/fapi/v1/algoOrder`): desde 2025-12 Binance
  no acepta STOP_MARKET/TAKE_PROFIT_MARKET en `/fapi/v1/order`.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from collections.abc import Callable
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from eim.core import Mode
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
    NetworkError,
    OrderRejected,
    OrderSpec,
    OrderState,
    Position,
)

TESTNET_HOSTS = frozenset({"testnet.binancefuture.com", "demo-fapi.binance.com"})
DEFAULT_URL = "https://testnet.binancefuture.com"
ENV_KEY, ENV_SECRET, ENV_URL = "EIM_TESTNET_API_KEY", "EIM_TESTNET_API_SECRET", "EIM_TESTNET_URL"
_NOT_FOUND = {-2011, -2013}
_DUPLICATE = {-4116}
_AMBIGUOUS_HTTP = {408, 418, 429}
_STATUS = {"NEW": NEW, "PARTIALLY_FILLED": "PARTIALLY_FILLED", "FILLED": "FILLED",
           "CANCELED": CANCELED, "REJECTED": "REJECTED", "EXPIRED": EXPIRED,
           "EXPIRED_IN_MATCH": EXPIRED, "TRIGGERING": TRIGGERED, "TRIGGERED": TRIGGERED,
           "FINISHED": TRIGGERED}
_KIND = {"STOP_MARKET": STOP, "STOP": STOP, "TAKE_PROFIT_MARKET": TAKE_PROFIT,
         "TAKE_PROFIT": TAKE_PROFIT, "MARKET": MARKET, "LIMIT": LIMIT}


def check_host(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in TESTNET_HOSTS:
        raise BrokerError(f"host bloqueado: '{parts.hostname}' no es la testnet de Binance")


class Credentials:
    """Clave y secreto de testnet. `repr` nunca muestra el secreto."""

    def __init__(self, key: str, secret: str) -> None:
        if not key or not secret:
            raise BrokerError(f"faltan {ENV_KEY}/{ENV_SECRET} en el entorno (claves de testnet)")
        self.key, self._secret = key, secret.encode()

    @classmethod
    def from_env(cls) -> Credentials:
        return cls(os.environ.get(ENV_KEY, ""), os.environ.get(ENV_SECRET, ""))

    def sign(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    def __repr__(self) -> str:
        return f"Credentials(key=…{self.key[-4:]}, secret=***)"


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
        check_host(url)
        self._client = client or httpx.Client(base_url=url, timeout=10.0)
        check_host(str(self._client.base_url))
        self._creds = creds or Credentials.from_env()
        self._recv, self._clock = recv_window, clock
        self._offset: int | None = None
        self._filters: dict[str, tuple[Decimal, Decimal, Decimal]] = {}
        self.last_ok: int | None = None            # ms de la última respuesta del exchange
        logging.getLogger("httpx").setLevel(logging.WARNING)

    def __repr__(self) -> str:
        return f"BinanceTestnetBroker({self._client.base_url}, {self._creds!r})"

    # --- HTTP --------------------------------------------------------------
    def _call(self, method: str, path: str, params: dict[str, Any] | None = None,
              signed: bool = True) -> Any:
        p = {k: v for k, v in (params or {}).items() if v is not None}
        headers: dict[str, str] = {}
        if signed:
            if self._offset is None:
                self._sync_time()
            p.update(timestamp=self._clock() + (self._offset or 0), recvWindow=self._recv)
            body = urlencode(p)
            body += "&signature=" + self._creds.sign(body)
            headers["X-MBX-APIKEY"] = self._creds.key
        else:
            body = urlencode(p)
        try:
            if method == "GET":
                resp = self._client.request("GET", f"{path}?{body}" if body else path,
                                            headers=headers)
            else:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                resp = self._client.request(method, path, content=body, headers=headers)
        except httpx.TransportError as exc:          # sin URL: nunca filtra la firma
            raise NetworkError(f"red: {type(exc).__name__} en {method} {path}") from None
        if resp.status_code >= 500 or resp.status_code in _AMBIGUOUS_HTTP:
            raise NetworkError(f"HTTP {resp.status_code} en {method} {path}")
        try:
            data = resp.json()
        except ValueError:
            raise NetworkError(f"respuesta ilegible en {method} {path}") from None
        if resp.status_code >= 400:
            code = data.get("code") if isinstance(data, dict) else None
            msg = str(data.get("msg", "")) if isinstance(data, dict) else ""
            if code == -1021:                        # reloj fuera de recvWindow: no procesada
                self._offset = None
                raise NetworkError(f"reloj desincronizado en {path}")
            raise OrderRejected(msg, code, duplicate=code in _DUPLICATE)
        self.last_ok = self._clock()
        return data

    def _sync_time(self) -> None:
        self._offset = 0
        server = self._call("GET", "/fapi/v1/time", signed=False)["serverTime"]
        self._offset = int(server) - self._clock()

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
            "timeInForce": "GTC" if spec.kind == LIMIT else None,
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
