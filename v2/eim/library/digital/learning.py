"""Aprendizaje y retroalimentación bibliográfica (T155), puro.

Por cada operación cerrada del libro fijo se arma la cadena
OPERACIÓN → DIAGNÓSTICO → ESTRATEGIA → LITERATURA → RESULTADO → CONCLUSIÓN, y en conjunto se mide
qué conocimiento está aportando: R medio de las operaciones que la literatura respaldaba frente a
las que contradecía, y para cada concepto con qué frecuencia su veredicto anticipó el resultado.

Una operación no prueba nada: con menos de `MIN_N` cierres por grupo se dice «muestra insuficiente»
y no se saca conclusión. Los intervalos son t de Student al 95 %; la diferencia entre grupos, de
Welch. Nada de esto cambia estrategias ni perfiles (las reglas nuevas pasan por el banco y T49).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from statistics import mean, stdev

from scipy import stats as sps

from eim.library.digital.consensus import KnowledgeBase
from eim.library.digital.contrast import CachedContrast, TradeContext

MIN_N = 30
VERDICT_SIGN = {"a favor": 1, "en contra": -1}


def _ci(xs: list[float]) -> tuple[float | None, float | None]:
    if len(xs) < 2:
        return None, None
    m, s = mean(xs), stdev(xs)
    h = sps.t.ppf(0.975, len(xs) - 1) * s / math.sqrt(len(xs))
    return m - h, m + h


def summarize(xs: list[float]) -> dict:
    lo, hi = _ci(xs)
    return {"n": len(xs), "mean_r": round(mean(xs), 4) if xs else None,
            "win_rate": round(sum(x > 0 for x in xs) / len(xs), 4) if xs else None,
            "ci_low": None if lo is None else round(lo, 4),
            "ci_high": None if hi is None else round(hi, 4),
            "enough": len(xs) >= MIN_N}


def welch(a: list[float], b: list[float]) -> dict:
    if len(a) < 2 or len(b) < 2:
        return {"diff": None, "p": None, "enough": False}
    r = sps.ttest_ind(a, b, equal_var=False)
    return {"diff": round(mean(a) - mean(b), 4), "p": round(float(r.pvalue), 4),
            "enough": min(len(a), len(b)) >= MIN_N}


def trace(row: dict, cc: CachedContrast) -> dict:
    """Cadena de una operación cerrada (fila de `paper_ledger`)."""
    side = 1 if (row.get("side") or 1) > 0 else -1
    ctx = TradeContext(side=side, strategy=row.get("strategy") or "",
                       family=row.get("family") or "", timeframe=row.get("timeframe") or "",
                       regime=row.get("regime"))
    c = cc(ctx)
    entry = {x: c["concepts"][x]["verdict"] for x in c["entry_concepts"]}
    signs = [VERDICT_SIGN.get(v, 0) for v in entry.values()]
    stance = 1 if sum(signs) > 0 else -1 if sum(signs) < 0 else 0
    r = row.get("r")
    won = None if r is None else r > 0
    anticipated = (None if won is None or stance == 0
                   else (stance > 0) == won)
    top = [e["cite"] for x in c["entry_concepts"]
           for e in (c["concepts"][x]["support"] + c["concepts"][x]["objections"])[:1]]
    return {
        "ledger_id": row.get("ledger_id"),
        "operacion": {"profile": row.get("profile"), "symbol": row.get("symbol"),
                      "side": side, "timeframe": row.get("timeframe"),
                      "opened_t": row.get("opened_t"), "exit_t": row.get("exit_t")},
        "diagnostico": {"regime": row.get("regime"), "summary": c["summary"]},
        "estrategia": {"strategy": row.get("strategy"), "family": row.get("family")},
        "literatura": {"entry_verdicts": entry, "stance": stance, "sources": top[:4]},
        "resultado": {"r": r, "reason": row.get("reason"), "won": won},
        "conclusion": _conclusion(stance, won),
        "anticipated": anticipated,
    }


def _conclusion(stance: int, won: bool | None) -> str:
    if won is None:
        return "Sin resultado en R: no evaluable."
    if stance == 0:
        return "La literatura no tomaba partido; el resultado no la evalúa."
    hit = (stance > 0) == won
    lit = "respaldaba" if stance > 0 else "contradecía"
    res = "cerró en positivo" if won else "cerró en negativo"
    return (f"La literatura {lit} la entrada y la operación {res}: "
            f"{'coincide' if hit else 'no coincide'}. Una sola operación no evalúa nada.")


def evaluate(rows: Iterable[dict], kb: KnowledgeBase) -> dict:
    """Trazas de todas las filas y la estadística de utilidad del conocimiento."""
    cc = CachedContrast(kb)
    traces = [trace(r, cc) for r in rows if r.get("r") is not None]
    groups = {s: [t["resultado"]["r"] for t in traces if t["literatura"]["stance"] == s]
              for s in (1, 0, -1)}
    per_concept: dict[str, dict[str, list[float]]] = {}
    for t in traces:
        for concept, v in t["literatura"]["entry_verdicts"].items():
            per_concept.setdefault(concept, {}).setdefault(v, []).append(t["resultado"]["r"])
    concepts = [{"concept": c, "by_verdict": {v: summarize(xs) for v, xs in by_v.items()},
                 "useful": _useful(by_v)} for c, by_v in sorted(per_concept.items())]
    sup, con = groups[1], groups[-1]
    return {
        "n_traces": len(traces), "min_n": MIN_N,
        "backed": summarize(sup), "neutral": summarize(groups[0]), "contradicted": summarize(con),
        "backed_vs_contradicted": welch(sup, con), "concepts": concepts,
        "verdict": _verdict(sup, con), "traces": traces,
    }


def _useful(by_v: dict[str, list[float]]) -> str:
    """¿Anticipó el veredicto el resultado en R? (no en acierto: con la escalera el acierto
    engaña, 68 % de ganadoras con esperanza negativa; fase 24)."""
    fav, con = by_v.get("a favor", []), by_v.get("en contra", [])
    if max(len(fav), len(con)) < MIN_N:
        return "muestra insuficiente"
    out = []
    for name, xs, good in (("a favor", fav, 1), ("en contra", con, -1)):
        if len(xs) < MIN_N:
            continue
        lo, hi = _ci(xs)
        if lo is not None and lo > 0:
            out.append(f"{name}: R medio > 0" + (" (anticipa)" if good > 0 else " (al revés)"))
        elif hi is not None and hi < 0:
            out.append(f"{name}: R medio < 0" + (" (anticipa)" if good < 0 else
                                                 " (respalda operaciones que pierden)"))
        else:
            out.append(f"{name}: R medio indistinguible de 0 (no aporta)")
    return "; ".join(out)


def _verdict(sup: list[float], con: list[float]) -> str:
    if min(len(sup), len(con)) < MIN_N:
        return (f"Muestra insuficiente: {len(sup)} operaciones respaldadas y {len(con)} "
                f"contradichas; hacen falta ≥ {MIN_N} en cada grupo para concluir.")
    w = welch(sup, con)
    if w["p"] is not None and w["p"] < 0.05:
        better = "mejor" if w["diff"] > 0 else "peor"
        return (f"Las operaciones respaldadas por la literatura rinden {better} que las "
                f"contradichas ({w['diff']:+.3f} R, p = {w['p']:.3f}).")
    return "Sin diferencia significativa entre operaciones respaldadas y contradichas."
