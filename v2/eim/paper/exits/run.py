"""Corrida completa del banco de salidas (T131): de las ideas al veredicto, con el pre-registro.

Junta las piezas en el orden que fija el pre-registro y no en otro:

1. **Variantes** de la rejilla que hoy existen (M0 y M1; T132 y T133 traen las demás). Las
   pendientes se declaran, porque cuentan como intentos en el Sharpe deflactado y en las
   correcciones aunque no se corran.
2. **Banco emparejado** con tamaño fijo: todas las variantes sobre las mismas entradas.
3. **Pliegues** de 12 + 3 meses con purga y embargo, y la comprobación de fuga.
4. **Selección** dentro de cada tramo de ajuste con el objetivo pre-registrado.
5. **Pruebas múltiples** sobre los tramos de PRUEBA: Romano-Wolf (principal) y Holm (referencia).
6. **PBO** por CSCV con el rendimiento de cada variante en cada tramo de prueba.
7. **Control aleatorio** y **estrés de costos**.

Nada aquí decide si una salida se adopta: eso es T134. Esto solo mide, y deja a la vista lo que no
se pudo medir.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields

import numpy as np

from eim.paper.engine import simulate
from eim.paper.exits import bench, metrics, select, stats
from eim.paper.exits import walkforward as wf
from eim.paper.exits.policy import ExitContext, ExitPolicy, LadderExit, ShadowExit
from eim.paper.exits.prereg import Prereg
from eim.paper.ideas import Idea
from eim.paper.ladder import simulate_ladder
from eim.paper.params import LadderParams
from eim.validation.stats import dsr, rng_for

HOUR_MS = 3_600_000
BASE_LADDER_FIRST_R = 0.1       # la escalera vigente de los perfiles Conservador y Moderado
BASE_BE = (1.0, 0.1)            # el BE+ vigente de `ExecParams` (la salida A de T111)


@dataclass(frozen=True)
class Variant:
    """Una variante corrible de la rejilla: su política y la perilla que la distingue."""

    id: str
    family: str
    policy: ExitPolicy
    knob: float

    @property
    def is_base(self) -> bool:
        return self.id in (base_id("M0"), base_id("M1"))


def base_id(family: str) -> str:
    if family == "M0":
        return f"M0 first_r={BASE_LADDER_FIRST_R:g}"
    return f"M1 be={BASE_BE[0]:g}/{BASE_BE[1]:g}"


def variants_of(pr: Prereg, ladder: LadderParams) -> list[Variant]:
    """Las variantes implementadas de la rejilla pre-registrada, en su orden de rejilla."""
    out: list[Variant] = []
    for v in pr.item("M0").params["first_r"]:
        lp = ladder.model_copy(update={"basis": "r", "first_r": v, "step_r": v / 2})
        vid = f"M0 first_r={v:g}"
        out.append(Variant(vid, "M0", LadderExit(lp, id=vid, label=vid), float(v)))
    m1 = pr.item("M1").params
    for trig in m1["be_trigger_r"]:
        for lock in m1["be_lock_r"]:
            vid = f"M1 be={trig:g}/{lock:g}"
            out.append(Variant(vid, "M1", ShadowExit(
                id=vid, label=vid,
                overrides={"be_trigger_r": float(trig), "be_lock_r": float(lock)}), float(trig)))
    return out


def neighbours_of(vs: Sequence[Variant]) -> dict[str, list[str]]:
    """Vecinos a ±1 paso DENTRO de cada familia (la meseta no cruza de M0 a M1)."""
    out: dict[str, list[str]] = {}
    for fam in dict.fromkeys(v.family for v in vs):
        same = [v for v in vs if v.family == fam]
        for i, v in enumerate(same):
            out[v.id] = [same[j].id for j in (i - 1, i + 1) if 0 <= j < len(same)]
    return out


def _tested(trades: Sequence[bench.BenchTrade], fs: Sequence[wf.Fold]) -> list:
    """Las operaciones que caen en algún tramo de prueba: lo que se informa fuera de muestra."""
    return [t for f in fs for t in wf.test_trades(trades, f)]


def _years(trades: Sequence[bench.BenchTrade], years: Sequence[int]) -> dict[str, float | None]:
    """E[R] por año natural (criterio 4 de §5.4)."""
    out: dict[str, float | None] = {}
    for y in years:
        rs = [t.r for t in trades if wf.iso(t.t).startswith(str(y))]
        out[str(y)] = float(np.mean(rs)) if rs else None
    return out


def fold_report(b: bench.Bench, vs: Sequence[Variant], fs: Sequence[wf.Fold],
                pr: Prereg) -> dict:
    """Por pliegue: purga, fugas, métricas de ajuste y de prueba y la variante elegida."""
    nb = neighbours_of(vs)
    out = []
    for f in fs:
        fit_scores, block = {}, {"fold": f.to_json(), "fit": {}, "test": {}}
        base_fit = metrics.summary(wf.fit_trades(b.trades(base_id("M0")), f))
        leaks: list[str] = []
        for v in vs:
            tr = b.trades(v.id)
            fit, test = wf.fit_trades(tr, f), wf.test_trades(tr, f)
            leaks += wf.leaks(fit, f)
            m_fit = metrics.summary(fit)
            block["fit"][v.id] = {**m_fit, "purga": wf.purged(tr, f)}
            block["test"][v.id] = metrics.summary(test)
            fit_scores[v.id] = select.score_of(v.id, m_fit, base_fit,
                                               min_trades=1)
        block["leaks"] = leaks
        block["selection"] = select.choose(fit_scores, nb, pr.selection.plateau_keep)
        block["scores"] = {k: s.to_json() for k, s in fit_scores.items()}
        out.append(block)
    return {"folds": out, "neighbours": nb,
            "leaks_total": sum(len(x["leaks"]) for x in out)}


def multiplicity(b: bench.Bench, vs: Sequence[Variant], fs: Sequence[wf.Fold],
                 pr: Prereg, base: str) -> dict:
    """Romano-Wolf y Holm del ΔE[R] emparejado frente a `base`, solo en los tramos de prueba."""
    keep = {t.id for t in _tested(b.trades(base), fs)}
    rows = [r for r in b.paired() if r.id in keep]
    diffs = {v.id: [(r.by_policy[v.id].day, r.by_policy[v.id].r - r.by_policy[base].r)
                    for r in rows]
             for v in vs if v.id != base}
    rng = rng_for(pr.seed, f"{pr.version}|rw|{base}")
    out = stats.romano_wolf(diffs, pr.multiple.reps, rng)
    out["ci"] = {k: list(stats.paired_ci(d, pr.bootstrap.reps, pr.bootstrap.level,
                                         rng_for(pr.seed, f"{pr.version}|ci|{k}|{base}")))
                 for k, d in diffs.items() if len(d) >= 2}
    out["base"] = base
    out["n_paired_in_test"] = len(keep)
    return out


def pbo_of(b: bench.Bench, vs: Sequence[Variant], fs: Sequence[wf.Fold], pr: Prereg) -> dict:
    """PBO por CSCV con el E[R] de cada variante en cada tramo de prueba."""
    cols = {}
    for v in vs:
        tr = b.trades(v.id)
        row = [metrics.summary(wf.test_trades(tr, f)).get("expectancy_r") for f in fs]
        cols[v.id] = [0.0 if x is None else float(x) for x in row]
    return stats.pbo(cols, pr.pbo.splits)


def analyse(ideas: Sequence[Idea], ctx: ExitContext, pr: Prereg, ladder: LadderParams,
            cost_factor: float = 1.0) -> dict:
    """Corrida del banco sobre `ideas` con la rejilla implementada. Devuelve todo en un dict."""
    vs = variants_of(pr, ladder)
    real = bench.real_ideas(ideas)
    b = bench.run(real, [v.policy for v in vs], ctx, pr.risk_usd)
    start, end = _span(b, pr)
    embargo = wf.embargo_for([t for v in vs for t in b.trades(v.id)],
                             feature_ms=int(pr.design.embargo_feature_hours * HOUR_MS),
                             q=pr.design.embargo_quantile)
    fs = wf.folds(start, end, embargo, pr.design.fit_months, pr.design.test_months,
                  pr.design.step_months)
    rng = rng_for(pr.seed, f"{pr.version}|ruin")
    per_variant = {}
    for v in vs:
        tested = _tested(b.trades(v.id), fs)
        per_variant[v.id] = {
            "family": v.family, "knob": v.knob, "params": v.policy.params,
            "all": metrics.summary(b.trades(v.id), pr.ruin.risk_pct, pr.ruin.trades,
                                   pr.ruin.reps, rng),
            "test": metrics.summary(tested, pr.ruin.risk_pct, pr.ruin.trades, pr.ruin.reps, rng),
            "years": _years(tested, pr.accept.years),
            "by_regime": metrics.by_group(tested, "regime"),
            "by_timeframe": metrics.by_group(tested, "timeframe"),
            "by_side": metrics.by_group(tested, "side"),
            "dsr": dsr([t.r for t in tested], pr.attempts()),
        }
    return {
        "cost_factor": cost_factor, "attempts": pr.attempts(),
        "pending_variants": pr.pending(), "bench": b.to_json(),
        "window": {"from": wf.iso(start), "to": wf.iso(end),
                   "embargo_hours": round(embargo / HOUR_MS, 2)},
        "variants": per_variant,
        "walkforward": fold_report(b, vs, fs, pr),
        "multiplicity": {base: multiplicity(b, vs, fs, pr, base)
                         for base in (base_id("M0"), base_id("M1"))},
        "pbo": pbo_of(b, vs, fs, pr),
    }


def _span(b: bench.Bench, pr: Prereg) -> tuple[int, int]:
    """Ventana del diseño recortada a lo que el banco tiene de verdad (nada supuesto)."""
    lo, hi = wf.from_iso(pr.design.start), wf.from_iso(pr.design.end)
    if b.rows:
        lo, hi = max(lo, b.rows[0].t), min(hi, b.rows[-1].t)
    return lo, hi


def engine_identity(ideas: Sequence[Idea], ctx: ExitContext, ladder: LadderParams,
                    risk_usd: float, sample: int = 500) -> dict:
    """Regresión contra T111 sobre datos REALES: los adaptadores no cambian nada del motor.

    T111 llamó a `simulate_ladder` y a `engine.simulate`. Si M0 y M1 devuelven exactamente lo
    mismo que esas dos funciones, campo a campo, cualquier cifra de T111 sale igual del banco.
    Aquí se comprueba sobre las primeras `sample` ideas de la copia, con su camino y sus velas
    finas reales (las pruebas de `tests/paper/exits/test_policy.py` lo cubren con fixtures).
    """
    m0, m1 = LadderExit(ladder), ShadowExit()
    picked = sorted(ideas, key=lambda x: (x.t, x.id))[:sample]
    bad, checked = [], 0
    for idea in picked:
        qty = bench.qty_for(idea, ctx.spec, risk_usd)
        if qty <= 0:
            continue
        checked += 1
        pairs = ((m0.simulate(idea, ctx, qty),
                  simulate_ladder(idea, ctx.path, ctx.ep, ladder, qty, ctx.fine, spec=ctx.spec,
                                  guard=ctx.guard)),
                 (m1.simulate(idea, ctx, qty), simulate(idea, ctx.path, ctx.ep)))
        for pid, (got, want) in zip(("M0", "M1"), pairs, strict=True):
            diff = [f.name for f in fields(got)
                    if getattr(got, f.name) != getattr(want, f.name)]
            if diff:
                bad.append({"policy": pid, "idea": idea.id, "fields": diff})
    return {"checked": checked, "sample": len(picked), "mismatches": bad,
            "identical": not bad}


def control_report(ideas: Sequence[Idea], ctx: ExitContext, pr: Prereg,
                   ladder: LadderParams) -> dict:
    """Control aleatorio: las mismas salidas sobre las entradas de `control_aleatorio`."""
    ctrl = bench.control_ideas(ideas)
    if not ctrl:
        return {"n_ideas": 0, "note": "la copia no tiene entradas de control_aleatorio"}
    vs = variants_of(pr, ladder)
    b = bench.run(ctrl, [v.policy for v in vs], ctx, pr.risk_usd)
    out = {"n_ideas": len(ctrl), "variants": {}}
    for v in vs:
        tr = b.trades(v.id, paired_only=False)
        m = metrics.summary(tr)
        gross = [(t.day, t.r + t.cost_r) for t in tr]
        ci = stats.paired_ci(gross, pr.bootstrap.reps, pr.bootstrap.level,
                             rng_for(pr.seed, f"{pr.version}|ctrl|{v.id}"))
        out["variants"][v.id] = {
            "n": m.get("n", 0), "expectancy_r": m.get("expectancy_r"),
            "cost_r": m.get("cost_r"), "gross_ci": list(ci),
            "zero_in_gross_ci": bool(ci[0] <= 0 <= ci[1]) if ci[0] == ci[0] else None}
    return out
