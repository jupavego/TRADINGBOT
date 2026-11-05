"""Topes de riesgo del libro de un perfil: riesgo abierto por dirección y frenos por drawdown.

Todo frena solo ENTRADAS NUEVAS (jamás cierra posiciones) y está apagado por defecto
(`CapParams()`), así que no cambia a ningún perfil hasta que se activa. El libro corre por
símbolo, de modo que «por dirección» ya es «por símbolo y dirección».

Dos frenos por drawdown, y conviven:

- el de siempre, **todo o nada**: pasada `dd_brake`, no se abre durante `dd_pause_hours`;
- el **gradual** de T136 (4): `dd_steps` recorta el riesgo por tramos antes de llegar a la parada.
  Es la práctica institucional (§2.3; Grossman y Zhou): reducir exposición a medida que la cuenta
  cae, en vez de operar igual hasta un umbral y pararse en seco.

Y un **límite de CVaR 95 % por perfil** (T136 (4), E12): si las pérdidas de cola realizadas son
peores que el límite, el riesgo se recorta. El CVaR se mide sobre los cierres del propio perfil y
se recalcula al cerrar, nunca al decidir: el libro decide ≈ 250 000 ideas por cálculo de la vista.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

HOUR_MS = 3_600_000
CVAR_WINDOW = 500           # cierres recientes que se guardan para el CVaR


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
    # T136 (4): freno GRADUAL. Pares (caída desde el máximo, multiplicador del riesgo) en orden
    # creciente de caída; se aplica el del tramo más profundo alcanzado. Un multiplicador 0 no
    # abre. () lo desactiva. Sus valores salen de la rejilla medida en el banco, no de ajustarlos
    # después de ver el resultado (E12).
    dd_steps: tuple[tuple[float, float], ...] = ()
    # T136 (4): límite del CVaR 95 % en R (negativo). Con al menos `cvar_min_n` cierres, si el
    # CVaR realizado es peor que el límite el riesgo se multiplica por `cvar_cut`. None lo
    # desactiva.
    cvar_limit_r: float | None = None
    cvar_min_n: int = 30
    cvar_cut: float = 0.5


def cvar95_r(rs: list[float] | tuple[float, ...], level: float = 0.95) -> float:
    """CVaR al `level`: media del peor (1 − level) de los R. 0,0 sin muestra.

    Es la misma definición que `exits/metrics.py` usa en el banco: media de la cola izquierda, no
    el cuantil. Devuelve un número negativo cuando hay pérdidas de cola.
    """
    if not rs:
        return 0.0
    k = max(1, int(round(len(rs) * (1.0 - level))))
    tail = sorted(rs)[:k]
    return sum(tail) / len(tail)


def dd_scale(caps: CapParams, peak: float, equity: float) -> tuple[float, str]:
    """Multiplicador del riesgo por el freno gradual. `(1.0, "")` si está apagado o no hay caída.

    Con un tramo de multiplicador 0 devuelve `(0.0, motivo)`: no se abre, pero tampoco se pausa
    por horas como el freno todo o nada; en cuanto la cuenta recupera, el riesgo vuelve.
    """
    if not caps.dd_steps or peak <= 0 or equity >= peak:
        return 1.0, ""
    dd = 1 - equity / peak
    scale, hit = 1.0, 0.0
    for level, mult in sorted(caps.dd_steps):
        if dd >= level:
            scale, hit = mult, level
    if scale >= 1.0:
        return 1.0, ""
    return scale, f"freno gradual: drawdown {dd:.1%} ≥ {hit:.0%} → riesgo ×{scale:g}"


def cvar_scale(caps: CapParams, cvar_r: float, n: int) -> tuple[float, str]:
    """Multiplicador del riesgo por el límite de CVaR. `(1.0, "")` si está apagado o cumple."""
    if caps.cvar_limit_r is None or n < caps.cvar_min_n or cvar_r >= caps.cvar_limit_r:
        return 1.0, ""
    return caps.cvar_cut, (f"CVaR 95 % realizado {cvar_r:.2f} R peor que el límite "
                           f"{caps.cvar_limit_r:.2f} R ({n} cierres) → riesgo "
                           f"×{caps.cvar_cut:g}")


@dataclass
class Brake:
    """Freno por drawdown del capital realizado, y memoria de cola para el CVaR."""

    peak: float = 0.0
    halt_until: int = 0
    activations: int = 0
    rs: deque[float] = field(default_factory=lambda: deque(maxlen=CVAR_WINDOW))
    cvar_r: float = 0.0        # CVaR 95 % de los cierres recientes, recalculado al cerrar

    def veto(self, t: int) -> str | None:
        if t < self.halt_until:
            until = datetime.fromtimestamp(self.halt_until / 1000, UTC).strftime("%Y-%m-%d %H:%M")
            return f"freno por drawdown: entradas en pausa hasta {until} UTC"
        return None

    def scale(self, caps: CapParams, equity: float) -> tuple[float, str]:
        """Recorte del riesgo por el freno gradual y por el límite de CVaR, combinados.

        Se multiplican porque son dos razones distintas para arriesgar menos: la cuenta va cayendo
        y su cola es peor de lo admitido. El motivo que se informa es el del recorte más fuerte.
        """
        a, why_a = dd_scale(caps, self.peak, equity)
        b, why_b = cvar_scale(caps, self.cvar_r, len(self.rs))
        why = why_a if a <= b else why_b
        return a * b, why if a * b < 1.0 else ""

    def closed(self, caps: CapParams, equity: float, initial: float, exit_t: int,
               r: float | None = None) -> str | None:
        """Registra un cierre; devuelve el texto si este cierre activa el freno todo o nada."""
        if r is not None:
            self.rs.append(r)
            self.cvar_r = cvar95_r(tuple(self.rs))
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
