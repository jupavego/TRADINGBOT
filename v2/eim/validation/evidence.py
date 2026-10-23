"""Evidencia de la puerta (T49): operaciones sombra → `Trade` (puro, sin I/O).

Cada `Trade` es una operación sombra CERRADA de una versión: su R neto, su costo en R y el R
que habría dado el lado contrario (`r_flip`, para la réplica de lado aleatorio de V3: misma
fecha, mismas distancias de entrada/SL/TP respecto del precio de la decisión, mismos costos).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

import numpy as np

from eim.paper.engine import Outcome, Path
from eim.paper.ideas import Idea
from eim.validation.lineage import Window, out_of_sample

DAY_MS = 86_400_000


@dataclass(frozen=True)
class Trade:
    t: int                 # decisión (cierre de la vela de contexto)
    exit_t: int
    r: float               # neto en R
    r_flip: float          # lado contrario (0 si no se llenaría; latente si sigue abierto)
    cost_r: float          # comisiones + deslizamiento + funding, en R
    regime: str
    origin: str            # vivo | backtest
    side: int = 1
    mfe_r: float = 0.0
    mae_r: float = 0.0


def flip_idea(idea: Idea, ref: float) -> Idea:
    """La misma idea del lado contrario: entrada, SL y TP reflejados alrededor de `ref` (precio
    de la decisión). En mercado `ref` = la entrada, así que solo se reflejan SL y TP."""
    return replace(idea, id=f"{idea.id}:contraria", side=-idea.side, entry=2 * ref - idea.entry,
                   sl=2 * ref - idea.sl, tp=2 * ref - idea.tp, key="")


def ref_price(o: Outcome, path: Path) -> float:
    """Precio de la decisión: la entrada a mercado o la apertura de 15 m en `t` (límites)."""
    i = o.idea
    if i.kind == "market":
        return i.entry
    j = int(np.searchsorted(path.t, i.t))
    return float(path.o[min(j, len(path.o) - 1)])


def flip_r(o: Outcome | None) -> float:
    """R del lado contrario para la réplica: cerrado → su R; abierto → latente; si no se
    habría llenado (cancelada, rechazada, pendiente) → 0 (no hay operación)."""
    if o is None or o.r is None or o.status not in ("CERRADA", "ABIERTA"):
        return 0.0
    return float(o.r)


def cost_r(o: Outcome) -> float:
    risk = o.risk
    return (o.fee_in + o.fee_out + o.slip + o.funding) / risk if risk > 0 else 0.0


def trade_of(o: Outcome, flipped: Outcome | None) -> Trade | None:
    if o.status != "CERRADA" or o.r is None or o.exit_t is None:
        return None
    i = o.idea
    return Trade(t=i.t, exit_t=int(o.exit_t), r=float(o.r), r_flip=flip_r(flipped),
                 cost_r=cost_r(o), regime=i.regime or "sin dato", origin=i.origin, side=i.side,
                 mfe_r=o.mfe_r, mae_r=o.mae_r)


@dataclass(frozen=True)
class Sample:
    """Lo que la puerta usa de una versión en `asof`."""
    oos: list[Trade]           # cerradas en exit_t ≤ asof y fuera de toda ventana de ajuste
    excluded: int              # cerradas ≤ asof pero dentro de una ventana de ajuste
    future: int                # cerradas después de asof (ignoradas: sin anticipación)


def select(trades: Iterable[Trade], windows: Sequence[Window], symbol: str, asof: int
           ) -> Sample:
    oos, excluded, future = [], 0, 0
    for x in trades:
        if x.exit_t > asof:
            future += 1
        elif not out_of_sample(x.t, symbol, windows):
            excluded += 1
        else:
            oos.append(x)
    oos.sort(key=lambda x: (x.exit_t, x.t))
    return Sample(oos, excluded, future)
