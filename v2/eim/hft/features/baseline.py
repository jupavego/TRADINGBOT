"""Línea base de T80: el agente `microstructure` v1 (T23/T104) como señal sobre el panel. Pura.

El entregable 0 de T80 dice que v1 es el listón: toda variable nueva se compara con él. Aquí se
reproduce su sesgo con las mismas piezas y los MISMOS pesos (`MicrostructureParams`): z del OFI
del mejor nivel, z del delta agresor y desequilibrio de profundidad, saturados con `tanh`.

Dos diferencias declaradas con el agente, inevitables al bajar de velas de 1 h a cubos de 1 s:
- el z se calcula contra una ventana hacia atrás del propio panel (`ref` cubos), no contra todas
  las velas del snapshot, que mirarían el futuro;
- no se incluye la divergencia precio/CVD, que en el agente necesita el retorno de la ventana de
  velas y a 1 s es ruido. Se anota en el informe.
"""

from __future__ import annotations

import numpy as np

from eim.agents.microstructure.params import MicrostructureParams
from eim.hft.features.book import depth_imbalance
from eim.hft.features.matrix import Panel
from eim.hft.features.sampling import trailing_std, trailing_sum

WINDOW = 30          # cubos de la ventana corta (≈ la `window` del agente, en segundos)
REF = 600            # cubos de la referencia del z (10 min)


def baseline_v1(panel: Panel, params: MicrostructureParams | None = None,
                window: int = WINDOW, ref: int = REF, eps: float = 1e-12) -> np.ndarray:
    """Sesgo del agente `microstructure` v1 sobre el panel, en [−1, 1] (NaN sin historia)."""
    p = params or MicrostructureParams()
    ofi1 = panel.ofi[:, 0]
    delta = panel.buy_v - panel.sell_v
    sd_o = trailing_std(ofi1, ref) * np.sqrt(window)
    sd_d = trailing_std(delta, ref) * np.sqrt(window)
    z_o = trailing_sum(ofi1, window) / np.maximum(sd_o, eps)
    z_d = trailing_sum(delta, window) / np.maximum(sd_d, eps)
    imb = depth_imbalance(panel.bid_q, panel.ask_q, panel.levels)
    bias = (p.w_ofi * np.tanh(z_o / p.z_scale) + p.w_delta * np.tanh(z_d / p.z_scale)
            + p.w_depth * imb)
    return np.clip(bias, -1.0, 1.0)
