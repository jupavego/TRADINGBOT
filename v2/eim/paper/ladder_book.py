"""Enganche del perfil PPP con el libro: viabilidad de entrada, tamaño y simulación de la escalera.

Los escalones se miden en USDT, así que la salida se simula DESPUÉS de dimensionar la posición
(el libro conoce la cantidad); la sombra de las demás estrategias (TP/BE/tiempo) no interviene.
"""

from __future__ import annotations

from dataclasses import dataclass

from eim.paper.engine import Outcome, Path
from eim.paper.ideas import Idea
from eim.paper.ladder import floor_qty, simulate_ladder
from eim.paper.params import ExecParams, ProfileParams


@dataclass(frozen=True)
class LadderSim:
    """Camino de precios y mecánica de ejecución con los que se simula la escalera."""

    path: Path
    ep: ExecParams


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
    return q, (simulate_ladder(i, sim.path, sim.ep, p.ladder, q) if q > 0 else Outcome(
        i, "RECHAZADA", "CANTIDAD"))
