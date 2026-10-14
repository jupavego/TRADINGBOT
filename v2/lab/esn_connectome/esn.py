"""Echo State Network mínimo (numpy) y construcción de los tres reservorios del laboratorio.

Variantes (mismo N, mismo radio espectral, misma lectura):
- `random`: Erdős–Rényi con la misma densidad que el subgrafo del conectoma, pesos gaussianos.
- `connectome`: topología y pesos reales (nº de sinapsis con signo por neurotransmisor).
- `topology`: topología real (misma máscara dirigida) con pesos gaussianos aleatorios.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

VARIANTS = ("random", "connectome", "topology")


def spectral_scale(w: np.ndarray, rho: float) -> np.ndarray:
    """Reescala `w` para que su radio espectral sea `rho` (si no es nilpotente)."""
    r = float(np.max(np.abs(np.linalg.eigvals(w))))
    if r < 1e-9:
        raise ValueError("matriz con radio espectral ~0: el reservorio no tiene memoria")
    return w * (rho / r)


def build_reservoir(
    variant: str, signed_syn: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Matriz sin escalar `W[post, pre]` para la variante pedida.

    `signed_syn` es la matriz del conectoma (sinapsis con signo, 0 = sin conexión).
    """
    n = signed_syn.shape[0]
    mask = signed_syn != 0
    if variant == "connectome":
        return np.sign(signed_syn) * np.log1p(np.abs(signed_syn))
    if variant == "topology":
        return np.where(mask, rng.standard_normal((n, n)), 0.0)
    if variant == "random":
        k = int(mask.sum())
        flat = np.zeros(n * n)
        flat[rng.choice(n * n, size=k, replace=False)] = rng.standard_normal(k)
        return flat.reshape(n, n)
    raise ValueError(f"variante desconocida: {variant}")


@dataclass(frozen=True)
class ESNParams:
    rho: float = 0.9  # radio espectral
    leak: float = 0.3  # tasa de fuga
    input_scale: float = 0.5
    washout: int = 200


def run_states(w: np.ndarray, u: np.ndarray, p: ESNParams, rng: np.random.Generator) -> np.ndarray:
    """Estados `(T, N)` del reservorio para entradas `u (T, d)`; causal (x_t solo ve u_≤t)."""
    n = w.shape[0]
    w = spectral_scale(w, p.rho)
    w_in = rng.uniform(-p.input_scale, p.input_scale, size=(n, u.shape[1] + 1))
    x = np.zeros(n)
    out = np.empty((len(u), n))
    for t in range(len(u)):
        pre = w @ x + w_in[:, 0] + w_in[:, 1:] @ u[t]
        x = (1 - p.leak) * x + p.leak * np.tanh(pre)
        out[t] = x
    return out


class Ridge:
    """Ridge con sesgo no penalizado; la matriz de Gram se calcula una vez por diseño `x`."""

    def __init__(self, x: np.ndarray) -> None:
        self.xa = np.hstack([np.ones((len(x), 1)), x])
        self.gram = self.xa.T @ self.xa

    def solve(self, y: np.ndarray, alpha: float) -> np.ndarray:
        reg = alpha * np.eye(self.gram.shape[0])
        reg[0, 0] = 0.0
        return np.linalg.solve(self.gram + reg, self.xa.T @ y)

    def fitted(self, beta: np.ndarray) -> np.ndarray:
        return self.xa @ beta


def ridge_predict(x: np.ndarray, beta: np.ndarray) -> np.ndarray:
    return np.hstack([np.ones((len(x), 1)), x]) @ beta
