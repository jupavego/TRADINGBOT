"""Contrato de lo que se VE en un video (T66): `VisualObservation`, inmutable y trazable.

Cada observación sale de un fotograma concreto (`frame_id`, marca de tiempo `t` en segundos desde
el inicio del video) y lleva su caja en la imagen, de qué capa salió (`ocr`, `vision` o `ambos`),
con qué motor, modelo y SHA de pesos, y el resultado de la validación determinista contra los
datos reales (`confirmada`, `plausible`, `inconsistente`, `no_verificable`). Lo que no se lee no
existe: no hay observación sin caja o cita que la respalde.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ObsKind = Literal["cifra", "titular", "nivel", "indicador", "dibujo"]
ObsSource = Literal["ocr", "vision", "ambos"]
Validation = Literal["confirmada", "plausible", "inconsistente", "no_verificable"]
ACCEPTED: frozenset[str] = frozenset({"confirmada", "plausible"})
Box = tuple[float, float, float, float]   # (x0, y0, x1, y1) en px del fotograma guardado


class VisualObservation(BaseModel):
    """Una cosa vista en un fotograma. `value` es número (cifra, nivel, indicador) o texto
    (titular, dibujo); `unit` aclara el número (`USD`, `%`, `precio`, `rsi:14`, `ema:200`…).

    `box` es la evidencia en la imagen (o `quote` si el modelo citó texto sin caja); sin ninguna
    de las dos el contrato la rechaza. `engine`, `model` y `weights_sha` van unidos con «+» si la
    observación la confirmaron dos capas (`source = ambos`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    video_id: str
    t: float = Field(ge=0)                      # segundos desde el inicio del video
    frame_id: str
    kind: ObsKind
    value: float | str
    unit: str = ""
    box: Box | None = None
    quote: str = ""                             # texto citado como evidencia (si no hay caja)
    source: ObsSource
    validation: Validation
    validation_note: str = ""                   # por qué ese estado (rango, recálculo, acuerdo)
    symbol: str | None = None                   # activo leído en el fotograma, si se leyó
    timeframe: str | None = None                # marco leído, si se leyó
    confidence: float | None = Field(default=None, ge=0, le=1)   # del OCR; None si no hay
    engine: str
    model: str
    weights_sha: str
    params_version: str                         # versión de los parámetros de lectura

    @model_validator(mode="after")
    def _evidence(self) -> VisualObservation:
        if self.box is None and not self.quote.strip():
            raise ValueError("observación sin evidencia: hace falta caja o cita")
        if self.kind in ("cifra", "nivel", "indicador") and not isinstance(self.value, float):
            raise ValueError(f"{self.kind} exige un valor numérico")
        if self.kind in ("titular", "dibujo") and not isinstance(self.value, str):
            raise ValueError(f"{self.kind} exige un texto")
        return self

    @property
    def accepted(self) -> bool:
        """Solo `confirmada` y `plausible` pasan a T67; el resto queda como registro."""
        return self.validation in ACCEPTED
