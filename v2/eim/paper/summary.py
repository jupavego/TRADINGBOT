"""Resumen de un perfil para la vista: cuenta, posiciones, órdenes, métricas y curva."""

from __future__ import annotations

import numpy as np

from eim.paper.book import ProfileState, liq_price
from eim.paper.feedback import Learner, judge
from eim.paper.ladder_stats import ladder_stats

CURVE_POINTS = 400


def _downsample(curve: list[tuple[int, float]], n: int = CURVE_POINTS) -> list[tuple[int, float]]:
    if len(curve) <= n:
        return curve
    idx = np.unique(np.linspace(0, len(curve) - 1, n).astype(int))
    return [curve[i] for i in idx]


def _max_dd_pct(curve: list[tuple[int, float]]) -> float:
    if not curve:
        return 0.0
    eq = np.array([x for _, x in curve])
    peak = np.maximum.accumulate(eq)
    return float(((peak - eq) / peak).max())


def positions_of(st: ProfileState, mmr: float) -> tuple[list[dict], list[dict], float]:
    """(posiciones abiertas, órdenes pendientes, PnL no realizado a la última marca)."""
    pos, orders, upnl = [], [], 0.0
    for s in st.slots.values():
        o, i = s.o, s.o.idea
        base = {"id": i.id, "strategy": i.strategy, "sid": i.sid, "timeframe": i.timeframe,
                "family": i.family, "side": i.side,
                "kind": i.kind, "t": i.t, "qty": s.qty, "sl": i.sl, "tp": i.tp,
                "conf": i.conf, "rr": i.rr,
                "leverage": s.leverage, "margin": s.margin, "weight": s.weight,
                "risk_usd": s.risk_usd, "floor": s.floor, "origin": i.origin, "why": list(i.why)}
        if not s.filled:
            orders.append({**base, "price": i.entry,
                           "expire_t": i.t + i.fill_ms if i.kind == "limit" else None})
            continue
        cost = s.qty * o.fill * (o.fee_in + o.slip + o.funding)   # ya pagado o devengado
        mark = o.mark if o.mark is not None else o.fill
        u = i.side * s.qty * (mark - o.fill) - cost
        upnl += u
        if o.ladder:       # PPP: sin TP ni vencimiento; el SL es el vigente y sube por escalones
            base = {**base, "tp": None, "sl": o.ladder["stop"], "ladder": o.ladder}
        pos.append({**base, "entry": o.fill, "mark": mark, "fill_t": o.fill_t,
                    "expire_t": None if o.ladder else o.fill_t + i.hold_ms,
                    "liq": liq_price(i.side, o.fill, s.leverage, mmr),
                    "cost_usd": cost, "upnl": u, "roe": u / s.margin if s.margin else None,
                    "funding_assumed": o.funding_assumed})
    return pos, orders, upnl


def profile_summary(st: ProfileState, learner: Learner, strategy_ids: list[str], now: int,
                    mmr: float) -> dict:
    p = st.p
    pos, orders, upnl = positions_of(st, mmr)
    tr = st.trades
    pnl = np.array([t["pnl"] for t in tr], dtype=float)
    rs = np.array([t["r"] for t in tr if t["r"] is not None], dtype=float)
    gains, losses = float(pnl[pnl > 0].sum()), float(-pnl[pnl < 0].sum())
    equity = st.equity + upnl
    curve = list(st.curve) + ([(now, equity)] if st.curve else [])
    by: dict[str, dict] = {}
    for t in tr:
        b = by.setdefault(t["sid"], {"n": 0, "pnl": 0.0, "wins": 0})
        b["n"] += 1
        b["pnl"] += t["pnl"]
        b["wins"] += int(t["pnl"] > 0)
    lad = ({"ladder": ladder_stats(
        tr, [{"elapsed_h": (x["ladder"]["elapsed_ms"] / 3_600_000)} for x in pos
             if x.get("ladder")], len(st.violations),
        sum(1 for x in pos if x.get("ladder", {}).get("incident")),
        p.ladder.first_usdt, p.ladder.step_usdt) | {"brake": st.lrisk.to_json(now)}}
           if p.exit_mode == "ladder" and p.ladder else {})
    return {
        **lad,
        "id": p.id, "name": p.name, "description": p.description,
        "params": p.model_dump(mode="json"),
        "initial": p.initial_equity, "balance": st.equity, "equity": equity, "upnl": upnl,
        "realized": st.equity - p.initial_equity,
        "return_pct": equity / p.initial_equity - 1,
        "margin_used": sum(x["margin"] for x in pos), "reserved": sum(x["margin"] for x in orders),
        "available": st.equity - st.used,
        "n_closed": len(tr), "win_rate": float((pnl > 0).mean()) if len(pnl) else None,
        "pf": gains / losses if losses > 0 else None,
        "avg_r": float(rs.mean()) if len(rs) else None,
        "best": float(pnl.max()) if len(pnl) else None,
        "worst": float(pnl.min()) if len(pnl) else None,
        "fees": float(sum(t["fees"] for t in tr)), "funding": float(sum(t["funding"] for t in tr)),
        "slip": float(sum(t["slip"] for t in tr)),
        "max_dd_pct": _max_dd_pct(curve),
        "positions": sorted(pos, key=lambda x: -x["fill_t"]),
        "orders": sorted(orders, key=lambda x: -x["t"]),
        "curve": _downsample(curve),
        "by_strategy": by,
        "weights": {sid: learner.at(sid, now, p.feedback).to_json() for sid in strategy_ids},
        "events_n": len(st.events),
        "min_open": {"target": p.min_open, "open": len(pos),
                     "pending_target": p.min_pending, "pending": len(orders),
                     "entries": sum(1 for t in tr if t.get("floor")),
                     "criteria": {k: judge(rs, p.feedback).to_json()
                                  for k, rs in st.floor_r.items()}},
    }
