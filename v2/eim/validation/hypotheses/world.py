"""Las etapas de T139 sobre datos ya leídos: cobertura, banco y lectura limpia. Puro salvo el reloj.

El orden importa: la lectura limpia es de un solo uso, así que el camino se comprueba antes donde ya
no queda nada que gastar. El script (`scripts/t139_entradas.py`) solo lee y escribe.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from eim.core import Candle
from eim.data.timeframes import tf_ms
from eim.paper.engine import Path, run_shadow
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams
from eim.validation.criteria import Criteria
from eim.validation.evidence import Trade
from eim.validation.gate import Verdict
from eim.validation.hypotheses import decision as dc
from eim.validation.hypotheses import nulls as nl
from eim.validation.hypotheses import pipeline as pp
from eim.validation.hypotheses import rules as ru
from eim.validation.hypotheses.prereg import Prereg
from eim.validation.hypotheses.signals import daily_candles
from eim.validation.lineage import Version, iso_ms

FLOW = ("flujo_sigue", "flujo_revierte")
Log = Callable[[str], None]


@dataclass
class World:
    symbol: str
    series: dict[str, ru.Series]
    funding: list[tuple[int, float]]
    path: Path
    minutes: ru.Minutes | None


def world_of(symbol: str, candles: Mapping[str, Sequence[Candle]],
             funding: Sequence[tuple[int, float]], minutes: ru.Minutes | None) -> World:
    """El mundo de T139: 1 h, 4 h y el 1 d agregado, el camino de 15 m y el funding."""
    series = {tf: ru.series_of(candles[tf], tf) for tf in ("1h", "4h")}
    series["1d"] = ru.series_of(daily_candles(candles["4h"]), "1d")
    path = Path(candles["15m"], funding, tf_ms("15m"))
    return World(symbol, series, list(funding), path, minutes)


def key_ideas(pr: Prereg, w: World, ep: ExecParams, dropped: Sequence[str] = ()
              ) -> dict[str, list[Idea]]:
    """Las ideas de cada clave. Una clave que cae (P0) sigue en Holm, sin operaciones."""
    out: dict[str, list[Idea]] = {}
    for h in pr.hypotheses:
        for tf in h.timeframes:
            sid = f"{h.strategy}@{tf}"
            if h.strategy in dropped:
                out[sid] = []
                continue
            s = w.series[tf]
            sides = ru.sides_for(h, s, w.funding, w.minutes)
            out[sid] = ru.ideas_for(h, s, sides, pr, ep, ru.fingerprint(pr, sid, ep))
    return out


def key_trades(pr: Prereg, w: World, ep: ExecParams, ideas: Mapping[str, list[Idea]],
               log: Log | None = None) -> dict[str, list[Trade]]:
    """La sombra de cada clave, con su lado contrario y su etiqueta de régimen."""
    labels = {tf: pp.RegimeLabels(s.candles, tf, w.symbol, s.bar_ms) for tf, s in w.series.items()}
    out = {}
    for sid, xs in ideas.items():
        tf = sid.split("@")[1]
        out[sid] = pp.trades_of(xs, w.path, ep, labels[tf].at)
        if log:
            log(f"  {sid}: {len(xs)} ideas, {len(out[sid])} cerradas")
    return out


def sample_counts(pr: Prereg, w: World, ep: ExecParams, ideas: Mapping[str, list[Idea]]) -> dict:
    """Muestra por clave y tramo, **sin ningún R**: sirve para ver si una regla no dispara."""
    a, b = iso_ms(pr.windows.adjust.from_), iso_ms(pr.windows.adjust.to)
    out = {}
    for sid, xs in ideas.items():
        c: Counter = Counter()
        for o in run_shadow(xs, w.path, ep):
            if o.status != "CERRADA":
                continue
            where = "antes de 2023" if o.idea.t < a else "banco" if o.idea.t < b else "en vivo"
            c[where] += 1
            c[f"{where} largos" if o.idea.side > 0 else f"{where} cortos"] += 1
        out[sid] = {"ideas": len(xs), **c}
    return out


def setup(pr: Prereg, ep: ExecParams, prior: Mapping[str, float | None], symbol: str
          ) -> tuple[list[Version], dict[str, float | None]]:
    """Las versiones y la familia de Holm. Falla si no suman lo que el pre-registro declaró."""
    versions = [ru.version_of(pr, sid, ep) for sid in pr.sids()]
    family = pp.family_of(prior, symbol, versions)
    if len(family) != pr.attempts.family:
        raise ValueError(f"familia de Holm: {len(family)} ≠ {pr.attempts.family} declaradas")
    return versions, family


def rows_of(r_id: str, verdicts: Sequence[Verdict], sides: Mapping[str, pp.SideStats]
            ) -> list[dict]:
    """Una fila por clave, con cada criterio de la puerta y el bruto por lado."""
    out = []
    for v in verdicts:
        m = v.measure
        s = sides[v.version.sid]
        ck = dc.checks_of(v)
        out.append({"reading": r_id, "id": v.version.label, "sid": v.version.sid,
                    "verdict": v.verdict, "reason": v.reason, "n": m.n, "mean_r": m.mean_r,
                    "ci_lo": m.ci[0], "ci_hi": m.ci[1], "p_raw": m.p_raw, "p_holm": v.p_holm,
                    "max_dd": m.dd, "windows": len(m.windows),
                    "windows_pos": sum(1 for _, _, x in m.windows if x > 0), "n_live": m.n_live,
                    "regimes": dict(m.regimes), **{k: ck[k] for k in ck}, **s.to_json()})
    return out


def _score(pr: Prereg, rid: str, versions, trades, family, crit, w: World
           ) -> tuple[list[Verdict], dict[str, pp.SideStats]]:
    """Una lectura: veredictos de la puerta y bruto por lado de lo que cuenta en ella."""
    r = pr.reading(rid)
    asof = int(w.path.end)
    verdicts = pp.score_reading(r, versions, trades, family, crit, w.symbol, asof,
                                (w.path.t, w.path.c))
    rule = pr.reading_rule
    sides = {v.sid: pp.side_stats(pp.selected(r, v, trades.get(v.sid, []), w.symbol, asof),
                                  rule.min_side_trades, rule.cost_stress) for v in versions}
    return verdicts, sides


def control_run(pr: Prereg, w: World, ep: ExecParams, paths: Sequence[Path],
                in_tramo: Callable[[Idea], bool]) -> dict[str, dict]:
    """`control_aleatorio` en cada marco frente a sus sustitutas: no puede destacar."""
    c = pr.control
    cat = nl.catalog_subset(ids=(c.strategy,))
    out = {}
    for tf in c.timeframes:
        ideas = [i for i in nl.catalog_ideas(w.series[tf], None, ep, w.symbol, cat)
                 if in_tramo(i)]
        gross, n = nl.gross_of(ideas, w.path, ep, in_tramo)
        null = nl.null_gross(paths, ideas, n, ep, pr, f"{c.strategy}@{tf}")
        out[tf] = {**nl.control_verdict(gross, n, null, c.alpha),
                   "null_p95": nl.null_summary(null, c.null_quantile)["p95"]}
    return out


def _closes(w: World, a: int, b: int) -> tuple[np.ndarray, float, int]:
    """Cierres de 1 min del tramo [a, b), con el precio y el instante de arranque."""
    if w.minutes is None or not len(w.minutes.t):
        raise ValueError("las sustitutas necesitan las velas de 1 min")
    m = w.minutes
    i, j = int(np.searchsorted(m.t, a)), int(np.searchsorted(m.t, b))
    return m.c[i:j], float(m.c[i]), int(m.t[i])


def bank_stage(pr: Prereg, crit: Criteria, w: World, ep: ExecParams,
               prior: Mapping[str, float | None], stored: Sequence[dict], log: Log,
               dropped: Sequence[str] = ()) -> dict:
    """Comprobar el camino donde ya no hay nada que gastar: regresión, control y banco."""
    versions, family = setup(pr, ep, prior, w.symbol)
    reg = nl.regression(stored, w.series["1h"], w.path, ep, pr)
    log(f"regresión: {reg}")
    ideas = key_ideas(pr, w, ep, dropped)
    trades = key_trades(pr, w, ep, ideas, log)
    verdicts, sides = _score(pr, "banco", versions, trades, family, crit, w)
    a, b = iso_ms(pr.windows.adjust.from_), iso_ms(pr.windows.adjust.to)
    fine, px0, t0 = _closes(w, a, b)
    paths = nl.surrogate_paths(fine, pr, px0, t0, log)
    control = control_run(pr, w, ep, paths, lambda i: a <= i.t < b)
    return {"versions": versions, "family": len(family), "regression": reg, "control": control,
            "rows": rows_of("banco", verdicts, sides), "trades": trades}


def clean_stage(pr: Prereg, crit: Criteria, w: World, ep: ExecParams,
                prior: Mapping[str, float | None], coverage_ok: bool, log: Log,
                dropped: Sequence[str] = ()) -> dict:
    """La lectura oficial, con la regla de lectura y la recomendación P0–P3."""
    versions, family = setup(pr, ep, prior, w.symbol)
    ideas = key_ideas(pr, w, ep, dropped)
    trades = key_trades(pr, w, ep, ideas, log)
    verdicts, sides = _score(pr, "oficial", versions, trades, family, crit, w)
    _, bank_sides = _score(pr, "banco", versions, trades, family, crit, w)
    a = iso_ms(pr.windows.adjust.from_)
    first = int(w.minutes.t[0]) if w.minutes is not None and len(w.minutes.t) else 0
    fine, px0, t0 = _closes(w, first, a)
    paths = nl.surrogate_paths(fine, pr, px0, t0, log)
    control = control_run(pr, w, ep, paths, lambda i: i.t < a)
    ctl_ok = {tf: x["ok"] for tf, x in control.items()}
    keys, nulls = [], {}
    for v in verdicts:
        sid = v.version.sid
        mine = [i for i in ideas[sid] if i.t < a]
        null = nl.null_gross(paths, mine, sides[sid].n, ep, pr, sid)
        nulls[sid] = nl.null_summary(null, pr.control.null_quantile)
        keys.append(dc.KeyReading(v, sides[sid], nulls[sid]["p95"], bank_sides[sid].gross,
                                  _control_for(sid, ctl_ok)))
    rows = rows_of("oficial", verdicts, sides)
    for row, k in zip(rows, keys, strict=True):
        sid = row["sid"]
        row.update(state=dc.state_of(k), conditions=dc.conditions(k), bank_gross=k.bank_gross,
                   bank_n=bank_sides[sid].n, null=nulls[sid])
    rec = dc.recommend(keys, coverage_ok, list(ctl_ok.values()))
    return {"versions": versions, "family": len(family), "control": control, "rows": rows,
            "recommendation": rec, "baseline": baseline(pr, w, ep, a), "trades": trades}


def _control_for(sid: str, ctl_ok: Mapping[str, bool | None]) -> bool | None:
    """El control de su marco; 1 d no tiene el suyo y exige que estén en verde los dos."""
    tf = sid.split("@")[1]
    if tf in ctl_ok:
        return ctl_ok[tf]
    vals = list(ctl_ok.values())
    return True if vals and all(x is True for x in vals) else None if None in vals else False


def baseline(pr: Prereg, w: World, ep: ExecParams, before: int) -> dict:
    """Línea base de solo lectura: lo que el catálogo que solo pide velas da en el tramo limpio."""
    out: dict[str, dict] = {}
    for tf in pr.baseline.timeframes:
        s = w.series[tf]
        ctxs = [c for c in ru.minimal_ctxs(s) if c["t"] < before]
        for fam in pr.baseline.families:
            cat = nl.catalog_subset(families=(fam,))
            cat = {k: v for k, v in cat.items() if v.runs_in(tf)}
            ideas = nl.catalog_ideas(s, w.series["4h"].candles, ep, w.symbol, cat, ctxs)
            gross, n = nl.gross_of(ideas, w.path, ep, lambda _i: True)
            out.setdefault(fam, {})[tf] = {"strategies": len(cat), "n": n, "gross_r": gross}
    return out
