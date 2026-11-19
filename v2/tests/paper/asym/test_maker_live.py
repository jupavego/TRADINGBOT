"""T189: la misma idea viva a mercado y como límite, emparejada por idea y por marco."""

from __future__ import annotations

from eim.core import Candle
from eim.paper.asym import prereg as P
from eim.paper.asym.maker_live import (
    MakerPair,
    halves_same_sign,
    live_market_ideas,
    pair_ideas,
    summary,
)
from eim.paper.engine import Outcome, Path
from eim.paper.ideas import Idea
from eim.paper.maker_ab import Leg
from eim.paper.params import ExecParams

STEP = 15 * 60_000
T0 = P.START_MS


def idea(k: int, **kw) -> Idea:
    base = dict(id=f"BTCUSDT:15m:{T0 + k * STEP}:agente_ema", strategy="agente_ema",
                family="agentes", symbol="BTCUSDT", t=T0 + k * STEP, side=1, kind="market",
                entry=100.0, sl=99.0, tp=102.0, fill_ms=0, hold_ms=4 * STEP, conf=0.5,
                why=("prueba",), origin="vivo", timeframe="15m")
    base.update(kw)
    return Idea(**base)


def test_only_live_market_ideas_since_the_start_without_control():
    ok = idea(1)
    picked = live_market_ideas([Outcome(ok, "CERRADA"),
                                Outcome(idea(2, origin="backtest"), "CERRADA"),
                                Outcome(idea(3, kind="limit"), "CERRADA"),
                                Outcome(idea(4, t=T0 - 1), "CERRADA"),
                                Outcome(idea(5, strategy="control_aleatorio",
                                             family="control"), "CERRADA"),
                                Outcome(idea(6, timeframe="1d"), "CERRADA"),
                                Outcome(idea(7), "CERRADA")], skip={idea(7).id})
    assert [i.id for i in picked] == [ok.id]


def test_pairs_resolve_both_arms_and_measure_on_planned_risk():
    candles = [Candle(t=T0 + k * STEP, o=100.0, h=100.4, l=99.8, c=100.1, v=1.0)
               for k in range(2)]
    candles += [Candle(t=T0 + k * STEP, o=100.5, h=102.5, l=100.4, c=102.2, v=1.0)
                for k in range(2, 12)]
    pairs = pair_ideas([idea(0)], Path(candles), ExecParams())
    assert len(pairs) == 1 and pairs[0].timeframe == "15m"
    p = pairs[0]
    assert p.taker.filled and p.maker.filled
    assert p.maker.cost_p < p.taker.cost_p          # la límite paga comisión de creador
    s = summary(pairs)
    assert s["n"] == 1 and s["costo_baja_r"] > 0


def _mp(k: int, d: float) -> MakerPair:
    return MakerPair(str(k), "15m", k, k, Leg(True, "SL", net_p=0.0),
                     Leg(True, "SL", net_p=d))


def test_sign_must_hold_in_both_halves():
    assert halves_same_sign([_mp(k, 0.1) for k in range(10)])
    assert not halves_same_sign([_mp(k, 0.1 if k < 5 else -0.2) for k in range(10)])
    assert not halves_same_sign([_mp(0, 0.1)])
