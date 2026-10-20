"""Tabla de puntuación del escuadrón (T59), pura: posturas guardadas → conceptos con evidencia.

Usa la puerta de T49 tal cual (`eim.validation.gate`), no otra vara: cada `bot@estrategia@marco@vN`
es una estrategia con sus operaciones sombra (`shadow`), costos de T25, fuera de muestra (el bot
no se ajustó con datos de EIM: parámetros de terceros fijados por su SHA, así que no hay ventanas
de ajuste) y réplica de lado aleatorio. La familia de Holm incluye TODAS las versiones de TODOS los
bots (también las retiradas) más un control aleatorio por cada una.
Sin I/O: el CLI (`scorecard_cli`) le pasa señales, velas, camino, fichas y aportes marginales.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from eim.bots.card import BotCard
from eim.bots.concept import DESHABILITADO, INFORMA, RECHAZADO, VOTA, assign
from eim.bots.health import assess
from eim.bots.marginal import Marginal
from eim.bots.shadow import BotId, RegimeAt, identities, shadow_trades
from eim.core import BotSignal, Candle
from eim.paper.engine import Path
from eim.paper.params import ExecParams
from eim.validation.criteria import Criteria
from eim.validation.evidence import Trade
from eim.validation.gate import Verdict, measure, validate_all
from eim.validation.lineage import Version

NOTE_WINDOWS = ("Parámetros de terceros fijados por SHA: EIM no los ajustó con ningún dato, así "
                "que no hay ventanas de ajuste; toda la historia posterior al alta del bot es "
                "fuera de muestra.")
CONTROL_SUFFIX = "#control"


@dataclass(frozen=True)
class Attempt:
    ident: BotId
    control: bool
    trades: list[Trade]

    @property
    def version(self) -> Version:
        i = self.ident
        sid = i.sid + (CONTROL_SUFFIX if self.control else "")
        return Version(sid, i.n, i.version, i.bot_id + ":" + i.strategy
                       + (CONTROL_SUFFIX if self.control else ""), i.timeframe, 0,
                       i.n - 1 or None, "tercero", NOTE_WINDOWS)

    @property
    def label(self) -> str:
        return self.version.label


def _verdict_row(v: Verdict, retired: bool, control: bool) -> dict:
    return {**v.to_json(), "retired": retired, "control": control}


def attempts_of(rows: Sequence[tuple[BotSignal, int]], candles: Sequence[Candle], path: Path,
                symbol: str, regime_at: RegimeAt | None, ep: ExecParams | None
                ) -> tuple[list[BotId], list[Attempt]]:
    idents = identities(rows)
    out: list[Attempt] = []
    for i in idents:
        mine = [r for r in rows if (r[0].bot_id, r[0].strategy, r[0].timeframe)
                == (i.bot_id, i.strategy, i.timeframe)]
        for control in (False, True):
            out.append(Attempt(i, control, shadow_trades(i, mine, candles, path, symbol,
                                                         regime_at, ep, control)))
    return idents, out


def by_regime(att: Sequence[Attempt], symbol: str, asof: int, crit: Criteria) -> dict:
    """Solo informe: ¿algún bot supera la puerta DENTRO de un régimen con la misma exigencia?

    Se exige lo mismo (V2, V3 con Holm sobre todos los intentos bot×régimen, V4, V6 y las
    operaciones mínimas de V1); lo único que no aplica es «≥ N regímenes» porque es uno solo.
    """
    cells = [(a, reg, [t for t in a.trades if t.regime == reg])
             for a in att if not a.control for reg in sorted({t.regime for t in a.trades})]
    ready = [c for c in cells if len(c[2]) >= crit.v1_data.min_trades]
    items = [(a.version, measure(f"{a.label}|{reg}", sub, (), symbol, asof, crit, len(ready)),
              ()) for a, reg, sub in ready]
    verdicts = {x.measure.label: x for x in validate_all(items, {}, crit)}
    rows, passing = [], []
    for a, reg, sub in cells:
        v = verdicts.get(f"{a.label}|{reg}")
        ok = v is not None and all(c.ok for c in v.checks if c.id in ("V2", "V3", "V4", "V6"))
        if ok:
            passing.append(f"{a.label}|{reg}")
        rows.append({"id": a.label, "regime": reg, "n_oos": len(sub), "evaluated": v is not None,
                     "passes": ok, "mean_r": None if v is None else v.measure.mean_r,
                     "p_holm": None if v is None else v.p_holm})
    return {"rows": rows, "passing": passing, "attempts": len(ready),
            "selection_by_regime": bool(passing),
            "note": ("algún bot supera la puerta dentro de un régimen" if passing else
                     "ningún bot supera la puerta dentro de un régimen: no se activa selección "
                     "por régimen (BACKLOG)")}


def lane_l(runs: Sequence) -> list[dict]:
    """Clase L (market making / grid / DCA): informe de simulación aparte, sin puerta."""
    out = []
    for r in runs:
        eq = np.array([e.equity for e in r.equity], dtype=float)
        dd = float(np.max(1 - eq / np.maximum.accumulate(eq))) if len(eq) else None
        out.append({
            "id": f"{r.bot_id}:{r.strategy}@{r.timeframe}", "version": r.version,
            "label": "simulado", "status": r.status, "start": r.start, "end": r.end,
            "fills": len(r.fills),
            "pnl_inventory": (float(eq[-1] - r.starting_balance) if len(eq) else None),
            "pnl_realized": float(sum(f.pnl for f in r.fills)),
            "costs_paid": float(-sum(f.fee_paid for f in r.fills)),
            "max_drawdown": dd,
            "inventory_risk": {"max_wallet_exposure": max((f.wallet_exposure for f in r.fills),
                                                          default=None),
                               "max_position": max((abs(f.psize_after) for f in r.fills),
                                                   default=None)},
            "costs_model": r.costs_assumed, "evidence": list(r.evidence),
            "note": "fuera de la puerta direccional; sin deslizamiento modelado; no vota"})
    return out


def score(rows: Sequence[tuple[BotSignal, int]], candles: Sequence[Candle], path: Path,
          symbol: str, crit: Criteria, cards: Mapping[str, BotCard], asof: int,
          regime_at: RegimeAt | None = None, marginals: Mapping[str, Marginal] | None = None,
          ep: ExecParams | None = None, sim_runs: Sequence = ()) -> dict:
    idents, att = attempts_of(rows, candles, path, symbol, regime_at, ep)
    n_att = len(att)
    prices = (path.t, path.c)
    items = [(a.version, measure(a.label, a.trades, (), symbol, asof, crit, n_att, prices), ())
             for a in att]
    done = validate_all(items, {}, crit)
    ver = {a.label: v for a, v in zip(att, done, strict=True)}
    latest = {(i.bot_id, i.strategy, i.timeframe): i for i in idents}      # la de mayor n
    concepts, attempts = [], []
    for a in att:
        i, v = a.ident, ver[a.label]
        retired = latest[(i.bot_id, i.strategy, i.timeframe)].n != i.n
        attempts.append(_verdict_row(v, retired, a.control))
    for key, i in sorted(latest.items()):
        card = cards.get(i.bot_id)
        if card is None:
            continue
        mine = next(a for a in att if a.ident == i and not a.control)
        ctl = next(a for a in att if a.ident == i and a.control)
        v = ver[mine.label].to_json()
        mi = [s for s, _ in rows if (s.bot_id, s.strategy, s.timeframe) == key]
        cur = [s for s in mi if s.version == i.version]
        prev = [s for s in mi if s.version != i.version
                and s.version == next((x.version for x in idents if (x.bot_id, x.strategy,
                                       x.timeframe) == key and x.n == i.n - 1), "")]
        live = [t.r for t in mine.trades if t.origin == "vivo" and t.exit_t <= asof]
        h = assess(live, ver[mine.label].measure.ci[0], cur, prev, cur)
        c = assign(mine.label, (i.bot_id, i.strategy, i.timeframe, i.version), card, v,
                   (marginals or {}).get(mine.label), h)
        row = c.to_json()
        row["verdict"] = {k: v[k] for k in ("verdict", "reason", "n_oos", "n_live", "mean_r",
                                            "p_raw", "p_holm", "checks", "extras")}
        row["control"] = {"id": ctl.label, "verdict": ver[ctl.label].verdict,
                          "n_oos": ver[ctl.label].measure.n,
                          "mean_r": ver[ctl.label].measure.mean_r,
                          "p_holm": ver[ctl.label].p_holm}
        row["retired_versions"] = [x.label for x in idents if (x.bot_id, x.strategy,
                                   x.timeframe) == key and x.n != i.n]
        concepts.append(row)
    states = Counter(c["state"] for c in concepts)
    return {
        "task": "T59", "mode": "SIMULADO", "symbol": symbol, "asof": asof,
        "criteria": {"version": crit.version, "sha256": crit.sha256},
        "attempts_total": n_att, "windows_note": NOTE_WINDOWS,
        "bots": concepts, "attempts": attempts,
        "regimes": by_regime(att, symbol, asof, crit),
        "lane_l": lane_l(sim_runs),
        "summary": {"states": {s: states.get(s, 0) for s in (VOTA, INFORMA, RECHAZADO,
                                                              DESHABILITADO)},
                    "votan": [c["id"] for c in concepts if c["state"] == VOTA],
                    "informan": [c["id"] for c in concepts if c["state"] == INFORMA],
                    "publicables": [c["id"] for c in concepts if c["publicable"]],
                    "modulan_confianza": [c["id"] for c in concepts
                                          if c["modulates_confidence"]]},
    }
