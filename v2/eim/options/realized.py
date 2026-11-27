"""Volatilidad realizada de una serie de cierres (T214): la otra mitad de la prima de varianza.

Pura. La usa el agente `vol_surface` con las velas del snapshot (cierre a cierre, descriptiva);
la evaluación pre-registrada de T214 usa en cambio la RV5 diaria de T162/T165.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import median

DAY_MS = 86_400_000
YEAR_MS = 365 * DAY_MS


def realized_vol(ts: Sequence[int], closes: Sequence[float], days: int, asof: int,
                 min_coverage: float = 0.9) -> float | None:
    """σ realizada anualizada (raíz de la media de los log-retornos al cuadrado, sin restar la
    media) de los cierres de los últimos `days` días antes de `asof`; `None` si no se cubre al
    menos `min_coverage` de la ventana."""
    if len(ts) < 3:
        return None
    step = median(b - a for a, b in zip(ts, ts[1:], strict=False))
    if step <= 0:
        return None
    lo = asof - days * DAY_MS
    sel = [(t, c) for t, c in zip(ts, closes, strict=True) if lo - step < t <= asof and c > 0]
    need = days * DAY_MS / step
    if len(sel) - 1 < min_coverage * need:
        return None
    r = [math.log(b / a) for (_, a), (_, b) in zip(sel, sel[1:], strict=False)]
    return math.sqrt(sum(x * x for x in r) / len(r) * (YEAR_MS / step))
