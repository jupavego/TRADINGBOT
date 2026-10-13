"""Mecánica de perpetuos lineales (funciones puras): deslizamiento, liquidación, intra-vela."""

from __future__ import annotations

from eim.backtest.params import CostParams
from eim.core import Candle


def slippage_frac(c: Candle, notional: float, cp: CostParams) -> float:
    """Deslizamiento relativo en la vela `c`: base + volatilidad + impacto por tamaño."""
    rng = (c.h - c.l) / c.o if c.o > 0 else 0.0
    traded = c.v * c.o
    impact = notional / traded if traded > 0 else 1.0
    frac = cp.slip_base_bps / 1e4 + cp.slip_vol_k * rng + cp.slip_impact_k * impact / 1e4
    return min(max(frac, 0.0), cp.slip_cap_bps / 1e4)


def liquidation_price(side: int, entry: float, leverage: float, mmr: float) -> float:
    """Margen aislado: liquida cuando la pérdida = margen inicial − mantenimiento."""
    return entry * (1 - side * (1 / leverage - mmr))


def fill(price: float, side: int, slip: float) -> float:
    """Precio de ejecución de una orden a mercado: el deslizamiento siempre perjudica."""
    return price * (1 + side * slip)


def exit_in_bar(side: int, sl: float, tp: float, liq: float, c: Candle) -> tuple[str, float] | None:
    """(motivo, precio de referencia) si la vela `c` toca SL, TP o liquidación; si no, None.

    Regla conservadora: dentro de una vela el camino es desconocido, así que si caben SL y TP
    se asume SL primero. Para un largo, el precio baja hacia el nivel más alto entre SL y
    liquidación (el que llegue antes). Un hueco de apertura más allá del nivel se ejecuta a la
    apertura (peor que el nivel), nunca a un precio mejor.
    """
    # Nivel adverso que se alcanza primero: el más cercano a la apertura
    if side > 0:
        adverse, kind = (sl, "sl") if sl >= liq else (liq, "liq")
        hit_adverse = c.l <= adverse
        hit_tp = c.h >= tp
        gap = c.o <= adverse
    else:
        adverse, kind = (sl, "sl") if sl <= liq else (liq, "liq")
        hit_adverse = c.h >= adverse
        hit_tp = c.l <= tp
        gap = c.o >= adverse
    if hit_adverse:
        return kind, (c.o if gap else adverse)
    if hit_tp:
        return "tp", tp
    return None
