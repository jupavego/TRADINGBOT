"""Evaluación pre-registrada de la recalibración (T160). Puro.

Brier emparejado por origen, prueba t de una cola en la submuestra sin solape, Holm sobre la
familia de 2 intentos y ECE de 3 clases como en `eim.forecast.calibration`
(`PLAN/notas/T160_preregistro.md` §4).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from scipy.stats import t as student_t

from eim.forecast.recal import IDS, Obs, brier

ALPHA = 0.05


def ece(pairs: Sequence[tuple[dict[str, float], str]], bins: int = 10) -> float:
    acc = [[0, 0.0, 0] for _ in range(bins)]
    for p, real in pairs:
        for i in IDS:
            b = min(int(p[i] * bins), bins - 1)
            acc[b][0] += 1
            acc[b][1] += p[i]
            acc[b][2] += real == i
    n = len(pairs)
    return sum(abs(s / k - h / k) * k for k, s, h in acc if k) / (3 * n) if n else float("nan")


def one_sided_t(d: Sequence[float]) -> dict:
    """H0: media(d) ≤ 0 frente a H1: media(d) > 0."""
    n = len(d)
    if n < 3:
        return {"n": n, "mean": statistics.fmean(d) if d else None, "t": None, "p": None,
                "ci95": None}
    m, sd = statistics.fmean(d), statistics.stdev(d)
    se = sd / math.sqrt(n)
    t = m / se if se > 0 else math.inf
    half = student_t.ppf(0.975, n - 1) * se
    return {"n": n, "mean": m, "t": t, "p": float(student_t.sf(t, n - 1)),
            "ci95": [m - half, m + half]}


def holm(pvals: dict[str, float | None], alpha: float = ALPHA) -> dict[str, bool]:
    """Holm-Bonferroni descendente; un p ausente nunca rechaza."""
    order = sorted((p, k) for k, p in pvals.items() if p is not None)
    m, out, stop = len(pvals), {k: False for k in pvals}, False
    for j, (p, k) in enumerate(order):
        if stop or p > alpha / (m - j):
            stop = True
            continue
        out[k] = True
    return out


def score(evals: Sequence[tuple[Obs, dict[str, float]]], stride: int) -> dict:
    """Brier bruto frente a recalibrado, diferencia sin solape (1 de cada `stride`) y ECE."""
    raw = [brier(o.probs, o.realized) for o, _ in evals]
    rec = [brier(p, o.realized) for o, p in evals]
    d = [a - b for a, b in zip(raw, rec, strict=True)]
    n = len(evals)
    return {
        "n": n, "brier_raw": statistics.fmean(raw) if n else None,
        "brier_recal": statistics.fmean(rec) if n else None,
        "d_mean_all": statistics.fmean(d) if n else None,
        "test": one_sided_t(d[::stride]),
        "ece_raw": ece([(o.probs, o.realized) for o, _ in evals]),
        "ece_recal": ece([(p, o.realized) for o, p in evals]),
        "top_hit_raw": _top(evals, raw=True), "top_hit_recal": _top(evals, raw=False),
        "mean_prob_raw": _means([o.probs for o, _ in evals]),
        "mean_prob_recal": _means([p for _, p in evals]),
        "realized_freq": {i: sum(o.realized == i for o, _ in evals) / n for i in IDS} if n else {},
    }


def _top(evals, raw: bool) -> float | None:
    if not evals:
        return None
    hits = [max(IDS, key=(o.probs if raw else p).get) == o.realized for o, p in evals]
    return sum(hits) / len(hits)


def _means(ps: Sequence[dict[str, float]]) -> dict[str, float]:
    return {i: statistics.fmean(p[i] for p in ps) for i in IDS} if ps else {}
