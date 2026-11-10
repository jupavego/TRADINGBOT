"""T150 — la síntesis que publica el panel (v2): cobertura y correlación medidas en vivo.

Lee el historial de reportes guardados (`ReportStore.history`, solo columnas) y llama a la
síntesis pura con esa evidencia. El bróker simulado, el plan y las estrategias de T49 siguen con
la síntesis v1 (sin evidencia): T150 no los toca.
"""

from __future__ import annotations

from collections.abc import Sequence

from eim.api.reports_db import ReportStore
from eim.core import AgentReport
from eim.observability import hooks_service
from eim.synthesis import synthesize
from eim.synthesis.evidence import coverage_of
from eim.synthesis.params import NON_DIRECTIONAL, EvidenceParams, SynthesisParams

PARAMS = EvidenceParams()


def published_synthesis(store: ReportStore, symbol: str, timeframe: str,
                        reports: Sequence[AgentReport], expected: Sequence[str] | None = None,
                        params: EvidenceParams = PARAMS) -> dict | None:
    """Síntesis v2 de `reports` con la evidencia de los instantes guardados hasta su `asof`.

    Si el historial no se puede leer, no se publica síntesis (None): publicar v1 sería volver a
    decir más de lo que se sabe. El fallo queda en el registro de servicio."""
    if not reports:
        return None
    asof = max(r.asof for r in reports)
    try:
        rows = store.history(symbol, timeframe, max(params.coverage_bars, params.corr_bars), asof)
    except Exception as exc:  # noqa: BLE001 - el mensaje de reportes no depende de esto
        hooks_service.service_error("synthesis.history", exc)
        return None
    agents = list(expected) if expected is not None else [r.agent_id for r in reports]
    sp = SynthesisParams()
    can_vote = [a for a in agents if a not in sp.excluded | NON_DIRECTIONAL | params.informative
                and sp.weights.get(a, 1.0) > 0]
    ev = coverage_of(rows, agents, params, can_vote)
    syn = synthesize(reports, expected=expected, evidence=ev, evidence_params=params)
    return syn.model_dump() if syn else None
