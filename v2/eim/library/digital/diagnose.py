"""Conocimiento aplicado al diagnóstico de una operación (T154), puro.

Primero los números de la operación (R/B, distancia del stop, liquidación aproximada, costo en R,
estadística propia de la estrategia); después, para cada dimensión, las fuentes pertinentes. La
literatura acompaña a los datos; nunca los sustituye ni decide: el resultado es un complemento.
"""

from __future__ import annotations

import math

from eim.library.digital.consensus import KnowledgeBase, consensus
from eim.library.digital.contrast import TradeContext, contrast
from eim.library.digital.profiles import lens, profile_notes, reweigh

MMR = 0.004            # margen de mantenimiento del primer tramo de BTCUSDT (supuesto declarado)
SMALL_N = 30
LABEL = "Diagnóstico bibliográfico · complemento del análisis cuantitativo, no una señal"


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def numbers(t: dict) -> dict:
    """Cifras de la operación a partir de una fila del libro o de una idea."""
    entry, sl, tp = _f(t.get("fill") or t.get("entry")), _f(t.get("sl")), _f(t.get("tp"))
    lev, qty = _f(t.get("leverage")), _f(t.get("qty"))
    risk = abs(entry - sl) if entry and sl else None
    rr = abs(tp - entry) / risk if risk and tp else None
    sl_frac = risk / entry if risk and entry else None
    liq_frac = (1 / lev - MMR) if lev and lev > 0 else None
    costs = (_f(t.get("fees")) or 0) + (_f(t.get("slip")) or 0)
    cost_r = costs / (qty * risk) if qty and risk and costs else None
    return {"entry": entry, "sl": sl, "tp": tp, "rr": rr,
            "breakeven_winrate": 1 / (1 + rr) if rr else None,
            "sl_pct": sl_frac * 100 if sl_frac else None, "leverage": lev,
            "liq_pct": liq_frac * 100 if liq_frac and liq_frac > 0 else None,
            "liq_ratio": liq_frac / sl_frac if liq_frac and sl_frac else None,
            "cost_r": cost_r, "result_r": _f(t.get("r")), "exit_reason": t.get("reason")}


def _refs(kb: KnowledgeBase, concept: str, k: int = 2) -> list[dict]:
    d = consensus(kb, concept, k)
    return [{**e, "verdict": d["verdict"]} for e in (d["support"] + d["objections"]
                                                     + d["conditions"])[:k]]


def _dim(id_: str, name: str, value, assessment: str, note: str, refs: list[dict]) -> dict:
    return {"id": id_, "name": name, "value": value, "assessment": assessment, "note": note,
            "refs": refs}


