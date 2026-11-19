"""Sombras de la entrada (T192 abstención, T193 síntesis ponderada por acierto). Puro.

Walk-forward estricto: en cada instante solo cuenta lo ya resuelto (el horizonte principal cerró
antes de ese instante). Nunca cambian nada: se comparan con la síntesis v1 en los mismos instantes
y la adopción pasa por la ◆ del usuario (`PLAN/notas/T190_preregistro.md`).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from eim.direction.board import Instant
from eim.direction.params import DirectionParams
from eim.direction.stats import holm, mcnemar_greater, wilson

ABSTAIN, WEIGHTED = "T192_abstencion", "T193_ponderada"
SHADOWS = (ABSTAIN, WEIGHTED)


class Live:
    """Aciertos y votos sin solape ya resueltos por (informante, régimen)."""

    def __init__(self, h: int, step: int) -> None:
        self.gap = h * step
        self.n: dict[tuple[str, str | None], int] = {}
        self.hits: dict[tuple[str, str | None], int] = {}
        self.last: dict[tuple[str, str | None], int] = {}

    def add(self, inst: Instant) -> None:
        if not inst.outcome:
            return
        for agent, s in inst.votes.items():
            k = (agent, inst.regime)
            if k in self.last and inst.asof < self.last[k] + self.gap:
                continue
            self.last[k] = inst.asof
            self.n[k] = self.n.get(k, 0) + 1
            self.hits[k] = self.hits.get(k, 0) + (s == inst.outcome)

    def get(self, agent: str, regime: str | None) -> tuple[int, int]:
        k = (agent, regime)
        return self.hits.get(k, 0), self.n.get(k, 0)


def decide_abstain(inst: Instant, live: Live, p: DirectionParams) -> tuple[int, list[str]]:
    """T192: entra solo si ≥ `min_agree` calificados coinciden y ninguno calificado se opone."""
    up, down = [], []
    for agent, s in inst.votes.items():
        hits, n = live.get(agent, inst.regime)
        ci = wilson(hits, n)
        if n >= p.qualify_min and ci is not None and ci[0] > 0.5:
            (up if s > 0 else down).append(agent)
    if len(up) >= p.min_agree and not down:
        return 1, sorted(up)
    if len(down) >= p.min_agree and not up:
        return -1, sorted(down)
    return 0, sorted(up + down)


def weights_at(inst: Instant, live: Live, p: DirectionParams) -> dict[str, float]:
    """T193: peso = máx(0, 2·acierto encogido − 1); el previo empuja hacia la moneda."""
    out = {}
    k = p.prior_strength
    for agent in inst.votes:
        hits, n = live.get(agent, inst.regime)
        acc = (hits + k / 2) / (n + k)
        out[agent] = max(0.0, 2 * acc - 1)
    return out


def decide_weighted(inst: Instant, live: Live, p: DirectionParams) -> tuple[int, dict]:
    w = weights_at(inst, live, p)
    score = sum(w[a] * s for a, s in inst.votes.items())
    if not any(w.values()) or score == 0:
        return 0, {a: round(x, 4) for a, x in w.items() if x > 0}
    return (1 if score > 0 else -1), {a: round(x, 4) for a, x in w.items() if x > 0}


def walk(instants: Sequence[Instant], step: int, p: DirectionParams) -> list[dict]:
    """Decisión de cada sombra en cada instante, con lo resuelto hasta ese momento."""
    live = Live(p.primary, step)
    pending: deque[Instant] = deque()
    out = []
    for inst in sorted(instants, key=lambda x: x.asof):
        while pending and pending[0].asof + p.primary * step <= inst.asof:
            live.add(pending.popleft())
        a, who = decide_abstain(inst, live, p)
        w, ws = decide_weighted(inst, live, p)
        out.append({"inst": inst, ABSTAIN: a, WEIGHTED: w, "qualified": who, "weights": ws})
        pending.append(inst)
    return out


def compare(decisions: Sequence[dict], name: str, step: int, p: DirectionParams) -> dict:
    """Sombra frente a la síntesis v1 en los mismos instantes, muestra sin solape."""
    total = len(decisions)
    active = [d for d in decisions if d[name]]
    pairs, last = [], None
    for d in decisions:
        inst = d["inst"]
        if not (d[name] and inst.synth and inst.outcome):
            continue
        if last is None or inst.asof >= last + p.primary * step:
            pairs.append(d)
            last = inst.asof
    n = len(pairs)
    hs = sum(d[name] == d["inst"].outcome for d in pairs)
    hb = sum(d["inst"].synth == d["inst"].outcome for d in pairs)
    b = sum(d[name] == d["inst"].outcome != d["inst"].synth for d in pairs)
    c = sum(d["inst"].synth == d["inst"].outcome != d[name] for d in pairs)
    skipped = [d for d in decisions if not d[name] and d["inst"].synth and d["inst"].outcome]
    sk_eff, last = [], None
    for d in skipped:
        if last is None or d["inst"].asof >= last + p.primary * step:
            sk_eff.append(d)
            last = d["inst"].asof
    sk_hits = sum(d["inst"].synth == d["inst"].outcome for d in sk_eff)
    ci = wilson(hs, n)
    now = decisions[-1] if decisions else None
    return {"n_pairs": n, "acc_shadow": hs / n if n else None,
            "acc_synth": hb / n if n else None, "delta": (hs - hb) / n if n else None,
            "discordant": [b, c], "p": mcnemar_greater(b, c), "ci95": list(ci) if ci else None,
            "coverage": len(active) / total if total else None, "instants": total,
            "synth_when_abstained": {"n_eff": len(sk_eff),
                                     "acc": sk_hits / len(sk_eff) if sk_eff else None},
            "now": None if now is None else {"asof": now["inst"].asof, "decision": now[name],
                                             "qualified": now["qualified"],
                                             "weights": now["weights"]}}


def gate(results: dict[str, dict], p: DirectionParams) -> None:
    """Holm sobre la familia (sombra × marco) y puerta en sombra. Modifica `results`."""
    adj = holm({k: (r["p"] if r["n_pairs"] >= p.gate_min_pairs else None)
                for k, r in results.items()})
    for k, r in results.items():
        r["p_holm"] = adj.get(k)
        r["passes"] = bool(
            r["n_pairs"] >= p.gate_min_pairs and r["p_holm"] is not None
            and r["p_holm"] < p.alpha and (r["delta"] or 0) >= p.gate_min_delta
            and r["ci95"] and r["ci95"][0] > 0.5)
