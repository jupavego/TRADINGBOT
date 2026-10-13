"""Agente `elliott`: pivotes zigzag y conteo tentativo de ondas como hipótesis, no como hecho."""

from __future__ import annotations

from eim.agents.base import no_data_report
from eim.agents.elliott.compute import estimate_probability, label_waves, validate_rules, zigzag
from eim.agents.elliott.params import ElliottParams
from eim.core import AgentReport, MarketSnapshot, Overlay


class ElliottAgent:
    id = "elliott"
    version = "1.0.0"
    requires = {"candles"}

    def __init__(self, params: ElliottParams | None = None) -> None:
        self.params = params or ElliottParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        c = snapshot.candles
        if len(c) < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"velas insuficientes: {len(c)} < {p.min_bars}")
        src = snapshot.sources.get("candles", "desconocida")
        pivots = zigzag([x.t for x in c], [x.h for x in c], [x.l for x in c], p.threshold_pct)
        labeled = label_waves(pivots)
        violations = validate_rules(labeled)
        prob = estimate_probability(labeled, violations)

        warnings = ["Conteo de Elliott = heurística sujeta a re-conteo; tratar como hipótesis, "
                    "no como hecho"]
        warnings += violations
        bias = (prob["prob_up_pct"] - 50) / 50
        complete = len(labeled) == 9
        confidence = p.base_confidence if labeled else 0.0
        if violations:
            confidence /= 2
        if not complete:
            confidence *= 0.5
            warnings.append(f"conteo parcial: {len(labeled)} de 9 pivotes")
        evidence = [f"{len(pivots)} pivotes zigzag (umbral {p.threshold_pct:g}%), "
                    f"{len(labeled)} etiquetados"]
        if labeled:
            evidence.append(f"Tramo en formación: onda {labeled[-1]['wave_label']}. "
                            f"{prob['wave_note']}")

        overlays = [
            Overlay(
                id=f"elliott:pivot:{q['t']}", agent_id=self.id, kind="marker", t_from=q["t"],
                t_to=q["t"],
                geometry={"t": q["t"], "p": q["price"], "action": f"pivot_{q['type']}"},
                label=f"Onda {q['wave_label']}", confidence=confidence,
                evidence=[f"pivote zigzag {q['type']} a {q['price']:g}; fuente {src}"],
            )
            for q in labeled
        ]
        by = {q["wave_label"]: q for q in labeled}
        for key, text in (("0", "Invalidación onda 2 (inicio de onda 1)"),
                          ("1", "Límite de solape de onda 4")):
            if key in by:
                overlays.append(Overlay(
                    id=f"elliott:level:{key}", agent_id=self.id, kind="level", t_from=by[key]["t"],
                    geometry={"p": by[key]["price"]}, label=text, confidence=confidence,
                    evidence=[f"precio del pivote de la onda {key}"],
                ))
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=confidence, horizon_bars=p.horizon_bars, evidence=evidence,
            metrics={
                "pivots": labeled, "threshold_pct": p.threshold_pct, "rule_violations": violations,
                "valid_count": not violations, "bars": len(c), "source": src,
                "coverage": snapshot.coverage.get("candles"), **prob,
            },
            warnings=warnings, overlays=overlays,
        )
