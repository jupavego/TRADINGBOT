"""Adaptador modo A (`jesse-example-strategies`): paridad con las reglas calculadas con TA-Lib,
no anticipación y marco permitido."""

import json
from pathlib import Path

import numpy as np
import pytest

from eim.bots.jesse_examples import (
    PARAMS,
    STRATEGIES,
    WINDOW,
    JesseExamplesAdapter,
    arrays_of,
    crossed,
    jesse_positions,
    stance_series,
)
from eim.bots.service import BotService
from eim.core import Candle, MarketSnapshot

FX = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "bots" / "jesse_parity.json")
                .read_text(encoding="utf-8"))
CS = [Candle(t=r[0], o=r[1], h=r[2], l=r[3], c=r[4], v=r[5]) for r in FX["candles"]]
STEP = 3_600_000


def _snap(n: int) -> MarketSnapshot:
    cs = CS[:n]
    return MarketSnapshot(symbol="BTCUSDT", timeframe="1h", candles=cs, asof=cs[-1].t + STEP,
                          sources={"candles": "fixture"})


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_parity_with_reference_rules(name):
    """Posturas idénticas a las de las reglas de Jesse calculadas vela a vela con TA-Lib."""
    native = FX["native"][name]
    by_t = {c.t: i for i, c in enumerate(CS)}
    checked = 0
    for key, want in native.items():
        i = by_t[int(key)]
        win = CS[i + 1 - WINDOW:i + 1]
        got = jesse_positions(STRATEGIES[name](arrays_of(win), PARAMS[name]))[-1]
        assert int(got) == want, (name, key)
        checked += 1
    assert checked >= 90
    assert len(set(native.values())) > 1 or name == "Donchian"   # no es una postura constante


def test_adapter_matches_reference_on_last_candle():
    got = {s.strategy: s for s in JesseExamplesAdapter().signals(_snap(len(CS)))}
    for name, native in FX["native"].items():
        assert got[name].stance == native[str(CS[-1].t)] or str(CS[-1].t) not in native
        assert got[name].status == "ok" and got[name].confidence is None


def test_no_lookahead_truncating_future_candles_keeps_the_stance():
    full = {k: stance_series(CS, k) for k in STRATEGIES}
    for cut in (1100, 1350, 1600):
        part = {k: stance_series(CS[:cut], k) for k in STRATEGIES}
        for k in STRATEGIES:
            assert np.array_equal(part[k], full[k][:cut], equal_nan=True), (k, cut)


def test_insufficient_candles_is_no_data():
    sigs = JesseExamplesAdapter().signals(_snap(WINDOW - 1))
    assert {s.status for s in sigs} == {"no_data"}


def test_crossed_follows_jesse_definition():
    s = np.array([np.nan, 30.0, 35.0, 36.0, 35.0, 34.0])
    assert list(crossed(s, 35, True)) == [False, False, False, True, False, False]
    assert list(crossed(s, 35, False)) == [False, False, False, False, False, True]


def test_service_skips_adapter_outside_its_timeframe():
    ad = JesseExamplesAdapter()
    snap = _snap(len(CS)).model_copy(update={"timeframe": "4h"})
    assert BotService([ad]).produce(snap) == []
