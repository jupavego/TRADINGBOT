"""Tomas sintéticas en el formato propio de T213 para las pruebas de T214 (sin red).

Precios de Black-76 con una sonrisa conocida σ(k) = atm − slope·k (k = ln K/F), pasados a la
moneda base dividiendo por el subyacente, como cotiza Deribit. **No son cifras reales**: sirven
para comprobar que los rasgos recuperan lo que se puso. Lo real está en `fixtures/options/`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from eim.options import black_scholes as bs

DAY = 86_400_000
T0 = int(datetime(2026, 11, 27, 23, 1, tzinfo=UTC).timestamp() * 1000)
F = 90_000.0


def expiry_rows(days: float, atm: float, slope: float = 0.0, *, fwd: float = F,
                ks: tuple[float, ...] = tuple(x / 100 for x in range(-40, 41, 5)),
                width: float = 0.02, mark_shift: float = 0.0) -> list[dict]:
    """Filas de un vencimiento a `days` días de `T0`. `mark_shift` mueve solo la IV de la marca
    (para simular una marca que se aparta del precio medio)."""
    expiry = T0 + int(days * DAY)
    t = days / 365.0
    out = []
    for k in ks:
        strike = round(fwd * math.exp(k), 2)
        sigma = atm - slope * k
        for kind in (bs.CALL, bs.PUT):
            px = bs.black76(fwd, strike, t, 0.0, sigma, kind) / fwd
            out.append({"instrument": f"BTC-X-{strike:g}-{kind[0].upper()}", "expiry": expiry,
                        "strike": strike, "kind": kind,
                        "bid": px * (1 - width / 2), "ask": px * (1 + width / 2),
                        "mark": px, "mark_iv": (sigma + mark_shift) * 100, "underlying": fwd,
                        "rate": 0.0, "oi": 10.0, "volume": 1.0, "ts": T0})
    return out


def chain(term: tuple[tuple[float, float], ...] = ((3, 0.50), (10, 0.48), (24, 0.46),
                                                   (52, 0.45)),
          slope: float = 0.0, **kw) -> list[dict]:
    return [r for days, atm in term for r in expiry_rows(days, atm, slope, **kw)]