def diagnose(kb: KnowledgeBase, trade: dict, stats: dict | None = None,
             trend: int = 0) -> dict:
    """Diagnóstico por dimensiones de una operación (abierta, cerrada o idea)."""
    side = 1 if str(trade.get("side", 1)).lower() in ("1", "long", "buy", "compra") else -1
    ctx = TradeContext(side=side, strategy=str(trade.get("strategy") or ""),
                       family=str(trade.get("family") or ""),
                       timeframe=str(trade.get("timeframe") or ""), regime=trade.get("regime"),
                       trend=trend, profile=trade.get("profile"))
    c, n, ln = contrast(kb, ctx), numbers(trade), lens(trade.get("profile"))
    entry_v = [c["concepts"][x]["verdict"] for x in c["entry_concepts"]]
    st = stats or {}
    dims = [
        _dim("entry", "Calidad de la entrada", c["summary"],
             "favorable" if c["backs"] and not c["contradicts"] else
             "desfavorable" if c["contradicts"] and not c["backs"] else "neutral",
             f"Metodología: {', '.join(c['entry_concepts'])}.",
             [e for x in c["entry_concepts"] for e in c["concepts"][x]["support"][:1]
              + c["concepts"][x]["objections"][:1]][:4]),
        _dim("context", "Contexto del mercado", trade.get("regime") or "sin régimen declarado",
             "neutral", "Las estrategias funcionan por épocas: condicionar al régimen.",
             _refs(kb, "regime") + _refs(kb, "market_efficiency", 1)),
        _dim("probability", "Probabilidad de éxito",
             {"n": st.get("n"), "win_rate": st.get("win_rate"), "mean_r": st.get("mean_r")},
             "sin datos" if not st.get("n") else
             "insuficiente" if st["n"] < SMALL_N else
             "favorable" if (st.get("ci_low") or -1) > 0 else "desfavorable",
             "Con menos de 30 cierres la estimación no permite conclusiones; el acierto solo "
             "vale junto al tamaño medio de ganancia y pérdida.",
             _refs(kb, "performance_stats") + _refs(kb, "multiple_testing", 1)),
        _dim("reward_risk", "Relación riesgo/beneficio",
             {"rr": n["rr"], "breakeven_winrate": n["breakeven_winrate"]},
             "sin datos" if n["rr"] is None else "favorable" if n["rr"] >= 1.5 else
             "neutral" if n["rr"] >= 1 else "desfavorable",
             "Sin TP fijo (escalera) la relación se mide al cerrar." if n["tp"] is None else
             f"Acierto necesario para no perder: {n['breakeven_winrate']:.0%}." if n["rr"]
             else "", _refs(kb, "position_sizing")),
        _dim("stop", "Ubicación del stop loss", {"sl_pct": n["sl_pct"], "cost_r": n["cost_r"]},
             "sin datos" if n["sl_pct"] is None else
             "desfavorable" if (n["cost_r"] or 0) > 0.15 else "neutral",
             "Un stop ceñido con costos altos en R resta valor salvo con autocorrelación "
             "positiva.", _refs(kb, "stop_loss")),
        _dim("take_profit", "Ubicación del take profit / salida", n["tp"],
             "neutral", "Salida por escalera: el valor de un stop dinámico depende del proceso "
             "de precios." if n["tp"] is None else "TP fijo declarado.",
             _refs(kb, "trailing_stop" if n["tp"] is None else "position_sizing")),
        _dim("adverse", "Escenarios adversos", None, "neutral",
             "Colas pesadas y caídas del momentum: el peor caso es más probable que en una "
             "normal.", _refs(kb, "return_distribution", 1) + _refs(kb, "momentum_crash", 1)
             + _refs(kb, "tail_risk", 1)),
        _dim("invalidation", "Condiciones de invalidación", n["sl"], "neutral",
             "La idea se invalida al tocar el stop o si cambia el régimen que la justificaba.",
             _refs(kb, "regime", 1)),
        _dim("liquidation", "Riesgo de liquidación",
             {"leverage": n["leverage"], "liq_pct": n["liq_pct"], "ratio": n["liq_ratio"]},
             "sin datos" if n["liq_ratio"] is None else
             "crítico" if n["liq_ratio"] < 1 else "desfavorable" if n["liq_ratio"] < 1.5
             else "favorable",
             f"Liquidación aproximada a {n['liq_pct']:.1f} % (margen aislado, MMR {MMR:.1%}, "
             "supuesto)." if n["liq_pct"] else "", _refs(kb, "liquidation")),
        _dim("continuation", "Continuación o reversión", None,
             _cont(c), "Lo que dicen las fuentes de tendencia y de reversión para este lado.",
             _refs(kb, "momentum", 1) + _refs(kb, "mean_reversion", 1)
             + _refs(kb, "time_series", 1)),
    ]
    cat = {r.id: r.curated.category for r in kb.refs.values()}
    for d in dims:
        d["refs"] = reweigh(d["refs"], cat, ln)
    return {"label": LABEL, "mode": "SIMULADO", "profile": ln.profile, "numbers": n,
            "contrast": c, "dimensions": dims,
            "profile_notes": profile_notes(ln, entry_v, n["leverage"], n["liq_ratio"]),
            "conclusion": _conclusion(dims)}


def _cont(c: dict) -> str:
    v = {x: c["concepts"].get(x, {}).get("verdict") for x in ("momentum", "trend_following",
                                                              "mean_reversion")}
    if "a favor" in (v["momentum"], v["trend_following"]):
        return "favorable"
    if "en contra" in (v["momentum"], v["trend_following"]):
        return "desfavorable"
    return "neutral"


def _conclusion(dims: list[dict]) -> str:
    bad = [d["name"] for d in dims if d["assessment"] in ("desfavorable", "crítico")]
    good = [d["name"] for d in dims if d["assessment"] == "favorable"]
    parts = []
    if good:
        parts.append("a favor: " + ", ".join(good))
    if bad:
        parts.append("en contra: " + ", ".join(bad))
    return ("; ".join(parts) or "sin argumentos fuertes en ningún sentido") + \
        ". Complemento del bróker simulado; no ejecuta ni veta."
