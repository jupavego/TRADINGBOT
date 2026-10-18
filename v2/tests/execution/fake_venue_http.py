"""API REST simulada (spot `/api/v3/*` o futuros `/fapi/*`) sobre un `Venue` (T45): comprueba la
firma y admite fallos como `FakeBinance`: `fault(método, ruta, before|after|503|reject)` y `down`.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl

import httpx

from tests.execution.fake_binance import KEY, SECRET, Fault

if TYPE_CHECKING:
    from tests.execution.fake_venue import Venue

SPOT_URL, FUT_URL = "https://testnet.binance.vision", "https://testnet.binancefuture.com"


def _spot_json(o: dict) -> dict:
    return {"symbol": o["symbol"], "orderId": o["orderId"], "clientOrderId": o["clientOrderId"],
            "price": str(o["price"]), "origQty": str(o["origQty"]),
            "executedQty": str(o["executedQty"]), "cummulativeQuoteQty": str(o["quote"]),
            "status": o["status"], "type": o["type"], "side": o["side"]}


def _fut_json(o: dict) -> dict:
    avg = o["quote"] / o["executedQty"] if o["executedQty"] else 0.0
    return {"clientOrderId": o["clientOrderId"], "orderId": o["orderId"], "symbol": o["symbol"],
            "side": o["side"], "type": o["type"], "origType": o["type"], "status": o["status"],
            "origQty": str(o["origQty"]), "executedQty": str(o["executedQty"]),
            "avgPrice": str(avg), "reduceOnly": o["reduceOnly"], "closePosition": False,
            "stopPrice": "0"}


def _err(code: int, msg: str, status: int = 400) -> httpx.Response:
    return httpx.Response(status, json={"code": code, "msg": msg})


class FakeHTTP:
    def __init__(self, venue: Venue) -> None:
        self.v = venue
        self.url = FUT_URL if venue.futures else SPOT_URL
        self.faults: list[Fault] = []
        self.down = False
        self.log: list[tuple[str, str, dict]] = []

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=self.url, transport=httpx.MockTransport(self.handle))

    def fault(self, method: str, path: str, mode: str, times: int = 1, **kw) -> None:
        self.faults.append(Fault(method, path, mode, times, **kw))

    def posts(self, path: str) -> list[dict]:
        return [p for m, pa, p in self.log if m == "POST" and pa == path]

    def handle(self, req: httpx.Request) -> httpx.Response:
        raw = req.url.query.decode() if req.method == "GET" else req.content.decode()
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
        try:
            resp = (self._fut if self.v.futures else self._spot)(req.method, path, params)
        except Exception as e:  # noqa: BLE001 - VenueError
            if not hasattr(e, 'code'):
                raise
            resp = _err(e.code, e.msg)
        if resp.status_code < 400:
            self.log.append((req.method, path, params))
        if f is not None and f.mode == "after":
            raise httpx.ReadTimeout("respuesta perdida", request=req)
        return resp

    def _book(self, sym: str, depth: bool) -> httpx.Response:
        t = self.v.top(sym)
        if not depth:
            return httpx.Response(200, json={"symbol": sym, "bidPrice": str(t[0] if t else 0),
                                             "askPrice": str(t[1] if t else 0)})
        q = self.v.liquidity.get(sym, 10.0)
        return httpx.Response(200, json={"bids": [[str(t[0]), str(q)]] if t else [],
                                         "asks": [[str(t[1]), str(q)]] if t else []})

    def _spot(self, method: str, path: str, p: dict) -> httpx.Response:
        v = self.v
        if path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_760_000_000_000})
        if path == "/api/v3/exchangeInfo":
            sym = p["symbol"]
            if sym not in v.mids:
                return _err(-1121, "Invalid symbol.")
            return httpx.Response(200, json={"symbols": [{
                "symbol": sym, "baseAsset": v.base_of(sym), "quoteAsset": "USDT", "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": str(v.step), "minQty": str(v.step)},
                    {"filterType": "PRICE_FILTER", "tickSize": str(v.tick)},
                    {"filterType": "NOTIONAL", "minNotional": str(v.min_notional)}]}]})
        if path in ("/api/v3/ticker/bookTicker", "/api/v3/depth"):
            return self._book(p["symbol"], path.endswith("depth"))
        if path == "/api/v3/account":
            return httpx.Response(200, json={"balances": [
                {"asset": a, "free": str(b), "locked": "0"} for a, b in v.balances.items()]})
        if path == "/api/v3/openOrders":
            return httpx.Response(200, json=[_spot_json(o) for o in v.orders.values()
                                             if o["symbol"] == p["symbol"]
                                             and o["status"] in ("NEW", "PARTIALLY_FILLED")])
        if path == "/api/v3/myTrades":
            o = next((o for o in v.orders.values() if str(o["orderId"]) == p["orderId"]), None)
            return httpx.Response(200, json=o["fills"] if o else [])
        if path == "/api/v3/order":
            return self._order(method, p, _spot_json, full=True)
        return _err(-1, f"ruta no simulada {path}", 404)

    def _fut(self, method: str, path: str, p: dict) -> httpx.Response:
        v = self.v
        if path == "/fapi/v1/time":
            return httpx.Response(200, json={"serverTime": 1_760_000_000_000})
        if path == "/fapi/v1/exchangeInfo":
            f = [{"filterType": "LOT_SIZE", "stepSize": str(v.step), "minQty": str(v.step)},
                 {"filterType": "PRICE_FILTER", "tickSize": str(v.tick)}]
            return httpx.Response(200, json={"symbols": [{"symbol": s, "filters": f}
                                                         for s in v.mids]})
        if path == "/fapi/v1/positionSide/dual":
            return httpx.Response(200, json={"dualSidePosition": False})
        if path == "/fapi/v1/marginType":
            return httpx.Response(200, json={"code": 200, "msg": "success"})
        if path == "/fapi/v1/leverage":
            v.leverage[p["symbol"]] = int(p["leverage"])
            return httpx.Response(200, json={"leverage": int(p["leverage"])})
        if path in ("/fapi/v1/ticker/bookTicker", "/fapi/v1/depth"):
            return self._book(p["symbol"], path.endswith("depth"))
        if path == "/fapi/v3/positionRisk":
            return httpx.Response(200, json=[v.risk_row(p["symbol"])])
        if path == "/fapi/v2/account":
            return httpx.Response(200, json=v.account())
        if path == "/fapi/v1/positionMargin":
            row = v.pos.get(p["symbol"])
            amount = float(p["amount"])
            if row is None or float(v.account()["availableBalance"]) < amount:
                return _err(-2019, "Margin is insufficient.")
            row[2] += amount
            return httpx.Response(200, json={"code": 200, "amount": amount, "type": 1})
        if path == "/fapi/v1/income":
            return httpx.Response(200, json=[r for r in v.income if r["symbol"] == p["symbol"]
                                             and r["time"] >= int(p["startTime"])])
        if path == "/fapi/v1/openOrders":
            return httpx.Response(200, json=[_fut_json(o) for o in v.orders.values()
                                             if o["symbol"] == p["symbol"]
                                             and o["status"] in ("NEW", "PARTIALLY_FILLED")])
        if path == "/fapi/v1/openAlgoOrders":
            return httpx.Response(200, json=[])
        if path == "/fapi/v1/order":
            return self._order(method, p, _fut_json, full=False)
        return _err(-1, f"ruta no simulada {path}", 404)

    def _order(self, method: str, p: dict, fmt: Callable[[dict], dict],
               full: bool) -> httpx.Response:
        v = self.v
        if method == "POST":
            o = v.place(p)
            body = fmt(o)
            if full:
                body["fills"] = list(o["fills"])
            return httpx.Response(200, json=body)
        cid = p.get("origClientOrderId", "")
        o = v.orders.get(cid)
        if o is None:
            return _err(-2013 if method == "GET" else -2011, "Order does not exist.")
        if method == "DELETE":
            if o["status"] not in ("NEW", "PARTIALLY_FILLED"):
                return _err(-2011, "Unknown order sent.")
            v.cancel(cid)
        return httpx.Response(200, json=fmt(o))
