"""Proveedor y cargador de arbitraje con HTTP simulado (sin red)."""

from __future__ import annotations

import httpx

from eim.arbitrage import ArbParams, scan_all
from eim.data.arb_market import load_arb_market
from eim.data.providers import BinanceFutures
from eim.data.providers.binance_arb import BinanceArbData

NOW = 1_760_000_000_000
H = 3_600_000
DELIVERY = NOW + 60 * 24 * H


def _depth(mid: float, n: int = 5) -> dict:
    return {"lastUpdateId": 1, "T": NOW - 5,
            "bids": [[str(mid - 1 - i), "2.0"] for i in range(n)],
            "asks": [[str(mid + 1 + i), "2.0"] for i in range(n)]}


SPOT = {
    "/api/v3/exchangeInfo": {"symbols": [
        {"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT"},
        {"symbol": "ETHUSDT", "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "USDT"},
        {"symbol": "ETHBTC", "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "BTC"},
        {"symbol": "USDCUSDT", "status": "TRADING", "baseAsset": "USDC", "quoteAsset": "USDT"},
        {"symbol": "OLDBTC", "status": "BREAK", "baseAsset": "OLD", "quoteAsset": "BTC"},
        {"symbol": "DOGEUSDT", "status": "TRADING", "baseAsset": "DOGE", "quoteAsset": "USDT"},
    ]},
}
FUT = {
    "/fapi/v1/exchangeInfo": {"symbols": [
        {"symbol": "BTCUSDT", "status": "TRADING", "contractType": "PERPETUAL",
         "baseAsset": "BTC", "marginAsset": "USDT", "deliveryDate": 4133404800000},
        {"symbol": "BTCUSDC", "status": "TRADING", "contractType": "PERPETUAL",
         "baseAsset": "BTC", "marginAsset": "USDC", "deliveryDate": 4133404800000},
        {"symbol": "BTCUSDT_261225", "status": "TRADING", "contractType": "CURRENT_QUARTER",
         "baseAsset": "BTC", "marginAsset": "USDT", "deliveryDate": DELIVERY},
        {"symbol": "BTCUSD_PERP", "status": "TRADING", "contractType": "PERPETUAL",
         "baseAsset": "BTC", "marginAsset": "BTC", "deliveryDate": 0},
    ]},
    "/fapi/v1/premiumIndex": [
        {"symbol": "BTCUSDT", "markPrice": "60010", "indexPrice": "60000",
         "lastFundingRate": "0.00010000", "nextFundingTime": NOW + H, "time": NOW},
        {"symbol": "BTCUSDC", "markPrice": "60020", "indexPrice": "60000",
         "lastFundingRate": "0.00005000", "nextFundingTime": NOW + H, "time": NOW},
        {"symbol": "BTCUSDT_261225", "markPrice": "61000", "indexPrice": "60000",
         "lastFundingRate": "", "nextFundingTime": 0, "time": NOW},
    ],
    "/fapi/v1/fundingInfo": [{"symbol": "BTCUSDC", "fundingIntervalHours": 4,
                              "adjustedFundingRateCap": "0.02",
                              "adjustedFundingRateFloor": "-0.02", "disclaimer": False}],
}
MIDS = {"BTCUSDT": 60_000, "ETHUSDT": 3_000, "ETHBTC": 0.05, "USDCUSDT": 1.0,
        "BTCUSDC": 60_020, "BTCUSDT_261225": 61_000}


def _handler(table: dict, fail: set[str]):
    def handler(req: httpx.Request) -> httpx.Response:
        path, sym = req.url.path, req.url.params.get("symbol")
        if path.endswith("/depth"):
            if sym in fail:
                return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
            return httpx.Response(200, json=_depth(MIDS[sym]))
        if path == "/fapi/v1/fundingRate":  # rejilla fija de liquidaciones cada 8 h
            lo, hi = int(req.url.params["startTime"]), int(req.url.params["endTime"])
            grid = [NOW - k * 8 * H for k in range(30, 0, -1)]
            return httpx.Response(200, json=[
                {"symbol": sym, "fundingTime": t, "fundingRate": "0.0001"}
                for t in grid if lo <= t <= hi])
        return httpx.Response(200, json=table[path])
    return handler


def _prov(fail: set[str] | None = None) -> BinanceArbData:
    def make(base: str, table: dict) -> BinanceFutures:
        client = httpx.Client(base_url=base,
                              transport=httpx.MockTransport(_handler(table, fail or set())))
        return BinanceFutures(client, sleep=lambda s: None, clock=lambda: NOW,
                              min_interval=0.0)
    return BinanceArbData(make("https://api.binance.com", SPOT),
                          make("https://fapi.binance.com", FUT), clock=lambda: NOW)


def test_provider_parses_contracts_premium_and_books():
    prov = _prov()
    assert {p.symbol for p in prov.spot_pairs()} == {"BTCUSDT", "ETHUSDT", "ETHBTC",
                                                     "USDCUSDT", "DOGEUSDT"}
    cs = {c.symbol: c for c in prov.futures_contracts()}
    assert set(cs) == {"BTCUSDT", "BTCUSDC", "BTCUSDT_261225"}  # sin coin-margined
    assert cs["BTCUSDT_261225"].kind == "quarterly" and cs["BTCUSDT_261225"].delivery_t == DELIVERY
    assert cs["BTCUSDC"].market == "usdcm"
    prem = prov.premium_index()
    assert set(prem) == {"BTCUSDT", "BTCUSDC"}  # el trimestral no tiene funding
    assert prem["BTCUSDC"].interval_h == 4.0 and prem["BTCUSDT"].interval_h == 8.0
    assert prem["BTCUSDT"].funding_rate == 0.0001
    book, t = prov.futures_book("BTCUSDT")
    assert t == NOW - 5 and book.bids[0] == (59_999.0, 2.0) and book.source == "binance-futures"


def test_loader_builds_market_with_sources_and_coverage():
    mkt = load_arb_market(_prov(), assets=("BTC",))
    assert set(mkt.spot_books) == {"BTCUSDT", "ETHUSDT", "ETHBTC", "USDCUSDT"}  # sin DOGE
    assert set(mkt.futures_books) == {"BTCUSDT", "BTCUSDC", "BTCUSDT_261225"}
    assert mkt.sources["book:usdcm:BTCUSDC"] == "binance-futures"
    assert mkt.coverage["funding:BTCUSDT"][1] < NOW and not mkt.errors
    assert mkt.quarterlies("BTC")[0].symbol == "BTCUSDT_261225"
    res = scan_all(mkt, p=ArbParams(assets=("BTC",)))
    assert {s.strategy: s.status for s in res.scans} == {
        "funding_carry": "ok", "basis": "ok", "triangular": "ok", "related_perps": "ok"}


def test_loader_records_failures_and_scan_reports_no_data():
    mkt = load_arb_market(_prov(fail={"BTCUSDT_261225", "USDCUSDT"}), assets=("BTC",))
    assert "book:usdm:BTCUSDT_261225" in mkt.errors and "book:spot:USDCUSDT" in mkt.errors
    assert "400" in mkt.errors["book:spot:USDCUSDT"]
    res = scan_all(mkt, p=ArbParams(assets=("BTC",)))
    status = {s.strategy: s for s in res.scans}
    assert status["basis"].status == "no_data"
    assert status["related_perps"].status == "no_data"
    assert "400" in status["related_perps"].missing[0]
    assert status["funding_carry"].status == "ok"
