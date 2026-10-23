"""Resumen de un perfil para la vista: cuenta, posiciones, órdenes, métricas y curva."""

from __future__ import annotations

import numpy as np

from eim.paper.account import LIQ, capped, liq_price, max_dd_pct
from eim.paper.book import ProfileState
from eim.paper.feedback import Learner, judge
from eim.paper.ladder_stats import ladder_stats

CURVE_POINTS = 400
# El recuento de operaciones no tiene ventana: la vista se rehace desde TODOS los contextos del
# almacén de ese símbolo en cada consulta (T106 A4), así que solo puede crecer.
COUNT_SCOPE = ("todo el almacén de este símbolo, sin ventana: la vista se recalcula desde todos "
               "los contextos guardados. Si la experiencia compartida (T61) importó contextos de "
               "otras máquinas, cuentan aquí también: el almacén no los distingue.")


def _downsample(curve: list[tuple[int, float]], n: int = CURVE_POINTS) -> list[tuple[int, float]]:
    if len(curve) <= n:
        return curve
    idx = np.unique(np.linspace(0, len(curve) - 1, n).astype(int))
    return [curve[i] for i in idx]


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
        liq = s.liq if s.liq is not None else liq_price(i.side, o.fill, s.leverage, mmr)
        # margen aislado: el flotante no puede perder más que el margen; si la marca ya atravesó
        # la liquidación, la posición debería estar cerrada y se dice (`liq_why`)
        u, liq_why = capped(i.side * s.qty * (mark - o.fill) - cost, s.margin, i.side, mark, liq)
        upnl += u
        if o.ladder:       # PPP: sin TP ni vencimiento; el SL es el vigente y sube por escalones
            base = {**base, "tp": None, "sl": o.ladder["stop"], "ladder": o.ladder}
        pos.append({**base, "entry": o.fill, "mark": mark, "fill_t": o.fill_t,
                    "expire_t": None if o.ladder else o.fill_t + i.hold_ms, "liq": liq,
                    "liq_why": liq_why,
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
    dd = max_dd_pct(curve)
    exits = [t["exit_t"] for t in tr if t["exit_t"] is not None]
    origins: dict[str, int] = {}
    for t in tr:
        origins[t["origin"]] = origins.get(t["origin"], 0) + 1
    by: dict[str, dict] = {}
    for t in tr:
        b = by.setdefault(t["sid"], {"n": 0, "pnl": 0.0, "wins": 0})
        b["n"] += 1
        b["pnl"] += t["pnl"]
        b["wins"] += int(t["pnl"] > 0)
    ladder_on = p.exit_mode == "ladder" and p.ladder is not None
    lad = ({"ladder": ladder_stats(
        tr, [{"elapsed_h": (x["ladder"]["elapsed_ms"] / 3_600_000)} for x in pos
             if x.get("ladder")], len(st.violations),
        sum(1 for x in pos if x.get("ladder", {}).get("incident")),
        *p.ladder.steps(st.equity * p.risk_pct),
        rejected=sum(1 for v in st.violations if not v.get("executed", True)))
        | {"brake": st.lrisk.to_json(now), "brake_on": p.ladder.brake,
           "basis": p.ladder.basis, "first_r": p.ladder.first_r, "step_r": p.ladder.step_r,
           "contrary_signals": st.contrary}}
           if ladder_on else {})
    return {
        **lad,
        "id": p.id, "name": p.name, "description": p.description,
        "params": p.model_dump(mode="json"),
        "initial": p.initial_equity, "balance": st.equity, "equity": equity, "upnl": upnl,
        "realized": st.equity - p.initial_equity,
        # una sola definición (T107): balance = realizado, equity = balance + flotante y la
        # rentabilidad se mide SIEMPRE sobre equity, con el capital inicial como base
        "return_pct": equity / p.initial_equity - 1, "return_base": "equity",
        "exhausted": st.exhausted_t is not None, "exhausted_t": st.exhausted_t,
        "min_equity": p.initial_equity * p.min_equity_frac,
        "margin_used": sum(x["margin"] for x in pos), "reserved": sum(x["margin"] for x in orders),
        "available": st.equity - st.used,
        "n_closed": len(tr), "win_rate": float((pnl > 0).mean()) if len(pnl) else None,
        "pf": gains / losses if losses > 0 else None,
        "avg_r": float(rs.mean()) if len(rs) else None,
        "best": float(pnl.max()) if len(pnl) else None,
        "worst": float(pnl.min()) if len(pnl) else None,
        "fees": float(sum(t["fees"] for t in tr)), "funding": float(sum(t["funding"] for t in tr)),
        "slip": float(sum(t["slip"] for t in tr)),
        "max_dd_pct": dd,
        # base y ventana declaradas: el máximo descenso es sobre la curva de equity, de la primera
        # operación a «ahora» (con el suelo de la cuenta no puede pasar del 100 %)
        "dd": {"pct": dd, "base": "equity",
               "from": curve[0][0] if curve else None, "to": curve[-1][0] if curve else None},
        "counts": {"closed": len(tr), "by_origin": origins, "scope": COUNT_SCOPE,
                   "liquidations": sum(1 for t in tr if t["reason"] == LIQ),
                   "violations": len(st.violations),
                   "from": min(exits) if exits else None, "to": max(exits) if exits else None},
        "positions": sorted(pos, key=lambda x: -x["fill_t"]),
        "orders": sorted(orders, key=lambda x: -x["t"]),
        "curve": _downsample(curve),
        "by_strategy": by,
        # con escalera el perfil aprende de SUS cierres (T109), no de la sombra con TP
        "weights": {sid: (st.lrisk.strategy(sid, p) if ladder_on
                          else learner.at(sid, now, p.feedback)).to_json()
                    for sid in strategy_ids},
        "learning": "cierres propios (escalera)" if ladder_on else "sombra (SL/TP/BE+/tiempo)",
        "events_n": len(st.events),
        "min_open": {"target": p.min_open, "open": len(pos),
                     "pending_target": p.min_pending, "pending": len(orders),
                     "entries": sum(1 for t in tr if t.get("floor")),
                     "criteria": {k: judge(rs, p.feedback).to_json()
                                  for k, rs in st.floor_r.items()}},
    }
