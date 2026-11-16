"""HMM gaussiano de covarianza diagonal, con Baum-Welch y filtro causal — T166.

Es el competidor «clásico» del modelo de saltos: la persistencia sale de la matriz de transición
estimada, no de un precio por saltar. Se implementa aquí porque `hmmlearn` no está en el venv y
porque la comparación pre-registrada exige los **mismos rasgos y el mismo reajuste** que
`jump.py`; con dos bibliotecas distintas eso no se puede garantizar.

Covarianza diagonal a propósito: con 4 rasgos y ventanas de unos cientos de días, una covarianza
llena se ajusta al ruido. El arranque es determinista (los centroides de `jump.init_centroids`),
así que la corrida es reproducible sin semillas.

Puro: solo numpy, sin red, sin disco y sin estado global.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eim.agents.regime.jump import init_centroids

_MIN_VAR = 1e-6
_LOG2PI = float(np.log(2 * np.pi))


@dataclass(frozen=True)
class GaussianHMM:
    """Parámetros ajustados: medias, varianzas diagonales, transición y distribución inicial."""

    means: np.ndarray              # k × d
    variances: np.ndarray          # k × d
    trans: np.ndarray              # k × k
    start: np.ndarray              # k
    loglik: float
    iters: int


def log_emissions(x: np.ndarray, means: np.ndarray, variances: np.ndarray) -> np.ndarray:
    """log p(x_t | s) de la normal diagonal, matriz n × k."""
    x = np.asarray(x, float)[:, None, :]
    v = np.maximum(np.asarray(variances, float), _MIN_VAR)[None, :, :]
    d = x - np.asarray(means, float)[None, :, :]
    return -0.5 * np.sum(_LOG2PI + np.log(v) + d * d / v, axis=2)


def _forward(logb: np.ndarray, trans: np.ndarray, start: np.ndarray
             ) -> tuple[np.ndarray, np.ndarray, float]:
    """Filtro con escalado: (posterior filtrada, factores de escala, log-verosimilitud)."""
    n, k = logb.shape
    shift = logb.max(axis=1, keepdims=True)
    b = np.exp(logb - shift)
    alpha = np.zeros((n, k))
    scale = np.zeros(n)
    a = start * b[0]
    scale[0] = a.sum() or 1.0
    alpha[0] = a / scale[0]
    for t in range(1, n):
        a = (alpha[t - 1] @ trans) * b[t]
        scale[t] = a.sum() or 1.0
        alpha[t] = a / scale[t]
    return alpha, scale, float(np.sum(np.log(scale)) + shift.sum())


def fit(x: np.ndarray, k: int, max_iter: int = 100, tol: float = 1e-4) -> GaussianHMM:
    """Baum-Welch con arranque determinista; corta cuando la log-verosimilitud deja de subir."""
    x = np.asarray(x, float)
    n, d = x.shape
    means = init_centroids(x, k)
    variances = np.tile(np.maximum(x.var(axis=0), _MIN_VAR), (k, 1))
    trans = np.full((k, k), 0.05 / max(k - 1, 1))
    np.fill_diagonal(trans, 0.95)
    start = np.full(k, 1.0 / k)
    prev, done = -np.inf, 0
    for done in range(1, max_iter + 1):  # noqa: B007 — `done` es el contador que se devuelve
        logb = log_emissions(x, means, variances)
        alpha, scale, ll = _forward(logb, trans, start)
        shift = logb.max(axis=1, keepdims=True)
        b = np.exp(logb - shift)
        beta = np.ones((n, k))
        for t in range(n - 2, -1, -1):
            beta[t] = (trans @ (b[t + 1] * beta[t + 1])) / scale[t + 1]
        gamma = alpha * beta
        gamma /= np.maximum(gamma.sum(axis=1, keepdims=True), 1e-300)
        xi = np.zeros((k, k))
        for t in range(n - 1):
            m = np.outer(alpha[t], b[t + 1] * beta[t + 1]) * trans / scale[t + 1]
            xi += m / max(m.sum(), 1e-300)
        start = gamma[0] / max(gamma[0].sum(), 1e-300)
        trans = xi / np.maximum(xi.sum(axis=1, keepdims=True), 1e-300)
        w = np.maximum(gamma.sum(axis=0), 1e-300)
        means = (gamma.T @ x) / w[:, None]
        for s in range(k):
            dev = x - means[s]
            variances[s] = np.maximum((gamma[:, s] @ (dev * dev)) / w[s], _MIN_VAR)
        if ll - prev < tol * max(1.0, abs(prev)):
            prev = ll
            break
        prev = ll
    return GaussianHMM(means, variances, trans, start, float(prev), done)


def filter_states(x: np.ndarray, model: GaussianHMM) -> np.ndarray:
    """Estado **causal** de cada día: argmax de la posterior filtrada (solo el pase hacia delante).

    No se usa Viterbi ni el suavizado hacia atrás: los dos miran días posteriores y no servirían
    para evaluar fuera de muestra.
    """
    logb = log_emissions(x, model.means, model.variances)
    alpha, _, _ = _forward(logb, model.trans, model.start)
    return np.asarray(np.argmax(alpha, axis=1), dtype=np.int16)
