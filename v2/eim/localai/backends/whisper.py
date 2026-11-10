"""Backend ASR faster-whisper (T62: CPU int8), en proceso, sin descargas en ejecución.

Los pesos viven en `%EIM_LOCALAI_DIR%\\models\\faster-whisper\\<modelo>` (bajados aparte con la
revisión fijada, `OPERACION.md` §7) y se cargan con `local_files_only=True`. Verificación: la
revisión de Hugging Face y el SHA-256 de `model.bin` que anota `snapshot_download` en
`.cache/huggingface/download/model.bin.metadata` (o `pins.json`) frente al calculado aquí.
"""

from __future__ import annotations

import gc
import os
from pathlib import Path
from typing import Any

from eim.localai import catalog
from eim.localai.backends.common import check_pin, sha256_file
from eim.localai.engines import EngineRefused
from eim.localai.results import Segment


def _metadata(folder: Path) -> tuple[str, str] | None:
    meta = folder / ".cache" / "huggingface" / "download" / "model.bin.metadata"
    try:
        lines = meta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return (lines[0].strip(), lines[1].strip().lower()) if len(lines) >= 2 else None


class WhisperBackend:
    engine_id = "faster-whisper"
    kind = "asr"

    def __init__(self, model: str, localai_dir: str, pins: dict[str, str] | None = None,
                 compute_type: str = "int8", beam_size: int = 5) -> None:
        a = catalog.approved(model, "asr", "faster-whisper")
        if a is None:
            raise EngineRefused(f"{model} no está en la lista aprobada de T62 para ASR")
        if not localai_dir:
            raise EngineRefused("EIM_LOCALAI_DIR vacío: no se sabe dónde están los pesos")
        self.model, self.pin, self.need_mb, self.pins = model, a.pin, a.need_mb, pins or {}
        self.folder = Path(localai_dir) / "models" / "faster-whisper" / model
        self.params: dict[str, Any] = {"compute_type": compute_type, "beam_size": beam_size,
                                       "vad_filter": True, "device": "cpu"}
        self._m: Any = None
        self._sha: str | None = None

    def weights_sha(self) -> str:
        if self._sha:
            return self._sha
        weights = self.folder / "model.bin"
        if not weights.is_file():
            raise EngineRefused(f"faltan los pesos {weights} (se bajan aparte, nunca en ejecución)")
        meta = _metadata(self.folder)
        if meta and self.pin and not meta[0].startswith(self.pin):
            raise EngineRefused(f"{self.model}: revisión {meta[0][:8]} distinta de la fijada "
                                f"({self.pin})")
        sha = sha256_file(weights)
        expected = self.pins.get(self.model) or (meta[1] if meta else "")
        if not expected:
            raise EngineRefused(f"{self.model}: sin SHA-256 de referencia (metadatos de la "
                                "descarga ni pins.json)")
        check_pin(self.model, sha, {self.model: expected})
        self.params["revision"] = meta[0] if meta else None
        self._sha = sha
        return sha

    def _load(self) -> Any:
        if self._m is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise EngineRefused("faster-whisper no instalado (extra [video], entorno de "
                                    "EIM_LOCALAI_DIR)") from e
            self._m = WhisperModel(str(self.folder), device="cpu",
                                   compute_type=self.params["compute_type"],
                                   cpu_threads=os.cpu_count() or 4, local_files_only=True)
        return self._m

    def transcribe(self, audio: Path, language: str | None, timeout_s: float) -> list[Segment]:
        segs, _ = self._load().transcribe(str(audio), language=language,
                                          beam_size=self.params["beam_size"], vad_filter=True)
        return [Segment(t_start=max(0.0, s.start), t_end=max(s.start, s.end), text=s.text.strip())
                for s in segs]   # el generador transcribe al recorrerlo

    def unload(self) -> None:
        self._m = None
        gc.collect()
