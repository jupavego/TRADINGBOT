"""¿La mejor de N era suerte? Contraste SPA de Hansen y Model Confidence Set (T161).

Elegir la mejor de N reglas infla su resultado aunque ninguna tenga ventaja. Holm corrige cada
p por separado; el **SPA** (Hansen 2005, *A Test for Superior Predictive Ability*) contesta la
pregunta de la familia entera: ¿alguna supera a la base, sabiendo que se eligió la mejor? El
**MCS** (Hansen, Lunde y Nason 2011) devuelve el conjunto de reglas que no son peores que la mejor.

Las reglas operan en momentos distintos, así que se alinean **por día UTC**: R sumado de las
operaciones decididas ese día y 0 los días sin operación (no operar es la base, con pérdida 0).
El bootstrap es estacionario y su bloque medio sale de Politis-White, no de √n.

Usa `arch` (licencia NCSA, extra `stats` de `pyproject.toml`); se importa al llamar, para que el
resto de `eim.validation` no dependa de ella.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

DAY_MS = 86_400_000


def daily_matrix(series: Mapping[str, Sequence[tuple[int, float]]], start_ms: int, end_ms: int
                 ) -> tuple[list[str], np.ndarray]:
    """(nombres, matriz días × reglas) con el R sumado por día de decisión; 0 si no operó.

    Cada serie es una lista de `(t_ms, r)`. Solo cuentan los `t` dentro de `[start_ms, end_ms)`.
    """
    names = sorted(series)
    d0, d1 = start_ms // DAY_MS, max(end_ms - 1, start_ms) // DAY_MS
    out = np.zeros((int(d1 - d0 + 1), len(names)))
    for j, k in enumerate(names):
        for t, r in series[k]:
            if start_ms <= t < end_ms:
                out[int(t // DAY_MS - d0), j] += r
    return names, out


def block_length(x: np.ndarray) -> float:
    """Bloque medio del bootstrap estacionario por Politis-White (2004, con la corrección de 2009);
    con varias columnas, la mediana. Nunca menor que 1."""
    from arch.bootstrap import optimal_block_length

    x = np.asarray(x, float)
    if x.ndim == 1:
        x = x[:, None]
    vals = []
    for j in range(x.shape[1]):
        col = x[:, j]
        if np.std(col) > 0:
            vals.append(float(optimal_block_length(col)["stationary"].iloc[0]))
    return max(1.0, float(np.median(vals))) if vals else 1.0


@dataclass(frozen=True)
class SpaResult:
    """p de la familia (consistente, la que se lee; inferior y superior como cotas) y la mejor."""

    p_consistent: float
    p_lower: float
    p_upper: float
    best: str
    best_mean: float
    days: int
    block: float
    reps: int

    def to_json(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def spa_test(names: Sequence[str], gains: np.ndarray, reps: int = 2000, seed: int = 0,
             block: float | None = None) -> SpaResult:
    """SPA de «alguna regla gana más que no operar» sobre la matriz diaria de ganancias.

    `arch` trabaja con pérdidas (menor es mejor): pérdida de la regla = −ganancia; la base pierde 0.
    """
    from arch.bootstrap import SPA

    g = np.asarray(gains, float)
    if g.ndim != 2 or g.shape[1] != len(names) or g.shape[0] < 10:
        raise ValueError("hace falta una matriz días × reglas con al menos 10 días")
    b = block_length(g) if block is None else block
    spa = SPA(np.zeros(g.shape[0]), -g, block_size=max(1, int(round(b))), reps=reps,
              bootstrap="stationary", studentize=True, seed=seed)
    spa.compute()
    p = spa.pvalues
    means = g.mean(axis=0)
    j = int(np.argmax(means))
    return SpaResult(float(p["consistent"]), float(p["lower"]), float(p["upper"]),
                     names[j], float(means[j]), g.shape[0], b, reps)


def mcs(names: Sequence[str], gains: np.ndarray, size: float = 0.10, reps: int = 2000,
        seed: int = 0, block: float | None = None) -> dict[str, float]:
    """p del MCS por regla (las que tienen p ≥ `size` forman el conjunto de las no peores).

    Incluye «no operar» como una regla más con ganancia 0: si sobrevive, ninguna regla es
    distinguible de quedarse fuera.
    """
    from arch.bootstrap import MCS

    g = np.asarray(gains, float)
    full = np.column_stack([g, np.zeros(g.shape[0])])
    labels = [*names, "no_operar"]
    b = block_length(g) if block is None else block
    m = MCS(-full, size=size, reps=reps, block_size=max(1, int(round(b))), method="R",
            bootstrap="stationary", seed=seed)
    m.compute()
    pv = m.pvalues["Pvalue"]
    return {labels[int(i)]: float(pv.loc[i]) for i in pv.index}


def mcs_losses(names: Sequence[str], losses: np.ndarray, size: float = 0.10, reps: int = 2000,
               seed: int = 0, block: float | None = None) -> dict[str, float]:
    """p del MCS por modelo a partir de pérdidas directas (menor es mejor), sin base añadida.

    Para comparar pronósticos (T162); `mcs` es la versión de reglas de trading con «no operar»."""
    from arch.bootstrap import MCS

    x = np.asarray(losses, float)
    b = block_length(x) if block is None else block
    m = MCS(x, size=size, reps=reps, block_size=max(1, int(round(b))), method="R",
            bootstrap="stationary", seed=seed)
    m.compute()
    pv = m.pvalues["Pvalue"]
    return {names[int(i)]: float(pv.loc[i]) for i in pv.index}


def mcs_with_aliases(names: Sequence[str], losses: np.ndarray, size: float = 0.10,
                     reps: int = 2000, seed: int = 0, block: float | None = None
                     ) -> tuple[dict[str, float], dict[str, str]]:
    """`mcs_losses` tolerante a modelos con pérdidas **idénticas** (T166).

    Dos modelos distintos pueden dar exactamente el mismo pronóstico —p. ej. un etiquetador de
    régimen que se queda en un solo estado da el mismo que no tener régimen—. Su diferencia de
    pérdidas es cero, el MCS de `arch` divide por una varianza nula y revienta. Aquí se agrupan
    las columnas iguales, el MCS corre con un representante de cada grupo y la p se copia a sus
    alias: por definición es la misma, así que no se inventa nada.

    Devuelve (p por modelo, alias → representante).
    """
    x = np.asarray(losses, float)
    reps_of: dict[str, str] = {}
    keep: list[int] = []
    for j, name in enumerate(names):
        same = next((i for i in keep if np.array_equal(x[:, i], x[:, j])), None)
        if same is None:
            keep.append(j)
        else:
            reps_of[name] = names[same]
    pv = mcs_losses([names[j] for j in keep], x[:, keep], size, reps, seed, block)
    out = {n: pv.get(reps_of.get(n, n), float("nan")) for n in names}
    return out, reps_of


def mean_diff_test(d: np.ndarray, reps: int = 2000, seed: int = 0, block: float | None = None
                   ) -> tuple[float, float, float]:
    """(IC95 % inferior, superior, p unilateral de media < 0) de una serie de diferencias de
    pérdida por bootstrap estacionario; p con la muestra recentrada bajo H0: media ≥ 0."""
    from arch.bootstrap import StationaryBootstrap

    d = np.asarray(d, float)
    b = block_length(d) if block is None else block
    bs = StationaryBootstrap(max(1.0, b), d, seed=seed)
    means = np.array([float(np.mean(x[0][0])) for x in bs.bootstrap(reps)])
    lo, hi = np.percentile(means, [2.5, 97.5])
    centered = means - d.mean()
    p = float((1 + np.sum(centered <= d.mean())) / (1 + reps))
    return float(lo), float(hi), p

