"""Retroalimentación y estadística por estrategia (funciones puras).

`Learner.at(estrategia@marco, t)` usa SOLO operaciones sombra cerradas en `exit_t ≤ t`: el peso
que un perfil aplica en `t` no conoce el futuro. Las estrategias en pausa siguen evaluándose en la
sombra, así que vuelven solas si se recuperan.

Aprendizaje por contexto (T48): además, cada pérdida cuenta en su contexto (estrategia@marco ×
régimen × lado); un contexto que pierde de forma consistente se pausa aunque la estrategia en
conjunto siga activa (`Learner.context_at`).
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from eim.backtest.edge import holm
from eim.paper.engine import Outcome
from eim.paper.params import FeedbackParams

STD_FLOOR = 0.5       # R: evita errores estándar irrisorios con muestras chicas
MIN_N_TEST = 5        # muestra mínima para el contraste y Holm
STATES = {"observacion": "En observación", "activa": "Activa", "reforzada": "Reforzada",
          "reducida": "Reducida", "pausa": "En pausa"}


@dataclass(frozen=True)
class Judgement:
    weight: float
    state: str
    m: float          # expectativa contraída (R por operación)
    se: float
    n: int

    def to_json(self) -> dict:
        return {"weight": round(self.weight, 3), "state": self.state,
                "state_label": STATES[self.state], "m": round(self.m, 4),
                "se": None if math.isnan(self.se) else round(self.se, 4), "n": self.n}


def judge(rs: Sequence[float], p: FeedbackParams) -> Judgement:
    n = len(rs)
    if n == 0:
        return _verdict(0, 0.0, 0.0, 0.0, p)
    r = np.asarray(rs, dtype=float)
    w = 0.5 ** (np.arange(n)[::-1] / p.half_life)          # 1 = la más reciente
    return _verdict(n, float(w.sum()), float((w * r).sum()), float((w * r * r).sum()), p)


def _decayed_sums(rs: Sequence[float], half_life: float) -> list[tuple[float, float, float]]:
    """(Σw, Σw·r, Σw·r²) de cada prefijo, w = 0,5^(antigüedad/half_life): lo mismo que `judge`
    calcula sobre `rs[:n]`, pero en O(1) por consulta (S_n = d·S_{n−1} + término nuevo)."""
    d = 0.5 ** (1 / half_life)
    s0 = s1 = s2 = 0.0
    out = [(0.0, 0.0, 0.0)]
    for r in rs:
        s0, s1, s2 = d * s0 + 1.0, d * s1 + r, d * s2 + r * r
        out.append((s0, s1, s2))
    return out


def _verdict(n: int, sw: float, s1: float, s2: float, p: FeedbackParams) -> Judgement:
    """Juicio a partir de las sumas ponderadas de los últimos `n` resultados en R."""
    if n == 0:
        return Judgement(p.observe_w, "observacion", 0.0, float("nan"), 0)
    m = s1 / (sw + p.prior_n)
    mean_w = s1 / sw
    sd = max(STD_FLOOR, math.sqrt(max(0.0, s2 / sw - mean_w * mean_w)))
    se = sd / math.sqrt(sw + p.prior_n)
    if n < p.n_min:
        return Judgement(p.observe_w, "observacion", m, se, n)
    if m + p.z_pause * se < 0:
        return Judgement(0.0, "pausa", m, se, n)
    weight = min(p.w_max, max(p.w_min, 1 + p.gain * m))
    state = "reforzada" if weight > 1.05 else "reducida" if weight < 0.95 else "activa"
    return Judgement(weight, state, m, se, n)


def closed(outcomes: Iterable[Outcome]) -> list[Outcome]:
    return [o for o in outcomes if o.status == "CERRADA" and o.r is not None]


def context_key(o_or_idea) -> str:
    """estrategia@marco|régimen|lado (la unidad del aprendizaje por contexto)."""
    i = getattr(o_or_idea, "idea", o_or_idea)
    return f"{i.sid}|{i.regime or 'sin dato'}|{'largo' if i.side > 0 else 'corto'}"


def _index(pairs: dict[str, list[tuple[int, float]]]):
    return ({k: [t for t, _ in sorted(v)] for k, v in pairs.items()},
            {k: [r for _, r in sorted(v)] for k, v in pairs.items()})


class Learner:
    """Resultados sombra cerrados por estrategia@marco y por contexto, ordenados por cierre.

    Las sumas ponderadas de cada prefijo se calculan una vez por clave y vida media: cada juicio
    sale en O(1) (recalcularlo sobre todo lo cerrado hacía cuadrática la vista del bróker con la
    historia completa de T49)."""

    def __init__(self, outcomes: Iterable[Outcome]) -> None:
        by: dict[str, list[tuple[int, float]]] = {}
        ctx: dict[str, list[tuple[int, float]]] = {}
        for o in closed(outcomes):
            by.setdefault(o.idea.sid, []).append((o.exit_t, o.r))
            ctx.setdefault(context_key(o), []).append((o.exit_t, o.r))
        self._t, self._r = _index(by)
        self._ct, self._cr = _index(ctx)
        self._sums: dict[tuple, list[tuple[float, float, float]]] = {}

    def _judge(self, ts: dict[str, list[int]], rs: dict[str, list[float]], key: str, t: int,
               p: FeedbackParams) -> Judgement:
        n = bisect_right(ts.get(key, []), t)
        if n == 0:
            return _verdict(0, 0.0, 0.0, 0.0, p)
        sk = (id(rs), key, p.half_life)
        sums = self._sums.get(sk)
        if sums is None:
            sums = self._sums[sk] = _decayed_sums(rs[key], p.half_life)
        return _verdict(n, *sums[n], p)

    def at(self, sid: str, t: int, p: FeedbackParams) -> Judgement:
        return self._judge(self._t, self._r, sid, t, p)

    def context_at(self, idea, t: int, p: FeedbackParams) -> Judgement:
        """Juicio del contexto de la idea con lo cerrado hasta `t` (sin mirar el futuro)."""
        return self._judge(self._ct, self._cr, context_key(idea), t, p)


def _p_one_sided(r: np.ndarray) -> float | None:
    """p de H0: media ≤ 0 (aprox. normal); None con muestra chica."""
    if len(r) < MIN_N_TEST:
        return None
    sd = float(r.std(ddof=1))
    if sd <= 0:
        return 0.0 if r.mean() > 0 else 1.0
    z = float(r.mean()) / (sd / math.sqrt(len(r)))
    return 0.5 * math.erfc(z / math.sqrt(2))


def _max_dd(r: np.ndarray) -> float:
    if not len(r):
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(r)])
    return float((np.maximum.accumulate(eq) - eq).max())


def _group(os_: Sequence[Outcome], key) -> dict[str, dict]:
    g: dict[str, list[float]] = {}
    for o in os_:
        g.setdefault(key(o), []).append(o.r)
    return {k: {"n": len(v), "mean_r": round(float(np.mean(v)), 4)} for k, v in g.items()}


def _curve(os_: Sequence[Outcome], points: int = 60) -> list[tuple[int, float]]:
    os_ = sorted(os_, key=lambda o: o.exit_t)
    cum = np.cumsum([o.r for o in os_]) if os_ else np.array([])
    idx = np.unique(np.linspace(0, len(os_) - 1, min(points, len(os_))).astype(int)) \
        if os_ else []
    return [(os_[i].exit_t, round(float(cum[i]), 3)) for i in idx]


def _contexts(cl: Sequence[Outcome], p: FeedbackParams) -> dict[str, dict]:
    g: dict[str, list[float]] = {}
    for o in sorted(cl, key=lambda o: o.exit_t):
        g.setdefault(context_key(o).split("|", 1)[1], []).append(o.r)
    return {k: {"n": len(v), "mean_r": round(float(np.mean(v)), 4),
                "state": judge(v, p).state} for k, v in g.items()}


def strategy_stats(outcomes: Sequence[Outcome], strategies: Sequence[dict],
                   p: FeedbackParams | None = None) -> list[dict]:
    """Ficha por estrategia@marco (todas las del catálogo, aunque no hayan operado)."""
    p = p or FeedbackParams()
    by: dict[str, list[Outcome]] = {}
    for o in outcomes:
        by.setdefault(o.idea.sid, []).append(o)
    rows: list[dict] = []
    for info in strategies:
        os_ = by.get(info["id"], [])
        cl = closed(os_)
        r = np.array([o.r for o in cl], dtype=float)
        cnt = {s: sum(o.status == s for o in os_) for s in
               ("ABIERTA", "PENDIENTE", "CANCELADA", "RECHAZADA")}
        pos, neg = float(r[r > 0].sum()), float(-r[r < 0].sum())
        hold = [(o.exit_t - o.fill_t) / 3_600_000 for o in cl]
        row = {
            **info, "n": len(cl), "open": cnt["ABIERTA"], "pending": cnt["PENDIENTE"],
            "cancelled": cnt["CANCELADA"], "rejected": cnt["RECHAZADA"],
            "fill_rate": (round((len(cl) + cnt["ABIERTA"]) / (len(cl) + cnt["ABIERTA"]
                          + cnt["CANCELADA"]), 3) if len(cl) + cnt["ABIERTA"] + cnt["CANCELADA"]
                          else None),
            "win_rate": round(float((r > 0).mean()), 4) if len(r) else None,
            "mean_r": round(float(r.mean()), 4) if len(r) else None,
            "median_r": round(float(np.median(r)), 4) if len(r) else None,
            "sum_r": round(float(r.sum()), 3),
            "pf": round(pos / neg, 3) if neg > 0 else (None if pos == 0 else float("inf")),
            "max_dd_r": round(_max_dd(r), 3),
            "last10_r": round(float(r[-10:].mean()), 4) if len(r) else None,
            "mfe_r": round(float(np.mean([o.mfe_r for o in cl])), 3) if cl else None,
            "mae_r": round(float(np.mean([o.mae_r for o in cl])), 3) if cl else None,
            "hold_h": round(float(np.mean(hold)), 2) if hold else None,
            "p": _p_one_sided(r),
            "by_side": _group(cl, lambda o: "largo" if o.idea.side > 0 else "corto"),
            "by_regime": _group(cl, lambda o: o.idea.regime or "sin dato"),
            "by_reason": {k: v["n"] for k, v in _group(cl, lambda o: o.reason).items()},
            "by_cause": {k: v["n"] for k, v in _group([o for o in cl if o.cause],
                                                      lambda o: o.cause).items()},
            "by_context": _contexts(cl, p),
            "curve": _curve(cl),
            "judgement": judge(list(r), p).to_json(),
            "origin_live": sum(o.idea.origin == "vivo" for o in cl),
        }
        if row["pf"] == float("inf"):
            row["pf"] = None
        rows.append(row)
    adj = holm({x["id"]: x["p"] for x in rows if x["p"] is not None})
    ctrls = {x.get("timeframe"): x for x in rows if x["family"] == "control"}
    for x in rows:
        ctrl = ctrls.get(x.get("timeframe"))     # el control del mismo marco
        x["p_holm"] = None if x["p"] is None else round(adj[x["id"]], 4)
        x["p"] = None if x["p"] is None else round(x["p"], 4)
        x["vs_control"] = (round(x["mean_r"] - ctrl["mean_r"], 4)
                           if ctrl and ctrl["mean_r"] is not None and x["mean_r"] is not None
                           and x is not ctrl else None)
    return rows


def timeframe_stats(outcomes: Sequence[Outcome]) -> list[dict]:
    """Resultado sombra agregado por marco: ¿en qué temporalidad se gana más?"""
    g: dict[str, list[float]] = {}
    for o in closed(outcomes):
        g.setdefault(o.idea.timeframe, []).append(o.r)
    return [{"timeframe": tf, "n": len(v), "win_rate": round(float(np.mean(np.array(v) > 0)), 4),
             "mean_r": round(float(np.mean(v)), 4), "sum_r": round(float(np.sum(v)), 3)}
            for tf, v in sorted(g.items(), key=lambda x: x[0])]


def family_stats(rows: Sequence[dict]) -> list[dict]:
    """Agregado por familia, ponderado por número de operaciones."""
    fam: dict[str, list[dict]] = {}
    for x in rows:
        fam.setdefault(x["family"], []).append(x)
    out = []
    for f, xs in fam.items():
        n = sum(x["n"] for x in xs)
        s = sum(x["sum_r"] for x in xs)
        out.append({"family": f, "n": n, "sum_r": round(s, 3),
                    "mean_r": round(s / n, 4) if n else None, "strategies": len(xs)})
    return sorted(out, key=lambda x: -(x["mean_r"] if x["mean_r"] is not None else -9))
