"""Combinación sin redundancia: votos → grupos → familias → sesgo condicionado por régimen.

1. Duplicados exactos (misma serie de votos) se colapsan en el primero.
2. Dentro de cada familia, los votos con correlación ≥ `cluster_corr` en la ventana se agrupan
   (componentes conexas): cada grupo vota con la media de sus miembros y pesa como uno solo.
3. Voto de familia = media ponderada de sus grupos (peso del grupo = media de pesos base).
4. Sesgo = media de familias ponderada por el régimen de cada vela (tendencia / rango / mixto).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from eim.agents.technical.params import FAMILIES, REGIMES, TechnicalParams
from eim.agents.technical.rules import Ctx


@dataclass(frozen=True)
class FamilyPlan:
    """Agrupación fija (se calcula sobre la ventana y se aplica a toda la serie)."""

    clusters: dict[str, list[list[str]]]  # familia → grupos de ids
    duplicates: dict[str, str]  # id duplicado → id que se conserva


def _same(a: np.ndarray, b: np.ndarray) -> bool:
    """Duplicado exacto: misma serie y con algún dato (dos series vacías no son duplicados)."""
    return bool(not np.isnan(a).all() and np.array_equal(a, b, equal_nan=True))


def _corr(a: np.ndarray, b: np.ndarray, min_obs: int) -> float:
    ok = ~(np.isnan(a) | np.isnan(b))
    if ok.sum() < min_obs:
        return float("nan")
    x, y = a[ok], b[ok]
    if x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _root(parent: dict[str, str], k: str) -> str:
    while parent[k] != k:
        k = parent[k]
    return k


def plan_families(votes: dict[str, np.ndarray], family_of: dict[str, str],
                  p: TechnicalParams) -> FamilyPlan:
    duplicates: dict[str, str] = {}
    kept: list[str] = []
    for rid, v in votes.items():
        same = (k for k in kept if family_of[k] == family_of[rid] and _same(votes[k], v))
        orig = next(same, None)
        if orig is None:
            kept.append(rid)
        else:
            duplicates[rid] = orig
    w = p.cluster_window
    clusters: dict[str, list[list[str]]] = {}
    for fam in FAMILIES:
        ids = [k for k in kept if family_of[k] == fam]
        parent = {k: k for k in ids}
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if _corr(votes[a][-w:], votes[b][-w:], p.cluster_min_obs) >= p.cluster_corr:
                    parent[_root(parent, b)] = _root(parent, a)
        groups: dict[str, list[str]] = {}
        for k in ids:
            groups.setdefault(_root(parent, k), []).append(k)
        if groups:
            clusters[fam] = list(groups.values())
    return FamilyPlan(clusters=clusters, duplicates=duplicates)


def _nanmean_w(cols: list[np.ndarray], weights: list[float]) -> np.ndarray:
    m = np.vstack(cols)
    w = np.asarray(weights, dtype=float)[:, None] * ~np.isnan(m)
    num = np.nansum(np.nan_to_num(m) * w, axis=0)
    den = w.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def family_votes(votes: dict[str, np.ndarray], plan: FamilyPlan,
                 p: TechnicalParams) -> dict[str, np.ndarray]:
    """Serie de voto por familia (NaN donde ningún miembro tiene dato)."""
    base = p.indicator_weights
    out: dict[str, np.ndarray] = {}
    for fam, groups in plan.clusters.items():
        gv = [_nanmean_w([votes[k] for k in g], [base.get(k, 1.0) for k in g]) for g in groups]
        gw = [float(np.mean([base.get(k, 1.0) for k in g])) for g in groups]
        out[fam] = _nanmean_w(gv, gw)
    return out


def _pct_rank(x: np.ndarray, n: int) -> np.ndarray:
    """Percentil del valor actual dentro de las últimas n observaciones (incluida)."""
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    win = sliding_window_view(x, n)
    with np.errstate(invalid="ignore"):
        out[n - 1:] = np.mean(win <= win[:, -1:], axis=1)
    out[np.isnan(x)] = np.nan
    return out


def regime_series(ctx: Ctx, p: TechnicalParams) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Índice de régimen por vela (en `REGIMES`), ADX y percentil del ancho de Bollinger."""
    adx = ctx.ind("DMI")["adx"]
    b = ctx.ind("BOLL")
    with np.errstate(invalid="ignore", divide="ignore"):
        width = (b["up"] - b["dn"]) / b["mb"]
    pct = _pct_rank(width, min(p.width_window, len(width)))
    with np.errstate(invalid="ignore"):
        trend = adx >= p.adx_trend
        rng = (adx <= p.adx_range) | ((adx < p.adx_trend) & (pct <= p.squeeze_pct))
    reg = np.where(trend, 0, np.where(rng, 1, 2))
    reg[np.isnan(adx)] = 2
    return reg, adx, pct


def bias_series(fam: dict[str, np.ndarray], regime: np.ndarray,
                p: TechnicalParams) -> np.ndarray:
    """Sesgo por vela: media de familias con los pesos del régimen de esa vela."""
    if not fam:
        return np.full(len(regime), np.nan)
    names = list(fam)
    m = np.vstack([fam[f] for f in names])
    wt = np.array([[p.family_weights[r].get(f, 1.0) for r in REGIMES] for f in names])
    w = wt[:, regime] * ~np.isnan(m)
    den = w.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.clip(np.where(den > 0, (np.nan_to_num(m) * w).sum(axis=0) / den, np.nan), -1, 1)
