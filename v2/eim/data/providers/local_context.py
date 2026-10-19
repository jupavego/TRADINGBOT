"""Analizador de contexto con un LLM LOCAL (Ollama, API HTTP en 127.0.0.1). Todo el I/O aquí.

Mismo contrato que `ClaudeContextAnalyzer` (`list[NewsItem] -> dict | None`), sin clave ni coste:
- Salida estructurada con `format` = esquema JSON de `ContextOutput` (el agente la revalida).
- Mismo prompt anti-inyección: los titulares van como datos delimitados, jamás instrucciones.
- Sin servidor local, sin el modelo o con un fallo → None (el agente dice `no_data`).
Solo habla con la máquina local: los titulares no salen del equipo.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from eim.agents.context.schema import ContextOutput
from eim.core import NewsItem
from eim.data.providers.claude_context import SYSTEM_PROMPT

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:4b"  # ajustable con EIM_LOCAL_LLM_MODEL; verificar licencia al instalarlo


class LocalContextAnalyzer:
    """Callable para inyectar en `ContextAgent`; CPU, un modelo a la vez, timeout generoso."""

    def __init__(self, host: str | None = None, model: str | None = None,
                 client: httpx.Client | None = None, timeout: float = 900.0,
                 num_predict: int = 700, max_items: int = 15) -> None:
        self.host = (host or os.environ.get("EIM_LOCAL_LLM_HOST") or DEFAULT_HOST).rstrip("/")
        self.model = model or os.environ.get("EIM_LOCAL_LLM_MODEL") or DEFAULT_MODEL
        self.client, self.timeout, self.num_predict = client, timeout, num_predict
        self.max_items = max_items  # CPU: menos titulares = prompt corto (los más recientes)

    def payload(self, items: list[NewsItem]) -> dict[str, Any]:
        items = items[: self.max_items]
        data = json.dumps([{"id": n.id, "fuente": n.source, "titular": n.title} for n in items],
                          ensure_ascii=False)
        return {
            "model": self.model, "stream": False, "think": False,
            "format": ContextOutput.model_json_schema(),
            "options": {"temperature": 0.1, "num_predict": self.num_predict},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"<headlines_data>\n{data}\n</headlines_data>"}],
        }

    def __call__(self, items: list[NewsItem]) -> dict[str, Any] | None:
        http = self.client or httpx.Client(timeout=self.timeout)
        try:
            r = http.post(f"{self.host}/api/chat", json=self.payload(items))
            r.raise_for_status()
            out = json.loads(r.json()["message"]["content"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        finally:
            if self.client is None:
                http.close()
        return out if isinstance(out, dict) else None

    def available(self) -> bool:
        """¿Hay servidor local con el modelo descargado? (para el diagnóstico, sin generar)."""
        http = self.client or httpx.Client(timeout=5.0)
        try:
            names = [m.get("name", "") for m in http.get(f"{self.host}/api/tags").json()["models"]]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return False
        finally:
            if self.client is None:
                http.close()
        return any(n == self.model or n.split(":")[0] == self.model for n in names)
