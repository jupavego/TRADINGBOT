"""Cálculos puros del agente `intermarket` (T183): impulso, tendencia y correlación diarias.

Las sesiones se alinean por fecha UTC (`t // día`): Binance abre su vela diaria a las 00:00 UTC y
Yahoo fecha la sesión a medianoche de Nueva York (04:00–05:00 UTC), que cae en la misma fecha.
La cripto cotiza todos los días; su retorno se mide entre las MISMAS fechas que el del índice
(viernes → lunes incluye el fin de semana), para no correlacionar cosas distintas.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from eim.core import Candle

DAY_MS = 86_400_000


def closes_by_day(cs: Sequence[Candle]) -> dict[int, float]:
    return {c.t // DAY_MS: c.c for c in cs if c.c > 0}


def momentum(cs: Sequence[Candle], mom: int, vol: int, sma: int, z_scale: float) -> dict | None:
    """Retorno de `mom` sesiones, su z frente a la volatilidad diaria y la tendencia; None si no
    hay sesiones suficientes."""
    cl = [c.c for c in cs if c.c > 0]
    if len(cl) < max(mom, sma) + 1 or len(cl) < vol + 1:
        return None
    rets = [math.log(b / a) for a, b in zip(cl[-vol - 1:-1], cl[-vol:], strict=True)]
    sd = statistics.pstdev(rets)
    r = math.log(cl[-1] / cl[-1 - mom])
    z = r / (sd * math.sqrt(mom)) if sd > 0 else 0.0
    ma = statistics.fmean(cl[-sma:])
    return {"ret_pct": round((math.exp(r) - 1) * 100, 3), "z": round(z, 3),
            "score": round(math.tanh(z / z_scale), 4), "above_sma": cl[-1] > ma,
            "sessions": len(cl)}


def aligned_returns(index: Sequence[Candle], crypto: dict[int, float]
                    ) -> tuple[list[float], list[float]]:
    """(retornos del índice, retornos de la cripto) entre fechas consecutivas del índice en las
    que la cripto también tiene cierre."""
    days = [d for d in sorted(closes_by_day(index)) if d in crypto]
    ic = closes_by_day(index)
    xs, ys = [], []
    for d0, d1 in zip(days, days[1:], strict=False):
        xs.append(math.log(ic[d1] / ic[d0]))
        ys.append(math.log(crypto[d1] / crypto[d0]))
    return xs, ys


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sxy / (sx * sy) if sx > 0 and sy > 0 else None


def regime(equity: float, haven: float | None, band: float) -> str:
    """Etiqueta llana del contexto: apetito por riesgo, aversión, huida a refugio o mixto."""
    if equity <= -band and haven is not None and haven >= band:
        return "huida a refugio"
    if equity >= band:
        return "apetito por riesgo"
    if equity <= -band:
        return "aversión al riesgo"
    return "mixto"
