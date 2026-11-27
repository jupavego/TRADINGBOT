"""De un análisis profundo a una oportunidad candidata con tres puntuaciones separadas (T94).

Cada puntuación va de 0 a 1 (más alto = más favorable) y lleva sus componentes a la vista; no se
combinan en un número único porque la priorización global comparable es T95 (con control de
multiplicidad). Donde falta un dato, el componente queda `None` con su nota: no se inventa.

- **Calidad de la señal** = confianza × acuerdo de la síntesis existente (sin tocarla).
- **Viabilidad operativa** = media de lo medible: calidad de los datos (etapa 3 de T93), liquidez
  (mediana del volumen en moneda de cotización por día frente al mínimo del embudo, en escala
  log: 1 a 100× el mínimo), diferencial (si hay cotización fresca) y la fracción de agentes que
  corrió sin degradarse.
- **Riesgo/costos** = (1 − costo de ida y vuelta / movimiento esperado del escenario a favor) ×
  (1 − probabilidad del escenario en contra). El costo sale del modelo de la clase (T92) con un
  nocional de referencia declarado (`REF_NOTIONAL`); el movimiento, de la mediana final del
  escenario a favor de la proyección.
"""

from __future__ import annotations

import math

import numpy as np

from eim.core import Candle, Synthesis
from eim.core.opportunity import (
    AgentVote,
    InputRef,
    Opportunity,
    Scores,
    opportunity_id,
)
from eim.data.timeframes import tf_ms
from eim.instruments.models import Instrument
from eim.scanner.params import DAY_MS, DEFAULT_PARAMS

SCORING_VERSION = "1.0.0"
#: Nocional de referencia para medir el deslizamiento (supuesto declarado; no es un tamaño).
REF_NOTIONAL = 10_000.0
LIQUIDITY_BARS = 20


def market_of(inst: Instrument) -> str:
    """`plaza·mercado` a partir del id (`crypto.binance.usdm.BTCUSDT` → `binance·usdm`)."""
    parts = inst.id.split(".")
    return "·".join(parts[1:-1]) if len(parts) > 3 else inst.venue


