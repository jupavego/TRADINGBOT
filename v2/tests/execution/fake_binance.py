"""Exchange simulado con la API REST de Binance Futures (testnet), sin red.

Traduce cada petición a un `SimBroker` y responde con el formato de Binance. Comprueba la firma
HMAC y la cabecera de la clave. Inyección de fallos por ruta:
- `before`: la petición no llega (ConnectError) · `after`: se procesa pero la respuesta se pierde
- `503`: error de servidor sin procesar · `reject`: rechazo 400 con código
- `down = True`: red cortada para todo.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from urllib.parse import parse_qsl

import httpx

from eim.execution.broker import (
    LIMIT,
    MARKET,
    STOP,
    TAKE_PROFIT,
    TRIGGERED,
    OrderRejected,
    OrderSpec,
    OrderState,
)
from eim.execution.sim_broker import SimBroker

KEY, SECRET = "test-key-1234", "test-secret-abcd"
URL = "https://testnet.binancefuture.com"


@dataclass
class Fault:
    method: str
    path: str
    mode: str                 # before | after | 503 | reject
    times: int = 1
    code: int = -2010
    msg: str = "rechazo simulado"


def _order_json(o: OrderState) -> dict:
    return {"clientOrderId": o.client_id, "orderId": int(o.exchange_id), "symbol": o.symbol,
            "side": "BUY" if o.side > 0 else "SELL", "type": o.kind, "origType": o.kind,
            "status": o.status, "origQty": str(o.qty), "executedQty": str(o.filled),
            "avgPrice": str(o.avg_price or 0), "reduceOnly": o.reduce_only,
            "closePosition": False, "stopPrice": "0"}


def _algo_json(o: OrderState) -> dict:
    return {"algoId": int(o.exchange_id), "clientAlgoId": o.client_id, "symbol": o.symbol,
            "side": "BUY" if o.side > 0 else "SELL", "algoType": "CONDITIONAL",
            "orderType": "STOP_MARKET" if o.kind == STOP else "TAKE_PROFIT_MARKET",
            "algoStatus": "FINISHED" if o.status == TRIGGERED else o.status,
            "triggerPrice": str(o.trigger), "closePosition": o.close_position,
            "quantity": "0" if o.close_position else str(o.qty), "reduceOnly": o.reduce_only}


def _err(code: int, msg: str, status: int = 400) -> httpx.Response:
    return httpx.Response(status, json={"code": code, "msg": msg})


class FakeBinance:
    def __init__(self, sim: SimBroker | None = None) -> None:
        self.sim = sim or SimBroker()
        self.faults: list[Fault] = []
        self.down = False
        self.log: list[tuple[str, str, dict]] = []        # (método, ruta, params) procesados
        self.raw: list[str] = []                          # todo lo que viajó (URL + cuerpo)
        self._margin_set: set[str] = set()

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=URL, transport=httpx.MockTransport(self.handle))

    def fault(self, method: str, path: str, mode: str, times: int = 1, **kw) -> None:
        self.faults.append(Fault(method, path, mode, times, **kw))

    def posts(self, path: str) -> list[dict]:
        return [p for m, pa, p in self.log if m == "POST" and pa == path]

    # --- transporte --------------------------------------------------------
    def handle(self, req: httpx.Request) -> httpx.Response:
        raw = req.url.query.decode() if req.method == "GET" else req.content.decode()
        self.raw.append(str(req.url) + " " + raw)
        if self.down:
            raise httpx.ConnectError("red cortada", request=req)
        path = req.url.path
        f = next((f for f in self.faults if f.times > 0 and f.method == req.method
                  and f.path == path), None)
        if f is not None:
            f.times -= 1
            if f.mode == "before":
                raise httpx.ConnectError("sin conexión", request=req)
            if f.mode == "503":
                return _err(-1001, "Internal error", 503)
            if f.mode == "reject":
                return _err(f.code, f.msg)
        params = dict(parse_qsl(raw))
        if "signature" in params:
            payload = raw.rsplit("&signature=", 1)[0]
            good = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
            if params.pop("signature") != good or req.headers.get("X-MBX-APIKEY") != KEY:
                return _err(-1022, "Signature for this request is not valid.")
        resp = self._route(req.method, path, params)
        if resp.status_code < 400:
            self.log.append((req.method, path, params))
        if f is not None and f.mode == "after":
            raise httpx.ReadTimeout("respuesta perdida", request=req)
        return resp

    def _route(self, method: str, path: str, p: dict) -> httpx.Response:
        s = self.sim
        try:
            if path == "/fapi/v1/time":
                return httpx.Response(200, json={"serverTime": 1_760_000_000_000})
            if path == "/fapi/v1/exchangeInfo":
                f = [{"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                     {"filterType": "PRICE_FILTER", "tickSize": "0.10"}]
                return httpx.Response(200, json={"symbols": [
                    {"symbol": x, "filters": f} for x in ("BTCUSDT", "ETHUSDT")]})
            if path == "/fapi/v1/positionSide/dual":
                return httpx.Response(200, json={"dualSidePosition": False})
            if path == "/fapi/v1/marginType":
                if p["symbol"] in self._margin_set:
                    return _err(-4046, "No need to change margin type.")
                self._margin_set.add(p["symbol"])
                return httpx.Response(200, json={"code": 200, "msg": "success"})
            if path == "/fapi/v1/leverage":
                s.prepare(p["symbol"], int(p["leverage"]))
                return httpx.Response(200, json={"leverage": int(p["leverage"])})
            if path in ("/fapi/v1/order", "/fapi/v1/algoOrder"):
                return self._order(method, path, p)
            if path == "/fapi/v1/openOrders":
                return httpx.Response(200, json=[_order_json(o) for o in s.open_orders(
                    p["symbol"]) if not o.conditional])
            if path == "/fapi/v1/openAlgoOrders":
                return httpx.Response(200, json=[_algo_json(o) for o in s.open_orders(
                    p["symbol"]) if o.conditional])
            if path == "/fapi/v3/positionRisk":
                pos = s.position(p["symbol"])
                return httpx.Response(200, json=[{"symbol": pos.symbol, "positionSide": "BOTH",
                                                  "positionAmt": str(pos.qty),
                                                  "entryPrice": str(pos.entry_price or 0)}])
            if path == "/fapi/v2/account":
                return httpx.Response(200, json={"totalMarginBalance": str(s.equity())})
        except OrderRejected as e:
            return _err(e.code or -1, str(e))
        return _err(-1, f"ruta no simulada {path}", 404)

    def _order(self, method: str, path: str, p: dict) -> httpx.Response:
        s, algo = self.sim, path.endswith("algoOrder")
        cid = p.get("clientAlgoId") or p.get("newClientOrderId") or p.get("origClientOrderId")
        if method == "POST":
            kind = {"STOP_MARKET": STOP, "TAKE_PROFIT_MARKET": TAKE_PROFIT, "MARKET": MARKET,
                    "LIMIT": LIMIT}[p["type"]]
            close = p.get("closePosition") == "true"
            o = s.post_order(OrderSpec(
                cid, p["symbol"], 1 if p["side"] == "BUY" else -1, kind,
                qty=None if close else float(p["quantity"]),
                price=float(p["price"]) if "price" in p else None,
                trigger=float(p["triggerPrice"]) if "triggerPrice" in p else None,
                reduce_only=p.get("reduceOnly") == "true", close_position=close))
            return httpx.Response(200, json=_algo_json(o) if algo else _order_json(o))
        o = s.order_by_id(cid)
        if o is None or o.conditional != algo:
            return _err(-2013 if method == "GET" else -2011, "Order does not exist.")
        if method == "DELETE":
            if not o.is_open:
                return _err(-2011, "Unknown order sent.")
            s.cancel(o.symbol, cid, algo)
            o = s.order_by_id(cid)
        return httpx.Response(200, json=json.loads(json.dumps(
            _algo_json(o) if algo else _order_json(o))))
