"""La sombra calibrada con el libro, por perfil y marco (T179). Puro.

La puerta de costo de T143 (3) decide con lo que la **sombra** dice que cuesta un marco, pero el
libro de cada perfil paga más. Emparejadas idea a idea en la corrida t143 (2026-11-17, 94 parejas
de 15 m), las dos tienen el mismo stop y la misma clase de entrada. Lo que cambia es la salida: la
escalera cierra por stop dinámico, como tomador, casi nunca por la misma salida que la sombra
(9 de 41 en el agresivo). Eso añade ≈ 1 pb de comisión y de 1,2 a 2,7 pb de deslizamiento, y más
al agresivo, que mueve más nocional. Por eso la sombra que el agresivo aceptaría da 0,132 R en
15 m y su libro paga 0,185.

El factor es costo vivido / costo de las gemelas de la sombra, sobre las operaciones del libro
fijo que cuentan como resultado (T144): un cociente de sumas, no una media de cocientes, para que
una operación con el stop pegado no lo dispare. Con menos de `MIN_PAIRS` parejas propias se usa el
de todos los perfiles en ese marco, y sin parejas, 1. Se acota a `BOUNDS`: medir no puede llevar
la puerta a un extremo absurdo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from eim.paper.cost_ledger import trade_cost
from eim.paper.engine import Outcome
from eim.paper.universe import result_rows

MIN_PAIRS = 30
BOUNDS = (0.5, 3.0)
ALL = "*"


def shadow_cost(o: Outcome) -> float | None:
    """Costo en R de una operación de la sombra, o None si no llegó a operar."""
    if o.status != "CERRADA" or not o.risk:
        return None
    return (o.fee_in + o.fee_out + o.slip + o.funding) / o.risk


def factors(rows: Iterable[Mapping], outcomes: Iterable[Outcome],
            min_pairs: int = MIN_PAIRS) -> dict[str, dict]:
    """`perfil@marco` (y `*@marco`: todos los perfiles) → {"factor", "n"} si hay muestra."""
    twin = {o.idea.id: c for o in outcomes if (c := shadow_cost(o)) is not None and c > 0}
    acc: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for r in result_rows(rows):
        s = twin.get(r.get("idea_id"))
        b = trade_cost(dict(r))["cost_r"]
        if s is None or b is None:
            continue
        tf = str(r.get("timeframe"))
        for key in ((str(r.get("profile")), tf), (ALL, tf)):
            acc.setdefault(key, []).append((b, s))
    out: dict[str, dict] = {}
    for (p, tf), v in acc.items():
        if len(v) < min_pairs:
            continue
        f = sum(b for b, _ in v) / sum(s for _, s in v)
        out[f"{p}@{tf}"] = {"factor": round(min(max(f, BOUNDS[0]), BOUNDS[1]), 4), "n": len(v)}
    return out


def factor_for(fac: Mapping[str, dict], profile: str, tf: str) -> tuple[float, str]:
    """(factor, de dónde sale) para un perfil y un marco."""
    for key, label in ((f"{profile}@{tf}", "propio"), (f"{ALL}@{tf}", "del marco")):
        if (x := fac.get(key)) is not None:
            return float(x["factor"]), f"{label}, {x['n']} parejas"
    return 1.0, "sin parejas con el libro"
