"""Estadística de la puerta de edge (T27): líneas base, nulos aleatorios y pruebas múltiples.

Todo es puro y reproducible con semilla. No cambia la estrategia: solo la mide.
- `RecordingStrategy` / `ReplayStrategy`: graban las señales de una estrategia y las reproducen,
  opcionalmente con el lado al azar (mismo instante de decisión, misma distancia de SL/TP,
  mismos costos) → nulo de «entrada aleatoria con el mismo riesgo».
- `buy_hold_returns`: retornos por vela de comprar y mantener (línea base).
- `sharpe_diff_pvalue`, `mean_pvalue`, `perm_pvalue`, `holm`: significancia.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from eim.backtest.metrics import _block_idx, _sharpe
from eim.backtest.strategy import Signal, Strategy
from eim.core import Candle, MarketSnapshot


@dataclass(frozen=True)
class Decision:
    close: float     # cierre de la vela de decisión
    signal: Signal


class RecordingStrategy:
    """Envuelve una estrategia y guarda cada señal por el tiempo de la última vela."""

    def __init__(self, inner: Strategy) -> None:
        self.inner = inner
        self.decisions: dict[int, Decision] = {}

    def on_bar(self, snapshot: MarketSnapshot) -> Signal | None:
        sig = self.inner.on_bar(snapshot)
        if sig is not None:
            c = snapshot.candles[-1]
            self.decisions[c.t] = Decision(c.c, sig)
        return sig


def flip(d: Decision) -> Signal:
    """Misma operación en el lado contrario: SL/TP reflejados alrededor del cierre."""
    s = d.signal
    return replace(s, side=-s.side, sl=2 * d.close - s.sl, tp=2 * d.close - s.tp)


class ReplayStrategy:
    """Reproduce decisiones grabadas; con `rng`, cada lado se elige al azar (p = ½)."""

    def __init__(self, decisions: dict[int, Decision],
                 rng: np.random.Generator | None = None) -> None:
        self.decisions = decisions
        self.rng = rng

    def on_bar(self, snapshot: MarketSnapshot) -> Signal | None:
        d = self.decisions.get(snapshot.candles[-1].t)
        if d is None:
            return None
        if self.rng is not None and self.rng.random() < 0.5:
            return flip(d)
        return d.signal


def buy_hold_returns(candles: list[Candle], a: int, b: int) -> np.ndarray:
    """Retornos cierre a cierre de las velas `[a, b)` (el primero parte del cierre `a−1`)."""
    c = np.array([x.c for x in candles[max(a - 1, 0):b]], dtype=float)
    return np.diff(c) / c[:-1]


def perm_pvalue(obs: float, null: list[float] | np.ndarray) -> float:
    """p unilateral (H1: obs mayor que el nulo), con corrección +1 (nunca 0)."""
    arr = np.asarray(null, dtype=float)
    return float((1 + np.sum(arr >= obs)) / (1 + len(arr)))


def mean_pvalue(x: np.ndarray, n_boot: int = 5000, seed: int = 0) -> float:
    """p unilateral de media > 0 por bootstrap bajo H0 (muestra recentrada en 0)."""
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return 1.0
    rng = np.random.default_rng(seed)
    z = x - x.mean()
    boots = z[rng.integers(0, len(x), size=(n_boot, len(x)))].mean(axis=1)
    return perm_pvalue(float(x.mean()), boots)


def sharpe_diff_pvalue(r_a: np.ndarray, r_b: np.ndarray, ppy: float, n_boot: int = 2000,
                       seed: int = 0) -> tuple[float, list[float]]:
    """p unilateral de Sharpe(a) > Sharpe(b) con bootstrap por bloques pareado + IC95 % de la
    diferencia. `r_a` y `r_b` deben estar alineados por vela."""
    r_a, r_b = np.asarray(r_a, float), np.asarray(r_b, float)
    n = min(len(r_a), len(r_b))
    r_a, r_b = r_a[:n], r_b[:n]
    if n < 10:
        return 1.0, [math.nan, math.nan]
    rng = np.random.default_rng(seed)
    block = max(2, int(math.sqrt(n)))
    diffs = []
    for _ in range(n_boot):
        i = _block_idx(rng, n, block)
        diffs.append(_sharpe(r_a[i], ppy) - _sharpe(r_b[i], ppy))
    d = np.array(diffs)
    p = float((1 + np.sum(d <= 0)) / (1 + n_boot))
    return p, [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """p ajustados por Holm–Bonferroni (monótonos, acotados en 1)."""
    keys = sorted(pvals, key=pvals.get)
    m, run, out = len(keys), 0.0, {}
    for k, key in enumerate(keys):
        run = max(run, min(1.0, (m - k) * pvals[key]))
        out[key] = run
    return out
