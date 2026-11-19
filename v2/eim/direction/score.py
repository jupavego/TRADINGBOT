"""Acierto de dirección por informante y veredicto pre-registrado (T190). Puro."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from eim.direction.board import Vote
from eim.direction.params import REGIMES, SYNTH_ID, DirectionParams
from eim.direction.stats import holm, p_greater, wilson

NO_VERDICT, NO_EDGE, EDGE, CONTRARY = "sin_veredicto", "sin_ventaja", "ventaja", "contraria"


def non_overlap(votes: Sequence[Vote], h: int, step: int) -> list[Vote]:
    """Un voto cada ≥ `h` velas (los votos de un mismo informante, ya en orden de `asof`)."""
    out, last = [], None
    for v in votes:
        if last is None or v.asof >= last + h * step:
            out.append(v)
            last = v.asof
    return out


def _acc(vs: Sequence[Vote], h: int) -> tuple[int, int]:
    """(aciertos, n) de los votos resueltos y no planos a `h`."""
    hits = n = 0
    for v in vs:
        o = v.outcome.get(h)
        if o:
            n += 1
            hits += o == v.sign
    return hits, n


def agent_stats(vs: Sequence[Vote], h: int, step: int) -> dict:
    """Cifras de un informante a un horizonte: toda la muestra y la sin solape (la que decide)."""
    hits, n = _acc(vs, h)
    resolved = [v for v in vs if v.outcome.get(h)]
    eff = non_overlap(resolved, h, step)
    he, ne = _acc(eff, h)
    ci = wilson(he, ne)
    by_reg = {}
    for r in REGIMES:
        hr, nr = _acc(non_overlap([v for v in resolved if v.regime == r], h, step), h)
        by_reg[r] = {"n_eff": nr, "acc_eff": hr / nr if nr else None}
    pending = sum(1 for v in vs if h not in v.outcome)
    return {"n": n, "acc": hits / n if n else None, "n_eff": ne, "hits_eff": he,
            "acc_eff": he / ne if ne else None, "ci95": list(ci) if ci else None,
            "p_gt": p_greater(he, ne), "pending": pending, "by_regime": by_reg,
            "long_share": (sum(v.sign > 0 for v in vs) / len(vs)) if vs else None}


def scoreboard(votes: Sequence[Vote], step: int, p: DirectionParams) -> dict[int, dict[str, dict]]:
    """horizonte → informante → cifras."""
    by_agent: dict[str, list[Vote]] = defaultdict(list)
    for v in sorted(votes, key=lambda v: v.asof):
        by_agent[v.agent].append(v)
    return {h: {a: agent_stats(vs, h, step) for a, vs in sorted(by_agent.items())}
            for h in p.horizons}


def verdict(st: dict, p_adj: float | None, p: DirectionParams) -> str:
    ne = st["n_eff"]
    if ne < p.min_eff_verdict:
        return NO_VERDICT
    if ne >= p.edge_min_eff and p_adj is not None and p_adj < p.alpha:
        return EDGE
    if ne >= p.edge_min_eff and st["ci95"] and st["ci95"][1] < 0.5:
        return CONTRARY
    return NO_EDGE


def judge(boards: dict[str, dict[int, dict[str, dict]]], p: DirectionParams) -> None:
    """Veredicto al horizonte principal con Holm sobre la familia informantes × marcos.

    `boards`: marco → horizonte → informante → cifras (se modifica: añade `p_holm` y `verdict`).
    """
    fam = {f"{tf}|{a}": st["p_gt"] if st["n_eff"] >= p.edge_min_eff else None
           for tf, b in boards.items() for a, st in b.get(p.primary, {}).items()}
    adj = holm(fam)
    for tf, b in boards.items():
        for a, st in b.get(p.primary, {}).items():
            st["p_holm"] = adj.get(f"{tf}|{a}")
            st["verdict"] = verdict(st, st["p_holm"], p)


def summary(board: dict[int, dict[str, dict]], p: DirectionParams) -> dict:
    """Lo que el vigía y el mapa necesitan: quién tiene ventaja y cómo va la síntesis."""
    prim = board.get(p.primary, {})
    edge = sorted(a for a, st in prim.items() if st.get("verdict") == EDGE and a != SYNTH_ID)
    contrary = sorted(a for a, st in prim.items() if st.get("verdict") == CONTRARY)
    ranked = sorted(((a, st) for a, st in prim.items() if st["n_eff"] >= p.min_eff_verdict
                     and a != SYNTH_ID), key=lambda x: -(x[1]["acc_eff"] or 0))
    return {"edge": edge, "contrary": contrary, "synth": prim.get(SYNTH_ID),
            "best": [{"agent": a, "acc_eff": st["acc_eff"], "n_eff": st["n_eff"],
                      "ci95": st["ci95"]} for a, st in ranked[:3]],
            "agents": len(prim)}
