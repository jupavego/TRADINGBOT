"""Selector: ordena por neto ajustado por riesgo y capital y descarta lo que no llega.

Puntuación = rendimiento neto sobre capital por día de tenencia (mínimo 1 día, para que lo
instantáneo no sea infinito) × (1 − aversión · penalización de riesgo ponderada).
Descartes, con motivo: estrategia no seleccionable, pata incompleta, precio caducado, neto
bajo el margen mínimo, liquidez insuficiente.
"""

from __future__ import annotations

from eim.arbitrage.params import ArbParams
from eim.core import Opportunity
from eim.core.market import Frozen


class Ranked(Frozen):
    opportunity: Opportunity
    score: float  # pb por día ajustados por riesgo


class Rejected(Frozen):
    opportunity: Opportunity
    reason: str


class Selection(Frozen):
    selected: list[Ranked] = []
    rejected: list[Rejected] = []


def score(o: Opportunity, p: ArbParams) -> float:
    days = max(o.horizon_h / 24.0, 1.0)
    return o.net_bps / days * (1.0 - p.risk_aversion * o.risk.penalty(p.risk_weights))


def reject_reason(o: Opportunity, p: ArbParams, now: int) -> str | None:
    if o.strategy not in p.selectable:
        return "informativa: estrategia fuera del alcance seleccionable (T33)"
    if not o.executable:
        return "pata incompleta: el libro visible no cubre la cantidad"
    if o.valid_until < now:
        return "precio caducado"
    if o.net_bps < p.min_net_bps:
        return f"neto {o.net_bps:.1f} pb < mínimo {p.min_net_bps:g} pb"
    if o.risk.liquidity > p.max_liquidity_risk:
        return (f"liquidez insuficiente: consume {o.risk.liquidity:.0%} del libro visible "
                f"(máx. {p.max_liquidity_risk:.0%})")
    return None


def select(opps: list[Opportunity], p: ArbParams, now: int | None = None) -> Selection:
    """`now` = hora de decisión (por defecto, `asof` de cada oportunidad)."""
    ranked: list[Ranked] = []
    rejected: list[Rejected] = []
    for o in opps:
        why = reject_reason(o, p, o.asof if now is None else now)
        if why:
            rejected.append(Rejected(opportunity=o, reason=why))
        else:
            ranked.append(Ranked(opportunity=o, score=score(o, p)))
    ranked.sort(key=lambda r: r.score, reverse=True)
    rejected.sort(key=lambda r: r.opportunity.net_bps, reverse=True)
    return Selection(selected=ranked, rejected=rejected)
