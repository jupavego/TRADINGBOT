"""Activación selectiva de los agentes sobre la lista corta (T94, 2/2). Modo ANÁLISIS.

Para cada instrumento de la lista corta de T93:

1. **Cobertura real** del snapshot del universo (`eligibility.coverage_of`) y **selección**: solo
   corren los agentes que `eligibility.eligible(...)` aprueba (`select`); los demás quedan en el
   reporte con su motivo («marco no soportado», «no hay libro L2»…), sin correr.
2. Los elegibles corren por `run_eligible` (la puerta de T91: adapta supuestos fuera de 24/7).
3. **Síntesis y proyección existentes, sin cambios**: `synthesize` con sus parámetros vigentes y
   `build_forecast` con la deriva de la síntesis (`drift_of`) y el SL del plan, exactamente como
   las encadena el pronosticador del panel (`eim/api/forecast.py`).
4. Si la síntesis tiene lado (|sesgo| ≥ `neutral_band`), una **oportunidad candidata** trazable
   (`eim/scanner/candidates.py`); si no, el reporte dice por qué no la hay.

Reproducible: el resultado depende solo de las velas (su `input_hash`), del instrumento y de las
versiones; `verify` lo vuelve a calcular. Nada de esto llega al motor de riesgo ni a ejecución.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field

import numpy as np

from eim.agents.eligibility import coverage_of, run_eligible, select
from eim.agents.runner import DEFAULT_TIMEOUT_S
from eim.core import Agent, AgentReport, Candle, MarketSnapshot
from eim.core.opportunity import Opportunity, stable_hash
from eim.forecast.scenarios import build_forecast
from eim.instruments.models import Instrument
from eim.scanner import candidates
from eim.scanner.jobs import DEEP_RUN_VERSION as DEEP_VERSION
from eim.synthesis import SynthesisParams, drift_of, synthesize

HORIZON = 25           # el del panel (`eim/api/forecast.py`, DEFAULT_HORIZON)
N_PATHS = 500


def input_hash(candles: Sequence[Candle], instrument_id: str, timeframe: str) -> str:
    """Huella de las velas exactas que ven los agentes (t, o, h, l, c, v)."""
    return stable_hash({"i": instrument_id, "tf": timeframe,
                        "c": [[k.t, k.o, k.h, k.l, k.c, k.v] for k in candles]}, size=16)


@dataclass
class DeepResult:
    instrument_id: str
    symbol: str
    timeframe: str
    asof: int
    input_hash: str
    coverage: dict
    ran: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    synthesis: dict | None = None
    forecast: dict | None = None
    opportunity: dict | None = None
    reason: str = ""                     # por qué no hay oportunidad (vacío si la hay)
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    version: str = DEEP_VERSION

    def as_json(self) -> dict:
        return asdict(self)


def _cov_json(cov) -> dict:
    return {"timeframe": cov.timeframe, "n_bars": cov.n_bars, "span_days": round(cov.span_days, 2),
            "volume": cov.volume, "taker_flow": cov.taker_flow, "fields": sorted(cov.fields)}


def _ran(rep: AgentReport, version: str, why: str) -> dict:
    elig = (rep.metrics.get("eligibility") or {}).get("reason", why)
    return {"agent_id": rep.agent_id, "version": version, "status": rep.status,
            "bias": round(rep.bias, 6), "confidence": round(rep.confidence, 6),
            "warnings": list(rep.warnings)[:5], "eligibility": elig}


def _synthesis_json(syn) -> dict:
    return {"bias": round(syn.bias, 6), "confidence": round(syn.confidence, 6),
            "agreement": round(syn.agreement, 6), "method": syn.method,
            "contributions": {k: round(v, 6) for k, v in sorted(syn.contributions.items())},
            "factors": dict(syn.factors), "thesis": syn.thesis}


def _stops(reports: Sequence[AgentReport]) -> dict[str, float]:
    """SL del plan del propio instrumento: invalida el escenario de su lado (como el panel)."""
    for r in reports:
        plan = (r.metrics.get("plan") or {}) if r.agent_id == "plan" else {}
        if plan.get("sl") and plan.get("side") in ("long", "short"):
            return {("bull" if plan["side"] == "long" else "bear"): float(plan["sl"])}
    return {}


def _forecast_json(fs) -> dict:
    sc = {}
    for s in fs.scenarios:
        sc[s.id] = {"p": round(s.probability, 6), "median_end": round(s.path[-1][1], 10),
                    "band_end": [round(s.band_low[-1][1], 10), round(s.band_high[-1][1], 10)],
                    "invalidation": s.invalidation.get("level")}
    return {"engine": fs.engine, "horizon_bars": fs.horizon_bars, "scenarios": sc,
            "warnings": list(fs.warnings), "label": "simulación estadística, no predicción"}


def analyze(inst: Instrument, candles: list[Candle], agents: Sequence[Agent], *, asof: int,
            timeframe: str, cut: int, run_id: str, source: str = "",
            screen: dict | None = None, spread_bps: float | None = None,
            timeout: float = DEFAULT_TIMEOUT_S) -> DeepResult:
    """Agentes elegibles → síntesis → proyección → oportunidad candidata (o el motivo de no)."""
    t0 = time.perf_counter()
    snap = MarketSnapshot(symbol=inst.symbol, timeframe=timeframe, candles=candles, asof=asof,
                          sources={"candles": source} if source else {})
    cov = coverage_of(snap, inst)
    h = input_hash(candles, inst.id, timeframe)
    res = DeepResult(inst.id, inst.symbol, timeframe, asof, h, _cov_json(cov))
    ok, out = select(list(agents), inst, cov)
    res.skipped = [{"agent_id": a.id, "version": a.version, "reason": why} for a, why in out]
    elig = [a for a, _ in ok]
    reports = run_eligible(elig, snap, inst, timeout=timeout) if elig else []
    res.ran = [_ran(r, a.version, why) for r, (a, why) in zip(reports, ok, strict=True)]
    syn = synthesize(reports) if reports else None
    if syn is None:
        res.reason = ("ningún agente elegible" if not elig
                      else "ningún agente elegible aportó (todos sin datos o sin peso)")
        return _done(res, t0)
    res.synthesis = _synthesis_json(syn)
    closes = np.array([c.c for c in candles], dtype=float)
    sigma = float(np.std(np.diff(np.log(closes)))) if len(closes) > 2 else 0.0
    try:
        fs = build_forecast(snap, HORIZON, N_PATHS, drift=drift_of(syn, sigma),
                            stops=_stops(reports))
    except ValueError as exc:
        res.reason = f"sin proyección: {exc}"
        return _done(res, t0)
    res.forecast = _forecast_json(fs)
    band = SynthesisParams().neutral_band
    if abs(syn.bias) < band:
        res.reason = f"síntesis neutral (|sesgo| {abs(syn.bias):.3f} < {band:g})"
        return _done(res, t0)
    opp: Opportunity = candidates.build(
        inst=inst, candles=candles, run_id=run_id, asof=asof, timeframe=timeframe, cut=cut,
        input_hash=h, source=source, coverage=res.coverage, ran=res.ran, syn=syn,
        forecast=res.forecast, horizon_bars=fs.horizon_bars, screen=screen,
        spread_bps=spread_bps, versions=versions())
    res.opportunity = opp.model_dump(mode="json")
    res.warnings = list(opp.warnings)
    return _done(res, t0)


def _done(res: DeepResult, t0: float) -> DeepResult:
    res.elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    return res


def versions() -> dict[str, str]:
    """Versiones que entran en el id de la oportunidad (cambiar una cambia el id)."""
    from eim.core.opportunity import OPPORTUNITY_VERSION
    from eim.scanner.jobs import capabilities_fingerprint

    return {"deep": DEEP_VERSION, "opportunity": OPPORTUNITY_VERSION,
            "scoring": candidates.SCORING_VERSION, "capabilities": capabilities_fingerprint(),
            "synthesis": "v1", "forecast": f"base+{HORIZON}x{N_PATHS}"}


# --- en la cola (otro proceso) ----------------------------------------------------------------
_AGENTS: list[Agent] | None = None


def default_agents() -> list[Agent]:
    """Última versión de cada agente del registro (una vez por proceso), sin los que el escáner
    no considera (`jobs.OUT_OF_SCANNER`, T214)."""
    global _AGENTS
    if _AGENTS is None:
        from eim.agents.registry import default_registry
        from eim.scanner.jobs import OUT_OF_SCANNER

        _AGENTS = [a for a in default_registry().latest() if a.id not in OUT_OF_SCANNER]
    return _AGENTS


def agents_fingerprint(agents: Sequence[Agent]) -> str:
    return stable_hash(sorted((a.id, a.version) for a in agents), size=6)


def run_payload(payload: dict) -> dict:
    """Manejador `deep_run` de la cola: relee la ventana y analiza (ver `jobs.deep_run`)."""
    from eim.data.scanner_market import SOURCE, read_window

    inst = Instrument.model_validate(payload["instrument"])
    cs = read_window(payload["root"], inst.symbol, payload["timeframe"], int(payload["n_bars"]),
                     int(payload["cut"]))
    res = analyze(inst, cs, default_agents(), asof=int(payload["asof"]),
                  timeframe=payload["timeframe"], cut=int(payload["cut"]),
                  run_id=payload["run_id"], source=payload.get("source") or SOURCE,
                  screen=payload.get("screen"), spread_bps=payload.get("spread_bps"))
    return res.as_json()


def verify(opp: dict, candles: list[Candle], agents: Sequence[Agent] | None = None,
           inst: Instrument | None = None) -> dict:
    """¿La oportunidad sale igual de sus datos? Hash de las velas y, con el instrumento, el
    análisis completo otra vez (mismo id y mismas cifras)."""
    h = input_hash(candles, opp["instrument_id"], opp["timeframe"])
    out = {"hash_ok": h == opp["input_hash"], "input_hash": h}
    if inst is None or not out["hash_ok"]:
        return out
    ref = opp["input_ref"]
    again = analyze(inst, candles, agents or default_agents(), asof=opp["asof"],
                    timeframe=opp["timeframe"], cut=ref["cut"], run_id=opp["run_id"],
                    source=opp["source"], screen=None, spread_bps=None)
    same = again.opportunity is not None and again.opportunity["opportunity_id"] == \
        opp["opportunity_id"] and again.opportunity["synthesis"] == opp["synthesis"]
    return out | {"reproduced": same}
