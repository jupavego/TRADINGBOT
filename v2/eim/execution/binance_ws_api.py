"""Órdenes por el WS API de Binance USDⓈ-M **testnet** (T83) + extras REST del carril HFT.

Por qué WS API y no REST (medición de T77, `v2/reports/hft_latency.md`): el presupuesto de
310 ms p99 se armó con la ida del WS API (p99 138 ms); por REST la ida p99 es ≈ 205 ms y lo
rompería en ≈ 66 ms. Además el WS API tiene su propio peso por IP (la IP ya gasta ≈ 12 % del
de REST con los demás servicios); el límite de órdenes por cuenta sí es común.

`BinanceWsApiBroker` = `BinanceTestnetBroker` con las órdenes normales (`order.place`,
`order.status`, `order.cancel`) por WS API; condicionales (SL/TP, T30), posición y cuenta siguen
por REST. Extras REST: `countdownCancelAll` (hombre muerto del exchange; parámetros verificados
en la documentación oficial el 2026-10-24: `symbol`, `countdownTime` en ms, 0 lo apaga, peso
10) y `listenKey` (flujo de usuario; solo cabecera de la clave).

Seguridad (como T30): solo el host de testnet, también si se inyecta la conexión; claves solo
por entorno; firma HMAC por petición sobre los parámetros ordenados por nombre (`apiKey` y
`timestamp` incluidos); ningún error ni registro lleva parámetros firmados. Sin `session.logon`
(exige Ed25519; T77 lo deja para cuando la latencia lo justifique).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from eim.execution.binance_rest import DEFAULT_WAIT_MS, Credentials
from eim.execution.binance_testnet import _NOT_FOUND, BinanceTestnetBroker, _num
from eim.execution.broker import (
    LIMIT,
    BrokerError,
    NetworkError,
    OrderRejected,
    OrderSpec,
    OrderState,
    RateLimited,
)

WS_HOSTS = frozenset({"testnet.binancefuture.com"})
WS_URL = "wss://testnet.binancefuture.com/ws-fapi/v1"
ENV_WS_URL = "EIM_TESTNET_WS_API_URL"


def check_ws_host(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "wss" or parts.hostname not in WS_HOSTS:
        raise BrokerError(f"host bloqueado: '{parts.hostname}' no es el WS API de la testnet")


def _connect(url: str):
    from websockets.sync.client import connect
    return connect(url, open_timeout=10, max_size=2**20)


class WsApiClient:
    """Cliente síncrono: una petición por mensaje, respuesta casada por `id`. Un 429/418 deja
    el cliente en espera (`blocked`) y mientras dure no se envía nada."""

    def __init__(self, creds: Credentials, url: str | None = None,
                 connect: Callable[[str], Any] | None = None,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000),
                 offset: Callable[[], int] = lambda: 0, recv_window: int = 5000,
                 timeout_s: float = 5.0, limits: Any = None) -> None:
        self.url = url or os.environ.get(ENV_WS_URL, WS_URL)
        check_ws_host(self.url)
        self._creds, self._connect = creds, connect or _connect
        self._clock, self._offset, self._recv, self._timeout = clock, offset, recv_window, timeout_s
        self._ws: Any = None
        self._seq = 0
        self._limits = limits if limits is not None else self   # dueño del bloqueo 429/418
        if limits is None:
            self.blocked: RateLimited | None = None
        self.last_ok: int | None = None
        self.rate_limits: list[dict] = []

    def disconnect(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001 — cerrar nunca debe fallar hacia arriba
                pass

    def _sign(self, p: dict[str, Any]) -> dict[str, Any]:
        p = {**p, "apiKey": self._creds.key, "timestamp": self._clock() + self._offset(),
             "recvWindow": self._recv}
        p["signature"] = self._creds.sign("&".join(f"{k}={p[k]}" for k in sorted(p)))
        return p

    def _roundtrip(self, method: str, params: dict[str, Any]) -> dict:
        self._seq += 1
        rid = f"eim-{self._seq}"
        try:
            if self._ws is None:
                self._ws = self._connect(self.url)
            self._ws.send(json.dumps({"id": rid, "method": method, "params": params}))
            deadline = time.monotonic() + self._timeout
            while True:
                left = max(deadline - time.monotonic(), 0.001)
                msg = json.loads(self._ws.recv(timeout=left))
                if isinstance(msg, dict) and msg.get("id") == rid:
                    return msg
        except Exception as exc:  # corte, tiempo agotado o ilegible: resultado desconocido
            self.disconnect()
            raise NetworkError(f"WS API: {type(exc).__name__} en {method}") from None

    def request(self, method: str, params: dict[str, Any], signed: bool = True) -> Any:
        b = self._limits.blocked
        if b is not None and self._clock() < b.until:
            raise RateLimited(f"en espera por {b}", b.status, b.until)
        p = {k: v for k, v in params.items() if v is not None}
        msg = self._roundtrip(method, self._sign(p) if signed else p)
        status = int(msg.get("status") or 0)
        err = msg.get("error") or {}
        self.rate_limits = msg.get("rateLimits") or self.rate_limits
        if status in DEFAULT_WAIT_MS:
            retry = (err.get("data") or {}).get("retryAfter")     # ms del exchange
            until = (int(retry) - self._offset() if retry else
                     self._clock() + DEFAULT_WAIT_MS[status])
            blocked = RateLimited(f"WS API {status} en {method}", status, until)
            self._limits.blocked = blocked
            raise blocked
        if status >= 500:
            raise NetworkError(f"WS API {status} en {method}")
        if status >= 400 or err:
            code, text = err.get("code"), str(err.get("msg", ""))
            if code == -1021:
                raise NetworkError(f"reloj desincronizado en {method}")
            raise OrderRejected(text, code, duplicate=code == -4116 or "duplicate" in text.lower())
        self.last_ok = self._clock()
        return msg.get("result")


class BinanceWsApiBroker(BinanceTestnetBroker):
    def __init__(self, creds: Credentials | None = None, base_url: str | None = None,
                 client=None, ws: WsApiClient | None = None,
                 ws_connect: Callable[[str], Any] | None = None, recv_window: int = 5000,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        super().__init__(creds, base_url, client, recv_window, clock)
        # el límite es por IP: un 429/418 del WS API también detiene el REST, y viceversa
        self.ws = ws or WsApiClient(self._creds, connect=ws_connect, clock=clock,
                                    offset=self._rest.offset, recv_window=recv_window,
                                    limits=self._rest)

    def __repr__(self) -> str:
        return f"BinanceWsApiBroker({self.ws.url}, {self._creds!r})"

    def _post_regular(self, spec: OrderSpec) -> OrderState:
        """Las órdenes normales van por WS API; las condicionales siguen por REST."""
        limit = spec.kind == LIMIT
        data = self.ws.request("order.place", {
            "symbol": spec.symbol, "side": "BUY" if spec.side > 0 else "SELL", "type": spec.kind,
            "quantity": _num(spec.qty or 0), "price": _num(spec.price) if limit and spec.price
            else None, "timeInForce": spec.tif if limit else None,
            "reduceOnly": "true" if spec.reduce_only else None,
            "newClientOrderId": spec.client_id, "newOrderRespType": "RESULT"})
        return self._order_state(data)

    def get_order(self, symbol: str, client_id: str, conditional: bool) -> OrderState | None:
        if conditional:
            return super().get_order(symbol, client_id, conditional)
        try:
            return self._order_state(self.ws.request("order.status", {
                "symbol": symbol, "origClientOrderId": client_id}))
        except OrderRejected as e:
            if e.code in _NOT_FOUND:
                return None
            raise

    def cancel(self, symbol: str, client_id: str, conditional: bool) -> None:
        if conditional:
            return super().cancel(symbol, client_id, conditional)
        try:
            self.ws.request("order.cancel", {"symbol": symbol, "origClientOrderId": client_id})
        except OrderRejected:
            o = self.get_order(symbol, client_id, False)
            if o is not None and o.is_open:           # sigue viva: el rechazo es real
                raise

    # --- REST del carril HFT ---------------------------------------------------------
    def countdown_cancel_all(self, symbol: str, ms: int) -> None:
        """Si no se renueva en `ms`, el exchange cancela todas las órdenes abiertas del símbolo."""
        self._call("POST", "/fapi/v1/countdownCancelAll",
                   {"symbol": symbol, "countdownTime": int(ms)})

    def listen_key(self) -> str:
        return str(self._rest.call("POST", "/fapi/v1/listenKey", signed=False,
                                   keyed=True)["listenKey"])

    def keepalive_listen_key(self) -> None:
        self._rest.call("PUT", "/fapi/v1/listenKey", signed=False, keyed=True)

    def close_listen_key(self) -> None:
        self._rest.call("DELETE", "/fapi/v1/listenKey", signed=False, keyed=True)
