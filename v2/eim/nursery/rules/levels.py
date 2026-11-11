"""Reglas nativas del agente `levels` (zonas S/R y canal). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num, nums, sign, steady

M = "metrics."
DSUP, DRES, ATR, TOUCH = M + "dist_support", M + "dist_resistance", M + "atr", \
    M + "zones[].touches"
ZLO, ZHI = M + "zones[].p_low", M + "zones[].p_high"
STATE, KIND, POS, R2, SLOPE = M + "channel.state", M + "channel.kind", M + "channel_pos", \
    M + "channel.r2", M + "channel.slope_per_bar"
EXPOSES = frozenset({DSUP, DRES, ATR, TOUCH, ZLO, ZHI, STATE, KIND, POS, R2, SLOPE})
_BROKEN = {"BROKEN_UP": 1, "BROKEN_DOWN": -1}


def _zone_touches(v: View, side: int) -> float:
    """Toques de la zona más cercana por debajo del cierre (soporte) o por encima (resistencia)."""
    lo, hi, tc = nums(v.get(ZLO)), nums(v.get(ZHI)), nums(v.get(TOUCH))
    c = v.close
    if c is None or not (len(lo) == len(hi) == len(tc)) or not tc:
        return 0.0
    if side > 0:
        cand = [(c - h, t) for h, t in zip(hi, tc, strict=True) if h <= c]
    else:
        cand = [(lw - c, t) for lw, t in zip(lo, tc, strict=True) if lw >= c]
    return min(cand)[1] if cand else 0.0


def niveles_rebote(v: View, p: dict) -> Signal:
    """A ≤ touch_atr ATR de un soporte (resistencia) con ≥ min_touches toques: largo (corto)."""
    a = num(v.get(ATR))
    if a is None or a <= 0:
        return NONE
    near = float(p["touch_atr"]) * a
    k = float(p["min_touches"])
    sides = [s for s, d in ((1, num(v.get(DSUP))), (-1, num(v.get(DRES))))
             if d is not None and 0 <= d <= near and _zone_touches(v, s) >= k]
    return Signal(enter=sides[0]) if len(sides) == 1 else NONE


def niveles_ruptura(v: View, p: dict) -> Signal:
    """El canal lleva break_bars cierres roto: entra a favor; sale si vuelve dentro."""
    n = int(p["break_bars"])
    if v.get(KIND) is None:
        return NONE
    now = _BROKEN.get(v.get(STATE), 0)
    run = now and all(_BROKEN.get(v.get(STATE, k), 0) == now for k in range(n))
    fresh = _BROKEN.get(v.get(STATE, n), 0) != now
    return Signal(enter=now if run and fresh else 0, hold=now)


def niveles_canal_extremos(v: View, p: dict) -> Signal:
    """Canal INSIDE: largo en el borde inferior (pos ≤ edge), corto en el superior.

    El objetivo es la mitad del canal, pero el reporte no publica sus bordes en `metrics`: sin
    objetivo, la plantilla `mean_target` sale por el horizonte del agente o por su SL (BACKLOG).
    """
    pos = num(v.get(POS))
    if v.get(STATE) != "INSIDE" or pos is None:
        return NONE
    e = float(p["edge"])
    return Signal(enter=1 if pos <= e else -1 if pos >= 1 - e else 0)


def niveles_canal_tendencia(v: View, p: dict) -> Signal:
    """Canal INSIDE con r² ≥ r2_min: en el signo de su pendiente; sale si el canal se rompe."""
    st, r2, sl = v.get(STATE), num(v.get(R2)), num(v.get(SLOPE))
    if st is None:
        return NONE
    if st != "INSIDE":
        return steady(0)
    ok = r2 is not None and r2 >= float(p["r2_min"])
    return Signal(enter=sign(sl) if ok else 0)


RULES = {"niveles_rebote": niveles_rebote, "niveles_ruptura": niveles_ruptura,
         "niveles_canal_extremos": niveles_canal_extremos,
         "niveles_canal_tendencia": niveles_canal_tendencia}
