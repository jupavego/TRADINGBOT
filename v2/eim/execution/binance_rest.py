"""REST firmado común a los brokers de testnet de Binance (futuros T30 y spot T45).

Seguridad:
- Cada broker declara sus hosts de testnet; cualquier otro se bloquea al construir, también
  si se inyecta un cliente. No hay camino a la API real desde aquí.
- Claves solo por entorno: nunca en el repositorio, en `repr` ni en mensajes de error. Los
  parámetros firmados de POST/DELETE van en el cuerpo y el registro de `httpx` se sube a
  WARNING para que ninguna URL firmada llegue a los logs.
- T83: un 429/418 bloquea el cliente hasta `Retry-After` (o la espera por defecto): mientras
  dure no sale ninguna petición (`RateLimited` local), porque insistir alarga el bloqueo.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from eim.execution.broker import BrokerError, NetworkError, OrderRejected, RateLimited

ENV_KEY, ENV_SECRET = "EIM_TESTNET_API_KEY", "EIM_TESTNET_API_SECRET"
_AMBIGUOUS_HTTP = {408, 418, 429}
# espera si el exchange no manda `Retry-After`: 429 → 1 s; 418 → 2 min (bloqueo mínimo de Binance)
DEFAULT_WAIT_MS = {429: 1_000, 418: 120_000}


def rate_wait_ms(status: int, retry_after_s: str | None) -> int:
    """Milisegundos de espera tras un 429/418 (`Retry-After` en segundos si lo trae)."""
    try:
        secs = float(retry_after_s or 0)
    except ValueError:
        secs = 0.0
    return int(secs * 1000) if secs > 0 else DEFAULT_WAIT_MS[status]


def check_host(url: str, hosts: frozenset[str], label: str = "la testnet de Binance") -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in hosts:
        raise BrokerError(f"host bloqueado: '{parts.hostname}' no es {label}")


class Credentials:
    """Clave y secreto de testnet. `repr` nunca muestra el secreto."""

    def __init__(self, key: str, secret: str, env: tuple[str, str] = (ENV_KEY, ENV_SECRET)) -> None:
        if not key or not secret:
            raise BrokerError(f"faltan {env[0]}/{env[1]} en el entorno (claves de testnet)")
        self.key, self._secret = key, secret.encode()

    @classmethod
    def from_env(cls, key_env: str = ENV_KEY, secret_env: str = ENV_SECRET) -> Credentials:
        return cls(os.environ.get(key_env, ""), os.environ.get(secret_env, ""),
                   (key_env, secret_env))

    def sign(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    def __repr__(self) -> str:
        return f"Credentials(key=…{self.key[-4:]}, secret=***)"


class SignedRest:
    """Cliente HTTP con firma HMAC, sincronía de reloj y errores tipados (`NetworkError` =
    resultado desconocido; `OrderRejected` = rechazo firme con código)."""

    def __init__(self, client: httpx.Client, creds: Credentials, hosts: frozenset[str],
                 time_path: str, recv_window: int, clock: Callable[[], int]) -> None:
        check_host(str(client.base_url), hosts)
        self.client, self.creds, self.time_path = client, creds, time_path
        self._recv, self._clock = recv_window, clock
        self._offset: int | None = None
        self.last_ok: int | None = None            # ms de la última respuesta del exchange
        self.blocked: RateLimited | None = None    # T83: último 429/418 (vigente hasta `until`)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    def offset(self) -> int:
        """Desfase reloj del exchange − local (ms); lo usa también el WS API (T83)."""
        if self._offset is None:
            self._sync_time()
        return self._offset or 0

    def call(self, method: str, path: str, params: dict[str, Any] | None = None,
             signed: bool = True, keyed: bool = False) -> Any:
        """`keyed`: solo cabecera de la clave, sin firma (flujo de usuario, `listenKey`)."""
        b = self.blocked
        if b is not None and self._clock() < b.until:
            raise RateLimited(f"en espera por {b}", b.status, b.until)
        p = {k: v for k, v in (params or {}).items() if v is not None}
        headers: dict[str, str] = {"X-MBX-APIKEY": self.creds.key} if keyed else {}
        if signed:
            if self._offset is None:
                self._sync_time()
            p.update(timestamp=self._clock() + (self._offset or 0), recvWindow=self._recv)
            body = urlencode(p)
            body += "&signature=" + self.creds.sign(body)
            headers["X-MBX-APIKEY"] = self.creds.key
        else:
            body = urlencode(p)
        try:
            if method == "GET":
                resp = self.client.request("GET", f"{path}?{body}" if body else path,
                                           headers=headers)
            else:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                resp = self.client.request(method, path, content=body, headers=headers)
        except httpx.TransportError as exc:          # sin URL: nunca filtra la firma
            raise NetworkError(f"red: {type(exc).__name__} en {method} {path}") from None
        if resp.status_code in DEFAULT_WAIT_MS:
            until = self._clock() + rate_wait_ms(resp.status_code, resp.headers.get("Retry-After"))
            self.blocked = RateLimited(f"HTTP {resp.status_code} en {method} {path}",
                                       resp.status_code, until)
            raise self.blocked
        if resp.status_code >= 500 or resp.status_code in _AMBIGUOUS_HTTP:
            raise NetworkError(f"HTTP {resp.status_code} en {method} {path}")
        try:
            data = resp.json()
        except ValueError:
            raise NetworkError(f"respuesta ilegible en {method} {path}") from None
        if resp.status_code >= 400:
            code = data.get("code") if isinstance(data, dict) else None
            msg = str(data.get("msg", "")) if isinstance(data, dict) else ""
            if code == -1021:                        # reloj fuera de recvWindow: no procesada
                self._offset = None
                raise NetworkError(f"reloj desincronizado en {path}")
            raise OrderRejected(msg, code,
                                duplicate=code == -4116 or "duplicate" in msg.lower())
        self.last_ok = self._clock()
        return data

    def _sync_time(self) -> None:
        self._offset = 0
        server = self.call("GET", self.time_path, signed=False)["serverTime"]
        self._offset = int(server) - self._clock()
