"""Parámetros de la cantera (T168): iguales para todas las cuentas, prospectos y controles.

La ejecución es la de la corrida aparte T143 tal cual (`paper/t143_config.py`, ◆ 2026-11-10): de
lo que se adapta solo, únicamente lo que figura en `AUTO_ADAPT` (puerta de costo por marco,
entrada maker en 1 h y 4 h, riesgo con costo). Lo demás que en el bróker se adapta solo queda
**fijo y comprobado al construir** (nota §9.1): peso aprendido de la escalera = 1, freno propio
apagado y salida adaptativa apagada. Cambiar algo de esto es una variante (§9.3), no un ajuste.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eim.paper.params import ExecParams
from eim.paper.t143_config import AUTO_ADAPT, EXEC_T143, PROFILES_T143

_MODERADO = next(p for p in PROFILES_T143 if p.id == "moderado")
NAME = "cantera"
LABEL = "Cantera (fase 27): perfiles propios por agente, cuenta propia, solo hacia adelante"

#: Puerta de costo de la cantera: **0,3 R, el límite V6 de T49** (nota §3), no los 0,15 R de la
#: corrida T143. Con 0,15 R la puerta cerraría 15 m en el primer ciclo (el punto de partida de
#: T136 para ese marco es 0,157 R) y la banda de scalping quedaría sin medir antes de empezar. El
#: mecanismo sigue siendo el mismo y automático (`paper/tf_gate.py`, `AUTO_ADAPT`); solo cambia el
#: valor, que **T170 congela en el pre-registro** (◆). 0,3 R es también el límite con el que T169
#: descarta por costo, así que la cantera y el examen físico usan la misma vara.
V6_MAX_COST_R = 0.30
EXEC_CANTERA = EXEC_T143.model_copy(update={"tf_max_cost_r": V6_MAX_COST_R})


class NurseryParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    initial_equity: float = 10_000.0
    risk_pct: float = 0.01                       # 1 % del saldo por operación (perfil Moderado)
    max_leverage: int = _MODERADO.max_leverage
    min_equity_frac: float = _MODERADO.min_equity_frac   # cuenta agotada: deja de abrir
    est_cost_frac: float = _MODERADO.est_cost_frac
    risk_includes_costs: bool = _MODERADO.risk_includes_costs   # AUTO_ADAPT (T143)
    exec: ExecParams = EXEC_CANTERA              # maker 1 h/4 h + puerta de costo (AUTO_ADAPT)
    # Plantillas de salida (fijas y comunes a la familia, nota §4)
    sl_atr: float = 1.5
    tp_atr: float = 2.5
    default_hold_bars: int = 24                  # si el agente no publica su horizonte
    history_bars: int = 4                        # velas anteriores que ve una regla (≤ t)
    # Gemelos aleatorios pareados (rec. 1): K entradas de lado al azar por operación real
    twins_k: int = Field(200, ge=1)
    seed: int = 168
    start_ms: int = 0                            # primer cierre que cuenta (T170 lo fija)
    # Lo que NO se adapta en la cantera (nota §9.1): se comprueba al construir
    ladder_weight: float = 1.0
    own_brake: bool = False
    adaptive_exit: bool = False

    @model_validator(mode="after")
    def _fixed(self) -> NurseryParams:
        if self.ladder_weight != 1.0:
            raise ValueError("cantera: el peso aprendido de la escalera queda fijo en 1 (§9.1)")
        if self.own_brake:
            raise ValueError("cantera: sin freno propio; su papel lo cumple el tope de drawdown")
        if self.adaptive_exit:
            raise ValueError("cantera: la salida adaptativa sigue apagada (T134 no aprobó ninguna)")
        if not 0 < self.risk_pct <= 0.02:
            raise ValueError("cantera: riesgo por operación fuera de (0, 2 %]")
        if self.exec.tf_max_cost_r is None:
            raise ValueError("cantera: la puerta de costo por marco es parte de AUTO_ADAPT y no "
                             "se apaga; su valor lo congela el pre-registro de T170")
        return self

    @property
    def tf_max_cost_r(self) -> float | None:
        return self.exec.tf_max_cost_r

    @property
    def maker_tfs(self) -> tuple[str, ...]:
        return self.exec.maker_entry_timeframes

    def auto_adapt(self) -> dict:
        """Lo que se adapta solo y su valor (para el evento de arranque del libro)."""
        return {"keys": sorted(AUTO_ADAPT), "tf_max_cost_r": self.tf_max_cost_r,
                "tf_cost_min_n": self.exec.tf_cost_min_n, "maker_entry_timeframes":
                list(self.maker_tfs), "risk_includes_costs": self.risk_includes_costs,
                "ladder_weight": self.ladder_weight, "own_brake": self.own_brake,
                "adaptive_exit": self.adaptive_exit}