def _clip(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def median_quote_volume_per_day(candles: list[Candle], timeframe: str) -> float | None:
    tail = candles[-LIQUIDITY_BARS:]
    if not tail:
        return None
    med = float(np.median([k.v * k.c for k in tail]))
    return med * DAY_MS / tf_ms(timeframe) if med > 0 else None


def round_trip_cost(inst: Instrument, last: Candle) -> tuple[float | None, str]:
    """Costo de ida y vuelta como fracción del precio (comisión taker + deslizamiento) y fuente."""
    from eim.backtest.costs import NotTradable, cost_model_for

    try:
        m = cost_model_for(inst)
        qty = REF_NOTIONAL / last.c
        fee = m.commission(qty, last.c) / REF_NOTIONAL
        slip = m.slippage_frac(last, REF_NOTIONAL)
    except NotTradable as exc:
        return None, f"sin modelo de costos: {exc}"
    except (TypeError, ValueError, AttributeError) as exc:   # modelo de otra clase sin ese uso
        return None, f"costo no medible: {type(exc).__name__}: {exc}"
    return 2 * (fee + slip), f"{m.version} (T92), nocional de referencia {REF_NOTIONAL:,.0f}"


def scores(*, inst: Instrument, candles: list[Candle], timeframe: str, side: str, syn: Synthesis,
           forecast: dict, ran: list[dict], screen: dict | None,
           spread_bps: float | None) -> Scores:
    notes: list[str] = []
    c: dict[str, float | None] = {"confidence": round(syn.confidence, 6),
                                  "agreement": round(syn.agreement, 6)}
    signal = _clip(syn.confidence * syn.agreement)
    # --- viabilidad -----------------------------------------------------------------------------
    q = (screen or {}).get("quality")
    c["data_quality"] = None if q is None else round(float(q), 6)
    mqv = median_quote_volume_per_day(candles, timeframe)
    c["quote_volume_day"] = None if mqv is None else round(mqv, 2)
    floor = DEFAULT_PARAMS.min_quote_volume_per_day
    c["liquidity"] = None if mqv is None else round(_clip(math.log10(mqv / floor) / 2), 6)
    if spread_bps is None:
        c["spread"] = None
        notes.append("spread sin medir (sin cotización fresca): fuera de la viabilidad")
    else:
        c["spread_bps"] = round(spread_bps, 3)
        c["spread"] = round(_clip(1 - spread_bps / DEFAULT_PARAMS.max_spread_bps), 6)
    c["agents_clean"] = round(sum(r["status"] == "ok" for r in ran) / len(ran), 6) if ran else None
    parts = [c[k] for k in ("data_quality", "liquidity", "spread", "agents_clean")
             if c[k] is not None]
    viability = _clip(sum(parts) / len(parts)) if parts else 0.0
    # --- riesgo/costos --------------------------------------------------------------------------
    sc = forecast["scenarios"]
    fav, adv = ("bull", "bear") if side == "largo" else ("bear", "bull")
    last = candles[-1].c
    move = abs(sc[fav]["median_end"] - last) / last if last > 0 else 0.0
    cost, cost_src = round_trip_cost(inst, candles[-1])
    c.update(expected_move=round(move, 6), p_favorable=sc[fav]["p"], p_adverse=sc[adv]["p"],
             round_trip_cost=None if cost is None else round(cost, 6))
    notes.append(f"costo: {cost_src}")
    if cost is None or move <= 0:
        cost_part = None if cost is None else 0.0
        if cost is None:
            notes.append("riesgo/costos sin el costo: solo la probabilidad en contra")
    else:
        cost_part = _clip(1 - cost / move)
    c["cost_to_move"] = None if cost is None or move <= 0 else round(cost / move, 6)
    risk = _clip((1.0 if cost_part is None else cost_part) * (1 - sc[adv]["p"]))
    return Scores(signal_quality=round(signal, 6), viability=round(viability, 6),
                  risk_cost=round(risk, 6), components=c, notes=notes)


def build(*, inst: Instrument, candles: list[Candle], run_id: str, asof: int, timeframe: str,
          cut: int, input_hash: str, source: str, coverage: dict, ran: list[dict],
          syn: Synthesis, forecast: dict, horizon_bars: int, screen: dict | None,
          spread_bps: float | None, versions: dict[str, str]) -> Opportunity:
    side = "largo" if syn.bias > 0 else "corto"
    step = tf_ms(timeframe)
    votes = [AgentVote(agent_id=r["agent_id"], version=r["version"], status=r["status"],
                       bias=r["bias"], confidence=r["confidence"],
                       votes=r["agent_id"] in syn.contributions, warnings=r["warnings"],
                       eligibility=r["eligibility"]) for r in ran]
    warnings = [f"{v.agent_id}: {w}" for v in votes for w in v.warnings[:2]
                if v.status != "ok"][:12]
    warnings += list(forecast.get("warnings", []))[:3]
    oid = opportunity_id(inst.id, timeframe, input_hash, versions,
                         [(r["agent_id"], r["version"]) for r in ran])
    return Opportunity(
        opportunity_id=oid, run_id=run_id, instrument_id=inst.id, symbol=inst.symbol,
        asset_class=inst.asset_class.value, market=market_of(inst), timeframe=timeframe,
        side=side, asof=asof, horizon_bars=horizon_bars, horizon_ms=horizon_bars * step,
        valid_until=cut + step,
        input_hash=input_hash,
        input_ref=InputRef(symbol=inst.symbol, timeframe=timeframe, n_bars=len(candles), cut=cut,
                           first_t=candles[0].t, last_t=candles[-1].t),
        source=source or "no declarada", coverage=coverage, agents=votes,
        synthesis={"bias": round(syn.bias, 6), "confidence": round(syn.confidence, 6),
                   "agreement": round(syn.agreement, 6),
                   "contributions": {k: round(v, 6) for k, v in
                                     sorted(syn.contributions.items())}},
        forecast=forecast,
        scores=scores(inst=inst, candles=candles, timeframe=timeframe, side=side, syn=syn,
                      forecast=forecast, ran=ran, screen=screen, spread_bps=spread_bps),
        versions=versions, warnings=warnings)
