"""Síntesis v1: agregación ponderada de sesgos con penalización por desacuerdo (funciones puras)."""

from __future__ import annotations

import math
from collections.abc import Sequence

from eim.core import AgentReport, Synthesis
from eim.synthesis.params import SynthesisParams


def _name(agent_id: str) -> str:
    return agent_id.replace("_", " ")


def _weight(agent_id: str, regime: str | None, p: SynthesisParams) -> float:
    w = p.weights.get(agent_id, 1.0)
    if regime:
        w *= p.regime_weights.get(regime, {}).get(agent_id, 1.0)
    return w


def synthesize(
    reports: Sequence[AgentReport],
    params: SynthesisParams | None = None,
    regime: str | None = None,
    expected: Sequence[str] | None = None,
) -> Synthesis | None:
    """Combina los reportes en una tesis; `None` si ningún agente aporta (todos sin datos).

    Peso efectivo = peso base × confianza × (factor si está degradado). El sesgo es el promedio
    ponderado; el acuerdo es 1 − desviación ponderada de los sesgos. La confianza es la
    confianza media sobre TODOS los agentes esperados (los ausentes o sin datos cuentan 0),
    penalizada si agentes con convicción apuntan en direcciones opuestas.
    """
    p = params or SynthesisParams()
    votes = [r for r in reports if r.agent_id not in p.excluded]
    byid = {r.agent_id: r for r in votes}
    ids = [i for i in (expected if expected is not None else byid) if i not in p.excluded]
    missing = [i for i in ids if i not in byid]

    eff: dict[str, float] = {}
    for r in votes:
        if r.status == "no_data":
            continue
        f = p.degraded_factor if r.status == "degraded" else 1.0
        eff[r.agent_id] = _weight(r.agent_id, regime, p) * r.confidence * f
    total = sum(eff.values())
    if total <= 0:
        return None

    bias = sum(eff[i] * byid[i].bias for i in eff) / total
    var = sum(eff[i] * (byid[i].bias - bias) ** 2 for i in eff) / total
    agreement = max(0.0, 1 - math.sqrt(var))
    contributions = {i: eff[i] * byid[i].bias / total for i in eff}

    wsum = sum(_weight(i, regime, p) for i in set(ids) | set(byid)) or 1.0
    conf = sum(_weight(i, regime, p) * byid[i].confidence
               * (p.degraded_factor if byid[i].status == "degraded" else 1.0)
               for i in eff) / wsum
    up = sorted(i for i in eff if byid[i].bias >= p.conflict_bias)
    down = sorted(i for i in eff if byid[i].bias <= -p.conflict_bias)
    if up and down:
        conf *= p.disagree_penalty

    return Synthesis(
        bias=max(-1.0, min(1.0, bias)), confidence=max(0.0, min(1.0, conf)),
        agreement=min(1.0, agreement), contributions=contributions,
        thesis=_thesis(bias, conf, agreement, contributions, up, down, byid, missing, regime, p),
    )


def _thesis(bias: float, conf: float, agreement: float, contrib: dict[str, float],
            up: list[str], down: list[str], byid: dict[str, AgentReport], missing: list[str],
            regime: str | None, p: SynthesisParams) -> str:
    """Texto determinista por plantilla (sin LLM)."""
    if abs(bias) < p.neutral_band:
        d = "neutral"
    else:
        d = "alcista" if bias > 0 else "bajista"
    out = [f"Sesgo {d} ({bias:+.2f}) con confianza {conf:.0%} y acuerdo {agreement:.0%} "
           f"entre {len(contrib)} agentes."]
    lead = sorted(contrib, key=lambda i: -abs(contrib[i]))[:2]
    if lead and d != "neutral":
        out.append("Lideran: " + ", ".join(f"{_name(i)} ({contrib[i]:+.2f})" for i in lead) + ".")
    if up and down:
        out.append("Desacuerdo: " + ", ".join(map(_name, up)) + " (alcista) vs "
                   + ", ".join(map(_name, down)) + " (bajista); la confianza se penaliza.")
    deg = sorted(i for i, r in byid.items() if r.status == "degraded")
    nod = sorted(i for i, r in byid.items() if r.status == "no_data") + missing
    if deg:
        out.append("Degradados (peso reducido): " + ", ".join(map(_name, deg)) + ".")
    if nod:
        out.append("Sin aporte: " + ", ".join(map(_name, nod)) + ".")
    if regime:
        out.append(f"Régimen: {regime}.")
    return " ".join(out)


def drift_of(syn: Synthesis | None, sigma: float, p: SynthesisParams | None = None) -> float | None:
    """Deriva (log-retorno por vela) para inclinar la proyección (T17); `None` si no hay tesis."""
    if syn is None:
        return None
    return syn.bias * syn.confidence * (p or SynthesisParams()).drift_scale * sigma
