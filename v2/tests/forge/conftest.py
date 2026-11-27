"""Serie sintética de 5 m para las pruebas de la forja (T208): sin red y reproducible."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from eim.forge import features, session
from eim.forge.data import Series

TF = 300_000


def make_series(days: int = 12, start: str = "2026-03-02", seed: int = 7) -> Series:
    """Velas de 5 m continuas (24 h) de `days` días naturales, con un paseo aleatorio."""
    t0 = int(datetime.fromisoformat(start).replace(tzinfo=UTC).timestamp() * 1000)
    n = days * 288
    t = t0 + TF * np.arange(n, dtype=np.int64)
    rng = np.random.default_rng(seed)
    step = rng.normal(0, 30, n)
    c = 60_000 + np.cumsum(step)
    o = np.r_[60_000.0, c[:-1]]
    wick = np.abs(rng.normal(0, 25, n))
    h = np.maximum(o, c) + wick
    lo = np.minimum(o, c) - wick
    v = np.abs(rng.normal(50, 15, n)) + 1
    tb = v * rng.uniform(0.3, 0.7, n)
    tr = np.maximum(np.round(v * 10), 1)
    return Series(t=t, o=o, h=h, l=lo, c=c, v=v, taker_buy_v=tb, trades=tr,
                  funding=np.zeros(n))


@pytest.fixture(scope="module")
def serie() -> Series:
    return make_series()


@pytest.fixture(scope="module")
def sesiones(serie: Series) -> session.Sessions:
    return session.build(serie.t)


@pytest.fixture(scope="module")
def rasgos(serie: Series, sesiones: session.Sessions) -> dict[str, np.ndarray]:
    return features.build(serie, sesiones)
