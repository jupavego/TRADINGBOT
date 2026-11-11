"""Proveedor Deribit público (sin claves): índice de volatilidad implícita DVOL (T165).

`public/get_volatility_index_data` devuelve velas OHLC del índice DVOL (σ implícita anualizada
en %, horizonte de 30 días) para BTC y ETH. La historia pública empieza el 2021-03-24T00:00Z.

Dos detalles de la API que el código respeta:

- El `timestamp` de cada fila es la **apertura** del intervalo, así que la última fila puede estar
  en formación: se descarta mientras `t + paso > ahora`.
- Cada respuesta trae como mucho 1 000 filas, las **más recientes** de la ventana pedida, y un
  `continuation` con el instante por el que seguir; se pagina **hacia atrás** usando ese valor como
  nuevo `end_timestamp` hasta que llega `null`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from eim.core import Candle
from eim.data.providers.binance import ProviderError

BASE_URL = "https://www.deribit.com"
SOURCE = "deribit-dvol"
PATH = "/api/v2/public/get_volatility_index_data"
HISTORY_START_MS = 1_616_544_000_000  # 2021-03-24T00:00Z: antes no hay índice publicado
_RETRY_STATUS = {429, 500, 502, 503, 504}
_RESOLUTION_MS = {"60": 60_000, "3600": 3_600_000, "43200": 43_200_000, "1D": 86_400_000}
_MAX_PAGES = 400  # 400 × 1 000 velas de 1 h ≈ 45 años: cota de seguridad, no un límite real


class DeribitPublic:
    """Índice DVOL por REST, con reintentos, límite de tasa y paginación hacia atrás."""

    name = SOURCE

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        base_url: str = BASE_URL,
        max_retries: int = 4,
        backoff: float = 1.0,
        min_interval: float = 0.2,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._client = client or httpx.Client(base_url=base_url, timeout=30.0)
        self._max_retries = max_retries
        self._backoff = backoff
        self._min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._last_call = 0.0

    def now(self) -> int:
        """Instante actual en ms según el reloj del proveedor (sustituible en las pruebas)."""
        return self._clock()

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        last_err = ""
        for attempt in range(self._max_retries + 1):
            self._last_call = time.monotonic()
            try:
                resp = self._client.get(PATH, params=params)
            except httpx.TransportError as exc:
                last_err = f"red: {exc}"
            else:
                if resp.status_code == 200:
                    body = resp.json()
                    if "error" in body:
                        raise ProviderError(f"{PATH} error de la API: {body['error']}")
                    return dict(body.get("result") or {})
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if resp.status_code not in _RETRY_STATUS:
                    raise ProviderError(f"{PATH} {last_err}")
            if attempt < self._max_retries:
                self._sleep(self._backoff * 2**attempt)
        raise ProviderError(f"{PATH} agotó {self._max_retries} reintentos ({last_err})")

    def volatility_index(self, currency: str, start: int, end: int,
                         resolution: str = "3600") -> list[Candle]:
        """Velas cerradas del DVOL con `t` (apertura) en [start, end), ordenadas por tiempo.

        `v` va a 0: el índice no tiene volumen. Lanza `ProviderError` si la API falla.
        """
        step = _RESOLUTION_MS.get(resolution)
        if step is None:
            raise ValueError(f"resolución no soportada: {resolution}")
        now = self._clock()
        rows: dict[int, Candle] = {}
        cursor = end
        for _ in range(_MAX_PAGES):
            if cursor <= start:
                break
            res = self._get({"currency": currency.upper(), "start_timestamp": start,
                             "end_timestamp": cursor, "resolution": resolution})
            data = res.get("data") or []
            for r in data:
                t = int(r[0])
                if not (start <= t < end) or t + step > now:
                    continue
                o, h, lo, c = (float(x) for x in r[1:5])
                rows[t] = Candle(t=t, o=o, h=max(h, o, c, lo), l=min(lo, o, c, h), c=c, v=0.0)
            cont = res.get("continuation")
            if not data or cont is None:
                break
            nxt = int(cont)
            if nxt >= cursor:
                break
            cursor = nxt
        return [rows[t] for t in sorted(rows)]
