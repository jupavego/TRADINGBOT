"""Ayudas de las pruebas de T102: una vista del escáner sintética con la forma de `build_view`.

Clases y tamaños a elección; cada instrumento de la lista corta tiene agentes que corrieron (con
el estado pedido), omitidos con su motivo, síntesis, proyección, oportunidad y fila de ranking.
"""

from __future__ import annotations

DAY = 86_400_000
ASOF = 1_795_651_200_000              # 2026-11-26 00:00 UTC (corte de la vela diaria)
NOW = ASOF + 3 * 3_600_000            # tres horas después
SRC = "binance-futures (escáner global, T93)"


def iid(cls: str, sym: str) -> str:
    return f"{cls}.binance.usdm.{sym}"


def make_view(counts: dict[str, int] | None = None, *, shortlist: int = 3, now: int = NOW,
              agent_status: dict[str, str] | None = None, above: int = 0,
              quality: float = 1.0, last_t: int | None = None) -> dict:
    counts = {"crypto": 6, "equity": 2} if counts is None else counts
    status = agent_status or {}
    last = ASOF - DAY if last_t is None else last_t
    rows, markets, instruments, opps, rk = [], [], {}, [], []
    k = 0
    for cls, n in counts.items():
        markets.append({"market": "binance·usdm", "asset_class": cls, "n": n, "abierto": n,
                        "cerrado": 0, "sin_calendario": 0})
        for j in range(n):
            k += 1
            sym = f"{cls[:3].upper()}{j}USDT"
            i = iid(cls, sym)
            deep = k <= shortlist
            oid = f"op-{k:020d}"
            rows.append({"instrument_id": i, "symbol": sym, "label": sym, "asset_class": cls,
                         "market": "binance·usdm", "state": "abierto", "rank": k,
                         "score": 1 - k / 100, "quality": quality, "last_t": last,
                         "deep": deep, "n_bars": 500 if deep else None,
                         "opportunity_id": oid if deep else None})
            if not deep:
                continue
            ran = [{"agent_id": a, "version": "1.0.0", "status": status.get(a, "ok"),
                    "bias": 0.5, "confidence": 0.6, "warnings": [], "eligibility": "elegible"}
                   for a in ("ema", "structure", "levels")]
            skipped = [{"agent_id": "derivatives", "version": "1.0.0",
                        "reason": "no hay funding (no es un perpetuo o no se sincronizó)"}]
            syn = {"bias": 0.4, "confidence": 0.5, "agreement": 0.7, "thesis": "Sesgo alcista",
                   "contributions": {"ema": 0.3, "structure": 0.1, "levels": 0.05}}
            fc = {"engine": "base", "horizon_bars": 25, "label": "simuladas", "warnings": [],
                  "scenarios": {"bull": {"p": 0.5, "median_end": 110.0},
                                "neutral": {"p": 0.3, "median_end": 100.0},
                                "bear": {"p": 0.2, "median_end": 90.0}}}
            instruments[i] = {"instrument_id": i, "symbol": sym, "timeframe": "1d", "asof": ASOF,
                              "input_hash": f"{k:032x}",
                              "coverage": {"n_bars": 500, "fields": ["candles"]}, "ran": ran,
                              "skipped": skipped, "synthesis": syn, "forecast": fc,
                              "reason": "", "warnings": [], "elapsed_ms": 100.0,
                              "asset_class": cls, "market": "binance·usdm", "state": "abierto",
                              "opportunity_id": oid}
            opps.append({"opportunity_id": oid, "run_id": "barrido-1", "instrument_id": i,
                         "symbol": sym, "asset_class": cls, "market": "binance·usdm",
                         "timeframe": "1d", "side": "largo", "asof": ASOF, "horizon_bars": 25,
                         "horizon_ms": 25 * DAY, "valid_until": ASOF + DAY,
                         "input_hash": f"{k:032x}", "source": SRC,
                         "input_ref": {"store": "universe_perps", "symbol": sym,
                                       "timeframe": "1d", "n_bars": 500, "cut": ASOF,
                                       "first_t": ASOF - 500 * DAY, "last_t": last},
                         "coverage": {"n_bars": 500}, "agents": [
                             {**r, "votes": True} for r in ran], "synthesis": syn,
                         "forecast": fc, "scores": {"signal_quality": 0.35, "viability": 0.9,
                                                    "risk_cost": 0.7, "components": {},
                                                    "notes": []},
                         "versions": {}, "warnings": []})
            rk.append({"opportunity_id": oid, "instrument_id": i, "symbol": sym,
                       "side": "largo", "priority": 0.6 - k / 100, "position": k,
                       "above_threshold": k <= above, "cluster_id": f"g-{k}",
                       "representative": True,
                       "multiplicity": {"p_holm": 1.0, "n_family": 1138, "verdict": "—",
                                        "validation": "no validada"}})
    return {
        "version": "2", "mode": "ANALISIS", "status_label": "candidata, no validada",
        "notice": "aviso", "generated_at": now,
        "universe": {"run_id": "barrido-1", "asof": ASOF, "timeframe": "1d",
                     "exclusions": {"liquidez": 5}, "notes": {"spread_sin_medir": k},
                     "lifecycle": {}, "n_scored": k, "markets": markets, "rows": rows},
        "deep": {"run_id": "agentes-1", "asof": ASOF, "n_shortlist": len(opps),
                 "n_opportunities": len(opps), "reasons": {}},
        "runs": [{"run_id": "agentes-1", "rhythm": "agentes", "asof": ASOF, "timeframe": "1d",
                  "started_at": now - 60_000, "finished_at": now, "detail": {"failed": []}}],
        "opportunities": opps,
        "ranking": {"available": True, "rows": rk, "n_above": above,
                    "threshold": {"status": "vigente", "value": 0.669, "p_global": 0.16},
                    "family": {"total": 1138, "matured": 0}},
        "instruments": instruments,
    }


STATUS = {"last_sweep": {"run_id": "barrido-1", "asof": ASOF, "n_catalog": 20, "n_stage1": 15,
                         "n_stage2": 8, "n_scored": 8, "n_shortlist": 3,
                         "ms_per_instrument": 3.2, "within_budget": True},
          "queue": {"pending": 0, "running": 0, "done": 30, "failed": 0}}
