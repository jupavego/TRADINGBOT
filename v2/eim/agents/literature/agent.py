"""Agente `literature` (T53): qué reglas de los libros están activas y si apoyan cada escenario.

Informa; no cambia las probabilidades calibradas (T19) ni publica sugerencias. Sesgo =
Σ(dirección·fuerza)/`bias_norm` de los aciertos activos en la última vela cerrada; confianza con
techo `max_confidence` mientras no haya medición (T54). Papel en la síntesis: no direccional.
"""

from __future__ import annotations

from eim.agents.base import no_data_report
from eim.agents.literature.params import CARD_META, LiteratureParams
from eim.agents.literature.rules import RULES, Ctx, RuleHit
from eim.core import AgentReport, MarketSnapshot, Overlay

SCENARIOS = ("bull", "neutral", "bear")  # ids de `eim.core.forecast.Scenario`
LABEL = {"bull": "alcista", "neutral": "neutral", "bear": "bajista"}
TAG = "Apoyo bibliográfico · no es una señal validada"


def _py(v: object) -> float | str:
    """Valor medido como tipo nativo (los arrays de numpy no serializan a JSON)."""
    return v if isinstance(v, str) else float(v)  # type: ignore[arg-type]


def _supports(sid: str, d: int) -> bool:
    return (sid == "bull" and d > 0) or (sid == "bear" and d < 0)


def _contradicts(sid: str, d: int) -> bool:
    # El escenario neutral lo contradice cualquier regla direccional activa.
    return sid == "neutral" or (sid == "bull" and d < 0) or (sid == "bear" and d > 0)


def scenario_support(hits: list[RuleHit], evaluated: int) -> dict[str, dict]:
    """Fichas que apoyan/contradicen cada escenario y neto −1..+1 (ponderado por fuerza).

    Las reglas codificadas son todas direccionales, así que a «neutral» solo pueden
    contradecirlo; su neto es ≤ 0 y nunca lo apoyan (no se inventa apoyo)."""
    out: dict[str, dict] = {}
    for sid in SCENARIOS:
        sup = [h for h in hits if _supports(sid, h.direction)]
        con = [h for h in hits if _contradicts(sid, h.direction)]
        s, c = sum(h.strength for h in sup), sum(h.strength for h in con)
        out[sid] = {
            "supports": [h.card_id for h in sup], "contradicts": [h.card_id for h in con],
            "net": round((s - c) / (s + c), 4) if s + c > 0 else 0.0,
            "rules_evaluated": evaluated, "label": TAG,
        }
    return out


class LiteratureAgent:
    id = "literature"
    version = "0.1.0"
    requires = {"candles"}

    def __init__(self, params: LiteratureParams | None = None) -> None:
        self.params = params or LiteratureParams()

    def _coded(self) -> frozenset[str]:
        allowed = self.params.coded_cards
        return frozenset(RULES) if allowed is None else frozenset(RULES) & allowed

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p, n = self.params, len(snapshot.candles)
        coded = self._coded()
        if not coded:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "ninguna ficha codificada: el agente no tiene reglas que evaluar")
        if n < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"velas insuficientes: {n} < {p.min_bars}")
        x, tf = Ctx.of(snapshot, p), snapshot.timeframe
        runnable = {k: s for k, s in RULES.items() if k in coded and n >= s.min_bars(p, tf)}
        skipped = sorted(coded - set(runnable))
        last = n - 1
        hits = [h for s in runnable.values() if (h := s.fn(x, p, last)) is not None]
        hits.sort(key=lambda h: -h.strength)

        net = sum(h.direction * h.strength for h in hits)
        mass = sum(h.strength for h in hits)
        bias = max(-1.0, min(1.0, net / p.bias_norm))
        agree = abs(net) / mass if mass else 0.0
        confidence = min(p.max_confidence, p.max_confidence * agree * min(1.0, mass / p.bias_norm))

        warnings = []
        if skipped:
            warnings.append(f"reglas sin velas suficientes en {tf}: {', '.join(skipped)}")
        markets = {m for h in hits for m in CARD_META[h.card_id].markets}
        if hits:
            warnings.append(f"reglas planteadas en {', '.join(sorted(markets))}, no en cripto: "
                            "supuesto 24/7 de cada ficha")
        authors = {CARD_META[h.card_id].author for h in hits if h.direction > 0}, \
                  {CARD_META[h.card_id].author for h in hits if h.direction < 0}
        if authors[0] and authors[1]:
            warnings.append("contradicción entre reglas activas: "
                            f"{', '.join(sorted(authors[0]))} (alcista) vs "
                            f"{', '.join(sorted(authors[1]))} (bajista)")
        warnings.append(f"{TAG}; confianza con techo {p.max_confidence} hasta medirla (T54)")

        evidence = [f"{CARD_META[h.card_id].cite}: {h.label} — "
                    + "; ".join(f"{c.name} {c.value}" for c in h.conditions) for h in hits] \
            or [f"Ninguna de las {len(runnable)} reglas evaluadas se cumple en la última vela"]
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=confidence, horizon_bars=p.horizon_bars, evidence=evidence,
            metrics={
                "hits": [{
                    "card_id": h.card_id, "direction": h.direction,
                    "strength": round(h.strength, 4), "horizon_bars": h.horizon_bars, "t": h.t,
                    "timeframe": h.timeframe, "label": h.label,
                    "cite": CARD_META[h.card_id].cite,
                    "conditions": [{"name": c.name, "value": _py(c.value), "ok": bool(c.ok)}
                                   for c in h.conditions]} for h in hits],
                "rules_evaluated": len(runnable), "rules_coded": len(coded),
                "scenario_support": scenario_support(hits, len(runnable)),
                "label": TAG, "source": snapshot.sources.get("candles", "desconocida"),
                "coverage": snapshot.coverage.get("candles"),
            },
            warnings=warnings, overlays=self._overlays(x, p, runnable, last, confidence),
            status="degraded" if skipped else "ok",
        )

    def _overlays(self, x: Ctx, p: LiteratureParams, runnable, last: int,
                  conf: float) -> list[Overlay]:
        out = []
        for i in range(max(0, last - p.overlay_lookback + 1), last + 1):
            for s in runnable.values():
                if (h := s.fn(x, p, i)) is None:
                    continue
                out.append(Overlay(
                    id=f"literature:{h.card_id}:{h.t}", agent_id=self.id, kind="marker",
                    t_from=h.t, t_to=h.t,
                    geometry={"t": h.t, "p": h.price,
                              "action": "buy" if h.direction > 0 else "sell"},
                    label=h.label, confidence=min(conf or 0.1, h.strength * p.max_confidence),
                    evidence=[f"{CARD_META[h.card_id].cite}; {TAG}"]))
        return out
