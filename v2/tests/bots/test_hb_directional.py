"""Adaptador modo A (`hummingbot-directional`): paridad con el bot nativo y no anticipación."""

import numpy as np
import pytest

from eim.bots.adapter import version_of
from eim.bots.card import card_of
from eim.bots.hb_directional import (
    STRATEGIES,
    BollingerV1,
    HummingbotDirectionalAdapter,
    stance_series,
)
from tests.bots.helpers import candles, load_fixture, snapshot

FX = load_fixture()


def _window_features(name: str, cs, i: int):
    params, fn = STRATEGIES[name]
    n = FX["native"][name]["max_records"]
    close = np.array([c.c for c in cs[i + 1 - n:i + 1]])
    return fn(close, params)


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_parity_with_native_bot_on_same_candles(name):
    """Posturas e indicadores idénticos a los de `update_processed_data` con pandas-ta real."""
    cs = candles()
    native = FX["native"][name]
    checked = 0
    for i, c in enumerate(cs):
        key = str(c.t)
        if key not in native["signals"]:
            continue
        sig, feats = _window_features(name, cs, i)
        assert int(sig[-1]) == native["signals"][key], (name, key)
        for k, v in native["features"][key].items():
            assert feats[k][-1] == pytest.approx(v, rel=1e-9, abs=1e-9), (name, k, key)
        checked += 1
    assert checked >= 250
    assert set(native["signals"].values()) - {0} or name == "macd_bb_v1"  # hay posturas ≠ 0


def test_adapter_signal_matches_native_on_last_candle():
    snap = snapshot()
    got = {s.strategy: s for s in HummingbotDirectionalAdapter().signals(snap)}
    for name, native in FX["native"].items():
        assert got[name].stance == native["signals"][str(snap.candles[-1].t)]
        assert got[name].status == "ok" and got[name].confidence is None


def test_adapter_signals_over_every_bar_match_native():
    cs = candles()
    ad = HummingbotDirectionalAdapter()
    for name, native in FX["native"].items():
        n = native["max_records"]
        for i in range(n - 1, len(cs), 7):
            sig = next(s for s in ad.signals(snapshot(i + 1, cs)) if s.strategy == name)
            assert sig.stance == native["signals"][str(cs[i].t)], (name, i)


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_no_lookahead_truncating_candles_does_not_change_past_postures(name):
    cs = candles()
    full = stance_series(cs, name)
    ad = HummingbotDirectionalAdapter()
    n = STRATEGIES[name][0].max_records
    for i in range(n - 1, len(cs), 5):
        sig = next(s for s in ad.signals(snapshot(i + 1, cs)) if s.strategy == name)
        assert sig.stance == full[i]
        assert sig.data_quality.last_candle_t == cs[i].t <= sig.asof


def test_future_candles_do_not_alter_the_posture_at_a_past_asof():
    cs = candles()
    a = HummingbotDirectionalAdapter().signals(snapshot(300, cs))
    altered = cs[:300] + [c.model_copy(update={"c": c.c * 3, "h": c.h * 3}) for c in cs[300:]]
    b = HummingbotDirectionalAdapter().signals(snapshot(300, altered))
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]


def test_insufficient_candles_is_no_data_without_exception():
    sigs = HummingbotDirectionalAdapter().signals(snapshot(50))
    assert {s.status for s in sigs} == {"no_data"}
    assert all(s.stance == 0 and s.confidence is None for s in sigs)
    assert all("insuficientes" in s.evidence[0] for s in sigs)


def test_version_changes_with_sha_and_with_parameters():
    card = card_of("hummingbot-directional")
    a = HummingbotDirectionalAdapter()
    assert a.version("bollinger_v1") == version_of(
        card.commit_sha, {"strategy": "bollinger_v1", **BollingerV1().model_dump()})
    other = card.model_copy(update={"commit_sha": "0" * 40})
    assert HummingbotDirectionalAdapter(other).version("bollinger_v1") != a.version("bollinger_v1")
    tuned = HummingbotDirectionalAdapter(strategies={"bollinger_v1": BollingerV1(bb_std=2.5)})
    assert tuned.version("bollinger_v1") != a.version("bollinger_v1")
    assert a.version("bollinger_v1") != a.version("macd_bb_v1")


def test_raw_keeps_what_the_bot_emitted_and_evidence_explains():
    s = HummingbotDirectionalAdapter().signals(snapshot())[0]
    assert s.raw["signal"] in (-1, 0, 1) and "bbp" in s.raw
    assert "regla portada" in s.evidence[0] and s.data_quality.coverage == 1.0
