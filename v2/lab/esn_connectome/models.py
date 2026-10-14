"""Pronosticadores de cuantiles sobre el objetivo estandarizado `y` y métricas.

Todos producen cuantiles del retorno terminal: `μ̂ + ŝ·q_τ` en unidades de σ√h, con
- `μ̂`: lectura ridge sobre las características (estados ESN, rezagos o nada),
- `ŝ`: segunda lectura ridge sobre log|residuo| (heterocedasticidad),
- `q_τ`: cuantiles empíricos del residuo estandarizado en entrenamiento.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lab.esn_connectome.esn import Ridge, ridge_predict

QUANTILES = np.array([0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95])
ALPHAS = (1e-1, 1e1, 1e3, 1e5)


@dataclass
class QuantileReadout:
    alpha: float
    beta_mu: np.ndarray | None = None
    beta_s: np.ndarray | None = None
    q: np.ndarray | None = None

    def fit(self, rg: Ridge, y: np.ndarray) -> QuantileReadout:
        self.beta_mu = rg.solve(y, self.alpha)
        e = y - rg.fitted(self.beta_mu)
        self.beta_s = rg.solve(np.log(np.abs(e) + 1e-3), self.alpha)
        s = np.exp(np.clip(rg.fitted(self.beta_s), -5, 3))
        self.q = np.quantile(e / s, QUANTILES)
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        """Cuantiles estandarizados `(n, nq)`."""
        mu = ridge_predict(x, self.beta_mu)
        s = np.exp(np.clip(ridge_predict(x, self.beta_s), -5, 3))
        return mu[:, None] + s[:, None] * self.q[None, :]


def pinball(y: np.ndarray, qs: np.ndarray) -> np.ndarray:
    """Pérdida pinball media por fila (y `(n,)`, qs `(n, nq)`)."""
    d = y[:, None] - qs
    return np.maximum(QUANTILES * d, (QUANTILES - 1) * d).mean(axis=1)


def fit_select(
    x: np.ndarray, y: np.ndarray, tr: np.ndarray, horizon: int, val_frac: float = 0.25
) -> tuple[QuantileReadout, float]:
    """Elige alpha en validación interna (final del entrenamiento, con hueco `horizon`).

    Devuelve la lectura reajustada con todo `tr` y la pérdida de validación del alpha elegido.
    """
    cut = int(len(tr) * (1 - val_frac))
    fit_idx, val_idx = tr[: cut - horizon], tr[cut::horizon]
    rg = Ridge(x[fit_idx])
    best: tuple[float, float] | None = None
    for a in ALPHAS:
        m = QuantileReadout(a).fit(rg, y[fit_idx])
        loss = float(pinball(y[val_idx], m.predict(x[val_idx])).mean())
        if best is None or loss < best[1]:
            best = (a, loss)
    assert best is not None
    return QuantileReadout(best[0]).fit(Ridge(x[tr]), y[tr]), best[1]


def cone_quantiles(y_train: np.ndarray, n: int) -> np.ndarray:
    """Cono de volatilidad: cuantiles empíricos del objetivo estandarizado (sin condicionar)."""
    return np.tile(np.quantile(y_train, QUANTILES), (n, 1))


def metrics(r: np.ndarray, qr: np.ndarray, cost: float) -> dict[str, np.ndarray]:
    """Métricas por origen en retorno log: pinball, aciertos de banda, dirección y PnL neto.

    La posición es el signo de la mediana pronosticada (0 = no opera); el PnL neto resta el
    costo de ida y vuelta solo cuando opera.
    """
    i25, i10, i50, i75, i90 = 2, 1, 3, 4, 5
    pos = np.sign(qr[:, i50])
    return {
        "pinball": pinball(r, qr),
        "in50": (r >= qr[:, i25]) & (r <= qr[:, i75]),
        "in80": (r >= qr[:, i10]) & (r <= qr[:, i90]),
        "pos": pos,
        "hit": np.where(pos != 0, np.sign(r) == pos, np.nan),
        "net": pos * r - np.abs(pos) * cost,
    }
