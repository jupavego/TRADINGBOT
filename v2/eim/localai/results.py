"""Resultados de la capa de motores locales (T63): toda salida lleva su procedencia.

Cada llamada devuelve un `EngineResult` con el dato (o nada), su estado y la `Provenance`
(motor, modelo, SHA de los pesos, parámetros, huella de la entrada, tiempo, RAM pico, llamador):
con eso la salida es reproducible y auditable. Un motor que no responde jamás inventa un valor:
`status` = `no_data`/`degraded` con `reason` y `data` = None.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["llm", "asr", "ocr", "vision", "embed"]
Status = Literal["ok", "degraded", "no_data"]
# resultado de la llamada para el registro de salud (`localai_calls`)
Outcome = Literal["valid", "repaired", "invalid", "timeout", "down", "deferred", "off"]
STATUS_OF: dict[str, Status] = {
    "valid": "ok", "repaired": "ok", "invalid": "degraded", "timeout": "degraded",
    "down": "no_data", "deferred": "no_data", "off": "no_data",
}

T = TypeVar("T")


def sha256_text(obj: Any) -> str:
    """Huella estable (SHA-256) de un texto u objeto JSON: entrada y esquema de cada llamada."""
    raw = obj if isinstance(obj, str) else json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                                       default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Provenance(BaseModel):
    """Con qué se produjo una salida. `weights_sha` es el SHA-256 de los pesos (o el digest del
    manifiesto de Ollama, que fija sus capas); en un motor remoto (Claude) es `api:<modelo>`."""

    model_config = ConfigDict(frozen=True)

    engine_id: str            # p. ej. `ollama`, `faster-whisper`, `rapidocr`, `fake`
    kind: Kind
    model: str
    weights_sha: str | None   # None solo si la llamada no llegó a un motor (apagado/aplazada)
    params: dict[str, Any] = {}
    input_sha: str = ""       # huella de la entrada (prompt/audio/imagen/textos)
    schema_sha: str = ""      # huella del esquema pedido (LLM/visión)
    started_ms: int = 0
    elapsed_s: float = 0.0
    ram_peak_mb: float | None = None   # RAM del sistema consumida en el pico de la llamada
    caller: str = ""
    attempts: int = 0


class Segment(BaseModel):
    """Tramo de una transcripción con marcas de tiempo (segundos desde el inicio)."""

    model_config = ConfigDict(frozen=True)

    t_start: float = Field(ge=0)
    t_end: float = Field(ge=0)
    text: str


class OCRLine(BaseModel):
    """Texto leído en una imagen: caja `[x0, y0, x1, y1]` en px y confianza 0..1."""

    model_config = ConfigDict(frozen=True)

    text: str
    box: tuple[float, float, float, float]
    confidence: float = Field(ge=0, le=1)


class EngineResult(BaseModel, Generic[T]):
    """Salida de un motor. `data` solo existe si `status` es `ok`."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    status: Status
    outcome: Outcome
    data: T | None = None
    reason: str = ""
    warnings: list[str] = []
    provenance: Provenance

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def make_result(outcome: Outcome, prov: Provenance, data: Any = None, reason: str = "",
                warnings: list[str] | None = None) -> EngineResult:
    """Construye el resultado y garantiza la regla: sin `ok` no hay dato."""
    status = STATUS_OF[outcome]
    return EngineResult(status=status, outcome=outcome, data=data if status == "ok" else None,
                        reason=reason, warnings=warnings or [], provenance=prov)
