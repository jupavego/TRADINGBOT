"""Métricas por perfil para comparar dos salidas (T111): A = TP/BE+/tiempo, B = escalera.

Amplían `ladder_stats` (que sirve al panel) con todo lo que pide la decisión de adopción: capital,
neto ganado y perdido, acierto, profit factor, expectativa, drawdown con su base declarada, costos,
motivos de cierre, errores de ejecución, estados inconsistentes y, cuando hay escalera, frecuencia
de activación, escalones alcanzados, flotante máximo, nivel máximo protegido y lo devuelto entre el
flotante máximo y el resultado final. Todo sale de lo REGISTRADO (operaciones cerradas, posiciones
abiertas al final y violaciones del libro): nada se estima. Función pura, sin I/O.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import numpy as np

from eim.paper.account import LIQ, max_dd_pct
from eim.paper.ladder_audit import SAFEGUARD

EXIT_KEYS = {"SL": "stop_inicial", "SLD": "stop_dinamico", LIQ: "liquidacion",
             SAFEGUARD: "salvaguarda", "TP": "tp", "BE": "be", "TIEMPO": "tiempo"}


def stats(xs: Sequence[float]) -> dict | None:
    """Media, mediana, máximo, mínimo y suma (None sin datos)."""
    if not xs:
        return None
    a = np.asarray(xs, dtype=float)
    return {"n": len(a), "mean": float(a.mean()), "median": float(np.median(a)),
            "max": float(a.max()), "min": float(a.min()), "sum": float(a.sum())}


def risk_of(t: dict) -> float | None:
    """Riesgo en USDT de la operación (el que la dimensionó); de `pnl / r` si no viene."""
    if t.get("risk_usd"):
        return float(t["risk_usd"])
    if t.get("r"):
        return abs(t["pnl"] / t["r"]) or None
    return None


def cost_of(t: dict) -> float:
    """Comisiones + deslizamiento + funding pagados (ya descontados del PnL, T106 (d))."""
    return t["fees"] + t["slip"] + t["funding"]


def max_dd_r(trades: Sequence[dict]) -> float:
    """Mayor caída del R acumulado (pico a valle, en R) en orden de cierre: no depende del tamaño
    de cada operación, así que compara salidas aunque no haya una cuenta detrás."""
    rs = [t["r"] for t in sorted(trades, key=lambda x: (x["exit_t"], x["id"]))
          if t["r"] is not None]
    if not rs:
        return 0.0
    cum = np.concatenate(([0.0], np.cumsum(rs)))
    return float((np.maximum.accumulate(cum) - cum).max())


def _protection(lad: list[dict], n: int) -> dict:
    """Lo que hizo la escalera en las operaciones cerradas que la tenían."""
    on = [t for t in lad if t["ladder"].get("stop_history")]
    maxf = [t["ladder"]["max_float_usd"] for t in lad
            if t["ladder"].get("max_float_usd") is not None]
    gaps = [t["ladder"]["max_float_usd"] - t["pnl"] for t in lad
            if t["ladder"].get("max_float_usd") is not None]
    prot = [t["pnl"] - t["ladder"]["protected_est_usd"] for t in lad
            if t["ladder"].get("protected_est_usd") is not None]
    top = max(lad, key=lambda t: (t["ladder"]["level"], t["ladder"].get("nominal_usd") or 0.0),
              default=None)
    levels = Counter(t["ladder"]["level"] for t in lad)
    risk = risk_of(top) if top else None
    return {
        "activated": len(on), "activation_rate": len(on) / n if n else None,
        "by_source": dict(Counter(t["ladder"].get("stop_source") or "inicial" for t in lad)),
        # escalón máximo de cada operación (la protección nunca baja: el final es el máximo)
        "levels": {str(k): levels[k] for k in sorted(levels)},
        "max_float_usd": stats(maxf),
        "max_level": top["ladder"]["level"] if top else 0,
        "max_level_usd": top["ladder"].get("nominal_usd") if top else None,
        "max_level_r": (top["ladder"]["nominal_usd"] / risk
                        if top and risk and top["ladder"].get("nominal_usd") else None),
        "gap_float_vs_final_usd": stats(gaps),
        "realized_vs_protected_usd": stats(prot),
    }


def profile_metrics(trades: Sequence[dict], open_pos: Sequence[dict], initial: float,
                    curve: Sequence[tuple[int, float]] | None, violations: Sequence[dict] = (),
                    dd_base: str = "equity") -> dict:
    """Métricas de un escenario. `open_pos` son las posiciones abiertas al final del camino (con
    su `upnl` ya acotado por el margen); entran en el capital final, nunca en las operaciones.
    Sin `curve` (A/B emparejado: no hay una cuenta detrás, los tamaños son los de A) no se informa
    capital ni drawdown en %, solo el neto y el drawdown en R."""
    pnl = [t["pnl"] for t in trades]
    rs = [t["r"] for t in trades if t["r"] is not None]
    won, lost = sum(x for x in pnl if x > 0), sum(x for x in pnl if x < 0)
    floating = float(sum(p.get("upnl", 0.0) for p in open_pos))
    n = len(trades)
    wins = sum(1 for x in pnl if x > 0)
    costs = [cost_of(t) for t in trades]
    cost_r = [cost_of(t) / r for t in trades if (r := risk_of(t))]
    mfe = [t["mfe_r"] * r for t in trades if t.get("mfe_r") is not None and (r := risk_of(t))]
    mfe_gap = [t["mfe_r"] * r - t["pnl"] for t in trades
               if t.get("mfe_r") is not None and (r := risk_of(t))]
    reasons = Counter(t["reason"] for t in trades)
    lad = [t for t in trades if t.get("ladder")]
    pos_lad = [p.get("ladder") or {} for p in open_pos]
    final = initial + sum(pnl) + floating
    return {
        "capital": None if curve is None else {
            "initial": initial, "final_balance": initial + sum(pnl), "floating_end": floating,
            "final_equity": final, "return_pct": final / initial - 1 if initial else None,
            "return_base": "equity (realizado + flotante de lo abierto al final)"},
        "floating_end": floating,
        "n": n, "wins": wins, "losses": n - wins,
        "win_rate": wins / n if n else None,
        "net": float(sum(pnl)), "net_won": float(won), "net_lost": float(lost),
        "pf": won / -lost if lost < 0 else None,
        "expectancy_usd": float(np.mean(pnl)) if pnl else None,
        "expectancy_r": float(np.mean(rs)) if rs else None,
        "avg_win_r": float(np.mean([r for r in rs if r > 0])) if any(r > 0 for r in rs) else None,
        "avg_loss_r": (float(np.mean([r for r in rs if r <= 0])) if any(r <= 0 for r in rs)
                       else None),
        "max_dd_pct": None if curve is None else max_dd_pct(list(curve)), "dd_base": dd_base,
        "max_dd_r": max_dd_r(trades),
        "costs": {"fees": float(sum(t["fees"] for t in trades)),
                  "slip": float(sum(t["slip"] for t in trades)),
                  "funding": float(sum(t["funding"] for t in trades)),
                  "total": float(sum(costs)), "mean_r": float(np.mean(cost_r)) if cost_r else None,
                  "funding_assumed": sum(1 for t in trades if t.get("funding_assumed"))},
        "exits": {**{v: reasons.get(k, 0) for k, v in EXIT_KEYS.items()},
                  "otros": sum(c for k, c in reasons.items() if k not in EXIT_KEYS)},
        "open_end": len(open_pos),
        "incidents": sum(1 for x in pos_lad if x.get("incident")),
        "inconsistent": (sum(1 for x in pos_lad if x.get("state") == "inconsistente")
                         + sum(1 for t in lad if t["ladder"].get("inconsistent"))),
        "violations": {"executed": sum(1 for v in violations if v.get("executed", True)),
                       "rejected": sum(1 for v in violations if not v.get("executed", True))},
        # avance máximo del PRECIO a favor (bruto, igual definición en A y B) y lo devuelto
        "mfe_usd": stats(mfe), "gap_mfe_vs_final_usd": stats(mfe_gap),
        "protection": _protection(lad, n) if lad else None,
    }
