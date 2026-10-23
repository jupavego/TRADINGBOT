"""Métricas de la protección progresiva (PPP) a partir de las operaciones cerradas del libro.

Solo lectura. Todo se calcula de lo registrado; los tiempos son analíticos y jamás cierran nada.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from eim.paper.account import LIQ
from eim.paper.ladder_audit import ALLOWED_CLOSE, SAFEGUARD

HOUR_MS = 3_600_000
DUR_EDGES_H = (1, 4, 12, 24, 72)


def _mean(xs: list[float]) -> float | None:
    return float(np.mean(xs)) if xs else None


def _bucket(h: float) -> str:
    for e in DUR_EDGES_H:
        if h < e:
            return f"< {e} h"
    return f"≥ {DUR_EDGES_H[-1]} h"


def _split(trades: list[dict], key) -> dict:
    out: dict[str, dict] = {}
    for t in trades:
        b = out.setdefault(str(key(t)), {"n": 0, "pnl": 0.0, "wins": 0})
        b["n"] += 1
        b["pnl"] += t["pnl"]
        b["wins"] += int(t["pnl"] > 0)
    return out


def exit_counts(tr: list[dict], incidents: int, rejected: int) -> dict:
    """Los cinco motivos que pueden terminar (o detener) una operación con escalera, por separado
    (T109), más lo que NO debería aparecer nunca: cierres con otro motivo y cierres rechazados."""
    n = Counter(t["reason"] for t in tr)
    return {"stop_inicial": n["SL"], "stop_dinamico": n["SLD"], "liquidacion": n[LIQ],
            "salvaguarda": n[SAFEGUARD], "incidencia_abierta": incidents,
            "otros_motivos": sum(v for k, v in n.items() if k not in ALLOWED_CLOSE),
            "rechazados": rejected}


def ladder_stats(trades: list[dict], open_pos: list[dict], violations: int,
                 incidents: int, first: float, step: float, rejected: int = 0) -> dict:
    tr = [t for t in trades if t.get("ladder")]
    maxf = [t["ladder"]["max_float_usd"] for t in tr if t["ladder"]["max_float_usd"] is not None]
    reached: Counter = Counter()
    for t in tr:
        for n in range(1, t["ladder"]["level"] + 1):
            reached[n] += 1
    top = max(reached, default=0)
    levels = [{"level": n, "nominal": first + (n - 1) * step, "reached": reached[n]}
              for n in range(1, top + 1)]
    by_level: dict[str, dict] = {}
    for t in tr:
        lv = t["ladder"]["level"]
        b = by_level.setdefault(str(lv), {"n": 0, "pnl": 0.0, "pullbacks": 0})
        b["n"] += 1
        b["pnl"] += t["pnl"]
        b["pullbacks"] += int(t["reason"] == "SLD")       # retrocedió y activó el SL vigente
    gaps = [t["ladder"]["max_float_usd"] - t["pnl"] for t in tr
            if t["ladder"]["max_float_usd"] is not None]
    prot = [t["pnl"] - t["ladder"]["protected_est_usd"] for t in tr
            if t["ladder"].get("protected_est_usd") is not None]
    hours = [t["ladder"]["elapsed_ms"] / HOUR_MS for t in tr]
    streak = best = 0
    for t in sorted(tr, key=lambda x: x["exit_t"]):
        streak = streak + 1 if t["pnl"] <= 0 else 0
        best = max(best, streak)
    long_run = sum(1 for p in open_pos if p.get("elapsed_h", 0) >= DUR_EDGES_H[-2])
    return {
        # `first`/`step` son los escalones de REFERENCIA del perfil (con basis "r" cada operación
        # tiene los suyos, guardados en su propio `ladder.first_usd`/`step_usd`).
        "n": len(tr), "reached": levels, "first_usd": first, "step_usd": step,
        "closed_initial_sl": sum(1 for t in tr if t["reason"] == "SL"),
        "closed_dynamic_sl": sum(1 for t in tr if t["reason"] == "SLD"),
        "avg_max_float_usd": _mean(maxf), "avg_realized_usd": _mean([t["pnl"] for t in tr]),
        "avg_gap_max_vs_realized_usd": _mean(gaps),
        # realizado − protegido estimado (deslizamiento, funding y huecos)
        "avg_realized_vs_protected_usd": _mean(prot),
        "by_max_level": by_level,
        "by_side": _split(tr, lambda t: "LONG" if t["side"] > 0 else "SHORT"),
        "by_regime": _split(tr, lambda t: t.get("regime") or "sin dato"),
        "by_entry_hour_utc": _split(tr, lambda t: (t["fill_t"] // HOUR_MS) % 24),
        "by_strategy": _split(tr, lambda t: t["sid"]),
        "avg_hours": _mean(hours),
        "duration": dict(Counter(_bucket(h) for h in hours)),
        "long_open_positions": long_run, "max_consecutive_losses": best,
        "violations": violations, "incidents": incidents,
        "exits": exit_counts(tr, incidents, rejected),
        "note": "Tiempos solo analíticos (nunca cierran). «Protegido estimado» = neto del SL "
                "vigente con el deslizamiento esperado; el realizado puede diferir por hueco, "
                "deslizamiento de la vela y funding.",
    }
