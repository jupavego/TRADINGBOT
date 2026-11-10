"""Backend Ollama (T62: motor aprobado) por HTTP en 127.0.0.1: LLM, visión y embeddings.

- Solo modelos de la lista aprobada; los pesos se verifican con el digest del manifiesto que da
  `/api/tags` frente al prefijo fijado en `catalog.APPROVED` (si no coincide: `EngineRefused`).
- Salida estructurada con `format` = esquema JSON, sin razonamiento (`think: false`),
  temperatura 0 y semilla fija: la misma entrada da la misma salida con los mismos pesos.
- `keep_alive` corto: el runner interno de Ollama escucha sin clave mientras hay un modelo
  cargado (`docs/SEGURIDAD.md`); `unload()` lo descarga en el acto.
Ollama debe correr con `OLLAMA_NO_CLOUD=1` y `OLLAMA_HOST=127.0.0.1:11434` (`OPERACION.md` §7).
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Any

import httpx

from eim.localai import catalog
from eim.localai.backends.common import get_json, post_json
from eim.localai.config import loopback_url
from eim.localai.engines import EngineRefused

KEEP_ALIVE = "2m"
SHA_TTL_S = 300.0


class OllamaBackend:
    engine_id = "ollama"

    def __init__(self, host: str, model: str, kind: str, client: httpx.Client | None = None,
                 num_predict: int = 1024, max_side: int = 768) -> None:
        self.host, self.model, self.kind, self.client = loopback_url(host), model, kind, client
        a = catalog.approved(model, kind, "ollama")
        if a is None:
            raise EngineRefused(f"{model} no está en la lista aprobada de T62 para {kind} con "
                                "Ollama (eim/localai/catalog.py)")
        self.pin, self.need_mb = a.pin, a.need_mb
        self.options = {"temperature": 0.0, "seed": 0, "num_predict": num_predict}
        self.max_side = max_side
        self.params: dict[str, Any] = {"host": self.host, "keep_alive": KEEP_ALIVE,
                                       **({} if kind == "embed" else self.options)}
        if kind == "vision":
            self.params["max_side"] = max_side
        self._sha: tuple[float, str] | None = None

    def weights_sha(self) -> str:
        if self._sha and time.monotonic() - self._sha[0] < SHA_TTL_S:
            return self._sha[1]
        rows = get_json(self.client, f"{self.host}/api/tags", what="Ollama").get("models", [])
        names = {self.model, f"{self.model}:latest"}
        digest = next((m.get("digest", "") for m in rows if m.get("name") in names), None)
        if digest is None:
            raise EngineRefused(f"el modelo {self.model} no está descargado en Ollama "
                                f"({self.host}); descargarlo es un paso de instalación")
        if self.pin and not digest.startswith(self.pin):
            raise EngineRefused(f"{self.model}: digest {digest[:12]} distinto del fijado en T62 "
                                f"({self.pin}); no se usa hasta repetir el banco")
        self._sha = (time.monotonic(), f"ollama-manifest:{digest}")
        return self._sha[1]

    def unload(self) -> None:
        path = "/api/embed" if self.kind == "embed" else "/api/generate"
        body: dict[str, Any] = {"model": self.model, "keep_alive": 0}
        if self.kind == "embed":
            body["input"] = []
        post_json(self.client, f"{self.host}{path}", body, 30.0, what="Ollama")

    def _chat(self, messages: list[dict[str, Any]], schema: dict[str, Any],
              timeout_s: float) -> str:
        body = {"model": self.model, "stream": False, "think": False, "format": schema,
                "options": self.options, "keep_alive": KEEP_ALIVE, "messages": messages}
        out = post_json(self.client, f"{self.host}/api/chat", body, timeout_s, what="Ollama")
        try:
            return str(out["message"]["content"])
        except (KeyError, TypeError) as e:
            raise EngineRefused("Ollama devolvió una respuesta sin mensaje") from e

    def generate(self, system: str, user: str, schema: dict[str, Any], timeout_s: float) -> str:
        return self._chat([{"role": "system", "content": system},
                           {"role": "user", "content": user}], schema, timeout_s)

    def _image_b64(self, image: Path) -> str:
        """Fotograma reducido a `max_side` px: la RAM del VLM crece con la resolución (T62)."""
        try:
            from PIL import Image
        except ImportError:
            return base64.b64encode(image.read_bytes()).decode()
        im = Image.open(image).convert("RGB")
        im.thumbnail((self.max_side, self.max_side))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def ask(self, image: Path, system: str, user: str, schema: dict[str, Any],
            timeout_s: float) -> str:
        return self._chat([{"role": "system", "content": system},
                           {"role": "user", "content": user, "images": [self._image_b64(image)]}],
                          schema, timeout_s)

    def embed(self, texts: list[str], timeout_s: float) -> list[list[float]]:
        out = post_json(self.client, f"{self.host}/api/embed",
                        {"model": self.model, "input": texts, "keep_alive": KEEP_ALIVE},
                        timeout_s, what="Ollama")
        return list(out.get("embeddings") or [])
