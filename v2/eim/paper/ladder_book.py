"""Enganche del perfil PPP con el libro: viabilidad de entrada, tamaño y simulación de la escalera.

Los escalones se miden en USDT —fijos o como fracción del riesgo (◆6 de T106)—, así que la salida
se simula DESPUÉS de dimensionar la posición (el libro conoce la cantidad); la sombra de las demás
estrategias (TP/BE/tiempo) no interviene.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from eim.paper.engine import Outcome, Path
from eim.paper.feedback import Judgement, context_key, judge
from eim.paper.ideas import Idea
from eim.paper.ladder import floor_qty, simulate_ladder
from eim.paper.params import ExecParams, LadderParams, ProfileParams, spec_for


@dataclass(frozen=True)
class LadderSim:
    """Camino de precios y mecánica de ejecución con los que se simula la escalera."""

    path: Path
    ep: ExecParams
    fine: Path | None = None     # velas de 1 min para las velas de 15 m ambiguas


def viability(p: ProfileParams, i: Idea, equity: float) -> str | None:
    """Motivo si el objetivo de la idea (solo una ESTIMACIÓN, no una salida) no alcanza a cubrir
    el primer escalón con sus costos: abrir sin posibilidad razonable de activar la protección
    no es una oportunidad."""
    lp = p.ladder
    risk = abs(i.entry - i.sl)
    if lp is None or risk <= 0:
        return None
    qty = equity * p.risk_pct / risk
    first, _ = lp.steps(qty * risk)      # con basis "r", el primer escalón sale del riesgo
    gross = abs(i.tp - i.entry) * qty
    cost = p.est_cost_frac * i.entry * qty
    if gross - cost < first * lp.min_target_vs_first:
        return (f"objetivo estimado neto {gross - cost:+.2f} USDT < primer escalón "
                f"{first:.2f} USDT: no hay recorrido razonable para activar la protección")
    return None


def open_ladder(p: ProfileParams, sim: LadderSim, i: Idea, qty: float) -> tuple[float, Outcome]:
    """Cantidad al paso del instrumento y resultado simulado de la escalera con esa cantidad.

    El paso, el mínimo y el tick salen de la ficha del símbolo (T108): por debajo del mínimo
    negociable la operación se rechaza en vez de redondearse a algo que el mercado no acepta.
    """
    assert p.ladder is not None
    spec = spec_for(i.symbol)
    q = floor_qty(qty, spec.qty_step)
    return q, (simulate_ladder(i, sim.path, sim.ep, p.ladder, q, sim.fine, spec=spec)
               if q >= spec.min_qty else Outcome(i, "RECHAZADA", "CANTIDAD"))


HOUR_MS = 3_600_000


def _capped(j: Judgement, lp: LadderParams | None) -> Judgement:
    """Peso acotado a `lp.max_weight` (T109): una racha corta no infla el tamaño. El estado se
    recalcula con el peso acotado, como en `feedback._verdict`."""
    if not lp or j.weight <= lp.max_weight:
        return j
    w = lp.max_weight
    return replace(j, weight=w, state="reforzada" if w > 1.05 else "reducida" if w < 0.95
                   else "activa")


@dataclass
class LadderRisk:
    """Memoria propia de la escalera: resultados en R de SUS cierres (por estrategia@marco y por
    contexto) y freno de entradas por pérdidas seguidas o drawdown. Nunca cierra posiciones.

    Es la única fuente de aprendizaje de un perfil con escalera (T109): la sombra mide salidas con
    TP/BE/tiempo que estos perfiles ya no usan, así que su memoria empieza de cero al encenderla
    (T106 §3) y el peso queda acotado a `LadderParams.max_weight`."""

    r_by_sid: dict[str, list[float]] = field(default_factory=dict)
    r_by_ctx: dict[str, list[float]] = field(default_factory=dict)
    peak: float = 0.0
    consec: int = 0
    halt_until: int = 0
    halt_reason: str = ""
    activations: list[dict] = field(default_factory=list)

    def strategy(self, sid: str, p: ProfileParams) -> Judgement:
        """Juicio de una estrategia@marco con lo que la escalera ya cerró (hasta ahora)."""
        return _capped(judge(self.r_by_sid.get(sid, []), p.feedback), p.ladder)

    def own(self, sid: str, ctx: str, p: ProfileParams) -> tuple[Judgement, Judgement]:
        """Juicio de la estrategia y del contexto con lo que la escalera ya cerró (hasta ahora)."""
        return (self.strategy(sid, p),
                _capped(judge(self.r_by_ctx.get(ctx, []), p.feedback), p.ladder))

    def veto(self, t: int) -> str | None:
        return (f"entradas en pausa hasta {t_iso(self.halt_until)} UTC: {self.halt_reason}"
                if t < self.halt_until else None)

    def closed(self, i: Idea, r: float | None, pnl: float, equity: float, exit_t: int,
               lp: LadderParams, initial: float) -> str | None:
        """Registra un cierre; devuelve el texto del freno si este cierre lo activa."""
        if r is not None:
            self.r_by_sid.setdefault(i.sid, []).append(r)
            self.r_by_ctx.setdefault(context_key(i), []).append(r)
        self.peak = max(self.peak or initial, equity)
        self.consec = self.consec + 1 if pnl <= 0 else 0
        if not lp.brake:             # los tres perfiles conservan su propio freno (`caps`)
            return None
        dd = 1 - equity / self.peak
        why = ""
        if self.consec >= lp.max_consec_losses:
            why = f"{self.consec} pérdidas seguidas"
        elif dd >= lp.max_drawdown:
            why = f"drawdown {dd:.1%} ≥ {lp.max_drawdown:.0%} desde el máximo"
        if not why or exit_t < self.halt_until:
            return None
        self.halt_until = exit_t + int(lp.pause_hours * HOUR_MS)
        self.halt_reason = why
        self.consec, self.peak = 0, equity           # al reanudar se parte de cero
        self.activations.append({"t": exit_t, "until": self.halt_until, "reason": why})
        return why

    def to_json(self, t: int) -> dict:
        return {"halted": t < self.halt_until, "until": self.halt_until or None,
                "reason": self.halt_reason, "consecutive_losses": self.consec,
                "activations": self.activations}


def t_iso(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d %H:%M")
