"""Configuración de la capa de motores locales: SOLO por variables `EIM_LOCALAI_*`.

El llamador nunca elige el motor: pide «un LLM» o «un OCR» y la configuración decide cuál
responde. Todo está apagado por defecto (`off`): sin configurar, cada motor dice `no_data` con su
motivo. Los servidores HTTP solo se aceptan en el bucle local (127.0.0.1, ::1, localhost).

| Variable | Valores | Defecto |
|---|---|---|
| `EIM_LOCALAI_LLM` | `ollama` · `llamacpp` · `claude` · `off` | `off` |
| `EIM_LOCALAI_LLM_MODEL` | modelo aprobado | `qwen3:4b-instruct` |
| `EIM_LOCALAI_VISION` / `_VISION_MODEL` | `ollama` · `off` | `off` / `qwen3-vl:2b-instruct…` |
| `EIM_LOCALAI_ASR` / `_ASR_MODEL` | `faster-whisper` · `off` | `off` / `small` |
| `EIM_LOCALAI_OCR` | `rapidocr` · `off` | `off` |
| `EIM_LOCALAI_EMBED` / `_EMBED_MODEL` | `ollama` · `off` | `off` / `qwen3-embedding:0.6b` |
| `EIM_LOCALAI_OLLAMA_HOST` | URL en 127.0.0.1 | `http://127.0.0.1:11434` |
| `EIM_LOCALAI_LLAMACPP_HOST` / `_LLAMACPP_KEY` / `_LLAMACPP_GGUF` | servidor, clave, GGUF | — |
| `EIM_LOCALAI_DIR` | carpeta de motores (pesos de whisper, `pins.json`) | — |
| `EIM_LOCALAI_TIMEOUT_S` | tope por llamada | `900` |
| `EIM_LOCALAI_WAIT_S` | espera máxima en la cola | `1800` |
| `EIM_LOCALAI_RETRIES` | reintentos ante motor caído | `1` |
| `EIM_LOCALAI_RAM_MARGIN_MB` | RAM libre que debe quedar además del modelo | `1024` |
| `EIM_LOCALAI_CPU_S_PER_DAY` | presupuesto de cómputo por día UTC (s; 0 = sin tope) | `0` |
| `EIM_LOCALAI_DB` | base del registro de salud | `<EIM_DATA_DIR>/localai/localai.duckdb` |
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from eim.localai.engines import EngineRefused

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
CHOICES = {
    "llm": {"off", "ollama", "llamacpp", "claude", "fake"},
    "vision": {"off", "ollama", "fake"},
    "asr": {"off", "faster-whisper", "fake"},
    "ocr": {"off", "rapidocr", "fake"},
    "embed": {"off", "ollama", "fake"},
}
DEFAULT_MODEL = {"llm": "qwen3:4b-instruct", "vision": "qwen3-vl:2b-instruct-q4_K_M",
                 "asr": "small", "ocr": "rapidocr-3.10.0", "embed": "qwen3-embedding:0.6b"}
_VAR = {"llm": "LLM", "vision": "VISION", "asr": "ASR", "ocr": "OCR", "embed": "EMBED"}


def loopback_url(url: str) -> str:
    """Devuelve la URL sin barra final si apunta al bucle local; si no, `EngineRefused`."""
    u = urlparse(url if "://" in url else f"http://{url}")
    if u.scheme not in {"http", "https"} or (u.hostname or "") not in LOOPBACK:
        raise EngineRefused(f"{url} no es un servidor del bucle local: los motores solo "
                            "escuchan en 127.0.0.1")
    return f"{u.scheme}://{u.netloc}".rstrip("/")


def _num(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(env.get(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class LocalAIConfig:
    backends: dict[str, str] = field(default_factory=lambda: dict.fromkeys(CHOICES, "off"))
    models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODEL))
    ollama_host: str = "http://127.0.0.1:11434"
    llamacpp_host: str = ""
    llamacpp_key: str = ""
    llamacpp_gguf: str = ""
    localai_dir: str = ""
    timeout_s: float = 900.0
    wait_s: float = 1800.0
    retries: int = 1
    ram_margin_mb: float = 1024.0
    cpu_s_per_day: float = 0.0
    db_path: str = ""
    problems: tuple[str, ...] = ()   # valores no reconocidos: se apaga ese motor y se avisa

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LocalAIConfig:
        env = os.environ if env is None else env
        backends, models, problems = {}, {}, []
        for kind, var in _VAR.items():
            val = env.get(f"EIM_LOCALAI_{var}", "off").strip().lower() or "off"
            if val not in CHOICES[kind]:
                problems.append(f"EIM_LOCALAI_{var}={val} no es un motor válido para {kind}")
                val = "off"
            backends[kind] = val
            models[kind] = env.get(f"EIM_LOCALAI_{var}_MODEL", "").strip() or DEFAULT_MODEL[kind]
        data_dir = Path(env.get("EIM_DATA_DIR", "data"))
        return cls(
            backends=backends, models=models,
            ollama_host=env.get("EIM_LOCALAI_OLLAMA_HOST", "").strip()
            or env.get("EIM_LOCAL_LLM_HOST", "").strip() or "http://127.0.0.1:11434",
            llamacpp_host=env.get("EIM_LOCALAI_LLAMACPP_HOST", "").strip(),
            llamacpp_key=env.get("EIM_LOCALAI_LLAMACPP_KEY", "").strip(),
            llamacpp_gguf=env.get("EIM_LOCALAI_LLAMACPP_GGUF", "").strip(),
            localai_dir=env.get("EIM_LOCALAI_DIR", "").strip(),
            timeout_s=_num(env, "EIM_LOCALAI_TIMEOUT_S", 900.0),
            wait_s=_num(env, "EIM_LOCALAI_WAIT_S", 1800.0),
            retries=max(0, min(3, int(_num(env, "EIM_LOCALAI_RETRIES", 1)))),
            ram_margin_mb=_num(env, "EIM_LOCALAI_RAM_MARGIN_MB", 1024.0),
            cpu_s_per_day=_num(env, "EIM_LOCALAI_CPU_S_PER_DAY", 0.0),
            db_path=env.get("EIM_LOCALAI_DB", "").strip()
            or str(data_dir / "localai" / "localai.duckdb"),
            problems=tuple(problems),
        )
