"""MAE de las ganadoras sin fuga ni circularidad (E5 de §8): el SL inicial de M8 y el umbral de M5.

Sweeney propone fijar el stop inicial con la distribución del MAE de las operaciones ganadoras. La
idea es buena y tiene **dos trampas** que E5 obliga a esquivar, y que son la razón de que esto viva
en su propio módulo con sus propias pruebas:

1. **Fuga entre tramos.** El cuantil de un pliegue se calcula **solo** con operaciones cerradas en
   su tramo de **ajuste**, con la purga y el embargo de T131 ya aplicados. Si se usaran las del
   tramo de prueba, el stop sabría cómo acabaron las operaciones que va a medir.
2. **Circularidad.** «Ganadora» se define con una salida de **referencia fija y pre-registrada**,
   nunca con la política que se está evaluando. Con la escalera, las ganadoras se cierran a +0,1 R
   enseguida y su MAE es diminuto: M8 heredaría stops ajustadísimos, que es exactamente el defecto
   H1 que la fase 22 intenta corregir. Medirse a sí misma haría que M8 «descubriera» que el stop
   bueno es el que ya tiene.

Y una tercera salvaguarda del proyecto: **sin muestra no se aprieta**. Por debajo de `min_trades`
operaciones ganadoras de esa estrategia@marco no hay cuantil, y la política se queda con el SL de
la idea en vez de inventar uno.

Unidad: el MAE se guarda en **σ**, no en R ni en precio, para que el cuantil de 2023 sirva en 2026.

Puro: sin red, sin disco y sin estado global.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from eim.paper.exits.bench import BenchTrade
from eim.paper.exits.walkforward import Fold, fit_trades, test_trades

MIN_TRADES = 30
QUANTILE = 0.9


@dataclass(frozen=True)
class WinnersMae:
    """Cuantil del MAE de las ganadoras, en σ, de UN tramo de ajuste."""

    fold: int
    quantile: float
    min_trades: int
    by_sid: dict[str, float]
    n_by_sid: dict[str, int]
    n_fit: int
    n_winners: int
    reference: str

    def of(self, sid: str) -> float | None:
        """Cuantil de esa estrategia@marco, o None si no llegó a la muestra mínima."""
        return self.by_sid.get(sid)

    def to_json(self) -> dict:
        return {"fold": self.fold, "quantile": self.quantile, "min_trades": self.min_trades,
                "reference": self.reference, "n_fit": self.n_fit, "n_winners": self.n_winners,
                "sids": {k: {"mae_sigma": round(v, 4), "n": self.n_by_sid[k]}
                         for k, v in sorted(self.by_sid.items())}}


def fit_fold(trades: Sequence[BenchTrade], fold: Fold,
             ratio_of: Callable[[BenchTrade], float | None], *, reference: str,
             quantile: float = QUANTILE, min_trades: int = MIN_TRADES) -> WinnersMae:
    """Cuantil por estrategia@marco con las ganadoras del tramo de AJUSTE de `fold`.

    `trades` son las operaciones de la salida de **referencia** (no de la que se evalúa).
    `ratio_of` convierte el MAE de R a σ: devuelve `riesgo en precio / σ` de esa operación, o None
    si no se puede (sin σ), y entonces la operación no cuenta.
    """
    fit = fit_trades(trades, fold)
    by_sid: dict[str, list[float]] = {}
    winners = 0
    for t in fit:
        if t.r <= 0:
            continue
        winners += 1
        ratio = ratio_of(t)
        if ratio is None or not np.isfinite(ratio) or ratio <= 0:
            continue
        by_sid.setdefault(t.sid, []).append(t.mae_r * ratio)
    out, counts = {}, {}
    for sid, xs in by_sid.items():
        counts[sid] = len(xs)
        if len(xs) >= min_trades:
            out[sid] = float(np.quantile(np.asarray(xs, dtype=float), quantile))
    return WinnersMae(fold.k, quantile, min_trades, out, counts, len(fit), winners, reference)


@dataclass(frozen=True)
class ByFold:
    """Los cuantiles de todos los pliegues, y a cuál le toca cada instante de decisión."""

    folds: tuple[Fold, ...]
    per_fold: tuple[WinnersMae, ...]

    def at(self, t: int) -> WinnersMae | None:
        """El cuantil del pliegue cuyo tramo de PRUEBA contiene `t`; None fuera de ellos."""
        for f, w in zip(self.folds, self.per_fold, strict=True):
            if f.test_from <= t < f.test_to:
                return w
        return None

    def quantile_of(self) -> Callable[[str, int], float | None]:
        """La función que piden `candidates.winners_mae_floor` y la fase de M5."""
        def of(sid: str, t: int) -> float | None:
            w = self.at(t)
            return None if w is None else w.of(sid)
        return of

    def to_json(self) -> dict:
        return {"folds": [w.to_json() for w in self.per_fold]}


def build(trades: Sequence[BenchTrade], folds: Sequence[Fold],
          ratio_of: Callable[[BenchTrade], float | None], *, reference: str,
          quantile: float = QUANTILE, min_trades: int = MIN_TRADES) -> ByFold:
    """Un cuantil por pliegue, cada uno con las ganadoras de SU tramo de ajuste."""
    per = tuple(fit_fold(trades, f, ratio_of, reference=reference, quantile=quantile,
                         min_trades=min_trades) for f in folds)
    return ByFold(tuple(folds), per)


def survival_r_of(w: WinnersMae | None, sid: str, sigma_over_risk: float | None,
                  base: float) -> float:
    """Umbral de la fase de supervivencia de M5, en R: el MAE típico de las ganadoras.

    El cuantil está en σ; la fase de M5 razona en R, así que hay que pasarlo con
    `sigma_over_risk = σ / riesgo en precio` de ESA operación. Sin cuantil o sin σ, el valor base.
    """
    if w is None or sigma_over_risk is None or not np.isfinite(sigma_over_risk):
        return base
    q = w.of(sid)
    return base if q is None else float(q * sigma_over_risk)


def leak_check(trades: Sequence[BenchTrade], fold: Fold) -> list[str]:
    """Las operaciones que alimentan el cuantil no pueden venir del tramo de prueba."""
    used = {t.id for t in fit_trades(trades, fold)}
    bad = [t.id for t in test_trades(trades, fold) if t.id in used]
    return [f"{tid}: está en el ajuste y en la prueba del pliegue {fold.k}" for tid in bad]
