"""Adaptador modo A (`trendrider-strategy`): paridad con la estrategia nativa de Freqtrade."""

import json
from pathlib import Path

import numpy as np

from eim.bots.service import BotService
from eim.bots.trendrider import STRATEGY, WINDOW, TrendRiderAdapter, stance_of
from eim.bots.trendrider_ind import adx_di, informative
from eim.core import Candle, MarketSnapshot

FX = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "bots"
                 / "trendrider_parity.json").read_text(encoding="utf-8"))
CS = [Candle(t=r[0], o=r[1], h=r[2], l=r[3], c=r[4], v=r[5]) for r in FX["candles"]]
BY_T = {c.t: i for i, c in enumerate(CS)}
STEP = 3_600_000


def _snap(n: int, symbol="BTCUSDT") -> MarketSnapshot:
    cs = CS[:n]
    return MarketSnapshot(symbol=symbol, timeframe="1h", candles=cs, asof=cs[-1].t + STEP,
                          sources={"candles": "fixture"})


def test_parity_with_native_strategy():
    """Postura y banderas de la última vela idénticas a las de `TrendRiderStrategy` real."""
    bad = []
    for key, nat in FX["native"].items():
        i = BY_T[int(key)]
        stance, last, _ = stance_of(CS[i + 1 - WINDOW:i + 1])
        got = {"stance": int(stance), "enter_last": last["enter_long"],
               "exit_last": last["exit_long"]}
        want = {k: nat[k] for k in got}
        if got != want:
            bad.append((key, got, want))
    assert not bad, bad
    assert len(FX["native"]) >= 25
    assert len({v["stance"] for v in FX["native"].values()}) > 1     # no es constante


def test_adapter_signal_and_version():
    sig = TrendRiderAdapter().signals(_snap(len(CS)))[0]
    nat = FX["native"][str(CS[-1].t)] if str(CS[-1].t) in FX["native"] else None
    assert sig.status == "ok" and sig.strategy == STRATEGY and sig.confidence is None
    if nat:
        assert sig.stance == nat["stance"]


def test_only_btcusdt_and_enough_history():
    ad = TrendRiderAdapter()
    assert ad.signals(_snap(len(CS), "ETHUSDT"))[0].status == "no_data"
    assert ad.signals(_snap(WINDOW - 1))[0].status == "no_data"


def test_no_lookahead_on_truncation():
    full = []
    for cut in (WINDOW + 5, WINDOW + 60, len(CS)):
        a = stance_of(CS[cut - WINDOW:cut])[0]
        b = stance_of(CS[cut - WINDOW:cut])[0]
        full.append(a == b)
        # añadir velas futuras no cambia lo que se decide en `cut`: la ventana termina en `cut`
        assert stance_of(CS[:cut][-WINDOW:])[0] == a
    assert all(full)


def test_adx_matches_wilder_reference_shape():
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 1, 300))
    adx, pdi, mdi = adx_di(c + 1, c - 1, c)
    assert np.isnan(adx[:27]).all() and not np.isnan(adx[27:]).any()
    assert ((adx[27:] >= 0) & (adx[27:] <= 100)).all() and ((pdi[14:] >= 0) & (mdi[14:] >= 0)).all()


def test_informative_only_complete_bars_and_closed_before_use():
    t = np.arange(9, dtype=np.int64) * STEP + 2 * STEP      # 02:00–10:00: grupos parciales
    x = np.arange(9, dtype=float)
    inf = informative(t, x, x, x, x, 4 * STEP)
    assert list(inf.t // STEP) == [4]                          # solo la barra 04:00–08:00 completa
    got = inf.align(np.array([7.0]), t)
    # la barra 04–08 está disponible al cierre de la vela de las 07:00 (apertura 07:00)
    assert np.isnan(got[t // STEP < 7]).all() and (got[t // STEP >= 7] == 7.0).all()


def test_service_skips_other_timeframes():
    snap = _snap(len(CS)).model_copy(update={"timeframe": "4h"})
    assert BotService([TrendRiderAdapter()]).produce(snap) == []
