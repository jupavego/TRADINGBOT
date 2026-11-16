"""Reglas nativas del agente `derivatives` (funding, interés abierto, largos/cortos). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num, sign

M = "metrics."
FZ, FLAST, OIZ, RET, LSZ = M + "funding_z", M + "funding_last", M + "oi_change_z", \
    M + "price_return", M + "long_short_z"
EXPOSES = frozenset({FZ, FLAST, OIZ, RET, LSZ})


def _contrarian(z: float | None, th: float) -> int:
    return 0 if z is None else -1 if z >= th else 1 if z <= -th else 0


def deriv_funding_contrario(v: View, p: dict) -> Signal:
    """Funding extremo (|z| ≥ z_high): en contra de quien paga."""
    return Signal(enter=_contrarian(num(v.get(FZ)), float(p["z_high"])))


def deriv_oi_tendencia(v: View, p: dict) -> Signal:
    """Precio que se mueve ≥ price_move con interés abierto que entra y funding sin extremos."""
    r, oi, fz = num(v.get(RET)), num(v.get(OIZ)), num(v.get(FZ))
    if r is None or oi is None or fz is None:
        return NONE
    ok = abs(r) >= float(p["price_move"]) and oi >= float(p["z_oi"]) and abs(fz) < 1.0
    return Signal(enter=sign(r) if ok else 0)


def deriv_saturacion(v: View, p: dict) -> Signal:
    """Subida con interés abierto entrando y funding caro: corto (largo en espejo)."""
    r, oi, fz = num(v.get(RET)), num(v.get(OIZ)), num(v.get(FZ))
    if r is None or oi is None or fz is None or oi < float(p["z_oi"]):
        return NONE
    th = float(p["z_high"])
    return Signal(enter=-1 if r > 0 and fz >= th else 1 if r < 0 and fz <= -th else 0)


def deriv_largos_cortos(v: View, p: dict) -> Signal:
    """Relación largos/cortos extrema (|z| ≥ z_high): en contra de la mayoría."""
    return Signal(enter=_contrarian(num(v.get(LSZ)), float(p["z_high"])))


RULES = {"deriv_funding_contrario": deriv_funding_contrario,
         "deriv_oi_tendencia": deriv_oi_tendencia, "deriv_saturacion": deriv_saturacion,
         "deriv_largos_cortos": deriv_largos_cortos}
