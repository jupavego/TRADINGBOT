"""Proveedor Binance USDⓈ-M Futures por REST (público, sin claves)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from eim.core import Candle
from eim.data.timeframes import tf_ms

BASE_URL = "https://fapi.binance.com"
SOURCE = "binance-futures"
_OI_RETENTION_MS = 29 * 24 * 3_600_000  # margen bajo los 30 días que acepta Binance
_RETRY_STATUS = {418, 429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """Fallo no recuperable del proveedor (tras reintentos)."""


class BinanceFutures:
    """Klines, funding rate y open interest históricos con reintentos y límite de tasa."""

    name = SOURCE

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        base_url: str = BASE_URL,
        max_retries: int = 4,
        backoff: float = 1.0,
        min_interval: float = 0.1,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._client = client or httpx.Client(base_url=base_url, timeout=15.0)
        self._max_retries = max_retries
        self._backoff = backoff
        self._min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._last_call = 0.0

    # --- HTTP -------------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any]) -> Any:
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        last_err: str = ""
        for attempt in range(self._max_retries + 1):
            self._last_call = time.monotonic()
            try:
                resp = self._client.get(path, params=params)
            except httpx.TransportError as exc:
                last_err = f"red: {exc}"
            else:
                if resp.status_code == 200:
                    return resp.json()
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if resp.status_code not in _RETRY_STATUS:
                    raise ProviderError(f"{path} {last_err}")
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit() and attempt < self._max_retries:
                    self._sleep(float(retry_after))
                    continue
            if attempt < self._max_retries:
                self._sleep(self._backoff * 2**attempt)
        raise ProviderError(f"{path} agotó {self._max_retries} reintentos ({last_err})")

    def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET JSON con reintentos y límite de tasa (lo reutiliza `binance_arb`)."""
        return self._get(path, params or {})

    # --- Datos ------------------------------------------------------------
    def klines(self, symbol: str, timeframe: str, start: int, end: int, *,
               path: str = "/fapi/v1/klines", limit: int = 1500) -> list[Candle]:
        """Velas cerradas en [start, end). `path`/`limit` permiten el spot (`/api/v3/klines`,
        1000) con el mismo formato de fila."""
        step = tf_ms(timeframe)
        now = self._clock()
        out: list[Candle] = []
        cursor = start
        while cursor < end:
            rows = self._get(
                path,
                {"symbol": symbol, "interval": timeframe, "startTime": cursor,
                 "endTime": end - 1, "limit": limit},
            )
            if not rows:
                break
            for r in rows:
                t = int(r[0])
                if t >= end or t + step > now:  # descarta la vela en formación
                    continue
                out.append(Candle(t=t, o=float(r[1]), h=float(r[2]), l=float(r[3]),
                                  c=float(r[4]), v=float(r[5]),
                                  trades=int(r[8]) if len(r) > 9 else None,
                                  taker_buy_v=float(r[9]) if len(r) > 9 else None))
            nxt = int(rows[-1][0]) + step
            if nxt <= cursor:
                break
            cursor = nxt
        return _dedupe(out)

    def funding_rates(self, symbol: str, start: int, end: int) -> list[tuple[int, float]]:
        out: list[tuple[int, float]] = []
        cursor = start
        while cursor < end:
            rows = self._get(
                "/fapi/v1/fundingRate",
                {"symbol": symbol, "startTime": cursor, "endTime": end - 1, "limit": 1000},
            )
            if not rows:
                break
            out += [(int(r["fundingTime"]), float(r["fundingRate"])) for r in rows]
            nxt = int(rows[-1]["fundingTime"]) + 1
            if nxt <= cursor:
                break
            cursor = nxt
        return sorted({t: v for t, v in out if start <= t < end}.items())

    def open_interest(
        self, symbol: str, timeframe: str, start: int, end: int
    ) -> list[tuple[int, float]]:
        """Binance solo conserva ~30 días de histórico de OI; lo anterior no existe."""
        step = tf_ms(timeframe)
        out: dict[int, float] = {}
        cursor = max(start, self._clock() - _OI_RETENTION_MS)
        while cursor < end:
            rows = self._get(
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": timeframe, "startTime": cursor,
                 "endTime": end - 1, "limit": 500},
            )
            if not rows:
                break
            for r in rows:
                t = int(r["timestamp"])
                if start <= t < end:
                    out[t] = float(r["sumOpenInterest"])
            nxt = int(rows[-1]["timestamp"]) + step
            if nxt <= cursor:
                break
            cursor = nxt
        return sorted(out.items())

    def _hist(
        self, path: str, params: dict[str, Any], field: str, timeframe: str, start: int, end: int
    ) -> list[tuple[int, float]]:
        """Serie `/futures/data/*` paginada (Binance retiene ~30 días)."""
        step = tf_ms(timeframe)
        out: dict[int, float] = {}
        cursor = max(start, self._clock() - _OI_RETENTION_MS)
        while cursor < end:
            rows = self._get(path, {**params, "period": timeframe, "startTime": cursor,
                                    "endTime": end - 1, "limit": 500})
            if not rows:
                break
            for r in rows:
                t = int(r["timestamp"])
                if start <= t < end:
                    out[t] = float(r[field])
            nxt = int(rows[-1]["timestamp"]) + step
            if nxt <= cursor:
                break
            cursor = nxt
        return sorted(out.items())

    def long_short_ratio(
        self, symbol: str, timeframe: str, start: int, end: int
    ) -> list[tuple[int, float]]:
        """Ratio long/short de cuentas (global); ~30 días de histórico."""
        return self._hist("/futures/data/globalLongShortAccountRatio", {"symbol": symbol},
                          "longShortRatio", timeframe, start, end)

    def basis(self, symbol: str, timeframe: str, start: int, end: int) -> list[tuple[int, float]]:
        """Basis del perpetuo ((futuro−índice)/índice); ~30 días de histórico."""
        return self._hist("/futures/data/basis",
                          {"pair": symbol, "contractType": "PERPETUAL"},
                          "basisRate", timeframe, start, end)


def _dedupe(candles: list[Candle]) -> list[Candle]:
    return sorted({c.t: c for c in candles}.values(), key=lambda c: c.t)
