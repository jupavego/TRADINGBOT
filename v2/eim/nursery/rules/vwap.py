"""Reglas nativas del agente `vwap` (diario, semanal y anclado). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num, sign, steady

M = "metrics."
DPOS, DVWAP, DSLOPE = M + "periods.daily.position", M + "periods.daily.vwap", \
    M + "periods.daily.slope_pct"
WPOS, WVWAP, CLOSE, ANCH = M + "periods.weekly.position", M + "periods.weekly.vwap", \
    M + "close", M + "anchored_vwap"
EXPOSES = frozenset({DPOS, DVWAP, DSLOPE, WPOS, WVWAP, CLOSE, ANCH})
_ABOVE = {"SOBRE_VWAP", "ESTIRADO_SOBRE", "EXTREMO_SOBRE"}
_BELOW = {"BAJO_VWAP", "ESTIRADO_BAJO", "EXTREMO_BAJO"}


def _side_of(pos: object) -> int:
    return 1 if pos in _ABOVE else -1 if pos in _BELOW else 0


def vwap_reversion(v: View, p: dict) -> Signal:
    """Extremo de la banda (±band_sigma σ, la del agente): entra en contra, objetivo el VWAP."""
    pos, vw = v.get(DPOS), num(v.get(DVWAP))
    side = 1 if pos == "EXTREMO_BAJO" else -1 if pos == "EXTREMO_SOBRE" else 0
    return Signal(enter=side, target=vw) if side and vw is not None else NONE


def vwap_tendencia(v: View, p: dict) -> Signal:
    """Cierre sobre el VWAP diario con pendiente > 0 (largo) o en espejo; sale al cruzarlo."""
    at = _side_of(v.get(DPOS))
    slope = num(v.get(DSLOPE))
    enter = at if at and sign(slope) == at else 0
    return Signal(enter=enter, hold=at if at else None)


def vwap_semanal(v: View, p: dict) -> Signal:
    """El cierre lleva θ-007 velas seguidas al otro lado del VWAP semanal: entra; sale al volver."""
    n = int(p["theta_007_persistence"])

    def at(back: int) -> int:
        c, w = num(v.get(CLOSE, back)), num(v.get(WVWAP, back))
        return 0 if c is None or w is None else sign(c - w)

    now = at(0)
    if not now:
        return NONE
    run = all(at(k) == now for k in range(n))
    return Signal(enter=now if run and at(n) == -now else 0, hold=now)


def vwap_anclado(v: View, p: dict) -> Signal:
    """Cierre sobre el VWAP anclado del agente (largo) o bajo él (corto); sale al cruzarlo."""
    c, a = num(v.get(CLOSE)), num(v.get(ANCH))
    return steady(sign(c - a)) if c is not None and a is not None else NONE


RULES = {"vwap_reversion": vwap_reversion, "vwap_tendencia": vwap_tendencia,
         "vwap_semanal": vwap_semanal, "vwap_anclado": vwap_anclado}
