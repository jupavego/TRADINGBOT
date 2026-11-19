"""T188 — el lado de la ganancia: la mitad de la posición sigue corriendo con un stop más amplio.

Por cada operación de perfil del libro fijo: la mitad sale como salió (la escalera) y la otra
mitad se simula sobre el camino de precios desde el llenado, con el SL inicial; tras avanzar
`RUNNER_BE_R` el stop pasa a la entrada más el costo y desde ahí sigue al extremo a
`RUNNER_TRAIL_R` de distancia; si nada lo saca, sale al cierre de la última vela del plazo.

Orden adverso dentro de cada vela: si en la misma vela se toca el stop y se marca un extremo
nuevo, sale el stop (no se mueve el stop con un extremo que pudo llegar después). Un hueco sale a
la apertura. Costo: el de la operación real (comisiones y deslizamiento sobre su riesgo); no suma
funding de la parte que sigue abierta (limitación declarada en el pre-registro).

Puro: recibe el camino como arreglos (`t`, `o`, `h`, `l`, `c`, `step`), igual que `engine.Path`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from eim.paper.asym import prereg as P
from eim.paper.asym.loss_side import Pair, day_of, num, unit_r


class PathLike(Protocol):
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray  # noqa: E741 - mismo nombre que `engine.Path`
    c: np.ndarray
    step: int


@dataclass(frozen=True)
class RunnerExit:
    price: float
    t: int
    reason: str          # "SL" (inicial), "STOP" (break-even o móvil) o "TIEMPO"
    r: float             # neto, sobre el riesgo de la operación


def run(path: PathLike, side: int, fill: float, sl: float, fill_t: int, hold_ms: int,
        cost_r: float) -> RunnerExit | None:
    """Salida de la parte que sigue. None si el camino aún no cubre el plazo y no salió."""
    dist = abs(fill - sl)
    if dist <= 0 or side not in (1, -1) or not len(path.t):
        return None
    j = int(np.searchsorted(path.t, fill_t))
    end_t = fill_t + hold_ms
    stop, moved, ext = sl, False, fill
    be = fill + side * cost_r * dist
    while j < len(path.t) and path.t[j] < end_t:
        o, h, lo = path.o[j], path.h[j], path.l[j]
        hit = lo <= stop if side > 0 else h >= stop
        if hit:
            gap = o <= stop if side > 0 else o >= stop
            px = float(o if gap else stop)
            r = side * (px - fill) / dist - cost_r
            return RunnerExit(px, int(path.t[j]), "STOP" if moved else "SL", r)
        ext = max(ext, h) if side > 0 else min(ext, lo)
        if side * (ext - fill) >= P.RUNNER_BE_R * dist:
            trail = ext - side * P.RUNNER_TRAIL_R * dist
            new = max(be, trail) if side > 0 else min(be, trail)
            if (new > stop) if side > 0 else (new < stop):
                stop, moved = new, True
        j += 1
    if j >= len(path.t) and int(path.t[-1]) + path.step < end_t:
        return None                     # el plazo no se cumplió todavía: no se compara
    k = max(0, j - 1)
    px = float(path.c[k])
    return RunnerExit(px, int(path.t[k]) + path.step, "TIEMPO", side * (px - fill) / dist - cost_r)


def cost_r_of(row: Mapping) -> float:
    """Comisiones y deslizamiento de la operación real, sobre su riesgo."""
    r, pnl = num(row.get("r")), num(row.get("pnl_usdt"))
    risk = abs(pnl / r) if r else 0.0
    return (num(row.get("fees")) + num(row.get("slip"))) / risk if risk > 0 else 0.0


def runner_pairs(rows: Sequence[Mapping], paths: Mapping[str, PathLike]) -> tuple[list[Pair], int]:
    """(parejas, pendientes). Las que el camino aún no resuelve no se comparan."""
    out, pending = [], 0
    for row in rows:
        path = paths.get(str(row.get("symbol")))
        hold = P.RUNNER_MAX_HOLD_MS.get(str(row.get("timeframe")))
        if path is None or hold is None:
            pending += 1
            continue
        ex = run(path, int(num(row.get("side"))), num(row.get("fill")), num(row.get("sl")),
                 int(num(row.get("fill_t"))), hold, cost_r_of(row))
        if ex is None:
            pending += 1
            continue
        w, r = num(row.get("weight"), 1.0), num(row.get("r"))
        a = unit_r(row)
        cf = w * ((1 - P.RUNNER_SHARE) * r + P.RUNNER_SHARE * ex.r)
        usd = num(row.get("pnl_usdt"))
        risk = abs(usd / r) if r else 0.0
        out.append(Pair(str(row.get("ledger_id")), day_of(row), a, cf, usd,
                        usd + risk * P.RUNNER_SHARE * (ex.r - r), True))
    return out, pending
