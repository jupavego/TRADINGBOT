"""Calibraciones por simulación del pre-registro `cantera_v1` (T170). Puras y con semilla.

- **Tope de drawdown** (rec. 13): el cuantil (1 − p) del drawdown máximo de la curva realizada de
  una cuenta **con la ventaja objetivo** (+0,25 R por operación, σ supuesta), riesgo fijo del 1 %
  del saldo y el número de operaciones que se espera en el plazo. Con ese tope, un prospecto con
  esa ventaja se da de baja injustamente por drawdown con probabilidad ≤ p en toda la fase.
- **Promesas falsas esperadas** bajo la nula global (rec. 20), simuladas con el modelo de los
  gemelos: el lado real es un lado más al azar, d = R_lado − media de K gemelos (K = 200), con
  D = (R_largo − R_corto)/2 ~ N(0, σ) por operación. Se reproduce el paso por e-BH de las seis
  revisiones (con el e-valor congelado al ascender). Los demás requisitos de Promesa (beneficio,
  consistencia, hermano, marginal) solo pueden quitar ascensos: la cifra es una **cota superior**.

Lo pesado (10⁵ caminos, 10⁴ réplicas) se corre por la cola (`scripts/t170_calibrar.py`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from eim.nursery.evalue import ebh, mixture, scaled
from eim.nursery.ladder_rules import LadderRules

CHUNK = 5_000


def dd_cap(n_trades: int, edge_r: float, sigma_r: float, risk: float, p_unfair: float,
           sims: int, seed: int) -> float:
    """Tope de drawdown (% del máximo de la curva) con baja injusta ≤ `p_unfair`."""
    rng = np.random.default_rng(seed)
    out = []
    left = sims
    while left > 0:
        k = min(CHUNK, left)
        r = rng.normal(edge_r, sigma_r, size=(k, int(n_trades)))
        logeq = np.cumsum(np.log1p(np.maximum(risk * r, -0.999)), axis=1)
        logeq = np.concatenate([np.zeros((k, 1)), logeq], axis=1)
        dd = 1 - np.exp(logeq - np.maximum.accumulate(logeq, axis=1))
        out.append(dd.max(axis=1))
        left -= k
    return float(np.quantile(np.concatenate(out), 1 - p_unfair) * 100)


def null_d(rng: np.random.Generator, shape: tuple[int, ...], sigma_r: float = 1.0,
           k: int = 200) -> np.ndarray:
    """d de operaciones sin información: lado al azar frente a la media de K gemelos al azar."""
    big_d = rng.normal(0.0, sigma_r, size=shape)
    p = rng.binomial(k, 0.5, size=shape) / k
    side = rng.integers(0, 2, size=shape) * 2 - 1
    return np.where(side > 0, 2 * (1 - p) * big_d, -2 * p * big_d)


def counts_by_review(n_term: int, rules: LadderRules) -> list[int]:
    """Operaciones cerradas en cada revisión con un ritmo constante de `n_term` en la fase."""
    t_end = rules.deadline_days
    return [int(round(n_term * d / t_end)) for d in rules.reviews_days]


def false_promises(n_term: Mapping[str, int], rules: LadderRules, m: int, sims: int, seed: int,
                   sigma_r: float = 1.0) -> dict:
    """Promesas falsas por e-BH bajo la nula global: media, P(≥ 1) y cuantiles (cota superior)."""
    rng = np.random.default_rng(seed)
    ids = list(n_term)
    reviews = {i: counts_by_review(n_term[i], rules) for i in ids}
    exit_n, exit_day = rules.nursery_exit.min_trades, rules.nursery_exit.max_days
    counts = np.zeros(sims, dtype=int)
    p = rules.primary
    for s0 in range(0, sims, max(1, CHUNK // 50)):
        reps = min(max(1, CHUNK // 50), sims - s0)
        ev = {}
        for i in ids:
            n = max(reviews[i][-1], 1)
            y = scaled(null_d(rng, (reps, n), sigma_r), p.clip_r)
            path = mixture(y, p.lambdas)                    # reps × (n + 1)
            ev[i] = path[:, [min(c, n) for c in reviews[i]]]
        for r in range(reps):
            frozen: dict[str, float] = {}
            for k, day in enumerate(rules.reviews_days):
                vec = {}
                for i in ids:
                    if i in frozen:
                        vec[i] = frozen[i]
                    elif reviews[i][k] >= exit_n or day >= exit_day:
                        vec[i] = float(ev[i][r, k])
                keys = list(vec)
                for j in ebh([vec[x] for x in keys], m, rules.promise.q):
                    frozen.setdefault(keys[j], vec[keys[j]])
            counts[s0 + r] = len(frozen)
    return {"sims": sims, "seed": seed, "m": m, "members": len(ids),
            "mean": round(float(counts.mean()), 4),
            "p_at_least_one": round(float((counts >= 1).mean()), 4),
            "p95": int(np.quantile(counts, 0.95)), "max": int(counts.max()),
            "sigma_r": sigma_r, "bound": "cota superior: solo el paso por e-BH"}


def power(rules: LadderRules, m: int, sims: int, seed: int, mus=(0.10, 0.25, 0.50),
          ns=(100, 150, 250, 400, 650), sigma_r: float = 1.0) -> dict:
    """P(e-valor ≥ m/q) tras n operaciones con d ~ N(μ, σ): llegar solo a Promesa por e-BH.

    Es la exigencia de un ascenso en solitario (con más ascensos a la vez, e-BH pide menos), así
    que es la potencia mínima de la capa sensible. Datos sintéticos, nunca de mercado.
    """
    rng = np.random.default_rng(seed)
    p, thr, out = rules.primary, m / rules.promise.q, {}
    for mu in mus:
        hits = np.zeros(len(ns))
        for s0 in range(0, sims, 1000):
            k = min(1000, sims - s0)
            path = mixture(scaled(rng.normal(mu, sigma_r, (k, max(ns))), p.clip_r), p.lambdas)
            hits += np.array([(path[:, n] >= thr).sum() for n in ns])
        out[f"{mu:.2f}"] = {str(n): round(float(h / sims), 3) for n, h in zip(ns, hits,
                                                                             strict=True)}
    return {"threshold_e": thr, "sigma_r": sigma_r, "sims": sims, "seed": seed, "by_mu": out}


def caps_for(n_term: Mapping[str, int], rules: LadderRules, sims: int | None = None
             ) -> dict[str, float]:
    """Tope de drawdown de cada prospecto con su número esperado de operaciones."""
    dd = rules.drawdown
    return {i: round(dd_cap(n, dd.target_edge_r, dd.sigma_r, dd.risk_pct, dd.p_unfair,
                            sims or dd.sims, dd.seed), 2) for i, n in sorted(n_term.items())}


def expected_terms(t169_rows: Sequence[dict], members: Sequence[str], without: int
                   ) -> dict[str, int]:
    """Operaciones esperadas en la fase: las de T169 si hay historia; si no, `without`."""
    got = {r["id"]: r["verdict"]["expected_in_term"] for r in t169_rows}
    return {i: max(1, int(round(got[i]))) if i in got else without for i in members}
