"""La física de un prospecto en la historia (T169): cuánto opera, cuánto le cuesta, cuánto aguanta.

Puro. Usa el motor de la cantera tal cual (`signals`, `build_order`, `simulate`) con la misma
regla de cupo que `book.run_book` para una cuenta: una posición a la vez y la espera al cerrar;
la puerta de costo y el saldo no cambian cuándo opera una cuenta, solo si la operación se apunta.

**No se mira el resultado.** De cada operación simulada se queda solo su física: cuándo se llenó,
cuándo salió, su costo en R y su nocional. Ni el precio de salida, ni el neto, ni el motivo de
salida (repartido por TP y SL sería el acierto): este módulo no lee esos campos, y
`tests/nursery/test_exam_no_performance.py` lo comprueba sobre su código.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from eim.data.timeframes import tf_ms
from eim.nursery.exam.plan import DAY_MS, Stretch, block_of, block_start
from eim.nursery.native import stored_key
from eim.nursery.params import NurseryParams
from eim.nursery.prospect import Prospect
from eim.nursery.signals import PROSPECT, Account, build_order, signals
from eim.nursery.sim import funding_step, simulate
from eim.paper import risk_budget
from eim.paper.engine import Path

FILLED = ("CERRADA", "ABIERTA")


@dataclass(frozen=True)
class Op:
    """Una orden del prospecto, vista solo por su física."""

    t: int                       # cierre de la vela de decisión
    block: int
    side: int
    filled: bool
    closed: bool                 # False y filled = abierta al final del tramo (censurada)
    fill_t: int | None
    exit_t: int | None           # salida (cerradas) o fin del tramo (censuradas)
    cost_r: float | None         # solo cerradas
    notional: float              # tamaño de la cantera con capital fijo (USDT)


def slice_path(path: Path, start: int, end: int) -> Path:
    """El camino de 15 m con velas `start ≤ t < end` (el funding se comparte)."""
    a, b = int(np.searchsorted(path.t, start)), int(np.searchsorted(path.t, end))
    p = Path.from_arrays({"t": path.t[a:b], "o": path.o[a:b], "h": path.h[a:b],
                          "l": path.l[a:b], "c": path.c[a:b]}, path.step)
    p.ft, p.fr = path.ft, path.fr
    return p


def account_of(p: Prospect) -> Account:
    return Account(p.account, PROSPECT, p.agent_id, p.timeframe, p.exit_template, p, p.max_bars)


def _notional(np_: NurseryParams, ref: float, sl: float) -> float:
    eq = np_.initial_equity
    qty = risk_budget.qty_for_risk(np_.risk_pct * eq, ref, sl, np_.est_cost_frac,
                                   np_.risk_includes_costs)
    return float(min(qty, eq * np_.max_leverage / ref) * ref)


def ops_in(p: Prospect, ctxs: Sequence[dict], path: Path, np_: NurseryParams,
           fstep: int, stretch: Stretch) -> tuple[list[Op], int, int]:
    """Órdenes del prospecto en un tramo, sus ideas (señales de entrada) y las rechazadas."""
    acc = account_of(p)
    sigs = signals(acc, ctxs, np_.history_bars)
    ideas = sum(1 for s in sigs if s.enter)
    seg = slice_path(path, stretch.start, stretch.end)
    free: int | None = 0
    out: list[Op] = []
    rejected = 0
    cool = np_.exec.cooldown_bars * tf_ms(p.timeframe)
    for i, c in enumerate(ctxs):
        t = int(c["t"])
        if free is None:
            break
        if t < free or not sigs[i].enter:
            continue
        o = build_order(acc, i, sigs[i].enter, ctxs, sigs, np_)
        if o is None:
            continue
        tr = simulate(o, seg, np_.exec, fstep)
        if tr.status == "RECHAZADA":
            rejected += 1
            continue
        filled, closed = tr.status in FILLED, tr.status == "CERRADA"
        exit_t = tr.exit_t if closed else (seg.end - 1 if filled else tr.exit_t)
        out.append(Op(t, stretch.block if stretch.block >= 0 else block_of(t), o.side, filled,
                      closed, tr.fill_t, exit_t, tr.cost_r if closed else None,
                      _notional(np_, o.ref, o.sl)))
        end = tr.busy_until
        free = None if end is None or tr.status == "PENDIENTE" else int(end) + cool
    return out, ideas, rejected


def _present(v: object) -> bool:
    return v is not None and not (isinstance(v, list) and (not v or all(x is None for x in v)))


def coverage(p: Prospect, ctxs: Sequence[dict]) -> dict:
    """Fracción de contextos con el agente con datos y con valor en cada variable declarada."""
    n = len(ctxs)
    rows = [(c.get("nat") or {}).get(p.agent_id) for c in ctxs]
    with_agent = sum(1 for r in rows if r is not None)
    per = [{"variable": v, "with_value": round(sum(
        1 for r in rows if r is not None and _present(r.get(stored_key(v)))) / n, 4) if n else None}
        for v in p.variables]
    return {"contexts": n, "agent_ok": round(with_agent / n, 4) if n else None, "variables": per}


def held_days(ops: Sequence[Op]) -> set[int]:
    """Días UTC con posición abierta (como `days_in_position` de la cantera)."""
    out: set[int] = set()
    for o in ops:
        if o.filled and o.fill_t is not None:
            end = o.exit_t if o.exit_t is not None else o.fill_t
            out.update(range(int(o.fill_t) // DAY_MS, int(end) // DAY_MS + 1))
    return out


def block_days(st: Stretch) -> dict[int, float]:
    """Días que el tramo cubre de cada bloque de 28 días (para la cadencia por bloque)."""
    if st.block >= 0:
        return {st.block: st.days}
    out = {}
    for k in range(block_of(st.start), block_of(st.end - 1) + 1):
        lo, hi = max(st.start, block_start(k)), min(st.end, block_start(k + 1))
        if hi > lo:
            out[k] = (hi - lo) / DAY_MS
    return out


def physics(p: Prospect, by_stretch: Sequence[tuple[Stretch, Sequence[dict]]], path: Path,
            np_: NurseryParams | None = None) -> dict:
    """Examen físico de un prospecto sobre sus tramos (contextos de su marco por tramo)."""
    np_ = np_ or NurseryParams()
    fstep = funding_step(path)
    ops: list[Op] = []
    ideas = rejected = 0
    all_ctx: list[dict] = []
    days = 0.0
    per_block: dict[int, float] = {}
    for st, ctxs in by_stretch:
        o, i, r = ops_in(p, ctxs, path, np_, fstep, st)
        ops += o
        ideas, rejected = ideas + i, rejected + r
        all_ctx += list(ctxs)
        days += st.days
        per_block.update(block_days(st))
    filled = [o for o in ops if o.filled]
    closed = [o for o in filled if o.closed]
    holds = [(o.exit_t - o.fill_t) / 3_600_000 for o in closed]
    costs = [o.cost_r for o in closed if o.cost_r is not None]
    in_pos = sum(o.exit_t - o.fill_t for o in filled)
    count = dict.fromkeys(per_block, 0)
    for o in filled:
        count[o.block] = count.get(o.block, 0) + 1
    month = [round(count[k] / per_block[k] * 30, 2) for k in sorted(count)
             if per_block.get(k, 0) >= 7]
    held = held_days(filled)
    held_by: dict[int, int] = {}
    for d in held:
        held_by[block_of(d * DAY_MS)] = held_by.get(block_of(d * DAY_MS), 0) + 1
    pos_by = [round(min(1.0, held_by.get(k, 0) / per_block[k]), 3) for k in sorted(per_block)
              if per_block[k] >= 7]
    sides = [o.side for o in filled]
    flips = sum(1 for a, b in zip(sides, sides[1:], strict=False) if a != b)
    return {
        "days": round(days, 2), "ideas": ideas, "orders": len(ops), "rejected": rejected,
        "filled": len(filled), "unfilled": len(ops) - len(filled),
        "closed": len(closed), "censored": len(filled) - len(closed),
        "ops_month": round(len(filled) / days * 30, 3) if days else 0.0,
        "ops_month_by_block": month,
        "cost_r_mean": round(float(np.mean(costs)), 4) if costs else None,
        "cost_r_sd": round(float(np.std(costs, ddof=1)), 4) if len(costs) > 1 else None,
        "hold_h_median": round(float(np.median(holds)), 2) if holds else None,
        "hold_h_p25_p75": [round(float(x), 2) for x in np.percentile(holds, [25, 75])]
        if holds else None,
        "exposure": round(in_pos / (days * DAY_MS), 4) if days else 0.0,
        "pos_days_frac": round(min(1.0, len(held) / days), 4) if days else 0.0,
        "pos_days_by_block": pos_by,
        "turnover_month": round(sum(2 * o.notional for o in filled) / np_.initial_equity
                                / days * 30, 2) if days else 0.0,
        "side_flips_month": round(flips / days * 30, 3) if days else 0.0,
        "long_share": round(sum(1 for s in sides if s > 0) / len(sides), 3) if sides else None,
        "coverage": coverage(p, all_ctx),
    }
