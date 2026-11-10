"""Utilidades comunes de los backends: HTTP solo al bucle local y SHA-256 de pesos con caché."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

import httpx

from eim.localai.engines import EngineDown, EngineRefused

_SHA_CACHE: dict[tuple[str, int, int], str] = {}
_SHA_LOCK = threading.Lock()


def sha256_file(path: Path) -> str:
    """SHA-256 del archivo de pesos, calculado una vez por (ruta, tamaño, fecha) y proceso."""
    st = path.stat()
    key = (str(path.resolve()), st.st_size, st.st_mtime_ns)
    with _SHA_LOCK:
        if key in _SHA_CACHE:
            return _SHA_CACHE[key]
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    with _SHA_LOCK:
        _SHA_CACHE[key] = h.hexdigest()
    return _SHA_CACHE[key]


def check_pin(name: str, sha: str, pins: dict[str, str]) -> None:
    """Si el operador fijó un SHA-256 exacto para `name` (pins.json), debe coincidir."""
    want = pins.get(name)
    if want and want != sha.lower():
        raise EngineRefused(f"pesos de {name} con SHA-256 {sha[:12]}… distinto del fijado "
                            f"{want[:12]}… en pins.json: no se usan")


def post_json(client: httpx.Client | None, url: str, body: dict[str, Any], timeout: float,
              headers: dict[str, str] | None = None, what: str = "el motor") -> dict[str, Any]:
    """POST JSON; transporte caído → `EngineDown`; 404 → `EngineRefused` (modelo ausente)."""
    http = client or httpx.Client(timeout=timeout)
    try:
        r = http.post(url, json=body, headers=headers, timeout=timeout)
        if r.status_code == 404:
            raise EngineRefused(f"{what} respondió 404 (¿modelo sin descargar?)")
        if r.status_code in (401, 403):
            raise EngineRefused(f"{what} rechazó la clave ({r.status_code})")
        r.raise_for_status()
        return r.json()
    except httpx.TimeoutException as e:
        raise EngineDown(f"{what} no respondió a tiempo") from e
    except httpx.TransportError as e:
        raise EngineDown(f"{what} no responde en {url.split('/api')[0]}") from e
    except httpx.HTTPStatusError as e:
        raise EngineDown(f"{what} respondió {e.response.status_code}") from e
    except ValueError as e:
        raise EngineDown(f"{what} devolvió una respuesta ilegible") from e
    finally:
        if client is None:
            http.close()


def get_json(client: httpx.Client | None, url: str, timeout: float = 10.0,
             what: str = "el motor") -> dict[str, Any]:
    http = client or httpx.Client(timeout=timeout)
    try:
        r = http.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise EngineDown(f"{what} no responde en {url}") from e
    finally:
        if client is None:
            http.close()
