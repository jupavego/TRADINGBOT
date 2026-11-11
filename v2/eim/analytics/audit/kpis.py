"""Indicadores del libro para la auditoría periódica (T159). Puro: filas → cifras.

Repite, en código, el método del diagnóstico de la fase 24
(`PLAN/notas/diagnostico_rentabilidad_2026-11-09.md`): solo el universo oficial de T144 (la columna
`counts_as_result` que ya trae `ledger.csv`), ganada = `r > 0`, costo por operación con
`eim.paper.cost_ledger.trade_cost` y bruto = neto + costo, ambos en R.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence

from eim.paper.cost_ledger import trade_cost

DAY_MS = 86_400_000
MIN_GROUP = 20          # por debajo, el grupo se lista pero no se lee como resultado


def _f(x) -> float:
    try:
        return float(x) if x not in (None, "") else 0.0
    except ValueError:
        return 0.0


def official(rows: Iterable[dict]) -> list[dict]:
    """Universo oficial de T144 (perfiles, vivas, con peso, sin `retro`), tal como lo marca la API."""
    return [r for r in rows if str(r.get("counts_as_result")).lower() == "true"
            and r.get("exit_t") not in (None, "")]


def fees(row: dict) -> tuple[float, float]:
    """(taker, maker) de los parámetros de costo con que se calculó la fila."""
    try:
        p = json.loads(row.get("cost_params") or "{}")
    except (TypeError, ValueError):
        p = {}
    return float(p.get("taker_fee", 0.0005)), float(p.get("maker_fee", 0.0002))


def stats(rows: Sequence[dict]) -> dict:
    """Acierto, reparto ganador/perdedor, equilibrio, esperanza con IC 95 %, costo y bruto."""
    n = len(rows)
    if n == 0:
        return {"n": 0}
    rs = [_f(r.get("r")) for r in rows]
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x <= 0]
    aw = statistics.fmean(wins) if wins else 0.0
    al = statistics.fmean(losses) if losses else 0.0
    mean = statistics.fmean(rs)
    sd = statistics.stdev(rs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else float("inf")
    costs = [trade_cost(r) for r in rows]
    cr = [c["cost_r"] for c in costs if c["cost_r"] is not None]
    cb = [c["cost_bps"] for c in costs if c["cost_bps"] is not None]
    pnl = [_f(r.get("pnl_usdt")) for r in rows]
    neg = sorted(x for x in pnl if x < 0)
    cost_r = statistics.fmean(cr) if cr else None
    return {
        "n": n, "win_rate": len(wins) / n, "avg_win_r": aw, "avg_loss_r": al,
        "breakeven_win_rate": abs(al) / (aw + abs(al)) if (aw + abs(al)) else None,
        "e_r": mean, "e_r_ci": [mean - half, mean + half],
        "cost_r": cost_r, "gross_r": mean + cost_r if cost_r is not None else None,
        "cost_bps_median": statistics.median(cb) if cb else None,
        "pnl_usdt": sum(pnl), "cost_usdt": sum(c["cost_usdt"] for c in costs),
        "worst5_share": (sum(neg[:5]) / sum(neg)) if neg else 0.0,
        # bruto (r + costo) por debajo de −1,05 R: salto o deslizamiento más allá del stop, no comisiones
        "beyond_sl_n": sum(1 for x, c in zip(rs, costs, strict=True)
                           if x + (c["cost_r"] or 0.0) < -1.05),
        "readable": n >= MIN_GROUP,
    }


def by(rows: Sequence[dict], key: Callable[[dict], str]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[key(r) or "—"].append(r)
    return {k: stats(v) for k, v in sorted(groups.items())}


def taker_savings(rows: Sequence[dict]) -> dict:
    """Lo que habría ahorrado entrar como maker en las entradas a mercado (solo la comisión de
    entrada; el deslizamiento de entrada se suma aparte porque el límite no lo paga)."""
    usdt, risk_r, n = 0.0, [], 0
    for r in rows:
        if r.get("kind") != "market":
            continue
        taker, maker = fees(r)
        notional = _f(r.get("notional"))
        save = (taker - maker) * notional
        pnl, rr = _f(r.get("pnl_usdt")), _f(r.get("r"))
        n += 1
        usdt += save
        if pnl and rr:
            risk_r.append(save / (abs(pnl) / abs(rr)))
    return {"n_market": n, "share_market": n / len(rows) if rows else 0.0, "usdt": usdt,
            "r_per_op": statistics.fmean(risk_r) if risk_r else None}


def window(rows: Sequence[dict], now_ms: int, days: int) -> list[dict]:
    t0 = now_ms - days * DAY_MS
    return [r for r in rows if _f(r.get("exit_t")) >= t0]


def book_kpis(rows: Sequence[dict], now_ms: int) -> dict:
    """Todo lo que la auditoría lee del libro, en un solo diccionario serializable."""
    off = official(rows)
    kept = {id(r) for r in off}
    first = min((_f(r.get("exit_t")) for r in off), default=0)
    return {
        "universe": "libro fijo de los perfiles · `counts_as_result` (T144)",
        "rows_total": len(rows), "rows_official": len(off),
        "excluded": dict(Counter(r.get("exclusion") or "sin cerrar" for r in rows
                                 if id(r) not in kept)),
        "first_exit_t": int(first),
        "all": stats(off), "last7": stats(window(off, now_ms, 7)),
        "last28": stats(window(off, now_ms, 28)),
        "by_profile": by(off, lambda r: r.get("profile", "")),
        "by_timeframe": by(off, lambda r: r.get("timeframe", "")),
        "by_kind": by(off, lambda r: r.get("kind", "")),
        "by_reason": by(off, lambda r: r.get("reason", "")),
        "by_leverage": by(off, lambda r: f"{_f(r.get('leverage')):g}x"),
        "by_strategy": by(off, lambda r: r.get("strategy", "")),
        "taker": taker_savings(off),
    }
