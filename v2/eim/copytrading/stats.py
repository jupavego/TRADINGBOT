"""Estadística robusta para elegir líderes (puro, sin dependencias).

Elegir «el mejor» entre muchas billeteras infla su Sharpe: aunque ninguna tenga ventaja, la
mejor de N parece buena por azar. Se corrige así:

- **Sharpe deflactado (DSR)**, Bailey y López de Prado (2014): probabilidad de que el Sharpe
  real supere al máximo esperado de N estimaciones nulas con la misma muestra,
  `SR0 = E[max Z_N] / √(n−1)`, con la asimetría y la curtosis de los datos.
- **Intervalos con Bonferroni**: nivel `1 − α/N` (bilateral) en vez de `1 − α`.

Todo Sharpe es **por operación** (sin anualizar): media/desviación del neto por operación.
"""

from __future__ import annotations

import math
from statistics import NormalDist

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def moments(xs: list[float]) -> tuple[float, float, float, float]:
    """(media, desviación muestral, asimetría, curtosis no en exceso; normal = 3)."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0, 0.0, 3.0
    m = sum(xs) / n
    if n < 2:
        return m, 0.0, 0.0, 3.0
    d = [x - m for x in xs]
    var = sum(v * v for v in d) / (n - 1)
    sd = math.sqrt(var)
    pop = sum(v * v for v in d) / n
    if pop <= 0:
        return m, sd, 0.0, 3.0
    skew = sum(v ** 3 for v in d) / n / pop ** 1.5
    kurt = sum(v ** 4 for v in d) / n / pop ** 2
    return m, sd, skew, kurt


def sharpe(xs: list[float]) -> float | None:
    m, sd, _, _ = moments(xs)
    return m / sd if len(xs) >= 2 and sd > 0 else None


def expected_max_z(n_trials: int) -> float:
    """Máximo esperado de N normales estándar independientes (aprox. de Gumbel)."""
    if n_trials <= 1:
        return 0.0
    return ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n_trials)
            + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n_trials * math.e)))


def sharpe_se(sr: float, n: int, skew: float, kurt: float) -> float:
    """Error estándar del Sharpe estimado con no normalidad (Mertens / Lo)."""
    v = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    return math.sqrt(max(v, 1e-12) / max(n - 1, 1))


def psr(sr: float, sr0: float, n: int, skew: float, kurt: float) -> float:
    """Probabilistic Sharpe Ratio: P(SR real > sr0)."""
    return _N.cdf((sr - sr0) / sharpe_se(sr, n, skew, kurt))


def deflated(xs: list[float], n_trials: int) -> tuple[float, float] | None:
    """(DSR, SR0) del neto por operación; None con menos de 3 operaciones o sin varianza."""
    n = len(xs)
    sr = sharpe(xs)
    if n < 3 or sr is None:
        return None
    _, _, skew, kurt = moments(xs)
    sr0 = expected_max_z(n_trials) / math.sqrt(n - 1)
    return psr(sr, sr0, n, skew, kurt), sr0


def z_bonferroni(level: float, n_trials: int) -> float:
    return _N.inv_cdf(1 - (1 - level) / (2 * max(n_trials, 1)))


def sharpe_ci(xs: list[float], level: float, n_trials: int) -> tuple[float, float] | None:
    sr = sharpe(xs)
    if sr is None or len(xs) < 3:
        return None
    _, _, skew, kurt = moments(xs)
    h = z_bonferroni(level, n_trials) * sharpe_se(sr, len(xs), skew, kurt)
    return sr - h, sr + h


def mean_ci(xs: list[float], level: float, n_trials: int) -> tuple[float, float] | None:
    m, sd, _, _ = moments(xs)
    if len(xs) < 3 or sd <= 0:
        return None
    h = z_bonferroni(level, n_trials) * sd / math.sqrt(len(xs))
    return m - h, m + h


def max_drawdown(pnl: list[float], base: float | None) -> float | None:
    """Caída máxima del neto acumulado respecto de `base` (valor de la cuenta) más el pico."""
    if not pnl or not base or base <= 0:
        return None
    peak = cum = worst = 0.0
    for x in pnl:
        cum += x
        peak = max(peak, cum)
        worst = max(worst, (peak - cum) / (base + peak))
    return worst


def quantile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo = math.floor(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)
