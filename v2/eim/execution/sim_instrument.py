"""Ficha de un instrumento para el `SimBroker` (T92): multiplicador, lote, tick, sesión y
comisión de su clase.

Un símbolo sin ficha (BTC/ETH, todo lo de T31) sigue exactamente igual que antes: comisión por
tasa sobre el nocional, multiplicador 1 y mercado siempre abierto. Con ficha:

- `is_open(t)`: con el mercado cerrado no se casa nada; las órdenes esperan y la primera
  `set_price` con el mercado abierto las llena a ese precio (el hueco de apertura).
- `commission(qty, px, maker)`: importe de su clase (por acción con mínimo, por contrato…).
- `multiplier`: el resultado y el margen de un futuro se cuentan por punto × multiplicador.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from eim.backtest.costs import CostModel, cost_model_for
from eim.instruments.models import Instrument


@dataclass(frozen=True)
class BrokerInstrument:
    multiplier: float = 1.0
    step: float | None = None          # lote (paso de cantidad); None = el del bróker
    tick: float | None = None          # paso de precio; None = el del bróker
    is_open: Callable[[int], bool] | None = None
    commission: Callable[[float, float, bool], float] | None = None
    cost_model: str = ""

    @classmethod
    def from_instrument(cls, inst: Instrument, model: CostModel | None = None,
                        is_open: Callable[[int], bool] | None = None) -> BrokerInstrument:
        """Ficha desde el registro (T89) y el modelo de costos de su clase (T92)."""
        model = model or cost_model_for(inst)
        m = inst.multiplier

        def commission(qty: float, px: float, maker: bool) -> float:
            return model.commission(qty, px, m, maker=maker)

        step = 1.0 if model.kind.value == "future" else inst.lot
        return cls(multiplier=m, step=step, tick=inst.tick, is_open=is_open,
                   commission=commission, cost_model=model.version)
