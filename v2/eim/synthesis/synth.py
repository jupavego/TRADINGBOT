"""Síntesis v1: agregación ponderada de sesgos con penalización por desacuerdo (funciones puras).

T44: los agentes no direccionales (`NON_DIRECTIONAL`) nunca votan; el calendario solo reduce
la confianza en ventana de evento; los agentes nuevos pesan menos si un existente con el que
están correlacionados ya vota en esa vela (sin doble conteo).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from eim.core import AgentReport, Synthesis
from eim.synthesis.evidence import Evidence, effective_votes, mean_rho
from eim.synthesis.params import NON_DIRECTIONAL, EvidenceParams, SynthesisParams


def _name(agent_id: str) -> str:
    return agent_id.replace("_", " ")


def _weight(agent_id: str, regime: str | None, p: SynthesisParams) -> float:
    w = p.weights.get(agent_id, 1.0)
    if regime:
        w *= p.regime_weights.get(regime, {}).get(agent_id, 1.0)
    return w


def _corr_factor(agent_id: str, voting: set[str], p: SynthesisParams) -> tuple[float, str]:
    """Factor (≤ 1) por correlación con agentes que ya votan, y con cuál (el más correlado)."""
    rho = {j: r for j, r in p.correlation.get(agent_id, {}).items() if j in voting and r > 0}
    if not rho:
        return 1.0, ""
    top = max(rho, key=rho.__getitem__)
    return max(0.0, 1 - p.corr_penalty * rho[top]), top


def event_factor(reports: Sequence[AgentReport], p: SynthesisParams) -> tuple[float, str]:
    """Factor de confianza por ventana de evento del calendario y su motivo (1.0 si no hay)."""
    cal = next((r for r in reports if r.agent_id == "calendar" and r.status != "no_data"), None)
    if cal is None:
        return 1.0, ""
    m = cal.metrics
    if m.get("blackout"):
        return p.blackout_conf, str(m.get("blackout_reason") or "ventana de evento")
    if m.get("window"):
        ev = m.get("window_event") or {}
        return p.event_conf, f"ventana {m['window']}-evento: {ev.get('name', '')}".strip()
    return 1.0, ""


def synthesize(
    reports: Sequence[AgentReport],
    params: SynthesisParams | None = None,
    regime: str | None = None,
    expected: Sequence[str] | None = None,
    evidence: Evidence | None = None,
    evidence_params: EvidenceParams | None = None,
) -> Synthesis | None:
    """Combina los reportes en una tesis; `None` si ningún agente aporta (todos sin datos).

    Peso efectivo = peso base × confianza × (factor si está degradado), con el peso base
    reducido por correlación (T44). El sesgo es el promedio ponderado; el acuerdo es
    1 − desviación ponderada de los sesgos. La confianza es la confianza media sobre TODOS los
    agentes esperados (los ausentes o sin datos cuentan 0), penalizada si agentes con
    convicción apuntan en direcciones opuestas y dentro de una ventana de evento.
    Un agente con peso base 0 no vota (queda a la vista en la UI, pero no mueve nada).

    Con `evidence` (T150, lo que publica el panel, `method="v2"`): el agente sin cobertura en la
    ventana en vivo no vota ni cuenta en el denominador, y la confianza se multiplica por
    (votos efectivos / votantes) ** `corr_exponent` (factor «correlacion»). Sin `evidence` el
    resultado es el de v1, bit a bit (bróker simulado, plan y estrategias de T49).
    """
    if params is None:
        from eim.synthesis.squad import default_params  # evita el ciclo params ← squad
        params = default_params()
    p = params
    skip = p.excluded | NON_DIRECTIONAL
    # T60: el escuadrón sin votantes (en esta vela o este símbolo) no pesa ni baja la confianza.
    squad = next((r for r in reports if r.agent_id == "bots"), None)
    if squad is not None and not squad.metrics.get("voters"):
        skip = skip | {"bots"}
    ep = evidence_params or EvidenceParams()
    present = {r.agent_id for r in reports} | set(expected or ())
    informative = (set(ep.informative) & present) - skip if evidence is not None else set()
    skip = skip | informative
    blocked = ({a for a, c in evidence.coverage.items() if not c.votes} - skip
               if evidence is not None else set())
    skip = skip | blocked
    votes = [r for r in reports if r.agent_id not in skip]
    byid = {r.agent_id: r for r in votes}
    ids = [i for i in (expected if expected is not None else byid) if i not in skip]
    voting = {i for i, r in byid.items() if r.status != "no_data"}

    base: dict[str, float] = {}
    corr: dict[str, str] = {}
    for i in set(ids) | set(byid):
        # v2 mide la ρ vigente (factor «correlacion»); la tabla fija de T44 sería contarla dos veces
        f, top = _corr_factor(i, voting, p) if evidence is None else (1.0, "")
        base[i] = _weight(i, regime, p) * f
        if top and base[i] > 0:
            corr[i] = top
    missing = [i for i in ids if i not in byid and base[i] > 0]

    eff: dict[str, float] = {}
    for i in sorted(voting):
        r = byid[i]
        if base[i] <= 0:
            continue
        f = p.degraded_factor if r.status == "degraded" else 1.0
        eff[i] = base[i] * r.confidence * f
    total = sum(eff.values())
    if total <= 0:
        return None

    bias = sum(eff[i] * byid[i].bias for i in eff) / total
    var = sum(eff[i] * (byid[i].bias - bias) ** 2 for i in eff) / total
    agreement = max(0.0, 1 - math.sqrt(var))
    contributions = {i: eff[i] * byid[i].bias / total for i in eff}

    wsum = sum(base.values()) or 1.0
    conf = sum(eff[i] for i in eff) / wsum
    factors: dict[str, float] = {}
    up = sorted(i for i in eff if byid[i].bias >= p.conflict_bias)
    down = sorted(i for i in eff if byid[i].bias <= -p.conflict_bias)
    if up and down:
        factors["desacuerdo"] = p.disagree_penalty
    if p.squad_confidence and squad is not None and squad.status != "no_data":
        split = squad.metrics.get("mod_disagreement")
        if split is not None and split >= p.squad_split:
            factors["escuadron"] = p.squad_conf
    ev_f, ev_why = event_factor(reports, p)
    if ev_f < 1.0:
        factors["evento"] = ev_f
    n_eff = rho_bar = None
    if evidence is not None:
        n_eff = effective_votes(eff, evidence, ep.rho_prior)
        rho_bar = mean_rho(list(eff), evidence, ep.rho_prior)
        if len(eff) > 1 and n_eff < len(eff):
            factors["correlacion"] = (n_eff / len(eff)) ** ep.corr_exponent
    for f in factors.values():
        conf *= f

    shown = {i: byid[i] for i in byid if base[i] > 0}
    extra = ({} if evidence is None else
             _evidence_fields(evidence, ep, reports, len(eff), n_eff, rho_bar, sorted(blocked),
                              sorted(informative)))
    return Synthesis(
        bias=max(-1.0, min(1.0, bias)), confidence=max(0.0, min(1.0, conf)),
        agreement=min(1.0, agreement), contributions=contributions,
        weights={i: round(base.get(i, 0.0), 6) for i in sorted(set(base) | blocked | informative)},
        factors=factors,
        thesis=_thesis(bias, conf, agreement, contributions, up, down, shown, missing, regime,
                       p, ev_why if ev_f < 1.0 else "", ev_f, corr, extra),
        **extra,
    )


def _source_of(r: AgentReport | None) -> str:
    """Fuente declarada por el agente en su último reporte (`metrics.source[s]`)."""
    if r is None:
        return "sin reporte"
    m = r.metrics
    if isinstance(m.get("sources"), dict) and m["sources"]:
        return ", ".join(sorted({str(v) for v in m["sources"].values()}))
    if m.get("source"):
        return str(m["source"])
    return "sin fuente en esta vela (sin datos)" if r.status == "no_data" else "no declarada"


def _evidence_fields(ev: Evidence, ep: EvidenceParams, reports: Sequence[AgentReport],
                     voters: int, n_eff: float | None, rho_bar: float | None,
                     blocked: list[str], informative: list[str]) -> dict:
    """Campos v2 del `Synthesis`: cobertura por agente con su fuente y ventana, votos efectivos."""
    byid = {r.agent_id: r for r in reports}
    cov = {a: {"state": c.state, "ok": c.ok, "degraded": c.degraded, "no_data": c.no_data,
               "window_bars": c.window_bars, "bad_fraction": round(c.bad_fraction, 4),
               "votes": c.votes, "short": c.short, "reason": c.reason(ep),
               "source": _source_of(byid.get(a))}
           for a, c in sorted(ev.coverage.items())}
    return {"method": "v2", "voters": voters,
            "effective_votes": None if n_eff is None else round(n_eff, 4),
            "rho_mean": None if rho_bar is None else round(rho_bar, 4),
            "coverage": cov, "blocked": blocked, "informative": informative,
            "window": {"coverage_bars": ep.coverage_bars, "max_bad": ep.max_bad,
                       "corr_bars": ev.corr_window, "rho_prior": ep.rho_prior,
                       "measured_pairs": len(ev.measured), "from": ev.first_asof,
                       "to": ev.last_asof, "source": "reportes guardados en vivo"}}


def _thesis(bias: float, conf: float, agreement: float, contrib: dict[str, float],
            up: list[str], down: list[str], byid: dict[str, AgentReport], missing: list[str],
            regime: str | None, p: SynthesisParams, event: str = "", ev_f: float = 1.0,
            corr: dict[str, str] | None = None, extra: dict | None = None) -> str:
    """Texto determinista por plantilla (sin LLM)."""
    if abs(bias) < p.neutral_band:
        d = "neutral"
    else:
        d = "alcista" if bias > 0 else "bajista"
    if extra and extra.get("effective_votes") is not None:
        rho = extra["rho_mean"]
        out = [f"Sesgo {d} ({bias:+.2f}) con confianza {conf:.0%} y acuerdo {agreement:.0%} "
               f"entre {len(contrib)} votantes ≈ {extra['effective_votes']:.1f} votos efectivos"
               + (f" (ρ medio {rho:.2f})." if rho is not None else ".")]
    else:
        out = [f"Sesgo {d} ({bias:+.2f}) con confianza {conf:.0%} y acuerdo {agreement:.0%} "
               f"entre {len(contrib)} agentes."]
    lead = sorted(contrib, key=lambda i: -abs(contrib[i]))[:2]
    if lead and d != "neutral":
        out.append("Lideran: " + ", ".join(f"{_name(i)} ({contrib[i]:+.2f})" for i in lead) + ".")
    if up and down:
        out.append("Desacuerdo: " + ", ".join(map(_name, up)) + " (alcista) vs "
                   + ", ".join(map(_name, down)) + " (bajista); la confianza se penaliza.")
    if event:
        out.append(f"Calendario: {event}; confianza ×{ev_f:.2f}.")
    if corr:
        out.append("Peso reducido por correlación: "
                   + ", ".join(f"{_name(i)} (con {_name(j)})" for i, j in sorted(corr.items()))
                   + ".")
    deg = sorted(i for i, r in byid.items() if r.status == "degraded")
    nod = sorted(i for i, r in byid.items() if r.status == "no_data") + missing
    if deg:
        out.append("Degradados (peso reducido): " + ", ".join(map(_name, deg)) + ".")
    if nod:
        out.append("Sin aporte: " + ", ".join(map(_name, nod)) + ".")
    if extra and extra.get("blocked"):
        w = extra["window"]["coverage_bars"]
        out.append(f"Sin voto por falta de datos en las últimas {w} velas: "
                   + ", ".join(map(_name, extra["blocked"])) + ".")
    if extra and extra.get("informative"):
        out.append("Informativos, no votan: " + ", ".join(map(_name, extra["informative"])) + ".")
    if regime:
        out.append(f"Régimen: {regime}.")
    return " ".join(out)


def drift_of(syn: Synthesis | None, sigma: float, p: SynthesisParams | None = None) -> float | None:
    """Deriva (log-retorno por vela) para inclinar la proyección (T17); `None` si no hay tesis."""
    if syn is None:
        return None
    return syn.bias * syn.confidence * (p or SynthesisParams()).drift_scale * sigma
