"""Estadística mínima de la boleta: Wilson, binomial de una cola, McNemar exacto y Holm. Puro."""

from __future__ import annotations

import math
from collections.abc import Mapping

from scipy.stats import binomtest

Z95 = 1.959963984540054


def wilson(hits: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """IC de Wilson de una proporción; None sin muestra."""
    if n <= 0:
        return None
    p = hits / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def p_greater(hits: int, n: int) -> float | None:
    """P de que el acierto supere la moneda (binomial exacta, una cola)."""
    return None if n <= 0 else float(binomtest(hits, n, 0.5, alternative="greater").pvalue)


def mcnemar_greater(b: int, c: int) -> float | None:
    """McNemar exacto de una cola: `b` = aciertos solo de A, `c` = solo de B. H1: A acierta más."""
    return None if b + c <= 0 else float(binomtest(b, b + c, 0.5, alternative="greater").pvalue)


def holm(pvals: Mapping[str, float | None]) -> dict[str, float | None]:
    """P ajustados por Holm (paso a paso, monótonos); los None quedan fuera de la familia."""
    known = sorted(((p, k) for k, p in pvals.items() if p is not None))
    m, out, run = len(known), {k: None for k in pvals}, 0.0
    for i, (p, k) in enumerate(known):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out
