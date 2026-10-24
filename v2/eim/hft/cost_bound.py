"""Cota analítica de costos (T77): ¿cuánto se mueve el mid frente a lo que cuesta operar?

Puro (sin red ni disco). Orientativo: la cota definitiva con features y previsión es T80.
- |Δmid| a horizonte h: para cada punto de la serie como origen, el precio del último punto
  ≤ t + h (se descarta si ese punto tiene más de `max_stale_ms` de antigüedad o si entre origen
  y destino hay un hueco de la recolección). La serie puede ser el mid del top del libro o una
  rejilla regular del último precio negociado (`asof_grid`);
- techo con previsión perfecta: E[max(|Δmid| − c, 0)] por ventana (se opera solo cuando paga y
  siempre en la dirección correcta, sin selección adversa ni cola: imposible de superar).
Las ventanas se solapan: los percentiles valen, los errores estándar no (eso es T80).
"""

from __future__ import annotations

import numpy as np

ROUND_TRIPS_BPS = {"taker": 10.0, "mixto": 7.0, "maker": 4.0}   # con CostParams (5 / 2 pb)
HORIZONS_S = (1, 2, 5, 10, 30, 60)
GAP_MS = 5_000                                                 # hueco de la recolección


def mid_moves_bps(t_ms: np.ndarray, mid: np.ndarray, horizon_ms: int,
                  max_stale_ms: int = 2_000) -> np.ndarray:
    """|Δmid| en pb entre cada origen y la última instantánea ≤ origen + h (sin huecos)."""
    t = np.asarray(t_ms, dtype=np.int64)
    m = np.asarray(mid, dtype=float)
    if t.size < 2:
        return np.empty(0)
    j = np.searchsorted(t, t + horizon_ms, side="right") - 1
    # destino dentro de los datos y con un punto reciente (al final de la serie no se acorta h)
    fresh = ((t + horizon_ms - t[j]) <= max_stale_ms) & (t + horizon_ms <= t[-1])
    # sin huecos entre origen y destino: el hueco máximo acumulado no puede crecer
    big = np.concatenate([[0], np.cumsum(np.diff(t) > GAP_MS)])
    ok = fresh & (j > np.arange(t.size)) & (big[j] == big)
    return np.abs(m[j[ok]] / m[ok] - 1.0) * 1e4


def asof_grid(t_ms: np.ndarray, price: np.ndarray, step_ms: int = 1_000,
              max_age_ms: int = GAP_MS) -> tuple[np.ndarray, np.ndarray]:
    """Último precio ≤ cada punto de una rejilla regular; se descartan los puntos cuyo último
    precio tiene más de `max_age_ms` (hueco de la recolección). Con spread de ≈ 1 tick, el
    precio de la última operación aproxima el mid a menos de medio tick."""
    t = np.asarray(t_ms, dtype=np.int64)
    p = np.asarray(price, dtype=float)
    if t.size == 0:
        return np.empty(0, dtype=np.int64), np.empty(0)
    grid = np.arange(t[0] - t[0] % step_ms + step_ms, t[-1] + 1, step_ms, dtype=np.int64)
    i = np.searchsorted(t, grid, side="right") - 1
    ok = (i >= 0) & (grid - t[np.clip(i, 0, None)] <= max_age_ms)
    return grid[ok], p[i[ok]]


def spread_summary(bid: np.ndarray, ask: np.ndarray) -> dict:
    """Spread relativo (pb) del top del libro: p50/p95/p99."""
    b, a = np.asarray(bid, dtype=float), np.asarray(ask, dtype=float)
    sp = (a - b) / ((a + b) / 2) * 1e4
    if not sp.size:
        return {}
    return {k: round(float(np.percentile(sp, q)), 4) for k, q in (("p50", 50), ("p95", 95),
                                                                 ("p99", 99))}


def bound_table(t_ms: np.ndarray, mid: np.ndarray, horizons_s=HORIZONS_S,
                costs_bps: dict[str, float] | None = None) -> dict:
    """Distribución de |Δmid| por horizonte y techo con previsión perfecta por costo."""
    costs = costs_bps or ROUND_TRIPS_BPS
    t = np.asarray(t_ms, dtype=np.int64)
    out = {"points": int(t.size),
           "hours": round(float((t[-1] - t[0]) / 3.6e6), 2) if t.size > 1 else 0.0,
           "costs_bps": costs, "horizons": {}}
    for h in horizons_s:
        d = mid_moves_bps(t, mid, int(h * 1000))
        if not d.size:
            out["horizons"][str(h)] = {"n": 0}
            continue
        row = {"n": int(d.size), "mean": round(float(d.mean()), 3)}
        row.update({f"p{q}": round(float(np.percentile(d, q)), 3) for q in (50, 90, 95, 99)})
        for name, c in costs.items():
            row[f"frac_gt_{name}"] = round(float((d > c).mean()), 5)
            row[f"ceiling_{name}"] = round(float(np.maximum(d - c, 0).mean()), 4)
        out["horizons"][str(h)] = row
    return out
