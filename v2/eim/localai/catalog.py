"""Lista aprobada en T62 (`PLAN/notas/T62_auditoria.md`): modelos, pesos fijados y RAM por etapa.

Un modelo fuera de esta lista no se usa (`EngineRefused`): añadir uno exige auditar su licencia de
código y de pesos y medirlo en el banco, y luego escribirlo aquí. `need_mb` es el pico medido en
`juanpablo-cpu` con los servicios en marcha (`v2/reports/localai/bench_juanpablo-cpu.md`); el
gestor de recursos aplaza la etapa si la RAM libre no lo cubre más el margen.

Fijación de pesos:
- Ollama: prefijo del digest del manifiesto (`ollama list`), que fija todas sus capas.
- faster-whisper / RapidOCR: revisión o versión fijada aquí y, si existe
  `%EIM_LOCALAI_DIR%\\pins.json` (`{"modelo": "sha256 del archivo de pesos"}`), el SHA-256
  exacto del archivo; si no coincide, el motor se rechaza.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Approved:
    kind: str           # llm | vision | asr | ocr | embed
    engine: str         # backend que lo sirve
    need_mb: int        # RAM pico medida (o estimada, ver `measured`)
    pin: str = ""       # prefijo de digest de Ollama o revisión de Hugging Face
    measured: bool = True
    license: str = "Apache-2.0"


APPROVED: dict[str, Approved] = {
    "qwen3:4b-instruct": Approved("llm", "ollama", 4500, "0edcdef34593"),
    "qwen3:1.7b": Approved("llm", "ollama", 2400, "8f68893c685c", measured=False),
    "qwen3-vl:2b-instruct-q4_K_M": Approved("vision", "ollama", 8800, "afc393e3572c"),
    "qwen3-embedding:0.6b": Approved("embed", "ollama", 2500, "ac6da0dfba84"),
    # llama.cpp sirve el MISMO GGUF de qwen3:4b-instruct (plan B, menos RAM: 2,6 GB medidos)
    "qwen3-4b-instruct.gguf": Approved("llm", "llamacpp", 2600, ""),
    "small": Approved("asr", "faster-whisper", 2600, "536b0662", license="MIT"),
    "large-v3-turbo": Approved("asr", "faster-whisper", 3900, "0a363e91", license="MIT"),
    "rapidocr-3.10.0": Approved("ocr", "rapidocr", 450, "3.10.0"),
}
# T24: la API de Claude va detrás de la misma interfaz (opcional, apagada por defecto); no tiene
# pesos locales ni RAM local.
REMOTE = {"claude-haiku-5-5": Approved("llm", "claude", 0, "", license="API de Anthropic")}

# Etapa → RAM por defecto si el modelo no está en la lista (solo el motor simulado)
DEFAULT_NEED_MB = {"llm": 4500, "vision": 8800, "asr": 2600, "ocr": 450, "embed": 2500}


def approved(model: str, kind: str, engine: str) -> Approved | None:
    """La entrada aprobada del modelo para esa etapa y ese motor, o None."""
    a = APPROVED.get(model) or REMOTE.get(model)
    return a if a and a.kind == kind and a.engine == engine else None


def need_mb(model: str, kind: str) -> int:
    a = APPROVED.get(model)
    return a.need_mb if a else DEFAULT_NEED_MB.get(kind, 0)


def file_pins(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """SHA-256 exactos fijados por el operador en `EIM_LOCALAI_DIR/pins.json` (opcional)."""
    env = os.environ if env is None else env
    root = env.get("EIM_LOCALAI_DIR", "").strip()
    if not root:
        return {}
    p = Path(root) / "pins.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v).lower() for k, v in raw.items()} if isinstance(raw, dict) else {}
