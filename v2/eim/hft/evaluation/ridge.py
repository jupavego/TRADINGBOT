"""Regresión ridge mínima (T80): forma cerrada con numpy, sin dependencias nuevas. Pura.

Sirve para la pregunta (b) de la prueba de techo: ¿las variables juntas predicen mejor que la
mejor por separado? Se estandariza con la media y la desviación del ENTRENAMIENTO (nunca de la
prueba) y la penalización se elige con un tramo interno del propio entrenamiento, así que los
días de prueba no tocan ni un parámetro.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ALPHAS = (1.0, 10.0, 100.0, 1_000.0, 10_000.0)
INNER_FRAC = 0.25            # cola del entrenamiento que elige la penalización


@dataclass(frozen=True)
class Ridge:
    center: np.ndarray
    scale: np.ndarray
    w: np.ndarray
    b: float
    alpha: float

    def predict(self, x: np.ndarray) -> np.ndarray:
        z = (np.asarray(x, float) - self.center) / self.scale
        return z @ self.w + self.b


def fit(x: np.ndarray, y: np.ndarray, alpha: float) -> Ridge:
    """Ajuste con penalización fija (el término constante no se penaliza)."""
    a = np.asarray(x, float)
    b = np.asarray(y, float)
    center = a.mean(axis=0)
    scale = np.where(a.std(axis=0) > 1e-12, a.std(axis=0), 1.0)
    z = (a - center) / scale
    k = z.shape[1]
    gram = z.T @ z + alpha * np.eye(k)
    w = np.linalg.solve(gram, z.T @ (b - b.mean()))
    return Ridge(center, scale, w, float(b.mean()), float(alpha))


def fit_cv(x: np.ndarray, y: np.ndarray, alphas=ALPHAS,
           inner_frac: float = INNER_FRAC) -> Ridge:
    """Elige la penalización con la cola del entrenamiento y reajusta con todo él."""
    a, b = np.asarray(x, float), np.asarray(y, float)
    n = a.shape[0]
    cut = int(n * (1 - inner_frac))
    if cut < 10 or n - cut < 10:
        return fit(a, b, alphas[len(alphas) // 2])
    best, best_mse = alphas[0], np.inf
    for al in alphas:
        m = fit(a[:cut], b[:cut], al)
        mse = float(np.mean((m.predict(a[cut:]) - b[cut:]) ** 2))
        if mse < best_mse:
            best, best_mse = al, mse
    return fit(a, b, best)
