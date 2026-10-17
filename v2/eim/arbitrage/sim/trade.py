"""Operación simulada y su libro de costos (T43).

`net = price_pnl + funding − fees − slippage − legging − liq_loss`, todo en USD:
- `price_pnl`: resultado de las patas a precio de referencia (apertura de la vela, sin
  fricción): convergencia de la base o su cambio, según la estrategia.
- `funding`: + cobrado, − pagado, en cada liquidación cruzada con la posición.
- `slippage`: frente al medio, recorriendo el perfil de profundidad capturado.
- `legging`: costo esperado de pata incompleta (prob. × deshacer la pata ejecutada).
- `liq_loss`: margen restante perdido en una liquidación (regla de T25).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eim.arbitrage.sim.depth import DepthModel
from eim.arbitrage.sim.params import SimParams
from eim.core import CostModel
from eim.core.arbitrage import MarketKind, Side

H_MS = 3_600_000


@dataclass
class SimTrade:
    strategy: str
    variant: str
    asset: str
    instrument: str
    entry_t: int
    capital: float
    notional: float
    exit_t: int = 0
    price_pnl: float = 0.0
    funding: float = 0.0
    fees: float = 0.0
    slippage: float = 0.0
    legging: float = 0.0
    liq_loss: float = 0.0
    settlements: int = 0
    rebalances: int = 0
    exit_reason: str = "time"
    events: list[tuple[float, float]] = field(default_factory=list)  # (nocional, costo deshacer)
    missing_depth: list[str] = field(default_factory=list)
    incomplete: bool = False  # alguna pata no cabía en el libro (escalado) visible

    @property
    def net(self) -> float:
        return (self.price_pnl + self.funding - self.fees - self.slippage - self.legging
                - self.liq_loss)

    @property
    def hold_h(self) -> float:
        return (self.exit_t - self.entry_t) / H_MS

    @property
    def net_bps(self) -> float:
        return self.net / self.capital * 1e4

    def summary(self) -> dict[str, float | int | str | bool]:
        return {"strategy": self.strategy, "variant": self.variant, "asset": self.asset,
                "instrument": self.instrument, "entry_t": self.entry_t, "exit_t": self.exit_t,
                "hold_h": round(self.hold_h, 2), "capital": round(self.capital, 2),
                "price_pnl": round(self.price_pnl, 4), "funding": round(self.funding, 4),
                "fees": round(self.fees, 4), "slippage": round(self.slippage, 4),
                "legging": round(self.legging, 4), "liq_loss": round(self.liq_loss, 4),
                "net": round(self.net, 4), "net_bps": round(self.net_bps, 3),
                "settlements": self.settlements, "rebalances": self.rebalances,
                "exit_reason": self.exit_reason, "incomplete": self.incomplete}


@dataclass(frozen=True)
class LegSpec:
    key: str  # clave del perfil de profundidad
    market: MarketKind
    side: Side
    notional: float  # USD
    scale: float = 1.0  # adelgazamiento por volumen en esa vela


class Executor:
    """Cobra comisiones (modelo T38), deslizamiento (perfil) y riesgo de pata incompleta."""

    def __init__(self, cm: CostModel, dm: DepthModel, sp: SimParams) -> None:
        self.cm, self.dm, self.sp = cm, dm, sp

    def leg(self, tr: SimTrade, lg: LegSpec) -> float:
        """Ejecuta una pata; devuelve el costo (comisión + deslizamiento) en USD."""
        fee = self.cm.fee_rate(lg.market) * lg.notional
        got = self.dm.cost(lg.key, lg.notional, lg.side, lg.scale * self.sp.depth_scale)
        if got is None:
            slip = 0.0
            if lg.key not in tr.missing_depth:
                tr.missing_depth.append(lg.key)
        else:
            slip, complete = got
            tr.incomplete |= not complete
        tr.fees += fee
        tr.slippage += slip
        return fee + slip

    def pair(self, tr: SimTrade, first: LegSpec, second: LegSpec) -> float:
        """Dos patas no atómicas: la primera es la menos líquida. Si la segunda falla
        (prob. `p_fail`) hay que deshacer la primera: ida y vuelta de comisión y
        deslizamiento sobre su nocional; se suma su valor esperado y se guarda el evento
        para la distribución por latencia (`legging.py`)."""
        c1 = self.leg(tr, first)
        c2 = self.leg(tr, second)
        undo = 2.0 * c1
        tr.legging += self.sp.p_fail * undo
        tr.events.append((first.notional, undo))
        return c1 + c2
