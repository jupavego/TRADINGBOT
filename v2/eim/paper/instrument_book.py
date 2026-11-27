"""Libro de papel por instrumento (T92): ideas sobre acciones, FX o futuros con las sesiones y
los costos de su clase, **sin tocar el camino de BTC/ETH**.

Cómo: la geometría (llenado, SL/TP/BE, tiempo, MFE/MAE) es exactamente la de
`eim.paper.engine.simulate`, que se llama con costos y funding a cero sobre un camino que solo
tiene velas **en sesión**; después se cobran los costos de la clase (`eim.backtest.costs`):
comisión, medio diferencial con deslizamiento y la financiación de la clase (préstamo del
corto, swap de FX). Con el mercado cerrado no se llena nada: una idea nacida fuera de sesión se
llena a la apertura de la primera vela abierta (el hueco de apertura), porque esa es la primera
vela del camino a partir de su instante.

Para un perpetuo, `simulate_instrument` devuelve `simulate(idea, path, p)` tal cual.
Fuera de alcance (BACKLOG T92): splits y dividendos dentro del libro de papel (el backtest por
instrumento sí los aplica) y la mesa en vivo de varios instrumentos.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

import numpy as np

from eim.backtest.costs import CostModel, cost_model_for
from eim.backtest.params import ZERO_COSTS
from eim.core import Candle
from eim.instruments.models import Instrument
from eim.paper.engine import Outcome, Path, _with_r, simulate
from eim.paper.params import ExecParams

DEFAULT_NOTIONAL = 10_000.0


def session_path(candles: Sequence[Candle], step_ms: int,
                 is_open: Callable[[int], bool] | None = None) -> Path:
    """Camino solo con las velas en sesión (sin `is_open`, todas las recibidas)."""
    kept = [c for c in candles if is_open is None or is_open(c.t)]
    return Path(kept, (), step_ms)


def _zero(p: ExecParams) -> ExecParams:
    return p.model_copy(update={"costs": ZERO_COSTS, "funding_8h_assumed": 0.0})


def simulate_instrument(idea, path: Path, inst: Instrument, p: ExecParams | None = None, *,
                        model: CostModel | None = None, notional: float = DEFAULT_NOTIONAL
                        ) -> Outcome:
    """Resultado de una idea en `inst`. `notional` (moneda de cotización) solo importa para
    las comisiones con mínimo o por contrato, que no escalan con el tamaño."""
    p = p or ExecParams()
    model = model or cost_model_for(inst)
    if model.uses_perp_engine:
        return simulate(idea, path, p)
    o = simulate(idea, path, _zero(p))
    if o.fill is None or o.status in ("PENDIENTE", "CANCELADA", "RECHAZADA"):
        return o
    m = inst.multiplier
    qty = notional / (o.fill * m)
    j_in = int(_index(path, o.fill_t))
    c_in = _candle(path, j_in)
    maker_in = idea.kind != "market"
    slip_in = 0.0 if maker_in else model.slippage_frac(c_in, notional, None, entry=True,
                                                       tick=inst.tick)
    fee_in = model.commission(qty, o.fill, m, maker=maker_in) / notional
    fill = o.fill * (1 + idea.side * slip_in)
    end_t = o.exit_t if o.status == "CERRADA" else path.end
    funding = model.financing(idea.side, notional, o.fill_t, end_t) / notional
    fee_out = slip_out = 0.0
    if o.status == "CERRADA":
        j_out = int(_index(path, o.exit_t))
        c_out = _candle(path, min(j_out, len(path.t) - 1))
        maker_out = o.reason == "TP"
        slip_out = 0.0 if maker_out else model.slippage_frac(c_out, notional, None,
                                                             tick=inst.tick)
        fee_out = model.commission(qty, o.exit, m, maker=maker_out) / notional
    # Misma convención que `simulate`: el llenado ya incluye el deslizamiento de entrada y el
    # bruto se mide desde él; la salida de referencia es el nivel (su deslizamiento va en `slip`).
    ref_out = o.exit if o.status == "CERRADA" else o.mark
    gross = idea.side * (ref_out - fill) / fill
    return _with_r(replace(o, fill=fill, fee_in=fee_in, fee_out=fee_out,
                           slip=slip_in + slip_out, funding=funding, funding_assumed=False,
                           gross=gross))


def _index(path: Path, t: int) -> int:
    j = int(np.searchsorted(path.t, t, "right")) - 1
    return max(0, j)


def _candle(path: Path, j: int) -> Candle:
    return Candle(t=int(path.t[j]), o=float(path.o[j]), h=float(path.h[j]), l=float(path.l[j]),
                  c=float(path.c[j]), v=0.0)
