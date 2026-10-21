"""Topes de riesgo del libro de un perfil: riesgo abierto por dirección y freno por drawdown.

Ambos frenan solo ENTRADAS NUEVAS (jamás cierran posiciones) y están apagados por defecto
(`CapParams()`), así que no cambian a ningún perfil hasta que se activan. El libro corre por
símbolo, de modo que «por dirección» ya es «por símbolo y dirección».
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

HOUR_MS = 3_600_000


class CapParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Riesgo abierto máximo hasta el SL en un mismo sentido, como fracción del capital realizado
    # (posiciones y órdenes pendientes). La orden que no cabe se reduce; si lo que cabe es menor
    # que `min_fill` de su riesgo, se rechaza. None lo desactiva.
    max_dir_risk: float | None = None
    min_fill: float = 0.25
    # Freno: si el capital realizado cae `dd_brake` desde su máximo no se abre durante
    # `dd_pause_hours`; al reanudar el máximo se reinicia al capital actual. None lo desactiva.
    dd_brake: float | None = None
    dd_pause_hours: float = 24.0


@dataclass
class Brake:
    """Freno por drawdown del capital realizado."""

    peak: float = 0.0
    halt_until: int = 0
    activations: int = 0

    def veto(self, t: int) -> str | None:
        if t < self.halt_until:
            until = datetime.fromtimestamp(self.halt_until / 1000, UTC).strftime("%Y-%m-%d %H:%M")
            return f"freno por drawdown: entradas en pausa hasta {until} UTC"
        return None

    def closed(self, caps: CapParams, equity: float, initial: float, exit_t: int) -> str | None:
        """Registra un cierre; devuelve el texto si este cierre activa el freno."""
        self.peak = max(self.peak or initial, equity)
        dd = 1 - equity / self.peak
        if caps.dd_brake is None or dd < caps.dd_brake or exit_t < self.halt_until:
            return None
        self.halt_until = exit_t + int(caps.dd_pause_hours * HOUR_MS)
        self.peak = equity
        self.activations += 1
        return f"drawdown {dd:.1%} ≥ {caps.dd_brake:.0%} desde el máximo"


def fit_risk(caps: CapParams, equity: float, open_risk: float, risk_usd: float) -> float:
    """Riesgo (USDT) que cabe bajo el tope por dirección; 0 si no cabe lo mínimo."""
    if caps.max_dir_risk is None:
        return risk_usd
    room = max(0.0, equity * caps.max_dir_risk - open_risk)
    if room >= risk_usd:
        return risk_usd
    return room if room >= caps.min_fill * risk_usd else 0.0
