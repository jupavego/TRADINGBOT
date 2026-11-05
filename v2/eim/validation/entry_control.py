"""Control de T137 y comprobación de regresión contra T134 y T136.

**El control de T134 no ponía a prueba la geometría.** `control_aleatorio@1h` no llegaba a la
muestra mínima de ganadoras, así que M8 no tocaba el SL y sobre las entradas al azar era M0 hasta
el último decimal (BACKLOG T134 (1)). Aquí el cuantil del control se toma de la estrategia con sus
mismas salidas (`entry_versions.QuantileBook`), y además se informa de cuántas ideas movió de
verdad: si una geometría casi no mueve nada, el control se declara «no la pone a prueba» y no cuenta
como aprobado, en vez de dar un «sí» que no mide nada.

El nulo es el de T134 (retornos reales barajados, `surrogate.py`), con una diferencia necesaria: la
distancia de SL y el R:B de las entradas al azar se sortean de las ideas reales del control, y la σ
sale de la propia serie sustituta. Con el 1 % fijo de T134, el tope de 0,08 R (un SL de al menos el
2 %) vetaría todas las entradas y no quedaría nada que medir.

**La regresión** reproduce con este mismo código lo ya publicado por T134 y T136. Si no coincide,
la geometría de T137 no es la que dio la señal, y entonces nada de lo demás vale.

Puro: recibe los caminos y las ideas ya leídos.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from eim.paper.engine import Path, simulate
from eim.paper.exits import bench, features, metrics, surrogate
from eim.paper.exits import walkforward as wf
from eim.paper.exits.candidates import InitialStopExit, sigma_floor, winners_mae_floor
from eim.paper.exits.policy import ExitContext, LadderExit
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams, LadderParams
from eim.paper.risk_budget import cost_r as ex_ante_cost
from eim.validation.entry_prereg import Prereg
from eim.validation.entry_run import VariantRun
from eim.validation.entry_versions import BASE, QuantileBook, rule_of
from eim.validation.evidence import cost_r
from eim.validation.stats import rng_for

SIGMA = "atr14"                  # el estimador con el que T134 aplica M8 y S1


@dataclass(frozen=True)
class Geometry:
    """La geometría real de las ideas de control: lo que se sortea en cada serie sustituta."""

    risk_frac: np.ndarray
    rr: np.ndarray
    hold_ms: int


def control_geometry(ideas: Sequence[Idea]) -> Geometry | None:
    """Distancias relativas y R:B de las ideas de control reales; None si no hay ninguna."""
    good = [i for i in ideas if i.entry > 0 and i.entry != i.sl]
    if not good:
        return None
    return Geometry(np.array([abs(i.entry - i.sl) / i.entry for i in good], dtype=float),
                    np.array([i.rr for i in good], dtype=float), int(good[0].hold_ms))


def random_ideas(path: Path, seed: int, n: int, g: Geometry, strategy: str, tf: str) -> list[Idea]:
    """Entradas al azar sobre una serie, con la geometría relativa del control real."""
    rng = np.random.default_rng([seed, 1370])
    last = len(path.t) - 2
    if last < 2:
        return []
    picks = sorted(rng.choice(np.arange(1, last), size=min(n, last - 1), replace=False))
    out = []
    for k, j in enumerate(picks):
        side = 1 if rng.random() < 0.5 else -1
        px = float(path.c[j])
        at = int(rng.integers(0, len(g.risk_frac)))
        d = px * float(g.risk_frac[at])
        out.append(Idea(id=f"S{seed}:{k}", strategy=strategy, family="control", symbol="BTCUSDT",
                        t=int(path.t[j]) + path.step, side=side, kind="market", entry=px,
                        sl=px - side * d, tp=px + side * float(g.rr[at]) * d, fill_ms=0,
                        hold_ms=g.hold_ms, conf=0.5, why=("control",), timeframe=tf))
    return out


def null_gross(pr: Prereg, variants: Sequence[str], fine_c: np.ndarray, px0: float, t0: int,
               g: Geometry, ep: ExecParams, tick: float, q0: float | None,
               log: Callable[[str], None] | None = None) -> tuple[dict, dict]:
    """Bruto medio por variante en cada sustituta, y la fracción de SL que movió cada una."""
    c = pr.control
    specs = {v: None if v == BASE else pr.variant(v) for v in variants}
    null: dict[str, list[float]] = {v: [] for v in variants}
    moved: dict[str, list[float]] = {v: [] for v in variants}
    for s in range(c.surrogates):
        rng = rng_for(pr.seed, f"{pr.version}|sur|{s}")
        coarse, _ = surrogate.surrogate_of(fine_c, rng, bars=c.bars, px0=px0, t0=t0,
                                           block=c.block_minutes)
        if not len(coarse.t):
            continue
        feats = features.build(coarse, SIGMA)
        ideas = random_ideas(coarse, s, c.ideas, g, c.strategy, c.timeframe)
        for v, spec in specs.items():
            rule = rule_of(spec, pr, feats, coarse.t, lambda _sid, _t: q0, tick)
            gross, n_moved = [], 0
            for i in ideas:
                w, mv, _ = rule.apply(i)
                n_moved += int(mv)
                if w is None:
                    continue
                o = simulate(w, coarse, ep)
                if o.status == "CERRADA" and o.r is not None:
                    gross.append(float(o.r) + cost_r(o))
            if gross:
                null[v].append(float(np.mean(gross)))
            moved[v].append(n_moved / len(ideas) if ideas else 0.0)
        if log and (s + 1) % 5 == 0:
            log(f"  sustitutas {s + 1}/{c.surrogates}")
    return null, moved


def real_gross(run: VariantRun, sid: str, start: int) -> tuple[float, int]:
    """Bruto medio de la versión de control sobre la serie real, desde `start`."""
    ts = [t for t in run.trades.get(sid, []) if t.t >= start]
    return (float(np.mean([t.r + t.cost_r for t in ts])) if ts else float("nan"), len(ts))


def control_report(pr: Prereg, runs: dict[str, VariantRun], null: dict, moved: dict,
                   start: int) -> dict[str, dict]:
    """Veredicto del control por variante: si destaca sobre el nulo y si de verdad la pone a prueba.

    El tope a secas no aparta ningún SL: lo que pone a prueba es qué entradas deja pasar, así que
    para él no se exige mover stops, y se comprueba que no se quede sin operaciones.
    """
    c = pr.control
    sid = f"{c.strategy}@{c.timeframe}"
    out = {}
    for vid, run in runs.items():
        gross, n = real_gross(run, sid, start)
        res = surrogate.verdict(gross, null.get(vid, []), c.alpha)
        st = run.stats.get(sid)
        frac = (st["moved"] / st["ideas"]) if st and st["ideas"] else 0.0
        spec = None if vid == BASE else pr.variant(vid)
        needs_move = spec is not None and spec.geometry is not None
        tested = (frac >= c.min_moved_frac) if needs_move else n > 0
        out[vid] = {**res, "n_real": n, "moved_frac_real": frac,
                    "moved_frac_null": float(np.mean(moved[vid])) if moved.get(vid) else None,
                    "tested": bool(tested)}
    return out


def check_parent(got: dict, want: dict, tol: float) -> dict:
    """El padre, corrido por el camino de las versiones, tiene que ser la M1 que publicó T134.

    Es lo que prueba el camino completo: de todas las ideas, por la regla y por `run_shadow`, sin
    tocar nada, se llega a las mismas operaciones que el banco midió con su propia salida.
    """
    a, b = got.get("mean_r"), want.get("expectancy_r")
    return {"n": got.get("n"), "expectancy_r": a, "want_n": want.get("n"),
            "want_expectancy_r": b, "ok": (a is not None and b is not None and abs(a - b) <= tol
                                           and got.get("n") == want.get("n"))}


def regression(ideas: Sequence[Idea], ctx: ExitContext, book: QuantileBook, atr, pr: Prereg,
               ladder: LadderParams, risk_usd: float, published: dict) -> dict:
    """Reproduce M8 q=0.95, S1 d_min=3 atr14 y el tope de 0,08 R con M0 sobre los tramos de T134."""
    path_t = ctx.path.t
    m8, s1 = "M8 q=0.95", "S1 d_min_sigma=3 sigma=atr14"
    base = "M0 first_r=0.1"
    lp = ladder.model_copy(update={"basis": "r", "first_r": 0.1, "step_r": 0.05})
    pols = [LadderExit(lp, id=base, label=base),
            InitialStopExit(m8, m8, "M8", atr, winners_mae_floor(atr, path_t, book.of),
                            inner=LadderExit(ladder, id=f"{m8}/M0", label=m8), knobs={"q": 0.95}),
            InitialStopExit(s1, s1, "S1", atr,
                            sigma_floor(atr, path_t, pr.geometry.s1.d_min_sigma),
                            inner=LadderExit(ladder, id=f"{s1}/M0", label=s1),
                            knobs={"d_min_sigma": 3.0})]
    b = bench.run(ideas, pols, ctx, risk_usd)
    folds = book.by_tf["1h"].folds[:-1]            # los 10 de T134, sin el pliegue siguiente
    by_id = {i.id: i for i in ideas}
    out = {}
    for vid in (base, m8, s1):
        tested = [t for f in folds for t in wf.test_trades(b.trades(vid, paired_only=False), f)]
        got = metrics.summary(tested)
        want = published.get(vid, {})
        out[vid] = {"n": got.get("n"), "expectancy_r": got.get("expectancy_r"),
                    "want_n": want.get("n"), "want_expectancy_r": want.get("expectancy_r")}
    # T136 mide el tope sobre lo que cerró la salida vigente, con el SL de la idea
    tested = [t for f in folds for t in wf.test_trades(b.trades(base, paired_only=False), f)]
    keep = [t for t in tested if ex_ante_cost(by_id[t.id].entry, by_id[t.id].sl,
                                              pr.cost_cap.est_cost_frac) <= pr.cost_cap.max_cost_r]
    want = published.get("cap", {})
    out["tope 0.08"] = {"n": len(keep),
                        "expectancy_r": float(np.mean([t.r for t in keep])) if keep else None,
                        "want_n": want.get("n"), "want_expectancy_r": want.get("expectancy_r")}
    tol = pr.regression.tolerance_r
    for row in out.values():
        a, b_ = row["expectancy_r"], row["want_expectancy_r"]
        row["ok"] = (a is not None and b_ is not None and abs(a - b_) <= tol
                     and row["n"] == row["want_n"])
    return out
