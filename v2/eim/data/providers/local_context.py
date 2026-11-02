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
import threading
from collections.abc import Mapping
from typing import Any

import httpx

from eim.agents.context.schema import ContextOutput
from eim.core import NewsItem
from eim.data.providers.claude_context import SYSTEM_PROMPT

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:4b"  # ajustable con EIM_LOCAL_LLM_MODEL; verificar licencia al instalarlo
CHECK_TIMEOUT_S = 2.0       # una unidad de red caída puede tardar minutos en contestar


def _exists(path: str, timeout: float) -> bool | None:
    """¿Existe la ruta? None si no contesta a tiempo."""
    out: list[bool] = []
    t = threading.Thread(target=lambda: out.append(os.path.exists(path)), daemon=True)
    t.start()
    t.join(timeout)
    return out[0] if out else None


def ollama_problem(env: Mapping[str, str] | None = None) -> str | None:
    """Por qué el Ollama configurado no puede arrancar en esta sesión, o None (T128). Solo si el
    usuario lo configuró con `EIM_OLLAMA_EXE`: sin la variable, Contexto sin LLM es una elección.
    El lanzador (`servicio_continuo.ps1`) solo arranca Ollama si la ruta existe."""
    exe = (os.environ if env is None else env).get("EIM_OLLAMA_EXE", "").strip().strip('"')
    if not exe:
        return None
    ok = _exists(exe, CHECK_TIMEOUT_S)
    if ok:
        return None
    return (f"EIM_OLLAMA_EXE apunta a {exe}, que {'no contesta' if ok is None else 'no existe'} "
            "en esta sesión: Ollama no arranca y Contexto queda sin datos. La tarea al encender "
            "no ve las unidades de red: apunta la variable a una copia local.")


TASK = ("Tarea: `tema` = el tema dominante en pocas palabras (no copies un titular). "
        "Devuelve de 2 a 4 `catalizadores`, cada uno con `texto` (tu resumen) y `fuente` "
        "(el `id` exacto de un titular de arriba). Un catalizador sin `fuente` válida se descarta.")


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
                {"role": "user",
                 "content": f"<headlines_data>\n{data}\n</headlines_data>\n{TASK}"}],
        }

    def __call__(self, items: list[NewsItem]) -> dict[str, Any] | None:
        """Un modelo pequeño a veces omite los catalizadores: se reintenta una vez (corre en
        segundo plano, el coste es tiempo de CPU, no del ciclo)."""
        out = self._once(items)
        if out is not None and not out.get("catalizadores"):
            out = self._once(items) or out
        return out

    def _once(self, items: list[NewsItem]) -> dict[str, Any] | None:
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
