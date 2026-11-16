"""Hipótesis secundarias de la cantera (T170, rec. 7 y 14): temas y nativo frente a genérico.

Ninguna asciende a nadie: describen y, en la mirada final, responden preguntas de la familia.

- **R encogido por tema** (Bayes empírico, efectos aleatorios de DerSimonian-Laird): la media de d
  de cada prospecto se encoge hacia la de su tema (tendencia, reversión, derivados, consenso) con
  peso τ² / (τ² + EE²). Agrupar fortalece la evidencia (Jensen, Kelly y Pedersen).
- **Hipótesis por tema**: la media del tema (efectos aleatorios) > 0, unilateral, Holm sobre los
  temas a α = 0,10 (capa sensible, no toca dinero).
- **Nativo frente a genérico**, una por agente: media de d de sus prospectos (operaciones juntas)
  > media de d del `agente_{id}` genérico, z de Welch unilateral, Holm sobre los agentes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import NormalDist

import numpy as np

from eim.backtest.edge import holm  # la misma corrección que T49

_N = NormalDist()


def _mean_se(xs: Sequence[float]) -> tuple[float, float] | None:
    x = np.asarray(xs, float)
    if len(x) < 2:
        return None
    return float(x.mean()), float(x.std(ddof=1) / math.sqrt(len(x)))


def random_effects(est: Sequence[tuple[float, float]]) -> tuple[float, float, float] | None:
    """(media, EE, τ²) de DerSimonian-Laird con (media, EE) por prospecto."""
    rows = [(m, s) for m, s in est if s > 0]
    if not rows:
        return None
    y = np.array([m for m, _ in rows])
    w = 1 / np.array([s for _, s in rows]) ** 2
    mu_f = float((w * y).sum() / w.sum())
    q = float((w * (y - mu_f) ** 2).sum())
    c = float(w.sum() - (w ** 2).sum() / w.sum())
    tau2 = max(0.0, (q - (len(rows) - 1)) / c) if c > 0 else 0.0
    ws = 1 / (1 / w + tau2)
    mu = float((ws * y).sum() / ws.sum())
    return mu, float(math.sqrt(1 / ws.sum())), tau2


def shrink(d_by: Mapping[str, Sequence[float]], theme_of: Mapping[str, str],
           clip_r: float) -> dict[str, dict]:
    """Media de d̃ encogida hacia su tema, por prospecto (sin muestra, None)."""
    est = {k: _mean_se(np.clip(np.asarray(v, float), -clip_r, clip_r))
           for k, v in d_by.items()}
    out: dict[str, dict] = {}
    for theme in sorted(set(theme_of.values())):
        ids = [k for k, t in theme_of.items() if t == theme and est.get(k)]
        re = random_effects([est[k] for k in ids])
        for k in [k for k, t in theme_of.items() if t == theme]:
            e = est.get(k)
            if e is None or re is None:
                out[k] = {"theme": theme, "raw": None if e is None else round(e[0], 4),
                          "shrunk": None}
                continue
            mu, _, tau2 = re
            b = tau2 / (tau2 + e[1] ** 2) if tau2 + e[1] ** 2 > 0 else 0.0
            out[k] = {"theme": theme, "raw": round(e[0], 4),
                      "shrunk": round(mu + b * (e[0] - mu), 4), "weight": round(b, 3)}
    return out


def theme_tests(d_by: Mapping[str, Sequence[float]], theme_of: Mapping[str, str],
                clip_r: float, alpha: float) -> dict[str, dict]:
    """Media de cada tema > 0 (efectos aleatorios), con Holm sobre los temas."""
    themes = sorted(set(theme_of.values()))
    res, ps = {}, {}
    for th in themes:
        est = [_mean_se(np.clip(np.asarray(d_by.get(k, ()), float), -clip_r, clip_r))
               for k, t in theme_of.items() if t == th]
        re = random_effects([e for e in est if e])
        p = 1.0 if re is None or re[1] == 0 else 1 - _N.cdf(re[0] / re[1])
        res[th] = {"mean": None if re is None else round(re[0], 4),
                   "se": None if re is None else round(re[1], 4), "p": round(p, 5)}
        ps[th] = p
    for th, pa in holm(ps).items():
        res[th]["p_holm"] = round(float(pa), 5)
        res[th]["holds"] = bool(pa < alpha)
    return res


def native_vs_generic(native: Mapping[str, Sequence[float]],
                      generic: Mapping[str, Sequence[float]], alpha: float) -> dict[str, dict]:
    """Por agente: d de sus prospectos frente al de su `agente_{id}` genérico, con Holm."""
    agents = sorted(native)
    res, ps = {}, {}
    for a in agents:
        x, y = _mean_se(native[a]), _mean_se(generic.get(a, ()))
        if x is None:
            p, z = 1.0, None
        else:
            my, sy = y if y else (0.0, 0.0)
            se = math.sqrt(x[1] ** 2 + sy ** 2)
            z = (x[0] - my) / se if se > 0 else None
            p = 1.0 if z is None else 1 - _N.cdf(z)
        res[a] = {"z": None if z is None else round(z, 3), "p": round(p, 5)}
        ps[a] = p
    for a, pa in holm(ps).items():
        res[a]["p_holm"] = round(float(pa), 5)
        res[a]["native_better"] = bool(pa < alpha)
    return res
