"""Modelo de saltos estadístico (*statistical jump model*) en NumPy — T166.

Descenso por coordenadas alternas: la asignación de estados se resuelve por programación dinámica
con un precio fijo `lam` por cada cambio de estado, y los centroides se recalculan como la media
de los días asignados a cada estado. Es el algoritmo de Nystrup y de Shu, Yu y Mulvey
([arXiv 2402.05272](https://arxiv.org/abs/2402.05272)); **no se copia código** de `jumpmodels`
(Apache 2.0, pero exige `scikit-learn`, que no está en el venv: ver
`PLAN/notas/T166_preregistro.md`).

A diferencia de un HMM, la persistencia no sale de una matriz de transición estimada sino del
precio de saltar: con `lam` = 0 es k-means día a día y con `lam` grande queda un solo estado.

Puro: solo numpy, sin red, sin disco y sin estado global.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def init_centroids(x: np.ndarray, k: int) -> np.ndarray:
    """Centroides iniciales deterministas: medias de los `k` tramos de igual tamaño al ordenar
    los días por su primer componente principal.

    Determinista a propósito (nada de semillas ni reinicios aleatorios): la comparación
    pre-registrada tiene que ser reproducible exactamente.
    """
    x = np.asarray(x, float)
    if len(x) < k:
        raise ValueError("hacen falta al menos k filas")
    xc = x - x.mean(axis=0)
    # primer componente principal por la matriz de covarianza (d es pequeño)
    w, v = np.linalg.eigh(np.cov(xc, rowvar=False) + 1e-12 * np.eye(x.shape[1]))
    proj = xc @ v[:, int(np.argmax(w))]
    order = np.argsort(proj)
    return np.array([x[chunk].mean(axis=0) for chunk in np.array_split(order, k)])


def sq_dist(x: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """Matriz n × k de distancias euclídeas al cuadrado."""
    d = np.asarray(x, float)[:, None, :] - np.asarray(centroids, float)[None, :, :]
    return np.einsum("nkd,nkd->nk", d, d)


def assign_dp(cost: np.ndarray, lam: float) -> np.ndarray:
    """Secuencia de estados que minimiza Σ cost[t, s_t] + lam · Σ 1[s_t ≠ s_{t−1}] (Viterbi).

    `cost` es n × k (típicamente `sq_dist`). Con `lam` = 0 es el argmin por fila.
    """
    cost = np.asarray(cost, float)
    n, k = cost.shape
    f = cost[0].copy()
    back = np.zeros((n, k), dtype=np.int16)
    for t in range(1, n):
        best = int(np.argmin(f))
        stay = f                                  # quedarse en el mismo estado: sin penalización
        move = f[best] + lam                      # venir del mejor estado anterior: con salto
        from_stay = stay <= move
        back[t] = np.where(from_stay, np.arange(k), best)
        f = cost[t] + np.where(from_stay, stay, move)
    out = np.zeros(n, dtype=np.int16)
    out[-1] = int(np.argmin(f))
    for t in range(n - 1, 0, -1):
        out[t - 1] = back[t, out[t]]
    return out


@dataclass(frozen=True)
class JumpModel:
    """Centroides ajustados, el precio del salto y el valor del objetivo alcanzado."""

    centroids: np.ndarray
    lam: float
    objective: float
    iters: int
    labels: np.ndarray             # asignación dentro de la ventana de ajuste


def fit(x: np.ndarray, k: int, lam: float, max_iter: int = 50) -> JumpModel:
    """Ajusta el modelo de saltos por coordenadas alternas (asignación por DP, luego centroides).

    El objetivo no crece en ninguna de las dos mitades, así que la iteración converge; se corta
    cuando la asignación deja de cambiar o al llegar a `max_iter`.
    """
    x = np.asarray(x, float)
    c = init_centroids(x, k)
    labels = np.zeros(len(x), dtype=np.int16)
    obj = np.inf
    for it in range(1, max_iter + 1):
        cost = sq_dist(x, c)
        new = assign_dp(cost, lam)
        obj = float(cost[np.arange(len(x)), new].sum() + lam * np.sum(new[1:] != new[:-1]))
        done = bool(np.array_equal(new, labels)) and it > 1
        labels = new
        for s in range(k):
            m = labels == s
            if m.any():
                c[s] = x[m].mean(axis=0)
        if done:
            return JumpModel(c.copy(), float(lam), obj, it, labels)
    return JumpModel(c.copy(), float(lam), obj, max_iter, labels)


def assign_filtered(x: np.ndarray, model: JumpModel) -> np.ndarray:
    """Asignación **causal**: el pase hacia delante del mismo DP, sin el pase hacia atrás.

    f_d(s) = ‖x_d − c_s‖² + min(f_{d−1}(s), min_{s'} f_{d−1}(s') + lam) y s_d = argmin_s f_d(s).
    Es el filtro del modelo —la versión en línea del criterio que se ajusta—, así que la
    penalización significa lo mismo al ajustar y al evaluar. `assign_dp` sí mira los días
    siguientes y por eso solo se usa dentro del ajuste.

    `f` se recentra en cada paso: restar una constante no cambia ningún argmin posterior y evita
    que crezca sin límite.
    """
    cost = sq_dist(x, model.centroids)
    out = np.zeros(len(cost), dtype=np.int16)
    f = cost[0].copy()
    out[0] = int(np.argmin(f))
    f -= f.min()
    for t in range(1, len(cost)):
        f = cost[t] + np.minimum(f, f.min() + model.lam)
        out[t] = int(np.argmin(f))
        f -= f.min()
    return out


def scale_for(x: np.ndarray, k: int) -> float:
    """Distancia cuadrática media al centroide con lam = 0 (k-means puro): la escala de los datos.

    Sirve para fijar la penalización **en unidades de los datos** en vez de en un número absoluto
    que depende de cuántos rasgos haya y de cómo se hayan estandarizado.
    """
    m = fit(x, k, 0.0)
    return float(sq_dist(x, m.centroids)[np.arange(len(x)), m.labels].mean())


def fit_scaled(x: np.ndarray, k: int, c: float, max_iter: int = 50) -> JumpModel:
    """Ajuste con `lam` = `c` × la escala de los datos: `c` es «cuántos días de prueba cuesta
    saltar»."""
    return fit(x, k, c * scale_for(x, k), max_iter)
