"""Potencia a priori: cuánta historia hace falta antes de gastar un intento (T161).

Dos preguntas distintas, las dos puras y sin dependencias nuevas:

- **MinTRL** (Bailey y López de Prado, *The Sharpe Ratio Efficient Frontier*, J. of Risk 2012):
  con el Sharpe observado y sus momentos, cuántas observaciones hacen falta para que el PSR frente
  a un umbral llegue a `1 − α`. Por construcción, `psr(sr, sr0, ceil(MinTRL), …) ≥ 1 − α`.
- **n a priori** (contraste de una media): si la ventaja verdadera fuera `edge` por operación con
  dispersión `sd`, cuántas operaciones hacen falta para detectarla con nivel `α` y potencia `1 − β`.
  Sirve antes de mirar ningún resultado: `n = ((z_α + z_β)·sd / edge)²`.

Todo Sharpe es **por operación** (sin anualizar), como en `copytrading/stats.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

from eim.copytrading.stats import moments, sharpe

_N = NormalDist()


def min_track_record(sr: float, sr0: float, skew: float = 0.0, kurt: float = 3.0,
                     alpha: float = 0.05) -> float:
    """Observaciones mínimas para rechazar `SR ≤ sr0` con confianza `1 − α` (inf si sr ≤ sr0).

    `kurt` es la curtosis no en exceso (normal = 3), igual que `sharpe_se`.
    """
    if sr <= sr0:
        return math.inf
    z = _N.inv_cdf(1 - alpha)
    v = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    return 1 + max(v, 1e-12) * (z / (sr - sr0)) ** 2


def n_needed(edge: float, sd: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Operaciones para detectar una media `edge` > 0 (unilateral) con la potencia pedida."""
    if edge <= 0 or sd <= 0:
        return math.inf
    z = _N.inv_cdf(1 - alpha) + _N.inv_cdf(power)
    return (z * sd / edge) ** 2


@dataclass(frozen=True)
class PowerRow:
    """MinTRL de una serie frente a 0 y frente al costo, y lo que falta para llegar."""

    n: int
    mean: float
    sd: float
    sr: float | None
    mintrl_zero: float           # para rechazar «media ≤ 0»
    mintrl_cost: float           # para rechazar «bruto ≤ costo» (inf si el bruto no lo supera)
    n_apriori: float             # si la ventaja real fuera `target`, cuántas hacen falta

    @property
    def enough_zero(self) -> bool:
        return self.n >= self.mintrl_zero

    def to_json(self) -> dict:
        def f(x: float | None) -> float | None:
            return None if x is None or math.isinf(x) else round(x, 6)
        return {"n": self.n, "mean": f(self.mean), "sd": f(self.sd), "sr": f(self.sr),
                "mintrl_zero": f(self.mintrl_zero), "mintrl_cost": f(self.mintrl_cost),
                "n_apriori": f(self.n_apriori), "enough_zero": self.enough_zero}


def power_row(r: list[float], cost: float = 0.0, target: float | None = None,
              alpha: float = 0.05, power: float = 0.8) -> PowerRow:
    """Tabla de potencia de una serie por operación.

    `r` es el resultado por operación (neto o bruto, según quien llame); `cost` es el umbral en
    las mismas unidades (0 para el neto, el costo medio para el bruto); `target` es la ventaja que
    se quiere poder detectar (por defecto, el mismo `cost`).
    """
    m, sd, skew, kurt = moments(r)
    sr = sharpe(r)
    if sr is None or sd <= 0:
        return PowerRow(len(r), m, sd, None, math.inf, math.inf, math.inf)
    tgt = cost if target is None else target
    return PowerRow(
        n=len(r), mean=m, sd=sd, sr=sr,
        mintrl_zero=min_track_record(sr, 0.0, skew, kurt, alpha),
        mintrl_cost=min_track_record(sr, cost / sd, skew, kurt, alpha),
        n_apriori=n_needed(tgt, sd, alpha, power) if tgt > 0 else math.inf,
    )
