"""Agente `bots`: consolida las `BotSignal` que el servicio de bots ya calculó (T57).

Puro: no lanza procesos ni lee disco; lee `snapshot.bot_signals`. Hasta T59 ningún bot está en
estado `vota`, así que `bias` es 0 y el agente solo muestra qué opina cada bot (contexto). Peso 0 y
`excluded` en la síntesis (`eim/synthesis/params.py`): no mueve la proyección ni el plan.
"""

from __future__ import annotations

import math
import statistics

from eim.agents.base import no_data_report
from eim.agents.bots.params import BotsParams
from eim.core import NOT_SAVED, VERSION_CHANGED, AgentReport, BotSignal, MarketSnapshot


def key_of(sig: BotSignal) -> str:
    return f"{sig.bot_id}@{sig.strategy}"


class BotsAgent:
    id = "bots"
    version = "0.1.0"
    requires = {"bot_signals"}

    def __init__(self, params: BotsParams | None = None) -> None:
        self.params = params or BotsParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        sigs = snapshot.bot_signals or []
        live = [s for s in sigs if s.status != "no_data"]
        if not live:
            why = ("el servicio de bots no produjo señales" if not sigs
                   else "ningún bot tiene datos suficientes")
            return no_data_report(self.id, self.version, snapshot.asof, why)

        rows, warnings = [], []
        for s in sigs:
            state = p.states.get(key_of(s), "observa")
            votes = state == p.voting_state and s.status == "ok"
            rows.append({
                "bot_id": s.bot_id, "strategy": s.strategy, "stance": s.stance,
                "confidence": s.confidence, "version": s.version, "status": s.status,
                "state": state, "votes": votes, "asof": s.asof, "evidence": s.evidence,
                "coverage": s.data_quality.coverage, "bars": s.data_quality.bars,
                "source": s.data_quality.source})
            if s.status == "degraded":
                warnings.append(f"{key_of(s)}: degradado — {'; '.join(s.evidence) or 'sin motivo'}")
            warnings += [f"{key_of(s)}: {n}" for n in s.data_quality.notes
                         if n.startswith((VERSION_CHANGED, NOT_SAVED))]

        voters = [(s, r) for s, r in zip(sigs, rows, strict=True) if r["votes"]]
        bias, conf, horizon = 0.0, 0.0, 0
        if voters:
            w = [s.confidence if s.confidence is not None else p.neutral_weight
                 for s, _ in voters]
            total = sum(w)
            bias = sum(wi * s.stance for wi, (s, _) in zip(w, voters, strict=True)) / total \
                if total > 0 else 0.0
            confs = [s.confidence if s.confidence is not None else p.fallback_confidence
                     for s, _ in voters]
            conf = sum(confs) / len(confs)
            if any(s.confidence is None for s, _ in voters):
                warnings.append("votan bots sin confianza propia: se usa la confianza supuesta "
                                f"{p.fallback_confidence:g} (hasta la calibración de T59)")
            hs = [s.horizon_bars for s, _ in voters if s.horizon_bars]
            horizon = int(statistics.median(hs)) if hs else 0

        ok = [s.stance for s in sigs if s.status == "ok"]
        disagreement = float(statistics.pstdev(ok)) if len(ok) >= 2 else None
        evidence = [f"{r['bot_id']}@{r['strategy']}: postura {r['stance']:+.0f}, "
                    f"estado {r['state']}, {r['status']}" for r in rows]
        if not voters:
            evidence.append("ningún bot está en estado «vota» (T59): solo contexto, sin sesgo")
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof,
            bias=max(-1.0, min(1.0, 0.0 if math.isnan(bias) else bias)), confidence=conf,
            horizon_bars=horizon, evidence=evidence, warnings=warnings,
            metrics={"bots": rows, "disagreement": disagreement, "voters": len(voters),
                     "signals": len(sigs), "source": "bot_signals"},
            status="degraded" if any(s.status == "degraded" for s in sigs) else "ok")
