"""Corrida de las versiones de T137: cada una con su propia sombra, y puntuada por la puerta de T49.

Cada versión simula **sus** operaciones: las ideas pasan por su regla y luego por `run_shadow`, una
idea viva a la vez por estrategia@marco. Con el stop más lejos una operación dura más y bloquea más
entradas, así que no sirve filtrar las operaciones del padre: y por eso ninguna versión hereda
evidencia de él, que es lo que pide la aceptación.

La puntuación es `gate.measure` + `gate.validate_all` sin cambiar nada: las lecturas descriptivas
solo le pasan otras ventanas (`entry_versions.complement`). Todas usan la misma familia de Holm con
los 520 intentos dentro, tengan o no operaciones.

Puro salvo el reloj: recibe las ideas, el camino y el registro ya leídos.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

import numpy as np

from eim.paper.engine import Path, run_shadow, simulate
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams
from eim.validation import stats as st
from eim.validation.criteria import Criteria
from eim.validation.entry_prereg import Prereg, Reading
from eim.validation.entry_versions import (
    BASE,
    FAR_MS,
    Rule,
    in_reading,
    windows_for,
)
from eim.validation.evidence import Trade, flip_idea, ref_price, select, trade_of
from eim.validation.gate import Verdict, measure, validate_all
from eim.validation.lineage import Version, iso_ms


@dataclass
class VariantRun:
    """Lo que queda de una variante al simularla: operaciones por estrategia@marco y recuentos."""

    vid: str
    trades: dict[str, list[Trade]] = field(default_factory=dict)
    stats: dict[str, Counter] = field(default_factory=dict)
    cost_sum: dict[str, float] = field(default_factory=dict)


def run_variant(ideas: Sequence[Idea], rule: Rule, fp_of: Mapping[str, str], path: Path,
                ep: ExecParams, flip_from: int = FAR_MS, stats_from: int = 0) -> VariantRun:
    """Aplica la regla, corre la sombra de la versión y convierte en `Trade` lo que cerró.

    `flip_from`: desde cuándo se simula el lado contrario para V3 (antes de ahí no se mide). El
    padre no lo necesita. `stats_from`: desde cuándo cuentan los recuentos de ideas movidas y
    vetadas; solo sirven para saber qué hizo la variante donde se mide.
    """
    out = VariantRun(rule.vid)
    kept: list[Idea] = []
    for i in ideas:
        w, moved, cost = rule.apply(i)
        if i.t >= stats_from:
            c = out.stats.setdefault(i.sid, Counter())
            c["ideas"] += 1
            c["moved"] += int(moved)
            c["vetoed"] += int(w is None)
            out.cost_sum[i.sid] = out.cost_sum.get(i.sid, 0.0) + cost
        if w is not None:
            kept.append(replace(w, version=fp_of.get(i.sid, "")))
    for o in run_shadow(kept, path, ep):
        if o.status != "CERRADA":
            continue
        flip = (simulate(flip_idea(o.idea, ref_price(o, path)), path, ep)
                if o.idea.t >= flip_from else None)
        t = trade_of(o, flip)
        if t is not None:
            out.trades.setdefault(o.idea.sid, []).append(t)
    return out


def holm_family(prior: Mapping[str, float | None], symbol: str,
                versions: Iterable[Version]) -> dict[str, float | None]:
    """La familia completa: lo ya registrado + todos los intentos de T137, midan algo o no."""
    out = dict(prior)
    for v in versions:
        out.setdefault(f"{symbol}|{v.label}", None)
    return out


def score_reading(r: Reading, versions: Sequence[tuple[Version, str]],
                  run_by_variant: Mapping[str, VariantRun], registry: Sequence[Version],
                  family: Mapping[str, float | None], crit: Criteria, symbol: str, asof: int,
                  prices: tuple[np.ndarray, np.ndarray] | None) -> list[Verdict]:
    """Veredictos de una lectura con la puerta tal cual. `versions`: (versión, variante)."""
    attempts = len(family)
    items = []
    for v, vid in versions:
        if not in_reading(r, v.sid):
            continue
        wins = windows_for(r, v, [x for x in registry if x.sid == v.sid])
        trades = run_by_variant[vid].trades.get(v.sid, [])
        m = measure(f"{symbol}|{v.label}", trades, wins, symbol, asof, crit, attempts, prices)
        items.append((v, m, wins))
    prior = {k: p for k, p in family.items() if k not in {m.label for _, m, _ in items}}
    return validate_all(items, prior, crit)


def pooled(trades: Sequence[Trade]) -> dict:
    """Agregado de un grupo de operaciones: lo comparable con T134 y T136."""
    if not trades:
        return {"n": 0, "mean_r": None, "win_rate": None, "pf": None, "cost_r": None,
                "gross_r": None}
    r = np.array([x.r for x in trades], dtype=float)
    c = np.array([x.cost_r for x in trades], dtype=float)
    return {"n": len(r), "mean_r": float(r.mean()), "win_rate": float((r > 0).mean()),
            "pf": st.profit_factor(r), "cost_r": float(c.mean()), "gross_r": float((r + c).mean())}


def pooled_table(r: Reading, parent: Mapping[str, Version],
                 versions: Sequence[tuple[Version, str]],
                 run_by_variant: Mapping[str, VariantRun], registry: Sequence[Version],
                 symbol: str, asof: int) -> dict[str, dict[str, dict]]:
    """variante → marco → agregado en esta lectura, con la versión padre al lado para comparar."""
    groups: dict[tuple[str, str], list[Trade]] = {}
    rows = [*versions, *((v, BASE) for v in parent.values())]
    for v, vid in rows:
        if not in_reading(r, v.sid) or vid not in run_by_variant:
            continue
        wins = windows_for(r, v, [x for x in registry if x.sid == v.sid])
        got = select(run_by_variant[vid].trades.get(v.sid, []), wins, symbol, asof)
        groups.setdefault((vid, v.timeframe), []).extend(got.oos)
    out: dict[str, dict[str, dict]] = {}
    for (vid, tf), ts in sorted(groups.items()):
        out.setdefault(vid, {})[tf] = pooled(ts)
    for vid, by_tf in out.items():
        by_tf["todos"] = pooled([t for (k, _), ts in groups.items() if k == vid for t in ts])
    return out


def cost_summary(run: VariantRun) -> dict[str, dict]:
    """Por marco: ideas, cuántas movió la geometría, cuántas vetó el tope y su costo ex ante."""
    tot: dict[str, Counter] = {}
    cost: dict[str, float] = {}
    for sid, c in run.stats.items():
        tf = sid.split("@")[1]
        tot.setdefault(tf, Counter()).update(c)
        cost[tf] = cost.get(tf, 0.0) + run.cost_sum.get(sid, 0.0)
    out = {}
    for tf, c in sorted(tot.items()):
        n = c["ideas"]
        out[tf] = {"ideas": n, "moved": c["moved"], "vetoed": c["vetoed"],
                   "moved_frac": c["moved"] / n if n else None,
                   "vetoed_frac": c["vetoed"] / n if n else None,
                   "cost_ex_ante_r": cost[tf] / n if n else None}
    return out


def is_inert(run: VariantRun, sid: str, has_geometry: bool) -> bool:
    """Una versión con geometría que no movió ni un SL es su padre con otro nombre (T134)."""
    return has_geometry and run.stats.get(sid, Counter())["moved"] == 0


def checks_of(v: Verdict) -> dict[str, bool | None]:
    return {c.id: c.ok for c in v.checks}


def candidates(pr: Prereg, by_reading: Mapping[str, Sequence[Verdict]],
               inert: Mapping[str, bool], variant_of: Mapping[str, str],
               control: Mapping[str, dict]) -> list[dict]:
    """La regla de lectura del pre-registro, sin más grados de libertad: qué versión la cumple."""
    reserve = {x.version.label: x for x in by_reading.get("reserva", ())}
    out = []
    for b in by_reading.get("banco", ()):
        label = b.version.label
        ck = checks_of(b)
        vid = variant_of[label]
        res = reserve.get(label)
        ctl = control.get(vid) or {}
        passed = {
            "banco_v1_v2_v3_v4_v6": all(ck[k] is True for k in ("V1", "V2", "V3", "V4", "V6")),
            "banco_v5_no_falla": ck["V5"] is not False,
            "reserva_n_y_r": bool(res is not None and res.measure.n >= 20
                                  and (res.measure.mean_r or 0.0) > 0),
            "no_inerte": not inert.get(label, False),
            "control": ctl.get("ok") is True and ctl.get("tested", True) is True,
        }
        if all(passed.values()):
            out.append({"id": label, "variant": vid, "passed": passed})
    return out


def sample_table(pr: Prereg, crit_all: Criteria, versions, runs, registry, parents, sym: str,
                 asof: int) -> dict:
    """Muestra por lectura: operaciones y versiones que llegan al mínimo de V1."""
    crit = crit_all.v1_data
    out = {}
    for r in pr.readings:
        meets, total = {}, {}
        for v, vid in versions:
            if not in_reading(r, v.sid):
                continue
            wins = windows_for(r, v, [x for x in registry if x.sid == v.sid])
            got = select(runs[vid].trades.get(v.sid, []), wins, sym, asof).oos
            by_regime: dict[str, int] = {}
            for t in got:
                by_regime[t.regime] = by_regime.get(t.regime, 0) + 1
            big = sum(1 for n in by_regime.values() if n >= crit.min_per_regime)
            ok = len(got) >= crit.min_trades and big >= crit.min_regimes
            total[vid] = total.get(vid, 0) + 1
            meets[vid] = meets.get(vid, 0) + int(ok)
        out[r.id] = {"meets_v1": meets, "versions": total,
                     "pooled": pooled_table(r, parents, versions, runs, registry, sym, asof)}
    return out


def tf15_block(pr, runs, parents_ids, asof) -> dict:
    """15 m: todo el tramo con contextos y, aparte, desde que M8 tiene cuantil."""
    start = iso_ms(pr.m8_folds.tf15m.test_from)
    out = {}
    for vid in ("base", *parents_ids):
        ts = [t for sid, xs in runs[vid].trades.items() if sid.endswith("@15m") for t in xs
              if t.exit_t <= asof]
        out[vid] = {"todo": pooled(ts),
                    "desde 2026-10-16": pooled([t for t in ts if t.t >= start])}
    return {"note": pr.timeframe_15m.note, "pooled": out}


def cap_left_out(pooled_banco: dict, pooled_15: dict) -> list[dict]:
    """Operaciones que deja fuera el tope frente a la gemela sin tope (T136 midió el 89 %)."""
    out = []
    pairs = (("tope", "base"), ("m8_tope", "m8"), ("s1_tope", "s1"))
    for with_, without in pairs:
        for scope, a, b in (
                ("1 h y 4 h, banco", pooled_banco.get(with_, {}).get("todos"),
                 pooled_banco.get(without, {}).get("todos")),
                ("15 m, todo", pooled_15.get(with_, {}).get("todo"),
                 pooled_15.get(without, {}).get("todo"))):
            if not a or not b or not b["n"]:
                continue
            out.append({"with": f"{with_} ({scope})", "without": without, "n_with": a["n"],
                        "n_without": b["n"], "left_out": 1 - a["n"] / b["n"]})
    return out
