"""Adaptador modo B de NFI (5 min): informativos sin futuro, tramos == una corrida, postura."""

import json
from pathlib import Path

from eim.bots.card import card_of
from eim.bots.nfi_adapter import WARM, NfiAdapter, informatives
from eim.core import Candle, MarketSnapshot
from eim.data.bots.runner import RunResult, RunSpec

S5 = 300_000
T0 = 1_760_000_000_000 // 86_400_000 * 86_400_000          # medianoche UTC


def _c5(n: int, t0: int = T0) -> list[Candle]:
    return [Candle(t=t0 + i * S5, o=100.0 + i, h=101.0 + i, l=99.0 + i, c=100.5 + i, v=1.0)
            for i in range(n)]


def _fake_runner(spec: RunSpec) -> RunResult:
    """Banderas causales: dependen solo del instante de cada vela (como un bot sin futuro)."""
    rows = json.loads(spec.files["candles.json"])
    info = json.loads(spec.files["info.json"])
    assert set(info) == {"15m", "1h", "4h", "1d"}
    ts = [r[0] for r in rows]
    el = [1 if (t // S5) % 90 == 0 else 0 for t in ts]
    xl = [1 if (t // S5) % 90 == 40 else 0 for t in ts]
    out = {"engine": "2026.9", "can_short": True, "startup_candle_count": WARM, "times": ts,
           "flags": {"enter_long": el, "exit_long": xl, "enter_short": [0] * len(ts),
                     "exit_short": [0] * len(ts)}}
    return RunResult("ok", out)


def _adapter(**kw) -> NfiAdapter:
    return NfiAdapter(Path("py"), Path("."), "2026.9", runner=_fake_runner,
                      card=card_of("nostalgia-for-infinity"), **kw)


def _snap(cs: list[Candle]) -> MarketSnapshot:
    return MarketSnapshot(symbol="BTCUSDT", timeframe="5m", candles=cs, asof=cs[-1].t + S5,
                          sources={"candles": "fixture"})


def test_informatives_have_only_closed_bars_and_enough_history():
    cs = _c5(300)                                  # 25 h de 5 min desde la medianoche
    info = informatives(cs, None)
    end = cs[-1].t + S5
    for tf, step in (("15m", 900_000), ("1h", 3_600_000), ("4h", 14_400_000), ("1d", 86_400_000)):
        assert all(r[0] + step <= end for r in info[tf]), tf     # ninguna barra abierta
    assert [r[0] for r in info["1d"]] == [T0] and len(info["4h"]) == 6


def test_chunked_history_equals_single_run():
    cs = _c5(WARM + 2500)
    one = _adapter()
    one.chunk = 10**9
    many = _adapter()
    many.chunk = 700
    snap = _snap(cs)
    a, b = one._run_all(snap, "X"), many._run_all(snap, "X")
    assert a["flags"] == b["flags"] and a["times"] == b["times"]


def test_history_emits_stance_from_flags_after_startup():
    cs = _c5(WARM + 400)
    sigs = _adapter().history(_snap(cs), "X", cs[WARM].t + S5)
    assert sigs and all(s.timeframe == "5m" and s.status == "ok" for s in sigs)
    assert {s.stance for s in sigs} <= {-1.0, 0.0, 1.0} and {1.0} <= {s.stance for s in sigs}
    assert min(s.asof for s in sigs) >= cs[WARM].t + S5
    assert "rebuy" in sigs[0].data_quality.notes[0]       # lo que no cabe en una postura, dicho


def test_failing_chunk_gives_no_history():
    def boom(spec):
        return RunResult("degraded", None, ("boom",))
    ad = NfiAdapter(Path("py"), Path("."), "2026.9", runner=boom,
                    card=card_of("nostalgia-for-infinity"))
    cs = _c5(WARM + 100)
    assert ad.history(_snap(cs), "X", 0) == []
