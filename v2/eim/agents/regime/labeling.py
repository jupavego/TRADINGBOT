"""Etiquetado de régimen por tramo y métricas de estabilidad (matriz de transición, entropía)."""

from __future__ import annotations

import numpy as np

LABELS = ("trend_up", "trend_down", "range", "volatile")


def segment_starts(n: int, cps: list[int]) -> np.ndarray:
    """Inicio del tramo vigente en cada vela, dado el conjunto de cambios detectados."""
    starts = np.zeros(n, dtype=int)
    cur = 0
    cps_set = set(cps)
    for i in range(n):
        if i in cps_set:
            cur = i
        starts[i] = cur
    return starts


def label_bars(rets: np.ndarray, starts: np.ndarray, min_seg: int, trend_t: float,
               vol_ratio: float) -> list[str]:
    """Etiqueta cada vela con los estadísticos de su tramo (mínimo `min_seg` velas atrás)."""
    n = len(rets)
    c1 = np.concatenate(([0.0], np.cumsum(rets)))
    c2 = np.concatenate(([0.0], np.cumsum(rets**2)))
    sig = np.zeros(n)
    mean = np.zeros(n)
    cnt = np.zeros(n)
    for i in range(n):
        lo = min(starts[i], max(0, i + 1 - min_seg))
        k = i + 1 - lo
        m = (c1[i + 1] - c1[lo]) / k
        var = max((c2[i + 1] - c2[lo]) / k - m * m, 0.0)
        sig[i], mean[i], cnt[i] = np.sqrt(var), m, k
    ref = float(np.median(sig[sig > 0])) if np.any(sig > 0) else 0.0
    out: list[str] = []
    for i in range(n):
        if ref > 0 and sig[i] > vol_ratio * ref:
            out.append("volatile")
            continue
        t = mean[i] / (sig[i] / np.sqrt(cnt[i])) if sig[i] > 0 else 0.0
        out.append("trend_up" if t >= trend_t else "trend_down" if t <= -trend_t else "range")
    return out


def stability(labels: list[str]) -> dict:
    """Matriz de transición, permanencia media por régimen y entropía normalizada."""
    idx = {name: k for k, name in enumerate(LABELS)}
    m = len(LABELS)
    counts = np.zeros((m, m))
    for a, b in zip(labels[:-1], labels[1:], strict=True):
        counts[idx[a], idx[b]] += 1
    rows = counts.sum(axis=1)
    trans = np.divide(counts, rows[:, None], out=np.zeros_like(counts), where=rows[:, None] > 0)
    occ = rows / rows.sum() if rows.sum() > 0 else rows
    safe = np.where(trans > 0, trans, 1.0)
    h_row = -np.sum(trans * np.log(safe), axis=1)
    entropy = float(np.sum(occ * h_row) / np.log(m))
    runs: dict[str, list[int]] = {name: [] for name in LABELS}
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            runs[labels[start]].append(i - start)
            start = i
    all_runs = [r for v in runs.values() for r in v]
    return {
        "labels": list(LABELS),
        "transition": trans.round(4).tolist(),
        "dwell_mean": {k: (float(np.mean(v)) if v else None) for k, v in runs.items()},
        "dwell_overall": float(np.mean(all_runs)),
        "entropy": entropy,
        "n_switches": len(all_runs) - 1,
    }
