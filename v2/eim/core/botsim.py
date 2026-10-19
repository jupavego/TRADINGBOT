"""Carril de simulación de bots clase L (T58): lo que un bot de market making / grid / DCA hizo.

Un bot L no da una postura direccional: gestiona órdenes e inventario. Por eso NO produce
`BotSignal` ni vota: su salida es una **corrida simulada** (fills y curva de capital sobre velas
históricas locales). Son simulaciones etiquetadas como tales, nunca operaciones; los costos que el
bot asumió se guardan aparte para que T59 los vuelva a calcular con el modelo de T25.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from eim.core.bots import VERSION_PATTERN, BotQuality, BotStatus
from eim.core.market import Frozen

SIM_LABEL = "simulado"  # etiqueta obligatoria de todo lo que sale de este carril


class SimFill(Frozen):
    """Un fill simulado por el motor del bot. `qty` > 0 compra, < 0 vende (convención del bot)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    t: int                               # ms epoch UTC del fill
    kind: str                            # tipo del bot: «entry_initial_normal_long»…
    qty: float
    price: float
    psize_after: float                   # tamaño de la posición tras el fill
    pnl: float                           # PnL realizado (USDT) con los costos del bot
    fee_paid: float                      # comisión que el bot cobró (negativa = pagada)
    liquidity: Literal["maker", "taker"]
    wallet_exposure: float


class SimEquityPoint(Frozen):
    model_config = ConfigDict(frozen=True, extra="forbid")

    t: int
    equity: float                        # capital total en USDT (con la posición abierta valorada)


class SimRun(Frozen):
    """Corrida simulada de una estrategia de un bot L sobre [start, end); inmutable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bot_id: str
    strategy: str
    version: str = Field(pattern=VERSION_PATTERN)   # SHA del bot + hash de (config, parámetros)
    symbol: str
    timeframe: str                       # marco de las velas de entrada («1m»)
    start: int                           # primera vela usada (incluye calentamiento)
    end: int                             # fin exclusivo de la última vela usada
    warmup_minutes: int = Field(ge=0)
    starting_balance: float = Field(gt=0)
    fills: list[SimFill] = []
    equity: list[SimEquityPoint] = []
    metrics: dict[str, float | int | bool] = {}   # las del bot, tal cual (T59 las recalcula)
    costs_assumed: dict[str, float] | None = None  # comisión/deslizamiento del bot; None = no dice
    data_quality: BotQuality
    status: BotStatus = "ok"
    label: Literal["simulado"] = SIM_LABEL
    evidence: list[str] = []

    @model_validator(mode="after")
    def _window(self) -> SimRun:
        if self.end <= self.start:
            raise ValueError("ventana vacía o invertida")
        last = self.data_quality.last_candle_t
        if last is not None and last >= self.end:
            raise ValueError("la corrida usa una vela fuera de su ventana")
        if any(f.t >= self.end for f in self.fills):
            raise ValueError("un fill cae después del fin de la ventana")
        return self
