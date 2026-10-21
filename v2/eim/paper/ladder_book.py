"""Enganche del perfil PPP con el libro: viabilidad de entrada, tamaño y simulación de la escalera.

Los escalones se miden en USDT, así que la salida se simula DESPUÉS de dimensionar la posición
(el libro conoce la cantidad); la sombra de las demás estrategias (TP/BE/tiempo) no interviene.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from eim.paper.engine import Outcome, Path
from eim.paper.feedback import Judgement, context_key, judge
from eim.paper.ideas import Idea
from eim.paper.ladder import floor_qty, simulate_ladder
from eim.paper.params import ExecParams, LadderParams, ProfileParams


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
    gross = abs(i.tp - i.entry) * qty
    cost = p.est_cost_frac * i.entry * qty
    if gross - cost < lp.first_usdt * lp.min_target_vs_first:
        return (f"objetivo estimado neto {gross - cost:+.2f} USDT < primer escalón "
                f"{lp.first_usdt:.2f} USDT: no hay recorrido razonable para activar la protección")
    return None


def open_ladder(p: ProfileParams, sim: LadderSim, i: Idea, qty: float) -> tuple[float, Outcome]:
    """Cantidad al paso del instrumento y resultado simulado de la escalera con esa cantidad."""
    assert p.ladder is not None
    q = floor_qty(qty, p.ladder)
    return q, (simulate_ladder(i, sim.path, sim.ep, p.ladder, q, sim.fine) if q > 0 else Outcome(
        i, "RECHAZADA", "CANTIDAD"))


HOUR_MS = 3_600_000


@dataclass
class LadderRisk:
    """Memoria propia de la escalera: resultados en R de SUS cierres (por estrategia@marco y por
    contexto) y freno de entradas por pérdidas seguidas o drawdown. Nunca cierra posiciones."""

    r_by_sid: dict[str, list[float]] = field(default_factory=dict)
    r_by_ctx: dict[str, list[float]] = field(default_factory=dict)
    peak: float = 0.0
    consec: int = 0
    halt_until: int = 0
    halt_reason: str = ""
    activations: list[dict] = field(default_factory=list)

    def own(self, sid: str, ctx: str, p: ProfileParams) -> tuple[Judgement, Judgement]:
        """Juicio de la estrategia y del contexto con lo que la escalera ya cerró (hasta ahora)."""
        return (judge(self.r_by_sid.get(sid, []), p.feedback),
                judge(self.r_by_ctx.get(ctx, []), p.feedback))

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
