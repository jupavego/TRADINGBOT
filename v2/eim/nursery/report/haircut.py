"""Recorte de Harvey y Liu (2015, «Backtesting», *Journal of Portfolio Management*). Puro.

Un graduado se presenta con su **ventaja esperada en vivo tras el recorte**, no con la cifra
bruta (nota de T167 §10, rec. 19). El recorte es no lineal: el Sharpe observado da una p de una
prueba suelta; esa p se ajusta por el número de pruebas de la familia (Bonferroni, Holm y BHY,
como en el artículo) y la p ajustada se devuelve a un Sharpe. Recorte = 1 − Sharpe recortado /
Sharpe observado. Un Sharpe alto apenas se recorta; uno marginal se recorta casi entero.

La unidad es la operación (Sharpe por operación, t = SR·√n); la ventaja en vivo es la media en R
por el cociente de Sharpes (el recorte se aplica a la media con la misma σ).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import NormalDist

import numpy as np

_N = NormalDist()


def sharpe(xs: Sequence[float]) -> tuple[float, int] | None:
    x = np.asarray(xs, float)
    if len(x) < 2 or float(x.std(ddof=1)) == 0:
        return None
    return float(x.mean() / x.std(ddof=1)), int(len(x))


def p_two_sided(sr: float, n: int) -> float:
    return float(2 * (1 - _N.cdf(abs(sr) * math.sqrt(n))))


def _sr_from_p(p: float, n: int) -> float:
    if p >= 1:
        return 0.0
    return _N.inv_cdf(1 - max(p, 1e-15) / 2) / math.sqrt(n)


def adjusted(p: float, family: Sequence[float], m: int) -> dict[str, float]:
    """p ajustada de una prueba con p `p` dentro de una familia de `m` pruebas.

    `family` son las p observadas del resto (las que falten hasta `m` cuentan como p = 1, que es
    lo prudente para intentos sin datos o bajas: siguen siendo intentos).
    """
    ps = sorted([*family, p])
    ps += [1.0] * max(0, m - len(ps))
    k = ps.index(p) + 1                                   # rango de la propia prueba
    bonf = min(1.0, p * m)
    holm = min(1.0, max((m - i) * ps[i] for i in range(k)))
    c = sum(1 / i for i in range(1, m + 1))
    bhy = min(1.0, min(ps[j] * m * c / (j + 1) for j in range(k - 1, m)))
    return {"bonferroni": bonf, "holm": holm, "bhy": bhy}


def haircut(xs: Sequence[float], family_p: Sequence[float], m: int) -> dict | None:
    """Sharpe, p, p ajustadas, recorte medio y ventaja en vivo (R por operación)."""
    s = sharpe(xs)
    if s is None:
        return None
    sr, n = s
    p = p_two_sided(sr, n)
    adj = adjusted(p, family_p, m)
    cuts = {k: (1 - _sr_from_p(v, n) / sr) if sr > 0 else 1.0 for k, v in adj.items()}
    mean_cut = float(np.mean(list(cuts.values())))
    mu = float(np.mean(xs))
    return {"n": n, "mean_r": round(mu, 4), "sharpe": round(sr, 4), "p": round(p, 6),
            "p_adjusted": {k: round(v, 6) for k, v in adj.items()},
            "haircut": {k: round(v, 4) for k, v in cuts.items()},
            "haircut_mean": round(mean_cut, 4),
            "live_edge_r": round(mu * (1 - mean_cut), 4) if sr > 0 else round(min(mu, 0.0), 4),
            "tests_m": m}


def family_pvalues(series: Mapping[str, Sequence[float]], skip: str | None = None
                   ) -> list[float]:
    """p de cada prospecto con muestra (el propio excluido)."""
    out = []
    for k, xs in series.items():
        if k == skip:
            continue
        s = sharpe(xs)
        if s is not None:
            out.append(p_two_sided(*s))
    return out
