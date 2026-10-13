"""Proveedor de liquidaciones: mapeo de símbolo, obsolescencia y agregación (sin red)."""
from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

import httpx
import pytest

from eim.agents.liquidations import LiquidationsAgent
from eim.core import MarketSnapshot
from eim.data.providers.liquidations import (
    BinanceLiquidations,
    LiquidationsUnavailable,
    aggregate,
    resolve_liquidation_symbol,
)

CSV = (
    "time,symbol,side,order_type,time_in_force,original_quantity,price,average_price,"
    "order_status,order_last_filled_quantity,order_filled_accumulated_quantity,order_trade_time\n"
    "1728864000000,ETHUSD_PERP,SELL,LIMIT,IOC,10,2500,2500,FILLED,10,10,1728864000000\n"
    "1728864001000,ETHUSD_PERP,BUY,LIMIT,IOC,4,2600,2600,FILLED,4,4,1728864001000\n"
)
LISTING = (
    '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
    "<Contents><Key>data/futures/cm/daily/liquidationSnapshot/ETHUSD_PERP/"
    "ETHUSD_PERP-liquidationSnapshot-2024-10-14.zip</Key></Contents></ListBucketResult>"
)


def _zip(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("x.csv", text)
    return buf.getvalue()


def _client(listing: str = LISTING) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        if "s3-ap-northeast-1" in str(req.url):
            return httpx.Response(200, content=listing.encode())
        if str(req.url).endswith("2024-10-14.zip"):
            return httpx.Response(200, content=_zip(CSV))
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _clock(date: str):
    ms = int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)
    return lambda: ms


def test_symbol_mapping():
    assert resolve_liquidation_symbol("ethusdt") == "ETHUSD_PERP"
    assert resolve_liquidation_symbol("BTCUSD_PERP") == "BTCUSD_PERP"
    with pytest.raises(ValueError):
        resolve_liquidation_symbol("SOLUSDT")


def test_aggregate_sides_and_levels():
    rows = [{"time": "1728864000000", "side": "SELL", "original_quantity": "10",
             "average_price": "2500"},
            {"time": "1728864001000", "side": "BUY", "original_quantity": "4",
             "average_price": "2600"}]
    daily, levels = aggregate(rows, price_bins=10)
    assert len(daily) == 1 and daily[0].longs_usd == 25_000 and daily[0].shorts_usd == 10_400
    assert sum(lv.longs_usd for lv in levels) == 25_000 and len(levels) == 2


def test_fetch_marks_stale_and_exposes_symbols(tmp_path):
    p = BinanceLiquidations(_client(), cache_dir=tmp_path, clock=_clock("2026-06-27"))
    liq = p.fetch("ETHUSDT")
    assert liq.stale and liq.most_recent_date == "2024-10-14" and liq.stale_age_days > 600
    assert (liq.requested_symbol, liq.liquidation_symbol) == ("ETHUSDT", "ETHUSD_PERP")
    assert liq.days_with_data == 1
    assert list(tmp_path.rglob("*.csv"))  # caché escrita; la segunda lectura no usa red
    offline = BinanceLiquidations(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, content=LISTING.encode() if "s3-" in str(r.url) else b""))),
        cache_dir=tmp_path, clock=_clock("2026-06-27"))
    assert offline.fetch("ETHUSDT").days_with_data == 1


def test_fetch_not_stale_when_recent():
    liq = BinanceLiquidations(_client(), clock=_clock("2024-10-20")).fetch("ETHUSDT")
    assert not liq.stale


def test_unavailable_raises_instead_of_empty():
    empty = '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"/>'
    with pytest.raises(LiquidationsUnavailable):
        BinanceLiquidations(_client(empty)).fetch("ETHUSDT")


def test_provider_output_feeds_agent_and_degrades():
    liq = BinanceLiquidations(_client(), clock=_clock("2026-06-27")).fetch("ETHUSDT")
    asof = int(datetime(2026, 6, 27, tzinfo=UTC).timestamp() * 1000)
    snap = MarketSnapshot(symbol="ETHUSDT", timeframe="1h", candles=[], asof=asof, liquidations=liq)
    rep = LiquidationsAgent().run(snap)
    assert rep.status == "degraded" and rep.bias == 0
