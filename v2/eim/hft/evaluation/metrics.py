"""Métricas del marco de evaluación (T80): IC, acierto, calibración y pb netos. Puras.

- **IC de Spearman** por día y su media (el IC de un solo número sobre 1,5 M de filas solapadas
  tiene un error estándar que no se puede creer; por día sí se puede remuestrear).
- **Acierto balanceado** sobre las filas en las que la etiqueta no es 0 (las que pagan el costo).
- **Brier** y **pinball** para la calidad de una probabilidad o de un cuantil.
- **pb netos por operación** con el costo de ida y vuelta y su IC por bloques de día
  (`eim/validation/stats.py`, el mismo que usa la puerta de T49).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import rankdata

from eim.hft.evaluation.splits import DAY_MS, day_of
from eim.validation.stats import day_block_ci, rng_for

MIN_PER_DAY = 100          # filas mínimas de un día para que su IC cuente


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Correlación de rangos (empates promediados); NaN con menos de 3 filas o sin variación."""
    a, b = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return math.nan
    ra, rb = rankdata(a[ok]), rankdata(b[ok])
    sa, sb = ra.std(), rb.std()
    if sa == 0 or sb == 0:
        return math.nan
    return float(((ra - ra.mean()) * (rb - rb.mean())).mean() / (sa * sb))


def ic_by_day(x: np.ndarray, y: np.ndarray, t_ms: np.ndarray,
              min_per_day: int = MIN_PER_DAY) -> tuple[np.ndarray, np.ndarray]:
    """(días, IC de cada día) con al menos `min_per_day` filas utilizables."""
    d = day_of(t_ms)
    days, ics = [], []
    for day in np.unique(d):
        m = d == day
        if int(m.sum()) < min_per_day:
            continue
        ic = spearman(np.asarray(x)[m], np.asarray(y)[m])
        if math.isfinite(ic):
            days.append(int(day))
            ics.append(ic)
    return np.asarray(days, dtype=np.int64), np.asarray(ics, float)


def mean_ci(values: np.ndarray, days: np.ndarray, reps: int, level: float,
            label: str, seed: int = 0) -> dict:
    """Media de una serie por día con IC por bootstrap de días (bloques de día de T49)."""
    v = np.asarray(values, float)
    if v.size == 0:
        return {"n_days": 0, "mean": None, "lo": None, "hi": None}
    lo, hi = day_block_ci(v, np.asarray(days, dtype=np.int64) * DAY_MS, reps, level,
                          rng_for(seed, label))
    return {"n_days": int(v.size), "mean": float(v.mean()),
            "lo": None if math.isnan(lo) else float(lo),
            "hi": None if math.isnan(hi) else float(hi),
            "positive_days": float((v > 0).mean())}


def balanced_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    """Acierto balanceado de la dirección sobre las filas con etiqueta ±1 (0 = no paga)."""
    yt, yp = np.asarray(y_true, float), np.asarray(y_pred, float)
    m = yt != 0
    if not m.any():
        return None
    recalls = []
    for cls in (1.0, -1.0):
        sel = m & (yt == cls)
        if sel.any():
            recalls.append(float((np.sign(yp[sel]) == cls).mean()))
    return float(np.mean(recalls)) if recalls else None


def brier(p_up: np.ndarray, y_up: np.ndarray) -> float | None:
    """Brier de la probabilidad de subida (`y_up` ∈ {0, 1}); menor es mejor."""
    p, y = np.asarray(p_up, float), np.asarray(y_up, float)
    ok = np.isfinite(p) & np.isfinite(y)
    return None if not ok.any() else float(((p[ok] - y[ok]) ** 2).mean())


def pinball(pred: np.ndarray, y: np.ndarray, tau: float) -> float | None:
    """Pérdida pinball del cuantil `tau` (0 < tau < 1); menor es mejor."""
    q, yy = np.asarray(pred, float), np.asarray(y, float)
    ok = np.isfinite(q) & np.isfinite(yy)
    if not ok.any():
        return None
    d = yy[ok] - q[ok]
    return float(np.maximum(tau * d, (tau - 1) * d).mean())


def net_bps(signal: np.ndarray, dmid_bps: np.ndarray, cost_bps: float,
            threshold: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """(pb netos de cada operación, máscara de las filas en las que se opera).

    Se opera en el signo de la señal cuando |señal| > umbral; el resultado es el Δmid a favor
    menos el costo de ida y vuelta. Sin modelo de cola: es la cota por arriba de una ejecución
    inmediata en los dos extremos.
    """
    s, d = np.asarray(signal, float), np.asarray(dmid_bps, float)
    take = np.isfinite(s) & np.isfinite(d) & (np.abs(s) > threshold)
    return np.sign(s[take]) * d[take] - cost_bps, take


def skill(loss: float | None, base: float | None) -> float | None:
    """Mejora relativa de una pérdida frente a su línea base (+ = mejor)."""
    if loss is None or base is None or base == 0:
        return None
    return float(1 - loss / base)
