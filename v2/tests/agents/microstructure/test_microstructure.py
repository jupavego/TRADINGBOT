"""Agente microstructure: flujo sintético comprador/vendedor, sin datos y con huecos."""
from __future__ import annotations

import math

from eim.agents.microstructure import MicrostructureAgent
from eim.agents.microstructure.agent import garman_klass, parkinson
from eim.core import Book, Candle, MarketSnapshot, MicroBar

H = 3_600_000
T0 = 1_700_000_000_000
N = 60


def _snap(flow: float, *, price_dir: float = 0.0, complete=True, micro=True, depth=0.0):
    """Ruido sinusoidal en las velas antiguas; en las últimas 6 el flujo vale `flow`."""
    candles, bars = [], []
    for i in range(N):
        c = 100.0 + 0.05 * math.sin(i) + price_dir * max(0, i - (N - 7)) * 0.2
        candles.append(Candle(t=T0 + i * H, o=c, h=c + 0.1, l=c - 0.1, c=c, v=1))
        noise = math.sin(i * 1.7)
        f = flow if i >= N - 6 else noise
        bars.append(MicroBar(t=T0 + i * H, ofi=10 * f, delta=5 * f, buy_v=10, sell_v=5, trades=50,
                             depth_imb=depth, complete=complete or i != 10))
    return MarketSnapshot(
        symbol="ETHUSDT", timeframe="1h", candles=candles, asof=T0 + N * H,
        micro=bars if micro else None, sources={"micro": "fixture"},
        orderbook=Book(bids=[(99.0, 5.0)], asks=[(101.0, 5.0)], source="fixture"),
    )


def test_sin_recoleccion_devuelve_no_data():
    r = MicrostructureAgent().run(_snap(1.0, micro=False))
    assert r.status == "no_data" and r.bias == 0 and r.confidence == 0


def test_poca_recoleccion_devuelve_no_data():
    s = _snap(1.0)
    s = s.model_copy(update={"micro": s.micro[-10:]})
    assert MicrostructureAgent().run(s).status == "no_data"


def test_flujo_comprador_da_sesgo_alcista_y_vendedor_bajista():
    up = MicrostructureAgent().run(_snap(+3.0, depth=0.3))
    dn = MicrostructureAgent().run(_snap(-3.0, depth=-0.3))
    assert up.status == "ok" and up.bias > 0.3 and up.confidence > 0
    assert dn.bias < -0.3
    assert up.metrics["ofi_z"] > 0 > dn.metrics["ofi_z"]
    assert up.metrics["parkinson"] > 0 and up.metrics["garman_klass"] > 0


def test_divergencia_precio_sube_con_cvd_vendedor():
    r = MicrostructureAgent().run(_snap(-3.0, price_dir=1.0))
    assert any("Divergencia bajista" in e for e in r.evidence)


def test_huecos_degradan_y_avisan():
    s = _snap(2.0)
    bars = [b.model_copy(update={"complete": i % 2 == 0}) for i, b in enumerate(s.micro)]
    r = MicrostructureAgent().run(s.model_copy(update={"micro": bars}))
    assert r.status == "degraded"
    assert any("huecos" in w for w in r.warnings)


def test_volatilidad_realizada_en_vela_plana_es_cero():
    c = [Candle(t=i, o=10, h=10, l=10, c=10, v=1) for i in range(5)]
    assert parkinson(c) == 0 and garman_klass(c) == 0
