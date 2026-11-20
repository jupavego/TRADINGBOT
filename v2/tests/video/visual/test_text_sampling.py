"""T66: lectura de cifras/activo/marco/indicadores y elección de fotogramas (puro)."""

from __future__ import annotations

import numpy as np
import pytest

from eim.video.visual import text as T
from eim.video.visual.imageops import dhash, grid, hamming
from eim.video.visual.params import VisualParams
from eim.video.visual.sampling import Sample, candidates, select
from tests.video.visual.synth import chart_image, slide_image


@pytest.mark.parametrize("raw,val", [
    ("61.250", 61250), ("61,250", 61250), ("3,5", 3.5), ("3.5", 3.5),
    ("61,250.50", 61250.5), ("61.250,50", 61250.5), ("1.234.567", 1234567), ("0.250", 0.25),
])
def test_parse_number(raw: str, val: float) -> None:
    assert T.parse_number(raw) == pytest.approx(val)


def test_numbers_units_and_noise() -> None:
    got = {(n.value, n.unit) for n in T.numbers("BTC $64.000 sube 3,5 % y toca 66k USDT 15")}
    assert (64000.0, "USD") in got and (3.5, "%") in got and (66000.0, "USD") in got
    assert all(v != 15 for v, _ in got)            # «15» suelto es un rótulo, no una cifra


def test_symbol_timeframe_indicators() -> None:
    assert T.symbol_of("BTC/USDT · Binance") == "BTCUSDT"
    assert T.symbol_of("Ethereum perpetual") == "ETHUSDT"
    assert T.symbol_of("mercado en general") is None
    assert T.timeframe_of("BTCUSDT · 4H") == "4h" and T.timeframe_of("15m chart") == "15m"
    inds = T.indicators("RSI (14) 62,35  EMA 200 64.120")
    assert [(i.unit, i.value) for i in inds] == [("rsi:14", 62.35), ("ema:200", 64120.0)]


def _samples(frames: list[np.ndarray], every: float = 1.0) -> list[Sample]:
    return [Sample(i * every, dhash(f), grid(f)) for i, f in enumerate(frames)]


def test_cut_between_two_dark_charts_with_same_mean() -> None:
    """Alerta 14 de T62: dos gráficos oscuros con la misma luminancia media sí son un corte."""
    a, b = chart_image(seed=1), chart_image(seed=2, level_y=None)
    assert abs(a.mean() - b.mean()) < 2.0
    c = candidates(_samples([a, a, b, b]))
    assert [x.reason for x in c] == ["inicio", "corte"]


def test_dedup_min_sampling_and_cap() -> None:
    a, s = chart_image(seed=1), slide_image()
    frames = [a] * 40 + [s] * 5 + [a] * 40            # vuelve al mismo gráfico: casi idéntico
    p = VisualParams(min_every_s=30.0)
    sel = select(_samples(frames), duration_s=85, p=p)
    reasons = [c.reason for c in candidates(_samples(frames), p)]
    assert "muestreo" in reasons and "corte" in reasons
    assert sel.n_duplicates >= 2                       # el regreso y los muestreos repetidos
    assert hamming(sel.chosen[0].hash, sel.chosen[1].hash) > p.dup_hash_bits
    many = [chart_image(seed=i) for i in range(12)]
    tight = VisualParams(frames_ocr_per_h=120, min_frames=3, dup_hash_bits=0)
    capped = select(_samples(many), duration_s=60, p=tight)   # 1 min → tope 3
    assert capped.cap == 3 and len(capped.chosen) == 3 and capped.n_over_cap > 0
    assert [c.t for c in capped.chosen] == sorted(c.t for c in capped.chosen)


def test_frame_cap_budget() -> None:
    p = VisualParams()
    assert p.frame_cap(3600) == 120 and p.frame_cap(1200) == 40
    assert p.frame_cap(1200, vlm=True) == 7 and p.frame_cap(5) == p.min_frames
