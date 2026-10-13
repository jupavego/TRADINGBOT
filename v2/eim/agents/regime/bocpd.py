"""BOCPD de Adams-MacKay con modelo Normal-Gamma (predictiva t de Student) y riesgo constante.

Implementación propia y vectorizada (referencia de diseño: Kats `bocpd.py`, MIT; no se copia
código ni se instala `kats`, ver `PLAN/notas/T04_auditoria.md`). Función pura sobre arrays.
"""

from __future__ import annotations

import numpy as np
from scipy.special import gammaln


def standardize(x: np.ndarray) -> np.ndarray:
    """Centra en la mediana y escala por MAD robusto (sigma ~ 1 sin cambios)."""
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826
    return (x - med) / (mad if mad > 0 else 1.0)


def bocpd(x: np.ndarray, hazard: float, max_run: int = 300, short_run: int = 5):
    """Devuelve (short_mass, map_run): P(racha <= short_run) y racha MAP en cada vela."""
    n = len(x)
    short_mass = np.zeros(n)
    map_run = np.zeros(n, dtype=int)
    probs = np.array([1.0])
    mu, kappa = np.array([0.0]), np.array([1.0])
    alpha, beta = np.array([1.0]), np.array([1.0])
    for t in range(n):
        xt = x[t]
        df = 2 * alpha
        scale2 = beta * (kappa + 1) / (alpha * kappa)
        z2 = (xt - mu) ** 2 / scale2
        logp = (gammaln((df + 1) / 2) - gammaln(df / 2) - 0.5 * np.log(np.pi * df * scale2)
                - (df + 1) / 2 * np.log1p(z2 / df))
        pred = np.exp(logp)
        growth = probs * pred * (1 - hazard)
        cp = float(np.sum(probs * pred * hazard))
        probs = np.concatenate(([cp], growth))
        total = probs.sum()
        probs = probs / total if total > 0 else np.full(len(probs), 1 / len(probs))
        mu_n = np.concatenate(([0.0], (kappa * mu + xt) / (kappa + 1)))
        beta_n = np.concatenate(([1.0], beta + kappa * (xt - mu) ** 2 / (2 * (kappa + 1))))
        kappa = np.concatenate(([1.0], kappa + 1))
        alpha = np.concatenate(([1.0], alpha + 0.5))
        mu, beta = mu_n, beta_n
        if len(probs) > max_run:  # truncado: la cola se funde en la última racha
            probs = np.concatenate((probs[:max_run - 1], [probs[max_run - 1:].sum()]))
            mu, kappa, alpha, beta = (a[:max_run] for a in (mu, kappa, alpha, beta))
        short_mass[t] = probs[: short_run + 1].sum()
        map_run[t] = int(np.argmax(probs))
    return short_mass, map_run


def change_points(map_run: np.ndarray, min_drop: int, min_gap: int) -> list[tuple[int, int]]:
    """(índice_del_cambio, índice_de_detección) cuando la racha MAP cae bruscamente."""
    out: list[tuple[int, int]] = []
    for t in range(1, len(map_run)):
        if map_run[t - 1] - map_run[t] >= min_drop:
            loc = t - int(map_run[t])
            if not out or loc - out[-1][0] >= min_gap:
                out.append((loc, t))
    return out
