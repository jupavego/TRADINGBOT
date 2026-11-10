"""Backend llama.cpp (`llama-server`, plan B de T62: menos RAM con el mismo GGUF), solo LLM.

No lanza el servidor: el operador lo arranca en 127.0.0.1 con `--offline --no-webui --api-key`
(`docs/SEGURIDAD.md`). Sin clave no se usa (por defecto trae CORS `*` y web UI sin clave).
Pesos verificados: SHA-256 del GGUF (`EIM_LOCALAI_LLAMACPP_GGUF`) frente al nombre del blob de
Ollama (`sha256-<hex>`, el mismo archivo) o frente a `pins.json`; sin ninguno, no se usa.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from eim.localai import catalog
from eim.localai.backends.common import check_pin, post_json, sha256_file
from eim.localai.config import loopback_url
from eim.localai.engines import EngineRefused

MODEL = "qwen3-4b-instruct.gguf"


class LlamaCppBackend:
    engine_id = "llama.cpp"
    kind = "llm"

    def __init__(self, host: str, key: str, gguf: str, pins: dict[str, str] | None = None,
                 client: httpx.Client | None = None, max_tokens: int = 1024) -> None:
        if not host:
            raise EngineRefused("EIM_LOCALAI_LLAMACPP_HOST vacío")
        if not key:
            raise EngineRefused("llama-server sin clave (EIM_LOCALAI_LLAMACPP_KEY): no se usa")
        self.host, self.key, self.client = loopback_url(host), key, client
        self.gguf, self.pins = Path(gguf) if gguf else None, pins or {}
        self.model = MODEL
        self.need_mb = catalog.APPROVED[MODEL].need_mb
        self.body = {"temperature": 0.0, "seed": 0, "max_tokens": max_tokens}
        self.params: dict[str, Any] = {"host": self.host, **self.body}

    def weights_sha(self) -> str:
        if self.gguf is None or not self.gguf.is_file():
            raise EngineRefused("EIM_LOCALAI_LLAMACPP_GGUF no apunta a un GGUF legible: sin él "
                                "no se pueden verificar los pesos")
        sha = sha256_file(self.gguf)
        expected = self.gguf.name.removeprefix("sha256-") if self.gguf.name.startswith(
            "sha256-") else self.pins.get(MODEL)
        if not expected:
            raise EngineRefused(f"{self.gguf.name}: sin SHA-256 de referencia (ni blob de Ollama "
                                "ni pins.json)")
        check_pin(MODEL, sha, {MODEL: expected.lower()})
        return sha

    def unload(self) -> None:
        """`llama-server` mantiene un solo modelo; no hay descarga por API."""

    def generate(self, system: str, user: str, schema: dict[str, Any], timeout_s: float) -> str:
        body = {**self.body, "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": user}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "salida", "schema": schema}}}
        out = post_json(self.client, f"{self.host}/v1/chat/completions", body, timeout_s,
                        headers={"Authorization": f"Bearer {self.key}"}, what="llama-server")
        try:
            return str(out["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            raise EngineRefused("llama-server devolvió una respuesta sin mensaje") from e
