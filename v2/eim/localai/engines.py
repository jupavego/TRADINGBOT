"""Interfaces de la capa de motores locales (T63).

Dos niveles:
- **Motores** (`LLMEngine`, `ASREngine`, `OCREngine`, `VisionEngine`, `EmbedEngine`): lo que usa
  el resto del proyecto. Devuelven `EngineResult` con procedencia; nunca lanzan por un fallo del
  motor (caído, lento, salida inválida, sin RAM) y nunca inventan un valor.
- **Backends** (`*Backend`): el adaptador crudo a un motor concreto (Ollama, llama.cpp,
  faster-whisper, RapidOCR, Claude API o el simulado). Pueden lanzar `EngineDown` (transitorio:
  se reintenta de forma acotada) o `EngineRefused` (configuración o pesos no verificados: no se
  reintenta). La fachada (`facade.py`) los envuelve con recursos, guardas y registro.

El llamador elige QUÉ pide; QUÉ motor responde lo decide la configuración (`EIM_LOCALAI_*`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from eim.localai.results import EngineResult, OCRLine, Segment

M = TypeVar("M", bound=BaseModel)


class EngineDown(Exception):
    """El motor no respondió (servidor apagado, error de transporte): transitorio."""


class EngineRefused(Exception):
    """El motor no debe usarse (pesos sin verificar, host fuera de 127.0.0.1, sin instalar)."""


@runtime_checkable
class Backend(Protocol):
    """Lo común a todo backend: identidad, pesos verificados y descarga explícita."""

    engine_id: str
    model: str
    params: dict[str, Any]

    def weights_sha(self) -> str:
        """SHA de los pesos que responden; `EngineRefused` si no se pueden verificar."""
        ...

    def unload(self) -> None:
        """Libera el modelo de la memoria (lo llama el gestor al cambiar de modelo o al cerrar)."""
        ...


class LLMBackend(Backend, Protocol):
    def generate(self, system: str, user: str, schema: dict[str, Any], timeout_s: float) -> str:
        """Texto crudo (se espera JSON conforme a `schema`)."""
        ...


class VisionBackend(Backend, Protocol):
    def ask(self, image: Path, system: str, user: str, schema: dict[str, Any],
            timeout_s: float) -> str:
        ...


class ASRBackend(Backend, Protocol):
    def transcribe(self, audio: Path, language: str | None, timeout_s: float) -> list[Segment]:
        ...


class OCRBackend(Backend, Protocol):
    def read(self, image: Path, timeout_s: float) -> list[OCRLine]:
        ...


class EmbedBackend(Backend, Protocol):
    def embed(self, texts: list[str], timeout_s: float) -> list[list[float]]:
        ...


# --- motores (lo que ve el resto del proyecto) ----------------------------------------------
class LLMEngine(Protocol):
    def complete(self, task: str, schema: type[M], *, data: Any = None, caller: str,
                 priority: int = 5) -> EngineResult[M]:
        """`task` = instrucción propia; `data` = contenido externo, SIEMPRE tratado como dato."""
        ...


class VisionEngine(Protocol):
    def ask(self, image: Path, question: str, schema: type[M], *, caller: str,
            priority: int = 5) -> EngineResult[M]:
        ...


class ASREngine(Protocol):
    def transcribe(self, audio: Path, *, language: str | None = None, caller: str,
                   priority: int = 5) -> EngineResult[list[Segment]]:
        ...


class OCREngine(Protocol):
    def read(self, image: Path, *, caller: str, priority: int = 5) -> EngineResult[list[OCRLine]]:
        ...


class EmbedEngine(Protocol):
    def embed(self, texts: list[str], *, caller: str,
              priority: int = 5) -> EngineResult[list[list[float]]]:
        ...
