"""Resumen de lectura del libro de la cantera (T168, entregable 5). Puro.

Por cuenta: **rentabilidad neta acumulada %, saldo, curva de capital (realizada, al cierre de cada
operación), drawdown máximo**, n, acierto, costo pagado, etapa y la vara contra la suerte: R neto
medio con su IC 95 % y d = R − media de los gemelos con el suyo. Lo hacia fuera es rentabilidad;
lo de dentro, R (nota §3). La banda semanal se mide por **día**: rendimiento diario realizado de la
cuenta y de sus gemelos. Comprar y mantener se da en % y en unidades de riesgo (1,5 ATR al inicio).
Ninguna cifra decide nada aquí: la etapa solo describe la muestra (los ascensos son de T170).

La serie diaria es de P&L **realizado**, apuntado al día del cierre de cada operación, con la
**misma convención para la cuenta y para sus gemelos**, que es lo que hace comparable la
diferencia (el bootstrap por bloques de T170 trabaja sobre esos pares). `days_in_position` cuenta
los días con posición abierta, que es la cadencia que la banda semanal tiene que cumplir (T169).
Valorar cada día a precio de mercado haría falta para una curva diaria continua: queda en BACKLOG,
no cambia la vara.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from eim.nursery.book import Book, Entry
from eim.paper.engine import Path

DAY_MS = 86_400_000
NURSERY_MIN_N = 30          # guardería → cantera (escalafón, nota §3)


def _ci(xs: Sequence[float]) -> dict:
    n = len(xs)
    if n == 0:
        return {"n": 0, "mean": None, "lo": None, "hi": None}
    m = float(np.mean(xs))
    if n < 2:
        return {"n": n, "mean": round(m, 4), "lo": None, "hi": None}
    half = 1.96 * float(np.std(xs, ddof=1)) / math.sqrt(n)
    return {"n": n, "mean": round(m, 4), "lo": round(m - half, 4), "hi": round(m + half, 4)}


def _max_dd(curve: Sequence[float]) -> float:
    peak, dd = -math.inf, 0.0
    for x in curve:
        peak = max(peak, x)
        dd = max(dd, (peak - x) / peak if peak > 0 else 0.0)
    return dd


def account_summary(book: Book, account: str) -> dict:
    p = book.params
    es = [e for e in book.of(account) if e.booked]
    closed = sorted((e for e in es if e.trade.status == "CERRADA"), key=lambda e: e.trade.exit_t)
    bal = p.initial_equity
    curve = [{"t": book.params.start_ms, "equity": round(bal, 2)}]
    for e in closed:
        bal += e.pnl_usd
        curve.append({"t": int(e.trade.exit_t), "equity": round(bal, 2)})
    rs = [e.trade.r for e in closed if e.trade.r is not None]
    ds = [e.d_r for e in closed if e.d_r is not None]
    daily: dict[str, list[float]] = {}
    for e in closed:
        day = str(int(e.trade.exit_t) // DAY_MS)
        acc = daily.setdefault(day, [0.0, 0.0])
        acc[0] += e.pnl_usd
        acc[1] += e.twin_pnl_usd
    side = {lab: _side(closed, s) for lab, s in (("largo", 1), ("corto", -1))}
    held = set()
    for e in es:
        if e.trade.fill_t is None:
            continue
        end = e.trade.exit_t if e.trade.exit_t is not None else e.trade.fill_t
        held.update(range(int(e.trade.fill_t) // DAY_MS, int(end) // DAY_MS + 1))
    return {
        "balance": round(bal, 2), "net_return_pct": round((bal / p.initial_equity - 1) * 100, 3),
        "max_drawdown_pct": round(_max_dd([c["equity"] for c in curve]) * 100, 3),
        "equity_curve": curve, "n": len(closed),
        "open": sum(1 for e in es if e.trade.status == "ABIERTA"),
        "unfilled": sum(1 for e in es if e.trade.status in ("NO_LLENADA", "CANCELADA")),
        "hit_rate": round(sum(1 for e in closed if e.pnl_usd > 0) / len(closed), 4)
        if closed else None,
        "cost_paid_usd": round(sum(e.qty * e.trade.fill * e.trade.cost for e in closed), 2),
        "stage": "guarderia" if len(closed) < NURSERY_MIN_N else "cantera",
        "r_net": _ci(rs), "d_vs_twins": _ci(ds),
        "markout_bps": _ci([e.trade.markout_bps for e in es
                            if e.trade.markout_bps is not None and e.order.maker]),
        "by_side": side, "daily": {k: [round(a, 2), round(b, 2)] for k, a, b in
                                   ((k, *v) for k, v in sorted(daily.items()))},
        "days_in_position": len(held),
        "shadow_trades": sum(1 for e in book.of(account) if not e.booked),
    }


def _side(closed: Sequence[Entry], s: int) -> dict:
    xs = [e for e in closed if e.side == s]
    return {"n": len(xs), "pnl_usd": round(sum(e.pnl_usd for e in xs), 2)}


def buy_and_hold(book: Book, path: Path, ctxs_first: dict | None) -> dict | None:
    """Comprar y mantener desde el primer cierre que cuenta: en % y en unidades de riesgo."""
    if ctxs_first is None or not len(path.t):
        return None
    t0 = int(ctxs_first["t"])
    j0 = int(np.searchsorted(path.t, t0))
    if j0 >= len(path.t):
        return None
    p0, p1 = float(path.o[j0]), float(path.c[-1])
    atr = ctxs_first.get("atr") or 0.0
    risk = book.params.sl_atr * atr
    return {"from_t": t0, "price_from": p0, "price_to": p1,
            "return_pct": round((p1 / p0 - 1) * 100, 3),
            "r_long": round((p1 - p0) / risk, 3) if risk > 0 else None,
            "r_short": round((p0 - p1) / risk, 3) if risk > 0 else None,
            "basis": f"1 R = {book.params.sl_atr:g} ATR del primer cierre que cuenta"}


def summarize(book: Book, path: Path, first_ctx: dict | None = None) -> dict:
    rows = []
    for a in book.accounts:
        s = account_summary(book, a.id)
        rows.append({"account": a.id, "kind": a.kind, "agent_id": a.agent_id,
                     "timeframe": a.timeframe, "exit_template": a.exit_template,
                     "prospect": a.prospect.model_dump(mode="json") if a.prospect else None, **s})
    return {"mode": "SIMULADO", "prospects": book.prospect_count,
            "controls": len(book.accounts) - book.prospect_count,
            "initial_equity": book.params.initial_equity, "risk_pct": book.params.risk_pct,
            "twins_k": book.params.twins_k, "start_ms": book.params.start_ms,
            "accounts": rows, "events": book.events,
            "buy_and_hold": buy_and_hold(book, path, first_ctx)}
