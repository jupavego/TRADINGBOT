"""T187 — el lado de la pérdida, en sombra sobre las operaciones de perfil del libro fijo.

Cada función recibe filas del libro (`eim.paper.ledger.COLS`, ya filtradas por el universo
oficial de T144) y devuelve, por fila, lo que habría dejado con la regla. La unidad común es el
**R unitario del perfil** (`r × peso`): el R del libro va sobre el riesgo de esa operación, que ya
incluye el peso, así que un cambio de tamaño no se vería en `r`; en R unitario sí.

Puro: sin red, sin disco y sin estado.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from eim.paper.asym import prereg as P
from eim.paper.feedback import judge
from eim.paper.params import FeedbackParams


def num(x: object, default: float = 0.0) -> float:
    """Número tolerante (el libro trae None y el CSV cadenas)."""
    if x is None or isinstance(x, bool):
        return default
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


@dataclass(frozen=True)
class Pair:
    """Una operación medida: lo que dejó y lo que habría dejado, en R unitario."""

    key: str            # ledger_id
    day: int            # día UTC de apertura (bloque del bootstrap)
    actual: float
    cf: float
    usd_actual: float = 0.0
    usd_cf: float = 0.0
    changed: bool = False

    @property
    def delta(self) -> float:
        return self.cf - self.actual


def unit_r(row: Mapping) -> float:
    return num(row.get("r")) * num(row.get("weight"), 1.0)


def day_of(row: Mapping) -> int:
    return int(num(row.get("opened_t")) // P.DAY_MS)


def measured(rows: Sequence[Mapping]) -> list[Mapping]:
    """Las que cuentan para la medición: abiertas desde el inicio del pre-registro."""
    return [r for r in rows if num(r.get("opened_t")) >= P.START_MS]


def _pair(row: Mapping, factor: float) -> Pair:
    a, usd = unit_r(row), num(row.get("pnl_usdt"))
    return Pair(str(row.get("ledger_id")), day_of(row), a, a * factor, usd, usd * factor,
                abs(factor - 1.0) > 1e-12)


# --- T187a: pérdida acotada a 1 R con costos (solo informa) ---------------------------------
def capped_loss(rows: Sequence[Mapping], est_cost_frac: Callable[[str], float]) -> list[Pair]:
    """Tamaño × d/(d + costo estimado), d = |entrada − SL|/entrada: la regla de
    `risk_budget.qty_for_risk` con `risk_includes_costs`. Las ya dimensionadas así no cambian."""
    out = []
    for row in rows:
        fill, sl = num(row.get("fill")), num(row.get("sl"))
        d = abs(fill - sl) / fill if fill > 0 else 0.0
        c = max(0.0, est_cost_frac(str(row.get("profile"))))
        out.append(_pair(row, d / (d + c) if d > 0 else 1.0))
    return out


# --- T187b: una idea, un solo riesgo ------------------------------------------------------
def bet_key(row: Mapping) -> tuple:
    return (row.get("profile"), row.get("symbol"), int(num(row.get("side"))),
            int(num(row.get("opened_t"))))


def one_bet(rows: Sequence[Mapping]) -> list[Pair]:
    """En un perfil, las entradas de la misma vela y el mismo sentido son una sola apuesta:
    cuenta la primera (`opened_t` menor; empate: mayor peso, luego `ledger_id`)."""
    order = sorted(rows, key=lambda r: (num(r.get("opened_t")), -num(r.get("weight")),
                                        str(r.get("ledger_id"))))
    seen: set[tuple] = set()
    keep: dict[str, bool] = {}
    for r in order:
        k = bet_key(r)
        keep[str(r.get("ledger_id"))] = k not in seen
        seen.add(k)
    return [_pair(r, 1.0 if keep[str(r.get("ledger_id"))] else 0.0) for r in rows]


# --- T187c: el peso no sube por rasguños ----------------------------------------------------
def edge_ok(rs: Sequence[float], fb: FeedbackParams) -> bool:
    """¿Respaldan los cierres propios un peso > 1? Solo con muestra y `m − z·se > 0`."""
    if len(rs) < P.WEIGHT_MIN_N:
        return False
    j = judge(rs, fb)
    return math.isfinite(j.se) and j.m - P.WEIGHT_Z * j.se > 0


def capped_weight(rows: Sequence[Mapping], history: Sequence[Mapping],
                  feedback: Callable[[str], FeedbackParams]) -> list[Pair]:
    """Peso tope `WEIGHT_CAP` salvo que los cierres previos de esa estrategia@marco en ese perfil
    (en `history`, cerrados antes de la apertura) lo respalden. Las del mínimo no cambian."""
    by: dict[tuple, list[tuple[float, float]]] = {}
    for h in history:
        by.setdefault((h.get("profile"), h.get("sid")), []).append(
            (num(h.get("exit_t")), num(h.get("r"))))
    for v in by.values():
        v.sort()
    out = []
    for row in rows:
        w = num(row.get("weight"), 1.0)
        if w <= P.WEIGHT_CAP or str(row.get("floor_trade")).lower() == "true":
            out.append(_pair(row, 1.0))
            continue
        t0 = num(row.get("opened_t"))
        rs = [r for t, r in by.get((row.get("profile"), row.get("sid")), []) if t < t0]
        ok = edge_ok(rs, feedback(str(row.get("profile"))))
        out.append(_pair(row, 1.0 if ok else P.WEIGHT_CAP / w))
    return out
