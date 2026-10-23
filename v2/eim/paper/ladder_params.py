"""Parámetros de la protección progresiva (PPP): ficha del instrumento por símbolo y escalera.

Viven aparte de `params.py` (que los reexporta) para que ningún archivo pase de 300 líneas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class SymbolSpec(BaseModel):
    """Precisión del instrumento: filtros reales del perpetuo USDⓈ-M (T108, A6 de T106).

    Antes vivían como constantes de BTCUSDT dentro de `LadderParams`; con ETHUSDT en la mesa
    (◆2) el redondeo del SL y de la cantidad tiene que ser el del símbolo, no el de BTC.
    """

    model_config = ConfigDict(frozen=True)

    tick: float          # PRICE_FILTER.tickSize
    qty_step: float      # LOT_SIZE.stepSize
    min_qty: float       # LOT_SIZE.minQty

    @model_validator(mode="after")
    def _positive(self) -> SymbolSpec:
        if self.tick <= 0 or self.qty_step <= 0 or self.min_qty <= 0:
            raise ValueError("tick, qty_step y min_qty deben ser positivos")
        return self


# Consultados en `fapi/v1/exchangeInfo` el 2026-10-22 (PERPETUAL). Un símbolo sin ficha no puede
# operar con escalera: `spec_for` falla con el motivo en vez de redondear con el paso de otro.
SYMBOL_SPECS: dict[str, SymbolSpec] = {
    "BTCUSDT": SymbolSpec(tick=0.1, qty_step=0.001, min_qty=0.001),
    "ETHUSDT": SymbolSpec(tick=0.01, qty_step=0.001, min_qty=0.001),
}


def spec_for(symbol: str) -> SymbolSpec:
    """Ficha del instrumento; falla con el motivo si el símbolo no la declara."""
    spec = SYMBOL_SPECS.get(symbol)
    if spec is None:
        raise ValueError(f"{symbol} no declara tick ni paso de cantidad en SYMBOL_SPECS: "
                         "un perfil con protección progresiva no puede operarlo")
    return spec


class LadderParams(BaseModel):
    """Protección progresiva de ganancias: SL dinámico por escalones de beneficio neto.

    Los escalones se miden en beneficio NETO estimado (tras comisiones, deslizamiento y funding),
    no en precio, y su tamaño se expresa de dos maneras (◆6 de T106):
    - `basis="r"`: fracción del RIESGO de cada operación (lo único comparable entre perfiles con
      riesgo distinto y lo único que no se desajusta cuando cambia el capital);
    - `basis="usdt"`: cantidad fija, como el perfil de control `ppp_btcusdt`, que no cambia.
    `steps()` resuelve el par (primer escalón, incremento) en USDT para una operación concreta.
    Los tres «prohibidos» son configuración visible pero no se pueden activar: la estrategia no
    tiene TP final, ni cierre por tiempo, ni dinero real (`ladder.py` los respeta).
    """

    model_config = ConfigDict(frozen=True)

    basis: Literal["usdt", "r"] = "usdt"
    first_usdt: float = 10.0         # basis "usdt": beneficio neto que activa la protección
    step_usdt: float = 5.0           # basis "usdt": cada +5 USDT de máximo eleva un escalón
    first_r: float = 0.0             # basis "r": primer escalón en fracciones del riesgo
    step_r: float = 0.0              # basis "r": incremento en fracciones del riesgo
    # ◆3 de T106: BE+ (`ExecParams.be_*`, solo en sus marcos) y los escalones conviven; el stop
    # vigente es el MEJOR de los dos y nunca retrocede (`ladder._Run.peek`, T109).
    be_with_ladder: bool = False
    min_target_vs_first: float = 1.0  # el objetivo de la idea (solo estimación) debe cubrir ≥ ×
    # Veto de una segunda posición del mismo lado decidida en la misma vela (correlación). Es del
    # control; en los tres perfiles chocaba con sus mínimos de abiertas y su cobertura (T106 §3).
    one_per_bar: bool = True
    # Freno propio (pérdidas seguidas / drawdown, abajo). Los tres perfiles conservan el suyo
    # (`caps`) y no suman este: cambiaría sus entradas, que T109 no toca.
    brake: bool = True
    # Peso máximo que la memoria propia de la escalera puede dar a una estrategia (T109). Con la
    # escalera las ganadoras son pequeñas y frecuentes y la memoria empieza de cero: una racha
    # corta no debe multiplicar el tamaño (el Agresivo llegaba a 3,0 con `gain` 2,5).
    max_weight: float = 1.5
    # Reservas del SL para que el neto realizado se parezca al nominal: deslizamiento de salida =
    # el MAYOR de las últimas `slip_lookback` velas (ya conocidas) y funding de `funding_reserve`
    # liquidaciones futuras a la tasa supuesta. Un hueco real puede seguir superándolas.
    slip_lookback: int = 4
    fine_tf: str = "1m"     # velas que resuelven el orden dentro de una vela ambigua de 15 m
    funding_reserve: int = 1
    # Freno de riesgo (solo frena ENTRADAS NUEVAS, jamás cierra posiciones): tras
    # `max_consec_losses` pérdidas seguidas, o si el capital cae `max_drawdown` desde su máximo,
    # no abre durante `pause_hours`; luego reanuda (el máximo se reinicia al capital actual).
    max_consec_losses: int = 4
    max_drawdown: float = 0.08
    pause_hours: float = 24.0
    fixed_take_profit: bool = False
    time_exit: bool = False
    real_money: bool = False

    @model_validator(mode="after")
    def _forbidden(self) -> LadderParams:
        if self.fixed_take_profit or self.time_exit or self.real_money:
            raise ValueError("PPP no admite TP fijo, cierre por tiempo ni dinero real")
        if self.basis == "usdt" and not (self.first_usdt > 0 and self.step_usdt > 0):
            raise ValueError("con basis 'usdt', first_usdt y step_usdt deben ser positivos")
        if self.basis == "r" and not (self.first_r > 0 and self.step_r > 0):
            raise ValueError("con basis 'r', first_r y step_r deben ser positivos")
        if self.slip_lookback < 1 or self.funding_reserve < 0 or self.pause_hours < 0:
            raise ValueError("slip_lookback ≥ 1, funding_reserve ≥ 0 y pause_hours ≥ 0")
        if self.max_consec_losses < 1 or not 0 < self.max_drawdown < 1:
            raise ValueError("max_consec_losses ≥ 1 y 0 < max_drawdown < 1")
        if self.max_weight <= 0:
            raise ValueError("max_weight debe ser positivo")
        return self

    def steps(self, risk_usd: float) -> tuple[float, float]:
        """(primer escalón, incremento) en USDT para una operación que arriesga `risk_usd`."""
        if self.basis == "r":
            return self.first_r * risk_usd, self.step_r * risk_usd
        return self.first_usdt, self.step_usdt
