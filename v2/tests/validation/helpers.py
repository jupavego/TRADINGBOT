"""Operaciones sintéticas para los tests de la puerta de validación (sin red)."""

from __future__ import annotations

import numpy as np

from eim.validation.evidence import Trade
from eim.validation.lineage import Version

H = 3_600_000
DAY = 24 * H
T0 = 1_700_000_000_000 // DAY * DAY


def trades(n: int = 220, mean: float = 0.5, sd: float = 1.0, seed: int = 0, step_h: float = 16,
           cost: float = 0.1, live_last: int = 40, t0: int = T0,
           regimes: tuple[str, ...] = ("range", "trend")) -> list[Trade]:
    """`n` operaciones cada `step_h` horas; R ~ N(mean, sd). El lado contrario pierde lo que
    ganó el original y paga los mismos costos (r_flip = −r − 2·cost)."""
    rng = np.random.default_rng(seed)
    out = []
    for k in range(n):
        r = float(rng.normal(mean, sd))
        t = t0 + int(k * step_h * H)
        out.append(Trade(t=t, exit_t=t + 2 * H, r=r, r_flip=-r - 2 * cost, cost_r=cost,
                         regime=regimes[k % len(regimes)],
                         origin="vivo" if k >= n - live_last else "backtest"))
    return out


def version(sid: str = "s@1h", n: int = 1, retired: int | None = None) -> Version:
    strategy, tf = sid.split("@")
    return Version(sid, n, f"fp{n}", strategy, tf, T0, n - 1 or None, "test", retired_ms=retired)
