"""Puerta de marcos por costo (T143, entregable 3): el marco caro no opera, y vuelve solo.

En 15 m el stop está más cerca que en ningún otro marco, así que la misma comisión pesa más en R:
T136 midió 0,157 R por operación en 15 m, 0,123 en 1 h y 0,091 en 4 h, y el diagnóstico de la
fase 24 encontró que la fricción del libro superaba la pérdida neta entera. Un marco cuyo costo
se come la sexta parte del riesgo en cada viaje no puede ganar: antes de buscar ventaja hay que
dejar de pagarla.

**La decisión no se toma a mano.** El umbral vive en `ExecParams.tf_max_cost_r` y se comprueba en
cada ciclo contra el costo que la **sombra** mide en ese marco. La sombra sigue evaluando todos
los marcos aunque los perfiles no operen en ellos —no consume capital—, así que si el costo de un
marco baja del umbral, el marco **vuelve por sí solo** sin que nadie toque configuración. Y al
revés: si 1 h se encareciera, saldría igual.

Mientras un marco no tenga operaciones de sombra suficientes (`tf_cost_min_n`) se usa la medición
de T136 como punto de partida, que es un dato, no un supuesto: sin ella el primer arranque
dejaría operar un marco del que todavía no se sabe nada, y de 15 m ya se sabe.

Puro: sin red, sin disco y sin estado.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence

from eim.paper.engine import Outcome

_log = logging.getLogger(__name__)

#: Costo medio en R por marco medido en el banco de T131 (T136 §1 · `reports/t136_riesgo.md`).
BASELINE_COST_R: Mapping[str, float] = {"15m": 0.157, "1h": 0.123, "4h": 0.091}


def cost_by_tf(outcomes: Iterable[Outcome]) -> dict[str, tuple[float, int]]:
    """Costo medio en R y número de operaciones por marco, medido en la sombra.

    Solo cuenta las cerradas con riesgo válido: una idea que no llegó a operar no tiene costo.
    """
    acc: dict[str, list[float]] = {}
    for o in outcomes:
        if o.status != "CERRADA" or not o.risk:
            continue
        cost = (o.fee_in + o.fee_out + o.slip + o.funding) / o.risk
        acc.setdefault(o.idea.timeframe, []).append(cost)
    return {tf: (sum(v) / len(v), len(v)) for tf, v in acc.items()}


def reference(tf: str, measured: Mapping[str, tuple[float, int]],
              min_n: int) -> tuple[float | None, str]:
    """Costo con el que se juzga el marco y de dónde sale (`source`, como pide el proyecto)."""
    c, n = measured.get(tf, (None, 0))
    if c is not None and n >= min_n:
        return c, f"sombra ({n} operaciones)"
    base = BASELINE_COST_R.get(tf)
    if base is None:
        return None, "sin medición"
    return base, f"T136 (banco de T131); la sombra lleva {n} de {min_n}"


def admitted(tfs: Sequence[str], measured: Mapping[str, tuple[float, int]],
             max_cost_r: float | None, min_n: int) -> tuple[str, ...]:
    """Marcos en los que los perfiles pueden operar. La sombra no se filtra nunca."""
    return tuple(tf for tf in tfs if not _blocked(tf, measured, max_cost_r, min_n))


def _blocked(tf: str, measured: Mapping[str, tuple[float, int]],
             max_cost_r: float | None, min_n: int) -> bool:
    if max_cost_r is None:          # puerta apagada (configuración de T31)
        return False
    c, _ = reference(tf, measured, min_n)
    return c is not None and c >= max_cost_r


def report(tfs: Sequence[str], measured: Mapping[str, tuple[float, int]],
           max_cost_r: float | None, min_n: int) -> list[dict]:
    """Una fila por marco para el panel y la auditoría: costo, procedencia y si opera."""
    out = []
    for tf in tfs:
        c, src = reference(tf, measured, min_n)
        out.append({"timeframe": tf, "cost_r": c, "source": src, "max_cost_r": max_cost_r,
                    "admitted": not _blocked(tf, measured, max_cost_r, min_n)})
    return out


def why(tf: str, measured: Mapping[str, tuple[float, int]], max_cost_r: float | None,
        min_n: int) -> str:
    """Motivo en una línea, para el registro del arranque."""
    if max_cost_r is None:
        return f"{tf}: puerta de costo apagada, opera"
    c, src = reference(tf, measured, min_n)
    if c is None:
        return f"{tf}: sin medición de costo, opera"
    verb = "no opera" if c >= max_cost_r else "opera"
    rel = "≥" if c >= max_cost_r else "<"
    return f"{tf}: costo {c:.3f} R {rel} {max_cost_r:.3f} R umbral → {verb} · {src}"


def gate(tfs: Sequence[str], outcomes: Sequence[Outcome], ep) -> tuple[list[dict], list[Outcome]]:
    """Filas del panel y operaciones que los perfiles pueden tomar. La sombra no se toca."""
    rows = report(tfs, cost_by_tf(outcomes), ep.tf_max_cost_r, ep.tf_cost_min_n)
    ok = {r["timeframe"] for r in rows if r["admitted"]}
    if not ok and tfs:
        # que no opere ningún marco es una decisión de la puerta, pero no puede pasar callada
        _log.warning("puerta de marcos: ningún marco opera (%s)",
                     "; ".join(f"{r['timeframe']} {r['cost_r']:.3f} R" for r in rows
                               if r["cost_r"] is not None))
    if len(ok) == len(tfs):
        return rows, list(outcomes)
    return rows, [o for o in outcomes if o.idea.timeframe in ok]


def check(ep) -> tuple[str, ...]:
    """Comprobación de arranque: umbral válido y, en el registro, qué marcos operan y por qué.

    Sin umbral (`None`) la puerta está apagada y todo marco opera. Falla fuerte con un umbral que
    no es positivo (todo marco quedaría fuera sin que nadie lo
    decidiera) o una muestra mínima menor que 1. Devuelve las líneas registradas.
    """
    if ep.tf_max_cost_r is not None and not ep.tf_max_cost_r > 0:
        raise ValueError(f"tf_max_cost_r debe ser > 0 (es {ep.tf_max_cost_r})")
    if ep.tf_cost_min_n < 1:
        raise ValueError(f"tf_cost_min_n debe ser ≥ 1 (es {ep.tf_cost_min_n})")
    lines = tuple(why(tf, {}, ep.tf_max_cost_r, ep.tf_cost_min_n) for tf in ep.timeframes)
    for line in lines:
        _log.info("puerta de marcos (arranque, línea base de T136; cada ciclo usa la sombra "
                  "en cuanto tiene %d operaciones por marco): %s", ep.tf_cost_min_n, line)
    return lines
