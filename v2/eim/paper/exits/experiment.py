"""El experimento pre-registrado de T134: corre la rejilla entera y aplica §5.4 tal cual.

Orden fijo, el del pre-registro, y no otro:

1. **Rasgos** por estimador σ, y las **bases** (M0 y M1 con sus valores vigentes).
2. **Pliegues** con el embargo medido sobre las bases, y el **cuantil del MAE de las ganadoras**
   (E5) con la salida de referencia que nombra el pre-registro.
3. **Las 89 variantes** de la rejilla, por **lotes**: el banco guarda una operación por idea y por
   política, así que las 89 a la vez serían millones de objetos en memoria. Cada lote lleva las dos
   bases dentro, de modo que el emparejado es exacto, y se queda solo con los agregados.
4. **Romano-Wolf y Holm** sobre todas las variantes a la vez, con el mismo remuestreo de días.
5. **PBO** por CSCV con el rendimiento por pliegue.
6. **Estrés de costos** ×1,5 y ×2, solo en las que pasan el criterio 1 con el costo base (una que
   no lo pasa al costo base tampoco lo pasaría con costos mayores: no cambia ningún veredicto).
7. **Control aleatorio** contra el nulo por series sustitutas, solo en esas mismas.
8. **Veredicto** de los ocho criterios y los insumos de potencia que T135 necesita (E9).

Puro salvo el reloj: recibe el camino y las ideas ya leídos.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from eim.paper.exits import bench, metrics, stats, surrogate
from eim.paper.exits import walkforward as wf
from eim.paper.exits.grid import Variant, neighbours
from eim.paper.exits.policy import ExitContext
from eim.paper.exits.prereg import Prereg
from eim.paper.exits.verdict import judge
from eim.paper.ideas import Idea
from eim.validation.stats import rng_for

HOUR_MS = 3_600_000
WEEK_MS = 7 * 86_400_000
BATCH = 8               # variantes por lote, además de las dos bases


@dataclass
class Totals:
    """Lo que se guarda de cada variante; las operaciones se tiran al cerrar su lote."""

    test: dict
    all: dict
    years: dict
    folds: list[float | None]
    diffs: dict[str, list[tuple[int, float]]]
    cuts: dict
    n_closed: int
    var_paired: dict[str, float | None]


def _years_of(trades: Sequence[bench.BenchTrade], years: Sequence[int]) -> dict:
    out = {}
    for y in years:
        rs = [t.r for t in trades if wf.iso(t.t).startswith(str(y))]
        out[str(y)] = float(np.mean(rs)) if rs else None
    return out


def _fold_deltas(tr: Sequence[bench.BenchTrade], base: Sequence[bench.BenchTrade],
                 fs: Sequence[wf.Fold]) -> list[float | None]:
    """ΔE[R] del pliegue frente a la base, sobre las ideas que las dos cerraron."""
    by_id = {t.id: t for t in base}
    out: list[float | None] = []
    for f in fs:
        d = [t.r - by_id[t.id].r for t in wf.test_trades(tr, f) if t.id in by_id]
        out.append(float(np.mean(d)) if d else None)
    return out


def run_batch(ideas: Sequence[Idea], bases: Sequence[Variant], batch: Sequence[Variant],
              ctx: ExitContext, pr: Prereg, fs: Sequence[wf.Fold],
              rng: np.random.Generator) -> dict[str, Totals]:
    """Un lote con las dos bases dentro: agregados por variante y diferencias emparejadas."""
    pols = [*(v.policy for v in bases), *(v.policy for v in batch)]
    b = bench.run(ideas, pols, ctx, pr.risk_usd)
    # `paired_only=False` a propósito. El conjunto emparejado de `bench` es la intersección de
    # TODAS las políticas de la corrida, así que con él las cifras de una variante dependerían de
    # con quién le toca lote —y de la composición de la rejilla—, que es inaceptable. Cada
    # variante se mide sobre las ideas que ELLA cerró, y cada comparación contra una base se hace
    # sobre las ideas que cerraron las dos, con su propio n a la vista.
    base_tr = {v.id: b.trades(v.id, paired_only=False) for v in bases}
    base_test = {k: [t for f in fs for t in wf.test_trades(v, f)] for k, v in base_tr.items()}
    out: dict[str, Totals] = {}
    for v in (*bases, *batch):
        tr = b.trades(v.id, paired_only=False)
        tested = [t for f in fs for t in wf.test_trades(tr, f)]
        diffs, var_p = {}, {}
        for bid, btest in base_test.items():
            if bid == v.id:
                continue
            by_id = {t.id: t for t in btest}
            pairs = [(t.day, t.r - by_id[t.id].r) for t in tested if t.id in by_id]
            diffs[bid] = pairs
            d = np.array([x[1] for x in pairs], dtype=float)
            var_p[bid] = float(d.var(ddof=1)) if len(d) > 1 else None
        out[v.id] = Totals(
            test=metrics.summary(tested, pr.ruin.risk_pct, pr.ruin.trades, pr.ruin.reps, rng),
            all=metrics.summary(tr),
            years=_years_of(tested, pr.accept.years),
            folds=_fold_deltas(tr, base_tr.get(bases[0].id, []), fs),
            diffs=diffs, n_closed=len(tr), var_paired=var_p,
            cuts={k: metrics.by_group(tested, k)
                  for k in ("regime", "timeframe", "sid", "side")})
    return out


def trades_per_week(ideas: Sequence[Idea], n_closed: int) -> float | None:
    """Operaciones cerradas por semana: el otro insumo de la potencia de E9."""
    if not ideas or n_closed <= 0:
        return None
    span = max(i.t for i in ideas) - min(i.t for i in ideas)
    return None if span <= 0 else n_closed / (span / WEEK_MS)


def control_null(pr: Prereg, variants: Sequence[Variant], fine_c: np.ndarray, px0: float,
                 t0: int, bars: int, ep, spec, make_ideas: Callable, log=None) -> dict:
    """Criterio 6: el bruto del control sobre la serie real frente al de las sustitutas."""
    cfg = pr.control
    if not cfg.by_surrogates or not len(fine_c):
        return {}
    null: dict[str, list[float]] = {v.id: [] for v in variants}
    for s in range(cfg.surrogates):
        rng = rng_for(pr.seed, f"{pr.version}|sur|{s}")
        coarse, fine = surrogate.surrogate_of(fine_c, rng, bars=bars, px0=px0, t0=t0,
                                              block=cfg.block_minutes)
        if not len(coarse.t):
            continue
        ctx = ExitContext(path=coarse, ep=ep, spec=spec, fine=fine)
        ideas = make_ideas(coarse, s)
        b = bench.run(ideas, [v.policy for v in variants], ctx, pr.risk_usd)
        for v in variants:
            ts = b.trades(v.id, paired_only=False)
            if ts:
                null[v.id].append(float(np.mean([t.r + t.cost_r for t in ts])))
        if log and (s + 1) % 5 == 0:
            log(f"  sustitutas {s + 1}/{cfg.surrogates}")
    return null


def verdicts(pr: Prereg, vs: Sequence[Variant], bases: Sequence[Variant],
             tot: dict[str, Totals], mult: dict[str, dict], pbo: dict,
             plateau: dict[str, bool], control: dict[str, dict],
             stress: dict[str, dict] | None = None,
             stress_tot: dict[str, Totals] | None = None) -> list:
    """Veredicto de §5.4 de cada variante que no es base.

    `stress` son los bloques de multiplicidad de la corrida con el deslizamiento ×1,5 y
    `stress_tot` sus agregados; una variante que no se midió con estrés deja su criterio 8
    pendiente, nunca cumplido.
    """
    base_m = {v.id: tot[v.id].test for v in bases if v.id in tot}
    stressed = set(stress_tot or ())
    out = []
    for v in vs:
        if v.id in base_m or v.id not in tot:
            continue
        deltas = {b: _delta_of(mult, b, v.id, tot[v.id], tot[b]) for b in base_m}
        st = None
        if v.id in stressed and stress and stress_tot:
            st = {b: _delta_of(stress, b, v.id, stress_tot[v.id], stress_tot.get(b))
                  for b in base_m if b in stress_tot}
        out.append(judge(v.id, v.family, tot[v.id].test, base_m, deltas, tot[v.id].folds,
                         tot[v.id].years, plateau.get(v.id), pbo.get("pbo"),
                         control.get(v.id), st, pr.accept))
    return out


def _delta_of(mult: dict[str, dict], base: str, vid: str, t: Totals | None,
              bt: Totals | None) -> dict:
    blk = mult.get(base, {})
    d = None
    if t is not None and bt is not None:
        a, b = t.test.get("expectancy_r"), bt.test.get("expectancy_r")
        d = None if a is None or b is None else a - b
    return {"delta": d, "ci": blk.get("ci", {}).get(vid), "p_rw": blk.get("p_rw", {}).get(vid),
            "p_holm": blk.get("p_holm", {}).get(vid), "p_raw": blk.get("p_raw", {}).get(vid)}


def multiplicity(pr: Prereg, tot: dict[str, Totals], base: str, tag: str) -> dict:
    """Romano-Wolf y Holm de todas las variantes frente a `base`, con el mismo remuestreo."""
    diffs = {k: v.diffs.get(base, []) for k, v in tot.items() if k != base}
    rng = rng_for(pr.seed, f"{pr.version}|{tag}|rw|{base}")
    out = stats.romano_wolf({k: v for k, v in diffs.items() if len(v) >= 2},
                            pr.multiple.reps, rng)
    out["ci"] = {k: list(stats.paired_ci(d, pr.bootstrap.reps, pr.bootstrap.level,
                                         rng_for(pr.seed, f"{pr.version}|{tag}|ci|{k}|{base}")))
                 for k, d in diffs.items() if len(d) >= 2}
    out["base"] = base
    return out


def pbo_of(pr: Prereg, tot: dict[str, Totals]) -> dict:
    """PBO por CSCV con el ΔE[R] por pliegue de cada variante (0 donde no hay dato)."""
    cols = {k: [0.0 if x is None else float(x) for x in v.folds] for k, v in tot.items()}
    return stats.pbo(cols, pr.pbo.splits)


def plateau_of(tot: dict[str, Totals], vs: Sequence[Variant], base: str,
               keep: float) -> dict[str, bool]:
    """Meseta de §5.3 sobre LA MEJORA frente a la base, con los vecinos de la rejilla."""
    nb = neighbours(vs)
    ref = tot[base].test.get("expectancy_r") if base in tot else None
    gain = {}
    for k, v in tot.items():
        a = v.test.get("expectancy_r")
        gain[k] = None if a is None or ref is None else a - ref
    out = {}
    for k, g in gain.items():  # noqa: PLR1702
        ns = [gain[x] for x in nb.get(k, ()) if gain.get(x) is not None]
        out[k] = bool(ns) and g is not None and g > 0 and all(x >= keep * g for x in ns)
    return out


def power_inputs(pr: Prereg, tot: dict[str, Totals], ideas: Sequence[Idea],
                 bases: Sequence[Variant]) -> dict:
    """Lo que T135 necesita para calcular la potencia (E9): varianza y ritmo de operaciones."""
    out = {}
    for k, v in tot.items():
        out[k] = {"var_paired": v.var_paired,
                  "sd_paired": {b: (None if x is None else float(np.sqrt(x)))
                                for b, x in v.var_paired.items()},
                  "n_closed": v.n_closed,
                  "n_tested": v.test.get("n", 0),
                  "trades_per_week": trades_per_week(ideas, v.n_closed)}
    for v in bases:
        if v.id in out:
            out[v.id]["is_base"] = True
    out["_nota"] = ("`var_paired` es la varianza de las diferencias emparejadas por operación "
                    "frente a cada base, en R². Con ella y las operaciones por semana se calcula "
                    "el efecto mínimo detectable en T135 (E9); el ritmo real por perfil hay que "
                    "tomarlo del libro en vivo, porque el banco corre con tamaño fijo y sin "
                    "cupos.")
    return out


def elapsed(t0: float) -> float:
    return round(time.perf_counter() - t0, 1)
