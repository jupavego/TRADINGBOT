"""Prueba de techo de T80 (a) y (d): ¿cuánto hay que capturar y cuánto se lo come el costo?

Puro: arreglos del panel dentro, diccionarios fuera. Dos lecturas por horizonte y estilo:

- **sin reacción**: cota de arriba inalcanzable. Se conoce la dirección del mid con previsión
  perfecta y se entra al instante, sin selección adversa, sin cola y sin impacto. Si aquí no
  paga, no paga en ninguna parte.
- **con la reacción medida** (T77): la señal se forma al cierre del cubo y la entrada ocurre un
  cubo después, así que lo que se puede capturar es el tramo que queda.

El techo por ventana es E[máx(|Δmid| − c, 0)]: se opera solo cuando paga y siempre del lado
bueno. La parte que consume el costo (entregable d) es 1 − techo/E[|Δmid|] sobre las ventanas que
pagan, y además se publica qué fracción del movimiento bruto medio es costo.

Las ventanas se solapan (una por cubo): los percentiles y las medias valen; los errores estándar
de aquí NO (eso lo da el marco fuera de muestra, `edge_oos.py`, con bloques de día).
"""

from __future__ import annotations

import numpy as np

from eim.hft.evaluation.labels import ROUND_TRIPS_BPS, forward_window_bps, passive_fill

PCTS = (50, 90, 95, 99)


def _dist(d: np.ndarray) -> dict:
    return {"n": int(d.size), "mean_abs_bps": round(float(np.abs(d).mean()), 4),
            **{f"p{q}_abs_bps": round(float(np.percentile(np.abs(d), q)), 4) for q in PCTS}}


def style_row(d: np.ndarray, cost_bps: float) -> dict:
    """Oportunidad y techo con previsión perfecta para un costo de ida y vuelta."""
    a = np.abs(d)
    pays = a > cost_bps
    gross = float(a[pays].mean()) if pays.any() else 0.0
    ceil = float(np.maximum(a - cost_bps, 0.0).mean())
    return {"cost_bps": cost_bps,
            "frac_pays": round(float(pays.mean()), 6),
            "ceiling_bps_per_window": round(ceil, 5),
            "gross_bps_when_pays": round(gross, 4),
            "net_bps_when_pays": round(gross - cost_bps if pays.any() else 0.0, 4),
            "cost_share_when_pays": round(cost_bps / gross, 4) if gross > 0 else None,
            "cost_share_of_mean_move": (round(cost_bps / float(a.mean()), 3)
                                        if a.mean() > 0 else None)}


def horizon_block(t: np.ndarray, mid: np.ndarray, complete: np.ndarray, horizon_s: int,
                  costs_bps: dict[str, float], reaction_ms: int) -> dict:
    """Distribución de |Δmid| y techo por estilo, sin reacción y con la reacción medida."""
    out: dict = {"horizon_s": horizon_s}
    for key, lag in (("no_reaction", 0), ("with_reaction", reaction_ms)):
        d, ok = forward_window_bps(t, mid, lag, horizon_s * 1000, complete)
        d = d[ok]
        if d.size == 0:
            out[key] = {"n": 0}
            continue
        block = _dist(d)
        block["styles"] = {name: style_row(d, c) for name, c in costs_bps.items()}
        out[key] = block
    return out


def bound_table(t: np.ndarray, mid: np.ndarray, complete: np.ndarray, horizons_s,
                costs_bps: dict[str, float] | None = None, reaction_ms: int = 1_000) -> dict:
    """Tabla de techo por horizonte (la (a) y la (d) del entregable 3)."""
    costs = costs_bps or ROUND_TRIPS_BPS
    return {"costs_bps": costs, "reaction_ms": reaction_ms,
            "horizons": {str(h): horizon_block(t, mid, complete, int(h), costs, reaction_ms)
                         for h in horizons_s}}


def fill_table(panel, wait_steps=(1, 5, 30)) -> dict:
    """Llenado de una orden pasiva al mejor precio con cola pesimista, por espera (en cubos).

    Es la condición de existencia de la entrada maker: sin llenado no hay operación barata, y el
    techo maker de arriba se tiene que multiplicar por esta fracción.
    """
    out: dict = {}
    for w in wait_steps:
        row = {}
        for side, name in ((1, "buy"), (-1, "sell")):
            f = passive_fill(panel.bid_q[:, 0], panel.ask_q[:, 0], panel.bid_p[:, 0],
                             panel.ask_p[:, 0], panel.buy_v, panel.sell_v, int(w), side)
            row[name] = round(float(f[panel.complete].mean()), 4)
        row["both"] = round((row["buy"] + row["sell"]) / 2, 4)
        out[str(w)] = row
    return out


def queue_summary(panel) -> dict:
    """Cola visible al llegar (BTC) y spread, para leer el llenado con contexto."""
    ok = panel.complete
    bq, aq = panel.bid_q[ok, 0], panel.ask_q[ok, 0]
    spread = (panel.ask_p[ok, 0] - panel.bid_p[ok, 0]) / panel.mid[ok] * 1e4
    turn = (panel.buy_v + panel.sell_v)[ok]
    return {"front_qty_p50": round(float(np.median(np.concatenate([bq, aq]))), 4),
            "spread_bps_p50": round(float(np.median(spread)), 4),
            "spread_bps_p95": round(float(np.percentile(spread, 95)), 4),
            "volume_per_s_p50": round(float(np.median(turn)), 4),
            "volume_per_s_mean": round(float(turn.mean()), 4)}
