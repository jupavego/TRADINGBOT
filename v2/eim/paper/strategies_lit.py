"""Estrategias «literatura» (T54): las reglas de los libros del agente `literature` como candidatas
del bróker simulado. Preregistro: `PLAN/notas/T54_preregistro.md` (reglas, SL/TP y marcos fijos).

El acierto de la regla viene de `ctx["lit"]` (aciertos compactos que guardó el contexto de la vela
cerrada); el SL derivado del patrón sale de las velas ≤ la decisión (`Ind`). Sin acierto en el
contexto (contextos anteriores a T54) no hay idea. Llegan al panel solo si salen VALIDADAS
(T49/T50).
"""

from __future__ import annotations

from eim.paper.ideas import Draft, StrategyInfo, atr_draft, finite
from eim.paper.strategies_ind import Ind

SL_BUFFER_ATR = 0.25     # colchón más allá del extremo del patrón
RISK_MIN_ATR = 0.5       # distancia de SL válida (misma regla que `ind_supertrend`)
RISK_MAX_ATR = 3.0
TP_R = 2.0               # TP = 2 R cuando el SL sale del patrón
DEF_SL_ATR = 1.5         # SL y TP por defecto de la mesa
DEF_TP_ATR = 2.5
HOLD_H = 36              # horas de 1 h (escaladas al marco)

NISON = "Nison (2001)"
MURPHY = "Murphy (1999)"
# ficha → cita corta (la completa la resuelve `GET /v2/library/cards/{id}`)
CITE = {
    "murphy_weekly_rule": f"{MURPHY}, cap. 9, pp. 256–258",
    "murphy_rsi": f"{MURPHY}, cap. 10, pp. 281–283, 285–286",
    "nison_engulfing": f"{NISON}, cap. 4, pp. 53–54",
    "nison_hammer": f"{NISON}, cap. 4, pp. 45–46",
    "nison_shooting_star": f"{NISON}, cap. 5, pp. 84–86",
    "nison_morning_star": f"{NISON}, cap. 5, pp. 72–73",
    "nison_evening_star": f"{NISON}, cap. 5, pp. 76–77",
}


def _hit(ctx: dict, cards: tuple[str, ...]) -> list | None:
    """El acierto más fuerte de `cards` en la vela de decisión: `[ficha, dirección, fuerza]`."""
    hits = [h for h in ((ctx.get("lit") or {}).get("hits") or []) if h[0] in cards]
    return max(hits, key=lambda h: h[2]) if hits else None


def _why(h: list) -> tuple[str, ...]:
    return (f"{CITE[h[0]]}: regla {h[0]} activa (fuerza {h[2]:.2f})",
            "Apoyo bibliográfico en prueba: no es una señal validada")


def _default(h: list, ctx: dict) -> Draft | None:
    return atr_draft(int(h[1]), ctx, DEF_SL_ATR, DEF_TP_ATR, float(h[2]), _why(h), hold_h=HOLD_H,
                     key=f"{h[0]}:{ctx['t']}")


def _pattern(h: list, ctx: dict, extreme: float) -> Draft | None:
    """SL a `SL_BUFFER_ATR` más allá del extremo del patrón (el autor lo da como soporte,
    resistencia o invalidación) y TP = 2 R; si la distancia no es válida, los de la mesa."""
    side, c, a = int(h[1]), ctx.get("close"), ctx.get("atr")
    if not finite(c, a, extreme) or a <= 0 or side == 0:
        return None
    sl = extreme - side * SL_BUFFER_ATR * a
    risk = (c - sl) * side
    if not RISK_MIN_ATR * a <= risk <= RISK_MAX_ATR * a:
        return _default(h, ctx)
    return Draft(side=side, sl=sl, tp=c + side * TP_R * risk, conf=float(h[2]), entry=c,
                 hold_h=HOLD_H, key=f"{h[0]}:{ctx['t']}",
                 why=_why(h) + (f"SL en el extremo del patrón {extreme:.2f} + "
                                f"{SL_BUFFER_ATR:g} ATR · TP {TP_R:g} R",))


def _simple(*cards: str):
    """Regla sin SL propio del autor utilizable en la mesa: SL y TP por defecto."""
    def fn(ctx: dict, _x: Ind, _i: int) -> Draft | None:
        h = _hit(ctx, cards)
        return h and _default(h, ctx)
    return fn


def _tail(ctx: dict, x: Ind, i: int) -> Draft | None:
    """Martillo (largo) / estrella fugaz (corto): el extremo es el de la propia vela."""
    h = _hit(ctx, ("nison_hammer", "nison_shooting_star"))
    if not h or i < 0:
        return None
    return _pattern(h, ctx, float(x.l[i] if h[1] > 0 else x.h[i]))


def _stars(ctx: dict, x: Ind, i: int) -> Draft | None:
    """Estrella de la mañana (largo) / vespertina (corto): extremo de las tres velas."""
    h = _hit(ctx, ("nison_morning_star", "nison_evening_star"))
    if not h or i < 2:
        return None
    return _pattern(h, ctx, float(x.l[i - 2:i + 1].min() if h[1] > 0 else x.h[i - 2:i + 1].max()))


LIT: tuple[StrategyInfo, ...] = (
    StrategyInfo(
        "lit_canal_4sem", "Canal de 4 semanas (Murphy)", "literatura",
        f"{CITE['murphy_weekly_rule']}: cierre fuera del máximo/mínimo de las 4 semanas previas. "
        f"El autor sale por ruptura contraria de 1–2 semanas (no modelada): SL {DEF_SL_ATR:g} ATR, "
        f"TP {DEF_TP_ATR:g} ATR. Solo 4 h (en 1 h el agente no tiene velas para evaluarla).",
        _simple("murphy_weekly_rule"), timeframes=("4h",)),
    StrategyInfo(
        "lit_rsi_recruce", "RSI recruza 30/70 (Murphy)", "literatura",
        f"{CITE['murphy_rsi']}: el RSI(14) vuelve a cruzar 30 al alza (largo) o 70 a la baja "
        f"(corto). SL {DEF_SL_ATR:g} ATR, TP {DEF_TP_ATR:g} ATR.",
        _simple("murphy_rsi"), timeframes=("1h", "4h")),
    StrategyInfo(
        "lit_envolvente", "Envolvente (Nison)", "literatura",
        f"{CITE['nison_engulfing']}: cuerpo que envuelve al anterior de color opuesto tras una "
        f"tendencia. SL {DEF_SL_ATR:g} ATR, TP {DEF_TP_ATR:g} ATR.",
        _simple("nison_engulfing"), timeframes=("1h", "4h")),
    StrategyInfo(
        "lit_vela_cola", "Martillo y estrella fugaz (Nison)", "literatura",
        f"{CITE['nison_hammer']} y {CITE['nison_shooting_star']}: SL tras el extremo de la vela "
        f"(+ {SL_BUFFER_ATR:g} ATR), TP {TP_R:g} R.",
        _tail, timeframes=("1h", "4h")),
    StrategyInfo(
        "lit_estrella_3v", "Estrellas de 3 velas (Nison)", "literatura",
        f"{CITE['nison_morning_star']} y {CITE['nison_evening_star']}: SL tras el extremo del "
        f"patrón (+ {SL_BUFFER_ATR:g} ATR), TP {TP_R:g} R.",
        _stars, timeframes=("1h", "4h")),
)
