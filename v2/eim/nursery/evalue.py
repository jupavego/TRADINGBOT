"""e-procesos y e-BH de la cantera (T170, `cantera_v1`). Puros.

**Hipótesis primaria de cada prospecto** (nota de T167 §3, rec. 1 y 14): H0 «E[d̃] ≤ 0», con
d̃ = recorte de d a [−B, B] y d = R de la operación − media de sus gemelos aleatorios pareados. El
recorte es parte de la hipótesis declarada, no un ajuste: sin él d no está acotada (una salida por
regla contraria puede durar todo un tramo) y no habría e-proceso por apuestas válido.

**e-proceso por apuestas** (Waudby-Smith y Ramdas 2023; Ramdas et al. 2023): con y = d̃/B ∈ [−1, 1],
cada λ fijo da la martingala de prueba Π (1 + λ·y_i), y la mezcla uniforme sobre una rejilla de λ
fijada de antemano sigue siendo un e-proceso. Bajo H0 su valor en cualquier tiempo de parada tiene
esperanza ≤ 1 (Ville), así que se puede mirar cuando se quiera sin pagar por mirar.

**e-BH** (Wang y Ramdas 2022): con m hipótesis y e-valores e_j, rechaza las k* mayores, con
k* = max{k : e_(k) ≥ m / (q·k)}. Controla la FDR ≤ q **bajo cualquier dependencia**, que es el caso
de decenas de prospectos sobre un único BTC. Las hipótesis sin e-valor (plazas de reserva vacías,
bajas) cuentan en m con e = 0.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import NormalDist

import numpy as np


def scaled(d: Sequence[float], clip_r: float) -> np.ndarray:
    """y = recorte(d, ±B) / B ∈ [−1, 1]."""
    x = np.asarray(d, float)
    return np.clip(x, -clip_r, clip_r) / clip_r


def mixture(y: np.ndarray, lambdas: Sequence[float]) -> np.ndarray:
    """Trayectoria del e-proceso mezcla, E_0 = 1, …, E_n (uno por observación más el inicial).

    `y` puede ser una matriz (semillas × observaciones): la mezcla se calcula fila a fila.
    """
    lam = np.asarray(lambdas, float)
    if lam.size == 0 or np.any(lam <= 0) or np.any(lam >= 1):
        raise ValueError("la rejilla de apuestas debe estar en (0, 1)")
    y = np.asarray(y, float)
    one = y.ndim == 1
    y2 = y[None, :] if one else y
    logs = np.cumsum(np.log1p(lam[:, None, None] * y2[None, :, :]), axis=2)
    path = np.exp(logs).mean(axis=0)
    path = np.concatenate([np.ones((path.shape[0], 1)), path], axis=1)
    return path[0] if one else path


def promise_evalue(d: Sequence[float], clip_r: float, lambdas: Sequence[float]) -> float:
    """e-valor de «d̃ > 0» con las operaciones dadas (1 sin operaciones)."""
    if len(d) == 0:
        return 1.0
    return float(mixture(scaled(d, clip_r), lambdas)[-1])


def ebh(evalues: Sequence[float], m: int, q: float) -> set[int]:
    """Índices rechazados por e-BH a nivel q con m hipótesis (len(evalues) ≤ m)."""
    e = np.asarray(evalues, float)
    if len(e) > m:
        raise ValueError(f"{len(e)} e-valores para una familia de {m}")
    if np.any(e < 0):
        raise ValueError("e-valor negativo")
    order = np.argsort(-e, kind="stable")
    k_star = 0
    for k in range(1, len(e) + 1):
        if e[order[k - 1]] >= m / (q * k):
            k_star = k
    return {int(i) for i in order[:k_star]}


def futility_bound(d: Sequence[float], clip_r: float, beta: float, looks: int) -> float | None:
    """Cota superior unilateral de E[d̃] en una revisión fija: media + z·EE, z = z(1 − β/looks).

    Bonferroni sobre las `looks` revisiones pre-registradas: la probabilidad de una baja injusta
    por futilidad (dar de baja un prospecto con E[d̃] ≥ μ_mín) en toda la fase es ≤ β, sea cual
    sea la fracción de información de cada revisión. None con menos de 2 operaciones.
    """
    x = np.clip(np.asarray(d, float), -clip_r, clip_r)
    if len(x) < 2:
        return None
    z = NormalDist().inv_cdf(1 - beta / looks)
    return float(x.mean() + z * x.std(ddof=1) / math.sqrt(len(x)))


def mean_se(d: Sequence[float], clip_r: float | None = None) -> tuple[float, float] | None:
    """(media, error estándar) de d (recortado si se da `clip_r`); None con menos de 2."""
    x = np.asarray(d, float)
    if clip_r is not None:
        x = np.clip(x, -clip_r, clip_r)
    if len(x) < 2:
        return None
    return float(x.mean()), float(x.std(ddof=1) / math.sqrt(len(x)))
