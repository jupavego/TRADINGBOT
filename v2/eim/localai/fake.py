"""Motor simulado (`FakeEngine`) para TODOS los tests de EIM: sin red, sin pesos, determinista.

    ai = fake_localai(llm=FakeBackend("llm", ['{"x": 1}']))
    r = ai.llm.complete("tarea", Esquema, data="...", caller="test")

Cada `FakeBackend` devuelve en orden lo guionizado en `script` (un valor, una excepción que se
lanza o una función `(llamada) -> valor`) y repite el último al agotarse. Guarda cada llamada
en `calls` (con el prompt completo) para comprobar qué vio el motor.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eim.localai.config import LocalAIConfig
from eim.localai.facade import LocalAI
from eim.localai.health import HealthLog
from eim.localai.resources import ComputeGuard, ResourceManager
from eim.localai.results import OCRLine, Segment, sha256_text

DEFAULTS: dict[str, Any] = {
    "llm": "{}",
    "vision": "{}",
    "asr": [Segment(t_start=0.0, t_end=1.0, text="hola")],
    "ocr": [OCRLine(text="BTC 64.000", box=(0, 0, 10, 10), confidence=0.9)],
    "embed": None,   # se calcula: un vector determinista por texto
}


class FakeBackend:
    engine_id = "fake"

    def __init__(self, kind: str, script: list[Any] | None = None, *, model: str = "fake-1",
                 need_mb: float = 0.0, delay_s: float = 0.0, dims: int = 4) -> None:
        self.kind, self.model, self.need_mb, self.delay_s, self.dims = (
            kind, model, need_mb, delay_s, dims)
        self.script = list(script) if script is not None else [DEFAULTS[kind]]
        self.params: dict[str, Any] = {"fake": True}
        self.calls: list[dict[str, Any]] = []
        self.unloads = 0

    def weights_sha(self) -> str:
        return sha256_text(f"fake-weights:{self.model}")

    def unload(self) -> None:
        self.unloads += 1

    def _next(self, call: dict[str, Any]) -> Any:
        self.calls.append(call)
        if self.delay_s:
            time.sleep(self.delay_s)
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item("simulado")
        return item(call) if callable(item) else item

    def generate(self, system: str, user: str, schema: dict[str, Any], timeout_s: float) -> str:
        return self._next({"system": system, "user": user, "schema": schema})

    def ask(self, image: Path, system: str, user: str, schema: dict[str, Any],
            timeout_s: float) -> str:
        return self._next({"image": str(image), "system": system, "user": user})

    def transcribe(self, audio: Path, language: str | None, timeout_s: float) -> list[Segment]:
        return self._next({"audio": str(audio), "language": language})

    def read(self, image: Path, timeout_s: float) -> list[OCRLine]:
        return self._next({"image": str(image)})

    def embed(self, texts: list[str], timeout_s: float) -> list[list[float]]:
        out = self._next({"texts": list(texts)})
        if out is not None:
            return out
        return [[int(sha256_text(t)[i * 2:i * 2 + 2], 16) / 255 for i in range(self.dims)]
                for t in texts]


def fake_backend(kind: str) -> FakeBackend:
    return FakeBackend(kind)


def fake_localai(*, ram: Callable[[], float | None] = lambda: 16_000.0,
                 config: LocalAIConfig | None = None, health: HealthLog | None = None,
                 cpu_s_per_day: float = 0.0, sleep: Callable[[float], None] = lambda s: None,
                 **backends: FakeBackend | None) -> LocalAI:
    """`LocalAI` con motores simulados (los no dados quedan apagados) y RAM simulada."""
    cfg = config or LocalAIConfig(timeout_s=5.0, wait_s=5.0, retries=1, ram_margin_mb=1024.0)
    res = ResourceManager(cfg.ram_margin_mb, cfg.wait_s, ComputeGuard(cpu_s_per_day),
                          ram_probe=ram, sample_every_s=0.01)
    full = {k: backends.get(k) for k in ("llm", "vision", "asr", "ocr", "embed")}
    return LocalAI(full, config=cfg, resources=res, health=health or HealthLog(None), sleep=sleep)
