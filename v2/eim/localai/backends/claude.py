"""Backend Claude API (T24) detrás de la misma interfaz `LLMBackend`. OPCIONAL y apagado.

Solo con `EIM_LOCALAI_LLM=claude` **y** `ANTHROPIC_API_KEY`. Es el único backend que sale del
equipo: el texto enviado viaja a la API de Anthropic. Reutiliza el `CostGuard` de T24 (presupuesto
en USD por día UTC; agotado ⇒ la etapa se aplaza). No hay pesos locales: `weights_sha` es
`api:<modelo>`, que identifica el modelo fijado, no un archivo.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from eim.data.providers.claude_context import API_URL, MODEL, CostGuard
from eim.localai.backends.common import post_json
from eim.localai.engines import EngineRefused
from eim.localai.resources import Deferred


class ClaudeBackend:
    engine_id = "claude-api"
    kind = "llm"
    need_mb = 0

    def __init__(self, api_key: str | None = None, guard: CostGuard | None = None,
                 client: httpx.Client | None = None, max_tokens: int = 1024,
                 max_usd_per_day: float = 0.25) -> None:
        self.key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.key:
            raise EngineRefused("EIM_LOCALAI_LLM=claude sin ANTHROPIC_API_KEY")
        self.model, self.client, self.max_tokens = MODEL, client, max_tokens
        self.guard = guard or CostGuard(max_usd_per_day)
        self._day = int(time.time() // 86_400)
        self.params: dict[str, Any] = {"temperature": 0.0, "max_tokens": max_tokens,
                                       "max_usd_per_day": self.guard.max_usd}

    def weights_sha(self) -> str:
        return f"api:{self.model}"

    def unload(self) -> None:
        """Nada que descargar: el modelo vive en la API."""

    def generate(self, system: str, user: str, schema: dict[str, Any], timeout_s: float) -> str:
        day = int(time.time() // 86_400)
        if day != self._day:
            self._day = day
            self.guard.reset()
        est_in = (len(system) + len(user) + len(json.dumps(schema))) // 3
        if not self.guard.allows(est_in, self.max_tokens):
            raise Deferred("presupuesto diario de la API de Claude agotado")
        body = {"model": self.model, "max_tokens": self.max_tokens, "temperature": 0.0,
                "system": [{"type": "text", "text": system,
                            "cache_control": {"type": "ephemeral"}}],
                "tools": [{"name": "salida", "description": "Salida estructurada.",
                           "input_schema": schema}],
                "tool_choice": {"type": "tool", "name": "salida"},
                "messages": [{"role": "user", "content": user}]}
        headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01"}
        out = post_json(self.client, API_URL, body, timeout_s, headers=headers,
                        what="la API de Claude")
        usage = out.get("usage", {})
        self.guard.add(usage.get("input_tokens", est_in), usage.get("output_tokens", 0))
        for block in out.get("content", []):
            if block.get("type") == "tool_use":
                return json.dumps(block.get("input"), ensure_ascii=False)
        return ""   # sin herramienta: la validación lo marcará y pedirá una reparación
