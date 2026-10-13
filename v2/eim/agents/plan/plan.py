"""Construcción y ciclo de vida del plan (funciones puras)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from eim.agents.plan.params import PlanParams
from eim.core import AgentReport
from eim.synthesis import synthesize


@dataclass(frozen=True)
class Plan:
    side: int                 # +1 largo, −1 corto
    entry: float
    sl: float
    tp1: float
    tp2: float | None
    rr: float
    confidence: float
    created_i: int
    created_t: int
    status: str = "VIGENTE"   # VIGENTE | INVALIDADO | CUMPLIDO | EXPIRADO
    resolved_i: int | None = None
    tp_hit: int = 0
    revisions: int = 0

    @property
    def name(self) -> str:
        return "largo" if self.side > 0 else "corto"


def combine(reports: list[AgentReport], p: PlanParams) -> tuple[float, float]:
    """Sesgo y confianza de la dirección: la síntesis (T20) de `structure` y `levels`."""
    syn = synthesize(reports, expected=[r.agent_id for r in reports])
    if syn is None:
        return 0.0, 0.0
    return syn.bias, min(syn.confidence, p.max_confidence)


def propose(side: int, close: float, a: float, supports: list[float],
            resistances: list[float], conf: float, i: int, t: int,
            p: PlanParams) -> Plan | str:
    """Plan para `side`, o el motivo (str) de que no hay plan.

    `supports`/`resistances`: niveles estructurales (bordes de zona o de canal) bajo/sobre el
    precio. Para un largo, la invalidación es el soporte más cercano (≥ min_sl_atr) y los TP
    son las siguientes resistencias; el corto es el espejo.
    """
    inval = supports if side > 0 else resistances
    targets = resistances if side > 0 else supports

    def dist(x: float) -> float:  # >0 = x está del lado de la invalidación
        return (close - x) * side

    cands = sorted((x for x in inval if dist(x) >= p.min_sl_atr * a), key=dist)
    if not cands:
        return "sin nivel de invalidación estructural cercano"
    sl = cands[0] - side * p.sl_buffer_atr * a
    risk = (close - sl) * side
    if risk > p.max_sl_atr * a:
        return f"invalidación demasiado lejos ({risk / a:.1f} ATR)"
    tps = sorted((x for x in targets if (x - close) * side > 0), key=lambda x: (x - close) * side)
    if not tps:
        return "sin zona objetivo opuesta"
    tp1 = tps[0]
    tp2 = next((x for x in tps[1:] if abs(x - tp1) >= p.tp_min_gap_atr * a), None)
    rr = (tp1 - close) * side / risk
    if rr < p.min_rr:
        return f"R:R {rr:.2f} < {p.min_rr:.2f}"
    return Plan(side=side, entry=close, sl=sl, tp1=tp1, tp2=tp2, rr=rr,
                confidence=conf, created_i=i, created_t=t)


def advance(plan: Plan, j: int, high: float, low: float, close: float, p: PlanParams) -> Plan:
    """Aplica la vela `j` a un plan vigente: invalida (cierre más allá del SL), cumple o expira."""
    if plan.status != "VIGENTE":
        return plan
    if (close - plan.sl) * plan.side <= 0:
        return replace(plan, status="INVALIDADO", resolved_i=j)
    reach = high if plan.side > 0 else low
    if (reach - plan.tp1) * plan.side >= 0:
        hit2 = plan.tp2 is not None and (reach - plan.tp2) * plan.side >= 0
        return replace(plan, status="CUMPLIDO", resolved_i=j, tp_hit=2 if hit2 else 1)
    if j - plan.created_i >= p.expiry_bars:
        return replace(plan, status="EXPIRADO", resolved_i=j)
    return plan


def improve(plan: Plan, new: Plan, a: float, p: PlanParams) -> Plan:
    """Mejora justificada: solo se acerca el SL (nunca se aleja), si mejora ≥ improve_atr."""
    if new.side == plan.side and (new.sl - plan.sl) * plan.side >= p.improve_atr * a:
        return replace(plan, sl=new.sl, revisions=plan.revisions + 1)
    return plan
