"""Construcción de backends según la configuración (`EIM_LOCALAI_*`); el llamador no elige.

Un backend que no se puede construir (modelo fuera de la lista aprobada, host fuera del bucle
local, falta la clave) queda en None con su motivo: ese motor dirá `no_data` y el resto sigue.
Las librerías pesadas (faster-whisper, RapidOCR) solo se importan al usarlas.
"""

from __future__ import annotations

from eim.localai import catalog
from eim.localai.config import LocalAIConfig
from eim.localai.engines import Backend, EngineRefused


def build(kind: str, cfg: LocalAIConfig) -> Backend | None:
    choice, model = cfg.backends.get(kind, "off"), cfg.models.get(kind, "")
    pins = catalog.file_pins({"EIM_LOCALAI_DIR": cfg.localai_dir})
    if choice == "off":
        return None
    if choice == "fake":
        from eim.localai.fake import fake_backend

        return fake_backend(kind)
    if choice == "ollama":
        from eim.localai.backends.ollama import OllamaBackend

        return OllamaBackend(cfg.ollama_host, model, kind)
    if choice == "llamacpp":
        from eim.localai.backends.llamacpp import LlamaCppBackend

        return LlamaCppBackend(cfg.llamacpp_host, cfg.llamacpp_key, cfg.llamacpp_gguf, pins)
    if choice == "claude":
        from eim.localai.backends.claude import ClaudeBackend

        return ClaudeBackend()
    if choice == "faster-whisper":
        from eim.localai.backends.whisper import WhisperBackend

        return WhisperBackend(model, cfg.localai_dir, pins)
    if choice == "rapidocr":
        from eim.localai.backends.rapidocr import RapidOCRBackend

        return RapidOCRBackend(pins)
    raise EngineRefused(f"motor {choice} desconocido para {kind}")


def build_all(cfg: LocalAIConfig) -> tuple[dict[str, Backend | None], dict[str, str]]:
    backends: dict[str, Backend | None] = {}
    problems: dict[str, str] = {}
    for p in cfg.problems:
        kind = next((k for k in cfg.backends if f"para {k}" in p), "")
        problems[kind] = p
    for kind in cfg.backends:
        try:
            backends[kind] = build(kind, cfg)
        except EngineRefused as e:
            backends[kind], problems[kind] = None, str(e)
    return backends, problems
