"""Calidad de la salida de cada perfil y A/B en vivo frente a la sombra (T130, ◆1 de T129).

Lo que decide si una salida destruye la poca ventaja que haya (T129 §1.4): ganancia y pérdida
media en R, acierto de equilibrio (el que haría falta para empatar con ellas), costo medio en R,
E[R] antes de costos y qué parte de lo ganado en bruto se llevan los costos. Y el A/B emparejado
en vivo: la sombra (`engine.simulate`) ya simula la salida A (TP/BE+/tiempo) para CADA idea, así
que comparar el libro del perfil con la sombra de las mismas ideas mide la salida sin tocar el
vivo. Las operaciones de varios perfiles comparten ideas: no son independientes entre sí.

Puro: sin I/O. `trades` son las filas del libro (`book.py`), `shadow` las `Outcome` de la vista.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence

import numpy as np

from eim.paper.ladder_metrics import cost_of, profile_metrics, risk_of


def _mean(xs: Sequence[float]) -> float | None:
    return float(np.mean(xs)) if xs else None


def _pairs(trades: Sequence[dict], shadow: Mapping[str, object]) -> dict | None:
    got = [(t, o) for t in trades if t.get("r") is not None
           and (o := shadow.get(t["id"])) is not None and o.status == "CERRADA"
           and o.r is not None]
    if not got:
        return None

    def side(sel: list[tuple[dict, object]]) -> dict | None:
        if not sel:
            return None
        return {"n": len(sel), "book_r": _mean([t["r"] for t, _ in sel]),
                "shadow_r": _mean([o.r for _, o in sel])}

    book_r, sh_r = [t["r"] for t, _ in got], [o.r for _, o in got]
    return {
        "n": len(got), "book_r": _mean(book_r), "shadow_r": _mean(sh_r),
        "delta_r": _mean([b - s for b, s in zip(book_r, sh_r, strict=True)]),
        "book_win_rate": sum(r > 0 for r in book_r) / len(got),
        "shadow_win_rate": sum(r > 0 for r in sh_r) / len(got),
        "shadow_exits": dict(Counter(o.reason for _, o in got)),
        # dónde gana y dónde pierde la salida del perfil frente a la sombra
        "when_shadow_tp": side([(t, o) for t, o in got if o.reason == "TP"]),
        "when_shadow_sl": side([(t, o) for t, o in got if o.reason == "SL"]),
    }


def exit_quality(trades: Sequence[dict], shadow: Mapping[str, object]) -> dict:
    """Resumen de la salida de un perfil sobre sus operaciones cerradas."""
    m = profile_metrics(trades, [], 0.0, None)
    gross = [t["pnl"] + cost_of(t) for t in trades]
    gross_r = [g / r for t, g in zip(trades, gross, strict=True) if (r := risk_of(t))]
    won, lost = m["avg_win_r"], m["avg_loss_r"]
    by_exit: dict[str, dict] = {}
    for reason in sorted({t["reason"] for t in trades}):
        rs = [t["r"] for t in trades if t["reason"] == reason and t["r"] is not None]
        by_exit[reason] = {"n": len(rs), "mean_r": _mean(rs)}
    gross_won = float(sum(g for g in gross if g > 0))
    return {
        "n": m["n"], "win_rate": m["win_rate"], "pf": m["pf"], "net": m["net"],
        "expectancy_r": m["expectancy_r"], "avg_win_r": won, "avg_loss_r": lost,
        # con estas ganancia y pérdida medias, el acierto que haría falta para empatar
        "breakeven_win_rate": (-lost / (won - lost) if won is not None and lost is not None
                               and won - lost > 0 else None),
        "cost_mean_r": m["costs"]["mean_r"], "gross_expectancy_r": _mean(gross_r),
        "costs_vs_gross_won": m["costs"]["total"] / gross_won if gross_won > 0 else None,
        "by_exit": by_exit, "vs_shadow": _pairs(trades, shadow),
    }


def desk_exit_quality(books: Mapping[str, object], outcomes: Iterable) -> dict:
    """`exit_quality` de cada perfil de una vista (`View.books`, `View.outcomes`)."""
    shadow = {o.idea.id: o for o in outcomes}
    return {pid: exit_quality(st.trades, shadow) for pid, st in books.items()}
