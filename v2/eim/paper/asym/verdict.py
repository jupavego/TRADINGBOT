"""Veredictos de T187–T189: tres miradas fijas e IC por bloques de día (pre-registro v1).

Una mirada solo decide en su fecha (`prereg.checkpoints_ms`). Entre miradas las cifras se
publican como provisionales y **no se decide con ellas**: parar en una semana que salga bien es
ajustar el resultado. El primer veredicto que no sea EN CURSO queda escrito y no se revisa
(lo guarda `adoption.settle`).

Puro: sin red, sin disco y sin estado (el azar sale de una semilla fija).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from eim.paper.asym import prereg as P

RUNNING, PASS, FAIL = "EN CURSO", "PASA", "NO PASA"


def due_look(now: int) -> int | None:
    """Índice de la última mirada cuya fecha ya pasó (0, 1 o 2), o None antes de la primera."""
    idx = None
    for k, t in enumerate(P.checkpoints_ms()):
        if now >= t:
            idx = k
    return idx


def day_block_ci(pairs: Sequence[tuple[int, float]], level: float = P.LEVEL,
                 reps: int = P.REPS, seed: int = P.SEED, salt: str = "") -> tuple[float, float,
                                                                                    float]:
    """(media, inferior, superior) de las diferencias, remuestreando días enteros.

    Por días porque las operaciones de un mismo día comparten mercado: tratarlas como
    independientes estrecha el intervalo sin razón.
    """
    if not pairs:
        return 0.0, -math.inf, math.inf
    days = sorted({d for d, _ in pairs})
    sums = {d: 0.0 for d in days}
    cnts = {d: 0 for d in days}
    for d, x in pairs:
        sums[d] += x
        cnts[d] += 1
    s = np.array([sums[d] for d in days], dtype=float)
    c = np.array([cnts[d] for d in days], dtype=float)
    mean = float(s.sum() / c.sum())
    if len(days) < 2:
        return mean, -math.inf, math.inf
    rng = np.random.default_rng([seed, sum(map(ord, salt))])
    idx = rng.integers(0, len(days), size=(reps, len(days)))
    means = s[idx].sum(axis=1) / c[idx].sum(axis=1)
    a = (1.0 - level) / 2.0
    lo, hi = (float(x) for x in np.quantile(means, [a, 1.0 - a]))
    return mean, lo, hi


def judge_book(pairs: Sequence[tuple[int, float]], look: int | None, rule: str) -> dict:
    """T187b, T187c y T188: operaciones de perfil emparejadas, en R unitario."""
    n, days = len(pairs), len({d for d, _ in pairs})
    mean, lo, hi = day_block_ci(pairs, salt=rule)
    base = {"n": n, "days": days, "delta": mean, "ci": [lo, hi], "look": look}
    if look is None:
        return {**base, "state": RUNNING, "why": "aún no llega la primera mirada (2026-12-17)"}
    last = look == len(P.CHECKPOINT_DAYS) - 1
    if n < P.MIN_N_BOOK or days < P.MIN_DAYS:
        why = f"faltan mínimos: {n} de {P.MIN_N_BOOK} operaciones, {days} de {P.MIN_DAYS} días"
        return {**base, "state": FAIL if last else RUNNING,
                "why": why + ("; última mirada: se queda lo de hoy" if last else "")}
    return {**base, **_decide(mean, lo, hi, last)}


def judge_maker(pairs: Sequence[tuple[int, float]], cost_drop: float, stable: bool,
                look: int | None, rule: str) -> dict:
    """T189 por marco: el criterio de T143 (costo baja ≥ 0,04 R, IC ≥ 0 y signo estable)."""
    n = len(pairs)
    mean, lo, hi = day_block_ci(pairs, salt=rule)
    base = {"n": n, "days": len({d for d, _ in pairs}), "delta": mean, "ci": [lo, hi],
            "costo_baja_r": cost_drop, "estable": stable, "look": look}
    if look is None:
        return {**base, "state": RUNNING, "why": "aún no llega la primera mirada (2026-12-17)"}
    last = look == len(P.CHECKPOINT_DAYS) - 1
    if n < P.MIN_N_IDEAS:
        why = f"faltan mínimos: {n} de {P.MIN_N_IDEAS} ideas emparejadas"
        return {**base, "state": FAIL if last else RUNNING,
                "why": why + ("; última mirada: se queda lo de hoy" if last else "")}
    d = _decide(mean, lo, hi, last)
    if d["state"] == PASS and not (cost_drop >= P.MAKER_MIN_COST_DROP_R and stable):
        bits = []
        if cost_drop < P.MAKER_MIN_COST_DROP_R:
            bits.append(f"el costo solo baja {cost_drop:.4f} R (hace falta "
                        f"{P.MAKER_MIN_COST_DROP_R:.2f})")
        if not stable:
            bits.append("el signo cambia entre la primera y la segunda mitad")
        d = {"state": FAIL if last else RUNNING, "why": "; ".join(bits)}
    return {**base, **d}


def _decide(mean: float, lo: float, hi: float, last: bool) -> dict:
    ci = f"IC {100 * P.LEVEL:.2f} % [{lo:+.4f}, {hi:+.4f}]"
    if mean > 0 and lo > 0:
        return {"state": PASS, "why": f"Δ {mean:+.4f} R por operación, {ci}: excluye el 0"}
    if hi < 0:
        return {"state": FAIL, "why": f"Δ {mean:+.4f} R, {ci}: empeora con claridad"}
    if last:
        return {"state": FAIL, "why": f"Δ {mean:+.4f} R, {ci}: en la última mirada no excluye "
                                      "el 0; se queda lo de hoy"}
    return {"state": RUNNING, "why": f"Δ {mean:+.4f} R, {ci}: aún no excluye el 0"}
