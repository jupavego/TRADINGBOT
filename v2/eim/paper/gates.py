"""Estado de la puerta del marco mayor, a la vista (T212). Función pura: sin red, disco ni estado.

El lado del libro lo fija una sola puerta por marco de decisión (`ProfileParams.htf`: EMA rápida
frente a EMA lenta en el marco mayor, `HtfTrend`) y el veto `contra_tendencia`
(`eim/paper/vetoes.py`) la aplica en los cuatro perfiles (`require_htf=True`). Cuando la puerta
tarda en girar, el libro sigue vendiendo una subida y **no se ve en ningún sitio**: el mínimo del
2026-11-21 fue 55 127 y la puerta de 15 m no giró hasta 35 h después, con el precio ya +11,1 %,
mientras las de 1 h y 4 h seguían bajistas 758 y 718 h después y las aperturas posteriores al
mínimo eran 49, 45 de ellas cortas, −731,7 USDT (`PLAN/notas/T212_asimilar_el_giro.md`).

Esto **no cambia la puerta** (T139 cerró la búsqueda de entradas con P1) y **no abre ni cierra
nada** (T145 D, solo análisis): publica su dirección, cuándo giró, cuánto lleva así y a qué
distancia está del extremo reciente, que es lo que había que reconstruir a mano.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from eim.core import Candle
from eim.paper.trend import HtfTrend

H_MS = 3_600_000
WINDOW_MS = 7 * 24 * H_MS      # ventana del extremo reciente (mínimo o máximo de 7 días)
DISAGREE_H = 24.0              # horas en el mismo estado para que el desacuerdo se avise
DISAGREE_PCT = 2.0             # % recorrido en contra de la puerta que lo convierte en aviso

#: Dirección → cómo se nombra en la interfaz y qué extremo la contradice.
LABEL = {1: "alcista", -1: "bajista", 0: "sin dato"}
AGAINST = {1: ("max", "máximo"), -1: ("min", "mínimo")}


@dataclass(frozen=True)
class Gate:
    """Puerta de un marco de decisión en un instante, con su retraso medido."""

    tf: str                        # marco de decisión que gobierna (15m, 1h, 4h)
    htf: str                       # marco mayor del que sale la dirección
    fast: int
    slow: int
    dir: int                       # +1 alcista, −1 bajista, 0 sin dato (calentamiento)
    since_t: int | None = None     # cierre de la vela en que empezó este estado
    hours: float | None = None     # horas en este estado hasta `now`
    extreme_kind: str | None = None    # "min" si la puerta es bajista, "max" si es alcista
    extreme_t: int | None = None
    extreme_px: float | None = None
    price: float | None = None     # último cierre del marco mayor usado para comparar
    move_pct: float | None = None  # % del precio frente a ese extremo (signo del recorrido)
    against_pct: float | None = None   # cuánto de ese recorrido va EN CONTRA de la puerta
    hours_since_extreme: float | None = None
    enforced_by: tuple[str, ...] = ()  # perfiles con `require_htf` (a quiénes veta)
    disagrees: bool = False        # ≥ DISAGREE_H en contra de un tramo de ≥ DISAGREE_PCT

    @property
    def text(self) -> str:
        """Una línea para la interfaz y para la auditoría; sin recomendación."""
        if self.dir == 0:
            return (f"{self.tf}: sin dirección todavía (faltan velas de {self.htf} para la "
                    f"EMA de {self.slow})")
        who = f"{LABEL[self.dir]} desde hace {self.hours:.0f} h"
        if self.against_pct is None or self.extreme_kind is None:
            return f"{self.tf} ({self.htf} EMA{self.fast}/{self.slow}): {who}"
        side = AGAINST[self.dir][1]
        return (f"{self.tf} ({self.htf} EMA{self.fast}/{self.slow}): {who} · precio "
                f"{self.move_pct:+.1f} % frente al {side} de 7 d"
                + (f" · lleva {self.against_pct:.1f} % en contra" if self.disagrees else ""))

    def to_json(self) -> dict:
        return {
            "timeframe": self.tf, "htf": self.htf, "fast": self.fast, "slow": self.slow,
            "dir": self.dir, "label": LABEL[self.dir], "since_t": self.since_t,
            "hours": None if self.hours is None else round(self.hours, 1),
            "extreme_kind": self.extreme_kind, "extreme_t": self.extreme_t,
            "extreme_px": self.extreme_px, "price": self.price,
            "move_pct": None if self.move_pct is None else round(self.move_pct, 2),
            "against_pct": None if self.against_pct is None else round(self.against_pct, 2),
            "hours_since_extreme": None if self.hours_since_extreme is None
            else round(self.hours_since_extreme, 1),
            "disagrees": self.disagrees, "enforced_by": list(self.enforced_by),
            "text": self.text,
            "thresholds": {"disagree_h": DISAGREE_H, "disagree_pct": DISAGREE_PCT,
                           "window_h": WINDOW_MS / H_MS},
        }


def status(tf: str, htf: str, fast: int, slow: int, candles: Sequence[Candle], bar_ms: int,
           now: int, enforced_by: Sequence[str] = ()) -> Gate:
    """Estado de la puerta de `tf` en `now`, con las velas de su marco mayor `htf`.

    Solo mira velas CERRADAS en `now` o antes, igual que `HtfTrend`, así que no se adelanta a lo
    que la puerta sabía en ese instante.
    """
    base = Gate(tf=tf, htf=htf, fast=fast, slow=slow, dir=0, enforced_by=tuple(enforced_by))
    closed = [c for c in candles if c.t + bar_ms <= now]
    if not closed:
        return base
    trend = HtfTrend(candles, bar_ms, fast, slow)
    stamps = [c.t + bar_ms for c in closed]
    d = trend.at(stamps[-1])
    if d == 0:
        return base
    since = stamps[-1]
    for t in reversed(stamps[:-1]):
        if trend.at(t) != d:
            break
        since = t
    win = [c for c in closed if c.t + bar_ms >= now - WINDOW_MS] or closed[-1:]
    kind = AGAINST[d][0]
    ext = min(win, key=lambda c: c.l) if kind == "min" else max(win, key=lambda c: c.h)
    ext_px = ext.l if kind == "min" else ext.h
    price = closed[-1].c
    move = (price / ext_px - 1) * 100 if ext_px else 0.0
    # en contra de la puerta: el precio subiendo con la puerta bajista, o bajando con la alcista
    against = max(0.0, -d * move)
    hours = (now - since) / H_MS
    return Gate(tf=tf, htf=htf, fast=fast, slow=slow, dir=d, since_t=since, hours=hours,
                extreme_kind=kind, extreme_t=ext.t, extreme_px=ext_px, price=price,
                move_pct=move, against_pct=against,
                hours_since_extreme=(now - (ext.t + bar_ms)) / H_MS,
                enforced_by=tuple(enforced_by),
                disagrees=hours >= DISAGREE_H and against >= DISAGREE_PCT)
