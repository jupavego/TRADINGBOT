"""Comprobación del ES (T136 (4), E12): ¿las pérdidas de cola reales coinciden con el CVaR?

Un límite de CVaR mal calibrado da una falsa seguridad: el perfil cree que su peor 5 % vale
−1,35 R y de hecho vale −2 R. Acerbi y Székely (2014), «Backtesting Expected Shortfall», proponen
contrastes directos sobre el ES; aquí se usa su **Z2**, el incondicional:

    Z2 = 1 + media_i( X_i · 1{X_i < −VaR} ) / (α · ES)

con `X` el resultado por operación en R (negativo = pérdida) y `VaR`, `ES` **positivos**, los que
el modelo predijo. Si el modelo acierta, la media de la cola es −ES y Z2 ≈ 0. Z2 **negativo** = la
cola real es peor que la prevista (el ES se queda corto), que es el error que importa.

El p-valor: el artículo simula el nulo desde la distribución predictiva del modelo, que aquí no
existe —el CVaR sale de una muestra, no de un modelo paramétrico—. Se usa en su lugar un
**remuestreo por bloques de día de la muestra de la que salió la estimación**, con el mismo VaR y
el mismo ES fijos: mide si la cola del tramo evaluado es peor de lo que daría volver a muestrear la
cola de la que se estimó. Es menos exigente que el contraste del artículo y se declara como tal.

Puro: sin red y sin disco.
"""

from __future__ import annotations

import math

import numpy as np

from eim.paper.exits import stats

LEVEL = 0.95             # α = 1 − LEVEL = 5 %: la misma cola que `caps.cvar95_r` y el banco


def var_es(rs: np.ndarray, level: float = LEVEL) -> tuple[float, float]:
    """(VaR, ES) **positivos** de una muestra de R al `level`. (nan, nan) sin muestra.

    VaR = magnitud del cuantil de la cola; ES = magnitud de la media de esa cola. Es la misma
    cola que mide `caps.cvar95_r`, con el signo cambiado para que las dos cifras sean positivas.
    """
    if len(rs) < 2:
        return math.nan, math.nan
    q = float(np.quantile(rs, 1.0 - level))
    tail = rs[rs <= q]
    if not len(tail):
        return math.nan, math.nan
    return -q, -float(tail.mean())


def _tail_values(rs: np.ndarray, var: float) -> np.ndarray:
    """`X·1{X < −VaR}`: el resultado donde hay pérdida de cola y 0 en el resto."""
    return np.where(rs < -var, rs, 0.0)


def z2(rs: np.ndarray, var: float, es: float, level: float = LEVEL) -> float:
    """Z2 de Acerbi y Székely con el VaR y el ES **predichos**. nan si no se puede calcular."""
    if not len(rs) or not math.isfinite(var) or not math.isfinite(es) or es <= 0:
        return math.nan
    alpha = 1.0 - level
    return 1.0 + float(_tail_values(rs, var).mean()) / (alpha * es)


def check(fit_days: np.ndarray, fit_rs: np.ndarray, test_days: np.ndarray, test_rs: np.ndarray,
          reps: int, rng: np.random.Generator, level: float = LEVEL) -> dict:
    """Estima VaR y ES en el tramo de ajuste y los contrasta con la cola del tramo de prueba.

    Devuelve el ES estimado, el realizado, Z2 y su p unilateral (Z2 tan negativo o más). Con
    `p ≤ 0,05` el ES se queda corto y el límite de CVaR del perfil está mal calibrado; con
    `veredicto` «sin muestra» no hay nada que concluir, y se dice.
    """
    var, es = var_es(np.asarray(fit_rs, dtype=float), level)
    out = {"level": level, "n_fit": int(len(fit_rs)), "n_test": int(len(test_rs)),
           "var_fit_r": None if math.isnan(var) else -var,
           "es_fit_r": None if math.isnan(es) else -es}
    if math.isnan(es) or len(test_rs) < 2:
        return out | {"z2": None, "p": None, "verdict": "sin muestra"}
    test_rs = np.asarray(test_rs, dtype=float)
    obs = z2(test_rs, var, es, level)
    _, es_real = var_es(test_rs, level)
    # nulo: medias de la serie de cola remuestreada por días DEL AJUSTE, con el ES fijo
    alpha = 1.0 - level
    null_means = stats.day_block_means(np.asarray(fit_days, dtype=np.int64),
                                       _tail_values(np.asarray(fit_rs, dtype=float), var),
                                       reps, rng)
    null = 1.0 + null_means[np.isfinite(null_means)] / (alpha * es)
    p = float((1 + int(np.sum(null <= obs))) / (1 + len(null))) if len(null) else None
    short = p is not None and p <= 0.05
    return out | {"es_test_r": -es_real, "z2": obs, "p": p, "reps": int(len(null)),
                  "null_median": float(np.median(null)) if len(null) else None,
                  "verdict": "el ES se queda corto" if short else "el ES aguanta",
                  "es_underestimated": bool(short)}
