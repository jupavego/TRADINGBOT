"""Deslizamiento del stop medido contra el libro capturado (T136 (6), E4b).

Hoy el costo del stop es un **modelo** (`CostParams`: base + volatilidad + impacto, con tope), no
un dato. La captura HFT de T78 guarda el mejor bid y el mejor ask con marca de tiempo, así que
desde que existe cobertura se puede comparar, para cada stop que el bróker simulado disparó, el
deslizamiento que el modelo supuso con el que daba el libro **en ese instante**.

Convenio de signo: `bps` **positivo = peor para el operador**. Un largo cierra vendiendo, así que
se cruza contra el **bid**; un corto cierra comprando y se cruza contra el **ask**.

Es prospectivo por definición: solo mide stops posteriores al inicio de la captura. Si el modelo
se queda corto, la corrección es una **versión nueva** del modelo de costos (◆), no un ajuste
silencioso.

Puro: sin red y sin disco. Quien lee los parquet es `scripts/t136_deslizamiento.py`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

STOP_REASONS = ("SL", "SLD", "SL_ESCALERA", "LIQ")   # cierres por stop del libro (T106)


@dataclass(frozen=True)
class StopFill:
    """Un stop que el bróker simulado disparó, como lo cuenta su libro."""

    id: str
    profile: str
    side: int
    qty: float
    stop: float             # nivel al que el libro dice que salió
    notional: float
    slip_usd: float         # deslizamiento que el modelo cobró
    exit_t: int


@dataclass(frozen=True)
class Touch:
    """La punta del libro capturado en un instante."""

    t_ms: int
    bid_p: float
    bid_q: float
    ask_p: float
    ask_q: float


def model_bps(f: StopFill) -> float:
    """Deslizamiento que supuso el modelo, en puntos básicos del nocional."""
    if f.notional <= 0:
        return math.nan
    return 1e4 * f.slip_usd / f.notional


def crossing(f: StopFill, b: Touch) -> dict:
    """Lo que daba el libro: contra qué punta se cruza, si aguanta la cantidad y cuánto cuesta."""
    touch = b.bid_p if f.side > 0 else b.ask_p
    room = b.bid_q if f.side > 0 else b.ask_q
    if not touch or f.stop <= 0:
        return {"touch": None, "enough": None, "real_bps": None}
    gap = (f.stop - touch) if f.side > 0 else (touch - f.stop)
    return {"touch": touch, "touch_qty": room, "enough": bool(room >= f.qty),
            "real_bps": 1e4 * gap / f.stop, "spread_bps": 1e4 * (b.ask_p - b.bid_p) / f.stop,
            "at_ms": b.t_ms}


def first_crossed(f: StopFill, book: Sequence[Touch]) -> Touch | None:
    """Primer instante de la ventana en que la punta alcanza el nivel del stop.

    Para un largo, cuando el bid baja al stop o por debajo; para un corto, cuando el ask sube a
    él. `None` si en toda la ventana el libro no llegó al nivel: eso no se inventa, se informa.
    """
    for b in book:
        if f.side > 0 and b.bid_p and b.bid_p <= f.stop:
            return b
        if f.side < 0 and b.ask_p and b.ask_p >= f.stop:
            return b
    return None


def rows_found(fills: Sequence[StopFill],
               found: dict[str, tuple[Touch | None, int]]) -> list[dict]:
    """Una fila por stop desde el cruce ya localizado: `{id: (punta o None, puntas en la vela)}`.

    Quien busca el cruce puede hacerlo en SQL (una vela de `bbo` son millones de mensajes), así
    que esta función no recorre nada: solo interpreta y dice por qué un stop no se pudo medir.
    """
    out = []
    for f in fills:
        b, n = found.get(f.id, (None, 0))
        row = {"id": f.id, "profile": f.profile, "side": f.side, "qty": f.qty, "stop": f.stop,
               "exit_t": f.exit_t, "model_bps": model_bps(f), "n_book": n}
        if not n:
            out.append(row | {"state": "sin cobertura", "real_bps": None})
            continue
        if b is None:
            out.append(row | {"state": "el libro no llegó al nivel", "real_bps": None})
            continue
        got = crossing(f, b)
        short = got["real_bps"] is not None and got["real_bps"] > row["model_bps"]
        out.append(row | got | {"state": "medido", "model_short": bool(short)})
    return out


def rows(fills: Sequence[StopFill], books: dict[str, Sequence[Touch]]) -> list[dict]:
    """Lo mismo con la ventana entera en memoria: busca el cruce y luego interpreta."""
    found = {}
    for f in fills:
        win = books.get(f.id) or ()
        found[f.id] = (first_crossed(f, win) if win else None, len(win))
    return rows_found(fills, found)


def summary(rs: Sequence[dict]) -> dict:
    """Resumen honesto: qué se pudo medir, qué dio y si el modelo se queda corto."""
    measured = [r for r in rs if r["state"] == "medido" and r["real_bps"] is not None]
    states: dict[str, int] = {}
    for r in rs:
        states[r["state"]] = states.get(r["state"], 0) + 1
    out = {"n_stops": len(rs), "n_measured": len(measured), "states": states}
    if not measured:
        return out | {"verdict": "sin cobertura suficiente", "model_short_share": None}
    real = np.array([r["real_bps"] for r in measured], dtype=float)
    mdl = np.array([r["model_bps"] for r in measured], dtype=float)
    short = float(np.mean(real > mdl))
    return out | {
        "real_bps": {"median": float(np.median(real)), "mean": float(real.mean()),
                     "p90": float(np.quantile(real, 0.9))},
        "model_bps": {"median": float(np.median(mdl)), "mean": float(mdl.mean())},
        "diff_bps_median": float(np.median(real - mdl)),
        "spread_bps_median": float(np.median([r["spread_bps"] for r in measured
                                              if r.get("spread_bps") is not None])),
        "enough_at_touch_share": float(np.mean([bool(r.get("enough")) for r in measured])),
        "model_short_share": short,
        # con menos de 30 stops medidos no se concluye nada sobre el modelo
        "verdict": ("muestra insuficiente para concluir" if len(measured) < 30 else
                    "el modelo se queda corto" if short > 0.5 else "el modelo aguanta"),
    }
