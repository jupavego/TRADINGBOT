"""Backend OCR RapidOCR 3.10.0 + onnxruntime (T62: 99 % de cifras), en proceso.

Los modelos ONNX vienen en el propio paquete (`rapidocr/models`). Si faltan, RapidOCR los
descargaría al iniciar: entonces no se usa (sin descargas en ejecución). La huella de los pesos
es el SHA-256 de la lista «nombre:SHA-256» de esos `.onnx`, comprobable contra `pins.json`.
"""

from __future__ import annotations

import gc
import hashlib
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from eim.localai.backends.common import check_pin, sha256_file
from eim.localai.engines import EngineRefused
from eim.localai.results import OCRLine

MODEL = "rapidocr-3.10.0"
VERSION = "3.10.0"


def _box(poly: Any) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


class RapidOCRBackend:
    engine_id = "rapidocr"
    kind = "ocr"
    need_mb = 450

    def __init__(self, pins: dict[str, str] | None = None) -> None:
        self.model, self.pins = MODEL, pins or {}
        self.params: dict[str, Any] = {"version": VERSION}
        self._eng: Any = None
        self._sha: str | None = None

    def weights_sha(self) -> str:
        if self._sha:
            return self._sha
        try:
            have = version("rapidocr")
        except PackageNotFoundError as e:
            raise EngineRefused("rapidocr no instalado (extra [video])") from e
        if have != VERSION:
            raise EngineRefused(f"rapidocr {have} instalado; la versión aprobada es {VERSION}")
        spec = find_spec("rapidocr")
        root = Path(spec.origin).parent / "models" if spec and spec.origin else None
        files = sorted(root.glob("*.onnx")) if root and root.is_dir() else []
        if not files:
            raise EngineRefused("RapidOCR sin modelos ONNX locales: los descargaría al iniciar")
        lines = "\n".join(f"{f.name}:{sha256_file(f)}" for f in files)
        sha = hashlib.sha256(lines.encode()).hexdigest()
        check_pin(MODEL, sha, self.pins)
        self.params["models"] = [f.name for f in files]
        self._sha = sha
        return sha

    def read(self, image: Path, timeout_s: float) -> list[OCRLine]:
        if self._eng is None:
            from rapidocr import RapidOCR

            self._eng = RapidOCR()
        out = self._eng(str(image))
        boxes = getattr(out, "boxes", None)
        txts = getattr(out, "txts", None) or ()
        scores = getattr(out, "scores", None) or ()
        if boxes is None:
            return []
        return [OCRLine(text=str(t), box=_box(b), confidence=min(1.0, max(0.0, float(s))))
                for b, t, s in zip(boxes, txts, scores, strict=False)]

    def unload(self) -> None:
        self._eng = None
        gc.collect()
