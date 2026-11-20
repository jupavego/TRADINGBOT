"""Lectura intermedia (T66): lo que una capa dice haber visto, antes de validar.

`Reading` es interno: la convierte en `VisualObservation` el lector (`reader.py`) tras validarla.
`Engine` = motor que la produjo (OCR, visión clásica o modelo visual) con su modelo y SHA.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from eim.core.video import Box, ObsKind, ObsSource

CV_ENGINE = ("eim.cv", "chart_cv_v1")     # visión clásica propia (sin pesos)


@dataclass(frozen=True)
class Engine:
    engine: str
    model: str
    weights_sha: str


@dataclass(frozen=True)
class Reading:
    kind: ObsKind
    value: float | str
    unit: str
    source: ObsSource
    engines: tuple[Engine, ...]
    box: Box | None = None
    quote: str = ""
    confidence: float | None = None
    other: float | None = None            # valor de la otra capa cuando ambas leyeron lo mismo
    tags: dict[str, str] = field(default_factory=dict)

    def merged(self, other: Reading) -> Reading:
        """Misma cosa leída por dos capas: `ambos`, motores unidos, caja de la primera."""
        engines = self.engines + tuple(e for e in other.engines if e not in self.engines)
        return replace(self, source="ambos", engines=engines, box=self.box or other.box,
                       quote=self.quote or other.quote,
                       other=other.value if isinstance(other.value, float) else None)


def box_center_y(box: Box) -> float:
    return (box[1] + box[3]) / 2


def box_height(box: Box) -> float:
    return max(0.0, box[3] - box[1])


def rel_diff(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-12)
