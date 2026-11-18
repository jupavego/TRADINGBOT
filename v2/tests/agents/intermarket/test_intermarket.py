"""T183: agente intermercado — informante puro, nunca `degraded`, peso 0 en la síntesis."""
from __future__ import annotations

import math

import pytest

from eim.agents.intermarket import IntermarketAgent, IntermarketParams
from eim.agents.intermarket.compute import aligned_returns, closes_by_day, pearson, regime
from eim.core import AgentReport, Candle, MarketSnapshot
from eim.synthesis import SynthesisParams, synthesize
from eim.synthesis.params import role_of

DAY = 86_400_000
T0 = 1_700_000_000_000 // DAY * DAY        # medianoche UTC


def daily(closes: list[float], start: int = T0, step_days: int = 1, offset: int = 0
          ) -> list[Candle]:
    return [Candle(t=start + i * step_days * DAY + offset, o=c, h=c * 1.01, l=c * 0.99, c=c, v=1)
            for i, c in enumerate(closes)]


def walk(n: int, drift: float, seed: int, amp: float = 0.01) -> list[float]:
    """Serie determinista con ruido seudoaleatorio (sin random: reproducible bit a bit)."""
    x, out = 100.0, []
    for i in range(n):
        x *= math.exp(drift + amp * math.sin(i * 1.7 + seed) * math.cos(i * 0.37 + 2 * seed))
        out.append(x)
    return out


def snap(im: dict[str, list[Candle]] | None, symbol: str = "BTCUSDT", days: int = 200
         ) -> MarketSnapshot:
    hourly = [Candle(t=T0 + days * DAY - (3 - i) * 3_600_000, o=1, h=1, l=1, c=1, v=1)
              for i in range(3)]
    return MarketSnapshot(symbol=symbol, timeframe="1h", candles=hourly, intermarket=im,
                          asof=T0 + days * DAY, sources={"intermarket:NASDAQ": "prueba"})


def world(eq_drift: float, n: int = 200, follow: float = 1.0) -> dict[str, list[Candle]]:
    nas = walk(n, eq_drift, 1)
    btc = [100 * (v / 100) ** follow for v in nas]       # la cripto sigue al índice
    return {"NASDAQ": daily(nas, offset=5 * 3_600_000), "BTCUSDT": daily(btc),
            "XAUUSDT": daily(walk(n, 0.0, 3))}


def test_sin_intermercado_es_sin_datos_nunca_degradado():
    r = IntermarketAgent().run(snap(None))
    assert r.status == "no_data" and r.bias == 0 and "sincroniz" in r.warnings[0]


def test_sin_la_propia_cripto_no_correlaciona():
    im = world(0.002)
    del im["BTCUSDT"]
    r = IntermarketAgent().run(snap(im))
    assert r.status == "no_data" and "BTCUSDT" in r.warnings[0]


def test_indices_viejos_son_sin_datos_no_degradado():
    im = world(0.002)
    r = IntermarketAgent().run(snap(im, days=230))     # 30 días sin velas nuevas
    assert r.status == "no_data" and "Nasdaq" in r.warnings[0]


@pytest.mark.parametrize("drift,sign", [(0.004, 1), (-0.004, -1)])
def test_indices_con_impulso_y_cripto_correlada_dan_sesgo_del_mismo_lado(drift, sign):
    r = IntermarketAgent().run(snap(world(drift)))
    assert r.status == "ok" and math.copysign(1, r.bias) == sign and abs(r.bias) > 0.1
    assert r.metrics["corr"]["NASDAQ"] > 0.9 and r.metrics["corr_ref"] == "NASDAQ"
    assert 0 < r.confidence <= IntermarketParams().max_confidence
    assert r.metrics["regime"] == ("apetito por riesgo" if sign > 0 else "aversión al riesgo")
    assert r.metrics["role"] == "informante" and "Informante" in r.warnings[0]
    assert r.metrics["sources"] == {"intermarket:NASDAQ": "prueba"}


def test_sin_correlacion_positiva_no_traslada_sesgo():
    im = world(0.004, follow=-1.0)                   # la cripto se mueve al revés
    r = IntermarketAgent().run(snap(im))
    assert r.status == "ok" and r.bias == 0 and r.metrics["corr"]["NASDAQ"] < 0


def test_correlacion_alinea_fechas_y_mide_el_fin_de_semana_en_la_cripto():
    idx = daily([100, 101, 102], step_days=3, offset=5 * 3_600_000)   # cada 3 días, a las 05 UTC
    crypto = closes_by_day(daily([100 + i for i in range(9)]))
    xs, ys = aligned_returns(idx, crypto)
    assert len(xs) == 2
    assert ys[0] == pytest.approx(math.log(103 / 100))   # tres días de cripto, no uno


def test_pearson_y_regimen():
    assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert pearson([1, 2], [1, 2]) is None and pearson([1, 1, 1], [1, 2, 3]) is None
    assert regime(-0.5, 0.5, 0.25) == "huida a refugio"
    assert regime(0.1, None, 0.25) == "mixto"


def test_es_puro_y_determinista():
    s = snap(world(0.003))
    assert IntermarketAgent().run(s) == IntermarketAgent().run(s)


def test_pesa_cero_y_no_cambia_la_sintesis_v1():
    """Regla de T44 y T31 intacta: el sesgo, la confianza y la tesis son los de antes."""
    base = [AgentReport(agent_id=a, version="1", asof=0, bias=b, confidence=0.8, horizon_bars=10)
            for a, b in (("ema", 0.5), ("structure", 0.4))]
    im = AgentReport(agent_id="intermarket", version="0.1.0", asof=0, bias=-0.9, confidence=0.5,
                     horizon_bars=10)
    p = SynthesisParams()
    s, ref = synthesize([*base, im], p), synthesize(base, p)
    assert s.model_dump(exclude={"weights"}) == ref.model_dump(exclude={"weights"})
    assert s.weights["intermarket"] == 0.0 and role_of("intermarket") == "contexto"
