"""Agente `liquidations` v2: flujo en vivo (parsers, lectura por vela, cascadas), sin red."""

from eim.agents.liquidations import LiquidationsAgent
from eim.core import Candle, LiqBar, MarketSnapshot
from eim.data.collectors.liq_ws import LiqCollector, parse_binance, parse_bybit, parse_okx
from eim.data.liq_flow import read_liq_flow

H = 3_600_000
T0 = 1_700_000_000_000 // H * H


def test_parsers_lado_de_la_posicion():
    b = {"data": {"e": "forceOrder", "E": 5, "o": {"s": "BTCUSDT", "S": "SELL", "p": "100",
                                                  "ap": "99", "q": "2", "z": "2", "T": 7}}}
    assert parse_binance(b, "BTCUSDT") == [(7, "binance", True, 99.0, 2.0, 198.0)]  # SELL ⇒ larga
    assert parse_binance(b, "ETHUSDT") == []
    y = {"topic": "allLiquidation.BTCUSDT", "data": [
        {"T": 9, "s": "BTCUSDT", "S": "Buy", "v": "3", "p": "10"}]}
    assert parse_bybit(y, "BTCUSDT") == [(9, "bybit", True, 10.0, 3.0, 30.0)]  # Buy ⇒ larga
    o = {"arg": {"channel": "liquidation-orders"}, "data": [{"instId": "BTC-USDT-SWAP", "details": [
        {"side": "buy", "posSide": "short", "bkPx": "100", "sz": "50", "ts": "11"}]}]}
    assert parse_okx(o, "BTCUSDT") == [(11, "okx", False, 100.0, 0.5, 50.0)]  # sz × 0,01 BTC


def _flow(n=40, spike=None, gaps=()):
    out = []
    for i in range(n):
        lg = sh = 100_000.0
        if spike and i in spike:
            lg, sh = spike[i]
        out.append(LiqBar(t=T0 + i * H, long_usd=lg, short_usd=sh, count=5,
                          by_venue={"binance": (lg + sh) / 2, "bybit": (lg + sh) / 2},
                          complete=i not in gaps))
    return out


def _snap(flow):
    cs = [Candle(t=T0 + i * H, o=1, h=1, l=1, c=1, v=1) for i in range(len(flow))]
    return MarketSnapshot(symbol="BTCUSDT", timeframe="1h", candles=cs, liq_flow=flow,
                          asof=cs[-1].t + H, sources={"liq_flow": "test"})


def test_sin_recoleccion_es_no_data():
    r = LiquidationsAgent().run(_snap(_flow(5)))
    assert r.status == "no_data" and r.bias == 0


def test_cascada_activa_de_largos_es_bajista():
    flow = _flow(spike={i: (5_000_000.0, 100_000.0) for i in (37, 38, 39)})
    r = LiquidationsAgent().run(_snap(flow))
    assert r.metrics["state"] == "active" and r.bias < -0.1 and 0 < r.confidence <= 0.5
    assert LiquidationsAgent().run(_snap(flow)) == r  # determinista


def test_cascada_agotada_da_sesgo_contrario():
    flow = _flow(spike={i: (5_000_000.0, 100_000.0) for i in (35, 36)})
    r = LiquidationsAgent().run(_snap(flow))
    assert r.metrics["state"] == "exhausted" and r.bias > 0


def test_huecos_de_captura_degradan_sin_sesgo():
    flow = _flow(spike={39: (9e6, 1e5)}, gaps=set(range(20, 40)))
    r = LiquidationsAgent().run(_snap(flow))
    assert r.status == "degraded" and r.bias == 0


def test_mercado_normal_sin_sesgo():
    r = LiquidationsAgent().run(_snap(_flow()))
    assert r.metrics["state"] == "quiet" and r.bias == 0 and r.confidence == 0


def test_recolector_a_parquet_y_lectura_con_marca_de_vida(tmp_path):
    col = LiqCollector(tmp_path, "BTCUSDT")
    col.connected.add("bybit")
    col.alive(T0 + 1000)
    col.on_message("bybit", {"topic": "allLiquidation.BTCUSDT", "data": [
        {"T": T0 + H + 5, "s": "BTCUSDT", "S": "Sell", "v": "1", "p": "100"}]})
    col.alive(T0 + 2 * H + 1)
    col.gap("bybit", "corte")
    col.flush()
    bars = read_liq_flow(tmp_path, "BTCUSDT", T0, H, 4)
    assert [b.t for b in bars] == [T0, T0 + H, T0 + 2 * H]  # la vela 3 no existe: sin datos
    assert bars[0].count == 0 and bars[1].short_usd == 100.0 and bars[1].long_usd == 0.0
