"""Reglas nativas del agente `microstructure` (OFI y delta de la captura propia). Puras.

Solo operan con la captura completa: `incomplete_fraction` ≤ 0,3 (el mismo límite del agente).
"""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num

M = "metrics."
OFI, DELTA, RET, GAPS = M + "ofi_z", M + "delta_z", M + "price_return", M + "incomplete_fraction"
EXPOSES = frozenset({OFI, DELTA, RET, GAPS})
MAX_GAPS = 0.3


def _complete(v: View) -> bool:
    g = num(v.get(GAPS))
    return g is not None and g <= MAX_GAPS


def micro_ofi(v: View, p: dict) -> Signal:
    """OFI extremo (|z| ≥ z_ofi): a favor del flujo de órdenes."""
    z = num(v.get(OFI))
    if not _complete(v) or z is None:
        return NONE
    th = float(p["z_ofi"])
    return Signal(enter=1 if z >= th else -1 if z <= -th else 0)


def micro_absorcion(v: View, p: dict) -> Signal:
    """Precio que sube ≥ price_move con delta vendedor (z ≤ −z_delta): corto; espejo en largo."""
    r, d = num(v.get(RET)), num(v.get(DELTA))
    if not _complete(v) or r is None or d is None:
        return NONE
    pm, zd = float(p["price_move"]), float(p["z_delta"])
    return Signal(enter=-1 if r >= pm and d <= -zd else 1 if r <= -pm and d >= zd else 0)


RULES = {"micro_ofi": micro_ofi, "micro_absorcion": micro_absorcion}
