"""Parámetros de la salida adaptativa del bróker simulado (T135).

Es una hoja sin dependencias del motor, como `ladder_params.py`, para que `params.py` la importe sin
ciclos. Solo describe la política; quien la construye y la conecta al libro es `adaptive.py`.

No están S1 ni M8, y es a propósito: cambian el SL inicial, y con él el tamaño que ya decidió
`policy.decide`, así que no caben sin tocar la autoridad. Además, tras T137 el usuario cerró la
línea de apartar el stop (§4 de `ESTADO_PROYECTO.md`).

Ningún perfil usa esto hoy: T134 rechazó las 87 variantes y no hay salida aprobada. Encender una es
una decisión ◆ con su pre-registro, y cada conjunto de valores es una versión distinta (`knobs`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from eim.paper.exits.sigma import OHLC

HARRV = "harrv_1m"           # el mismo nombre que `exits/features.py`; ahí vive el estimador


class AdaptiveParams(BaseModel):
    """Una política de T132 y sus valores: una sola por perfil, nunca el máximo de varias (H5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: Literal["M2", "M3", "M5", "M6", "M7"]
    sigma: str = "atr14"             # estimador de `exits/sigma.py`, o `harrv_1m`
    floor_n: float = 2.0             # piso de ruido en σ (§4.5): ningún stop más cerca
    k: float = 3.0                   # M2, y el arrastre M2 de M5
    activate_r: float = 0.0          # M2: avance desde el que arrastra
    buffer_sigma: float = 0.25       # M3, y el arrastre M3 de M5
    swing_bars: Literal[3, 5] = 5    # M3: fractal de 3 o 5 velas
    survival_r: float = 0.3          # M5: fase de supervivencia
    a_r: float = 1.0                 # M5: avance que dispara el BE+
    b_r: float = 0.1                 # M5: lo que bloquea el BE+, además de los costos
    trail: Literal["M2", "M3"] = "M2"  # M5: con qué arrastra
    bars: int | None = None          # M6: barrera de tiempo, en velas del camino
    min_r: float = 0.0               # M6: 0 = cierra siempre a las `bars` velas
    fine_tf: str = "1m"              # velas finas: las mismas en el vivo y en el recálculo
    # Tope del peso aprendido, el mismo de la escalera (T109): una racha corta no infla el tamaño.
    # No entra en `knobs`: decide cuánto se abre, no cómo se sale.
    max_weight: float = 1.5

    @model_validator(mode="after")
    def _coherent(self) -> AdaptiveParams:
        if self.policy == "M6" and (self.bars is None or self.bars < 1):
            raise ValueError("M6 exige `bars` ≥ 1: sin barrera de tiempo no es M6")
        if self.floor_n < 0 or self.k <= 0 or self.max_weight <= 0:
            raise ValueError("`floor_n` no puede ser negativo; `k` y `max_weight`, positivos")
        if self.sigma != HARRV and self.sigma not in OHLC:   # falla al construir, no al operar
            raise ValueError(f"estimador de volatilidad desconocido: {self.sigma!r}; "
                             f"disponibles: {[*sorted(OHLC), HARRV]}")
        return self

    def knobs(self) -> dict:
        """Solo los valores que esta política usa: los demás no pueden crear una versión nueva."""
        common = {"sigma": self.sigma, "floor_n": self.floor_n}
        if self.policy == "M2":
            return {**common, "k": self.k, "activate_r": self.activate_r}
        if self.policy == "M3":
            return {**common, "swing_bars": self.swing_bars, "buffer_sigma": self.buffer_sigma}
        if self.policy == "M5":
            inner = ({"k": self.k} if self.trail == "M2"
                     else {"swing_bars": self.swing_bars, "buffer_sigma": self.buffer_sigma})
            return {**common, **inner, "trail": self.trail, "survival_r": self.survival_r,
                    "a_r": self.a_r, "b_r": self.b_r}
        if self.policy == "M6":
            return {"bars": self.bars, "min_r": self.min_r}
        return {}
