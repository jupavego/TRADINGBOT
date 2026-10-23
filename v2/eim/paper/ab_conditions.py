"""Condiciones de mercado por día UTC para separar el A/B (T111). Descriptivas, nunca deciden nada.

Reglas fijadas ANTES de ver el resultado del A/B y sin parámetros que ajustar al histórico: los
cortes son cuantiles de TODOS los días del camino (los mismos para dentro y fuera de muestra), no
umbrales elegidos para que un escenario salga mejor. Cada operación hereda la etiqueta del día UTC
de su decisión; el día se mide con sus velas de 15 m completas (es una lectura ex post del día, no
una señal: no entra en ninguna regla de entrada ni de salida).

- Tendencia / intermedio / lateral: eficiencia direccional del día = |cierre − apertura| / suma de
  |variaciones de cierre| (Kaufman); tercio superior = tendencia, tercio inferior = lateral.
- Volatilidad alta / baja: rango del día (máximo − mínimo) / apertura, por encima o debajo de la
  mediana.
- Movimiento brusco: la mayor vela de 15 m del día (|cierre / apertura − 1|) en el decil superior.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from eim.paper.engine import Path

DAY_MS = 86_400_000
MIN_COVER = 0.9            # fracción mínima de velas de 15 m del día para etiquetarlo
TREND_Q = (1 / 3, 2 / 3)   # tercios de la eficiencia direccional
VOL_Q = 0.5                # mediana del rango diario
JUMP_Q = 0.9               # decil superior de la mayor vela de 15 m
TREND_LABELS = ("tendencia", "intermedio", "lateral")
VOL_LABELS = ("vol_alta", "vol_baja")
SHOCK = "brusco"
LABEL_NAMES = {"tendencia": "Tendencia", "intermedio": "Intermedio", "lateral": "Lateral",
               "vol_alta": "Volatilidad alta", "vol_baja": "Volatilidad baja",
               SHOCK: "Movimiento brusco", "sin_brusco": "Sin movimiento brusco"}


def day_features(path: Path) -> dict[int, tuple[float, float, float]]:
    """{día: (eficiencia, rango relativo, mayor vela)} de los días con velas suficientes."""
    if not len(path.t):
        return {}
    day = path.t // DAY_MS
    keys, start = np.unique(day, return_index=True)
    ends = np.append(start[1:], len(day))
    need = MIN_COVER * DAY_MS / path.step
    out = {}
    for d, a, b in zip(keys, start, ends, strict=True):
        if b - a < need:
            continue
        o, c = path.o[a:b], path.c[a:b]
        steps = np.abs(np.diff(np.concatenate(([o[0]], c)))).sum()
        if not (o[0] > 0 and steps > 0):
            continue
        er = abs(c[-1] - o[0]) / steps
        rng = (path.h[a:b].max() - path.l[a:b].min()) / o[0]
        jump = float(np.max(np.abs(c / np.where(o > 0, o, np.nan) - 1)))
        out[int(d)] = (float(er), float(rng), jump)
    return out


def day_labels(path: Path) -> dict[int, tuple[str, ...]]:
    """{día: etiquetas} con los cortes calculados sobre todos los días del camino."""
    f = day_features(path)
    if not f:
        return {}
    er, rng, jump = (np.array(x) for x in zip(*f.values(), strict=True))
    lo, hi = np.quantile(er, TREND_Q)
    med, top = np.quantile(rng, VOL_Q), np.quantile(jump, JUMP_Q)
    out = {}
    for d, (e, r, j) in f.items():
        trend = TREND_LABELS[0] if e >= hi else TREND_LABELS[2] if e < lo else TREND_LABELS[1]
        vol = VOL_LABELS[0] if r >= med else VOL_LABELS[1]
        out[d] = (trend, vol, SHOCK if j >= top else "sin_brusco")
    return out


def labeler(path: Path) -> Callable[[int], tuple[str, ...]]:
    """Función t (ms) → etiquetas del día UTC de ese instante («sin_dato» si el día no cuenta)."""
    lab = day_labels(path)
    return lambda t: lab.get(int(t // DAY_MS), ("sin_dato",))


def ex_ante(t: dict) -> tuple[str, ...]:
    """Régimen que el agente asignó a la idea AL DECIDIR (sí se conoce antes de entrar)."""
    return (t.get("regime") or "sin_dato",)


def by_condition(trades: Sequence[dict], label: Callable[[int], tuple[str, ...]],
                 key: Callable[[dict], tuple[str, ...]] | None = None) -> dict:
    """Operaciones cerradas por etiqueta de condición: n, neto, R medio y acierto. `key` etiqueta
    la operación entera (p. ej. `ex_ante`) en vez del día de su decisión."""
    out: dict[str, dict] = {}
    for t in trades:
        for k in (key(t) if key else label(t["t"])):
            b = out.setdefault(k, {"n": 0, "net": 0.0, "sum_r": 0.0, "n_r": 0, "wins": 0})
            b["n"] += 1
            b["net"] += t["pnl"]
            b["wins"] += int(t["pnl"] > 0)
            if t["r"] is not None:
                b["sum_r"] += t["r"]
                b["n_r"] += 1
    for b in out.values():
        b["mean_r"] = b["sum_r"] / b["n_r"] if b["n_r"] else None
        b["win_rate"] = b["wins"] / b["n"] if b["n"] else None
    return out
