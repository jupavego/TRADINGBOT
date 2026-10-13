"""Agente levels: series sintéticas conocidas (canal, rango, ruptura) y fixture real."""
from __future__ import annotations

import math

from eim.agents.levels import LevelsAgent
from eim.core import Candle, MarketSnapshot
from tests.agents.conftest import make_snapshot

H = 3_600_000


def _snap(closes: list[float], spread: float = 1.0) -> MarketSnapshot:
    cs = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        cs.append(Candle(t=i * H, o=o, h=max(o, c) + spread, l=min(o, c) - spread,
                         c=c, v=100.0))
    return MarketSnapshot(
        symbol="X", timeframe="1h", candles=cs, asof=cs[-1].t + H,
        sources={"candles": "sintético"}, coverage={"candles": (cs[0].t, cs[-1].t)})


def _wave(n: int, mid: float, amp: float, period: int = 30, slope: float = 0.0) -> list[float]:
    return [mid + slope * i + amp * math.sin(2 * math.pi * i / period) for i in range(n)]


def test_range_detected_with_zones():
    rep = LevelsAgent().run(_snap(_wave(300, 100, 10)))
    ch = rep.metrics["channel"]
    assert ch and ch["kind"] == "range" and ch["state"] == "INSIDE"
    assert any(o.kind == "range" for o in rep.overlays)
    tops = [z for z in rep.metrics["zones"] if z["p_low"] > 105]
    assert tops and all(z["touches"] >= 2 for z in rep.metrics["zones"])
    assert any(109 <= z["p_high"] <= 113 for z in tops)


def test_perfect_channel_slope():
    rep = LevelsAgent().run(_snap(_wave(300, 100, 10, slope=0.2)))
    ch = rep.metrics["channel"]
    assert ch["kind"] == "channel" and abs(ch["slope_per_bar"] - 0.2) < 0.03
    assert ch["r2"] > 0.8
    o = next(o for o in rep.overlays if o.kind == "channel")
    assert o.t_to is None and o.geometry["upper"][1][0] > rep.asof - H  # extendido adelante
    assert o.geometry["upper"][1][1] > o.geometry["lower"][1][1]


def test_channel_broken_down():
    closes = _wave(300, 100, 10, slope=0.0)
    closes += [closes[-1] - 8 * k for k in range(1, 8)]
    rep = LevelsAgent().run(_snap(closes))
    assert rep.metrics["channel"]["state"] == "BROKEN_DOWN"
    assert rep.bias < 0
    assert any("roto" in o.label for o in rep.overlays if o.kind in {"range", "channel"})


def test_no_zone_with_single_touch_and_flat_no_data():
    # Tendencia limpia sin retrocesos: sin pivotes → sin zonas ni canal.
    rep = LevelsAgent().run(_snap([100 + i for i in range(120)]))
    assert rep.metrics["zones"] == [] and rep.metrics["channel"] is None
    assert rep.status == "degraded" and rep.confidence == 0
    assert LevelsAgent().run(make_snapshot(10)).status == "no_data"


def test_max_zones_per_side_and_contract(snapshot):
    rep = LevelsAgent().run(snapshot)
    assert rep.status in {"ok", "degraded"} and -1 <= rep.bias <= 1
    assert rep.metrics["source"] and rep.metrics["coverage"]
    up = [o for o in rep.overlays if o.kind == "zone" and o.geometry["role"] == "resistencia"]
    dn = [o for o in rep.overlays if o.kind == "zone" and o.geometry["role"] == "soporte"]
    assert len(up) <= 2 and len(dn) <= 2 and (up or dn)
    for o in up + dn:
        assert o.geometry["p_low"] < o.geometry["p_high"] and o.geometry["touches"] >= 2
    assert rep == LevelsAgent().run(snapshot)  # determinista


def test_stable_when_adding_one_candle():
    """Al añadir una vela, a lo sumo una zona cambia (centro a >0.5 ATR de las previas)."""
    changed = 0
    prev = None
    for n in range(600, 700):
        r = LevelsAgent().run(make_snapshot(n))
        a = r.metrics["atr"]
        mids = [(z["p_low"] + z["p_high"]) / 2 for z in r.metrics["zones"]]
        if prev is not None:
            kept = sum(any(abs(m - q) < 0.5 * a for q in prev) for m in mids)
            changed += kept < len(mids) - 1
        prev = mids
    assert changed <= 5
