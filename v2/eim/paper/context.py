"""Contexto compacto de una vela cerrada: lo que sabían los agentes en `asof` (función pura).

Es la parte cara (agentes, síntesis, sugerencias, escenarios); se persiste una vez y las
estrategias —baratas— se reevalúan sobre él cuantas veces haga falta. Solo usa velas ≤ `asof`.
"""

from __future__ import annotations

import math

import numpy as np

from eim.agents.levels.pivots import atr
from eim.core import AgentReport, ForecastSet, MarketSnapshot
from eim.synthesis import synthesize
from eim.synthesis.setups import SetupParams, levels_of, suggest
from eim.synthesis.synth import drift_of

CTX_VERSION = 2       # 2: añade `lit` (aciertos compactos del agente `literature`, T54)
HOUR_MS = 3_600_000
VOL_BARS = 200        # mismas velas que `/v2/setups` para la volatilidad
ATR_PERIOD = 14
_R = 6                # decimales al guardar


def _r(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), _R)


def vol_inputs(snap: MarketSnapshot, bar_ms: int) -> tuple[float, float, float]:
    """(cierre, ATR, σ del precio por hora en USDT) de las últimas `VOL_BARS` velas."""
    cs = snap.candles[-(VOL_BARS + 1):]
    c = np.array([x.c for x in cs])
    h = np.array([x.h for x in cs])
    lo = np.array([x.l for x in cs])
    close = float(c[-1])
    bar_h = bar_ms / HOUR_MS
    sigma_h = float(np.std(np.diff(np.log(c)))) * close / math.sqrt(bar_h) if len(c) > 2 else 0.0
    return close, atr(h, lo, c, ATR_PERIOD), sigma_h


def forecast_summary(fs: ForecastSet | None) -> dict | None:
    """Por escenario: probabilidad, mediana/banda al final del horizonte e invalidación."""
    if fs is None:
        return None
    out: dict = {"h": fs.horizon_bars, "engine": fs.engine}
    for s in fs.scenarios:
        out[s.id] = {
            "p": _r(s.probability), "end": _r(s.path[-1][1]) if s.path else None,
            "lo": _r(s.band_low[-1][1]) if s.band_low else None,
            "hi": _r(s.band_high[-1][1]) if s.band_high else None,
            "inv": _r(s.invalidation.get("level")), "inv_low": _r(s.invalidation.get("level_low")),
        }
    out["q"] = {k: _r(v[-1][1]) for k, v in fs.quantiles.items() if v}
    return out


def _plan(rep: AgentReport | None) -> dict | None:
    plan = rep.metrics.get("plan") if rep is not None and rep.status == "ok" else None
    if not plan:
        return None
    return {"side": plan["side"], "entry": _r(plan["entry"]), "sl": _r(plan["sl"]),
            "tp": [_r(x) for x in plan["tp"]], "rr": _r(plan.get("rr")),
            "status": plan.get("status"), "created_t": plan.get("created_t"),
            "conf": _r(rep.confidence)}


def lit_summary(rep: AgentReport | None) -> dict | None:
    """Aciertos compactos de `literature` en la vela (T54): `[ficha, dirección, fuerza]`, neto por
    escenario y la versión del agente. None si el agente no corrió o no tenía reglas/velas."""
    if rep is None or rep.status == "no_data":
        return None
    sup = rep.metrics.get("scenario_support") or {}
    return {"v": rep.version,
            "hits": [[h["card_id"], int(h["direction"]), _r(h["strength"])]
                     for h in rep.metrics.get("hits") or []],
            "net": {k: _r(v["net"]) for k, v in sup.items()},
            "n": rep.metrics.get("rules_evaluated")}


def make_ctx(snap: MarketSnapshot, reports: list[AgentReport], expected: list[str],
             forecast: ForecastSet | None, bar_ms: int,
             setup_params: SetupParams | None = None) -> dict:
    """Contexto compacto de `snap.asof` a partir de reportes ya calculados."""
    byid = {r.agent_id: r for r in reports}
    syn = synthesize(reports, expected=expected)
    close, a, sigma_h = vol_inputs(snap, bar_ms)
    setups = (suggest(close, sigma_h, a, levels_of(reports), syn, setup_params,
                      bar_hours=bar_ms / HOUR_MS) if a > 0 and sigma_h > 0 else [])
    reg = byid.get("regime")
    return {
        "v": CTX_VERSION, "t": snap.asof, "close": _r(close), "atr": _r(a), "sigma_h": _r(sigma_h),
        "agents": {r.agent_id: [_r(r.bias), _r(r.confidence), r.status] for r in reports},
        "regime": reg.metrics.get("regime") if reg is not None and reg.status == "ok" else None,
        "syn": None if syn is None else {"bias": _r(syn.bias), "conf": _r(syn.confidence),
                                         "agree": _r(syn.agreement)},
        "plan": _plan(byid.get("plan")),
        "lit": lit_summary(byid.get("literature")),
        "setups": [{"side": s.side, "entry": _r(s.entry), "sl": _r(s.sl), "tp": _r(s.tp),
                    "rr": _r(s.rr), "p_fill": _r(s.p_fill), "p_tp": _r(s.p_tp), "ev_r": _r(s.ev_r),
                    "hours": _r(s.hours), "aligned": s.aligned, "conf_n": s.confluence,
                    "basis": f"{s.entry_basis} · SL {s.sl_basis} · TP {s.tp_basis}"}
                   for s in setups],
        "fc": forecast_summary(forecast),
    }


def synthesis_drift(reports: list[AgentReport], expected: list[str],
                    snap: MarketSnapshot) -> float | None:
    """Deriva de la síntesis (log-retorno por vela) que inclina la proyección, como en T20."""
    syn = synthesize(reports, expected=expected)
    closes = np.array([c.c for c in snap.candles])
    if syn is None or len(closes) < 3:
        return None
    return drift_of(syn, float(np.std(np.diff(np.log(closes)))))
