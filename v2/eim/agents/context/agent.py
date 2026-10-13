"""Agente `context`: contexto de noticias/sentimiento. SOLO INFORMA.

Nunca abre operaciones ni fija tamaño: `bias` es siempre 0. Su aporte son métricas que el
riesgo/síntesis pueden usar: `confidence_multiplier` (reducir confianza) y `event_pause`
(pausa por evento cuando el riesgo es alto).

El agente no hace I/O: recibe titulares ya cargados en el snapshot y un `analyzer` inyectado
(`data/providers/claude_context.py` en producción, un simulado en tests). Sin analyzer, sin
titulares suficientes o ante cualquier fallo del LLM → `status="no_data"`.

Defensa ante inyección: (1) los titulares con patrones de instrucciones se excluyen antes de
llegar al LLM; (2) el texto va siempre como datos delimitados (ver `claude_context.py`);
(3) toda afirmación debe citar el id de un titular realmente entregado: si no, se descarta.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from eim.agents.base import no_data_report
from eim.agents.context.params import ContextParams
from eim.agents.context.schema import ContextOutput
from eim.core import AgentReport, MarketSnapshot, NewsItem

Analyzer = Callable[[list[NewsItem]], "ContextOutput | dict[str, Any] | None"]
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮]")


class ContextAgent:
    id = "context"
    version = "1.0.0"
    requires = {"headlines"}

    def __init__(self, params: ContextParams | None = None,
                 analyzer: Analyzer | None = None) -> None:
        self.params = params or ContextParams()
        self.analyzer = analyzer
        self._inj = [re.compile(p, re.IGNORECASE) for p in self.params.injection_patterns]

    def _clean(self, snapshot: MarketSnapshot, warnings: list[str]) -> list[NewsItem]:
        p = self.params
        min_t = snapshot.asof - p.max_age_hours * 3_600_000
        out: list[NewsItem] = []
        for n in sorted(snapshot.headlines or [], key=lambda x: -x.t):
            if n.t < min_t or n.t > snapshot.asof:
                continue
            title = _CTRL.sub("", n.title).strip()[: p.max_title_chars]
            if any(r.search(title) for r in self._inj):
                warnings.append(f"titular {n.id} excluido: posible inyección de instrucciones")
                continue
            out.append(n.model_copy(update={"title": title}))
            if len(out) >= p.max_headlines:
                break
        return out

    def _no_data(self, snapshot: MarketSnapshot, warnings: list[str], reason: str) -> AgentReport:
        r = no_data_report(self.id, self.version, snapshot.asof, reason)
        return r.model_copy(update={"warnings": [*warnings, *r.warnings]})

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        warnings: list[str] = []
        if self.analyzer is None:
            return self._no_data(snapshot, warnings,
                                 "sin analizador LLM configurado (clave/red no disponibles)")
        items = self._clean(snapshot, warnings)
        if len(items) < p.min_headlines:
            return self._no_data(snapshot, warnings,
                                 f"titulares insuficientes ({len(items)}/{p.min_headlines})")
        try:
            raw = self.analyzer(items)
            if raw is None:
                raise ValueError("el analizador no devolvió resultado")
            out = raw if isinstance(raw, ContextOutput) else ContextOutput.model_validate(raw)
        except (ValidationError, ValueError, OSError, RuntimeError) as e:
            return self._no_data(snapshot, warnings,
                                 f"LLM no disponible o salida inválida: {type(e).__name__}")

        by_id = {n.id: n for n in items}
        claims = [c for c in out.catalizadores if c.fuente in by_id]
        dropped = len(out.catalizadores) - len(claims)
        if dropped:
            warnings.append(f"{dropped} afirmación(es) descartada(s) por no citar fuente válida")
        sources = sorted({c.fuente for c in claims} | {s for s in out.fuentes if s in by_id})
        pause = out.riesgo_evento == "alto"
        if pause:
            warnings.append("riesgo de evento alto: se recomienda pausa por evento")
        status = "ok" if len(claims) >= p.min_valid_claims else "degraded"
        if status == "degraded":
            warnings.append("sin catalizadores con fuente válida: contexto no verificable")
        conf = min(p.max_confidence, len(sources) / len(items) + 0.2) if sources else 0.0
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof,
            bias=0, confidence=conf, horizon_bars=p.horizon_bars, status=status,
            evidence=[f"{c.texto} [fuente: {by_id[c.fuente].source} · {c.fuente}]"
                      for c in claims],
            metrics={
                "tema": out.tema, "sentiment": out.sentimiento,
                "event_risk": out.riesgo_evento, "event_pause": pause,
                "confidence_multiplier": p.confidence_multiplier[out.riesgo_evento],
                "sources": [{"id": s, "title": by_id[s].title, "source": by_id[s].source,
                             "url": by_id[s].url} for s in sources],
                "headlines_used": len(items), "claims_dropped": dropped,
            },
            warnings=warnings,
        )
