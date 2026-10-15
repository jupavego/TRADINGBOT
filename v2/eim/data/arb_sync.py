"""Escáner periódico de arbitraje (T39): Binance (REST público) → `ArbStore`.

Corre dentro de la API como el calendario. Contratos, pares spot e intervalos de funding
cambian poco y `exchangeInfo` de spot es pesado: se cachean `meta_ttl_s` segundos. El funding
realizado solo cambia en cada liquidación (8 h) y su endpoint tiene un límite compartido de
500 peticiones / 5 min: se cachea `hist_ttl_s`. Libros y funding previsto, nunca.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eim.core import ArbMarket, FuturesContract, SpotPair
from eim.data.arb_market import load_arb_market
from eim.data.arb_store import ArbStore
from eim.data.providers.binance_arb import BinanceArbData

log = logging.getLogger(__name__)


class CachedArbData(BinanceArbData):
    """`BinanceArbData` con caché de metadatos y funding realizado (libros y funding previsto,
    nunca)."""

    def __init__(self, *args: Any, meta_ttl_s: float = 3600.0, hist_ttl_s: float = 300.0,
                 **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.meta_ttl_s, self.hist_ttl_s = meta_ttl_s, hist_ttl_s
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cached(self, key: str, fn: Callable[[], Any], ttl: float | None = None) -> Any:
        hit = self._cache.get(key)
        now = time.monotonic()
        if hit is not None and now - hit[0] < (self.meta_ttl_s if ttl is None else ttl):
            return hit[1]
        val = fn()
        self._cache[key] = (now, val)
        return val

    def spot_pairs(self) -> list[SpotPair]:
        return self._cached("spot_pairs", super().spot_pairs)

    def futures_contracts(self) -> list[FuturesContract]:
        return self._cached("contracts", super().futures_contracts)

    def funding_intervals(self) -> dict[str, float]:
        return self._cached("intervals", super().funding_intervals)

    def funding_history(self, symbol: str, start: int, end: int) -> list[tuple[int, float]]:
        return self._cached(f"funding:{symbol}",
                            lambda: super(CachedArbData, self).funding_history(symbol, start, end),
                            self.hist_ttl_s)


class ArbSync:
    """Carga la fotografía cada `interval_s`, la guarda y avisa con `on_scan` (p. ej. WS)."""

    def __init__(self, data_root: Path, provider: BinanceArbData | None = None, *,
                 assets: tuple[str, ...] = ("BTC", "ETH"), interval_s: float = 10.0,
                 borrow_apr: dict[str, float] | None = None) -> None:
        self.store = ArbStore(data_root)
        self.provider = provider or CachedArbData()
        self.assets, self.interval_s = assets, interval_s
        self.borrow_apr = borrow_apr or {}
        self.last: ArbMarket | None = None

    def run_once(self) -> ArbMarket:
        mkt = load_arb_market(self.provider, assets=self.assets, borrow_apr=self.borrow_apr)
        self.store.save(mkt)
        self.last = mkt
        return mkt

    async def loop(self, on_scan: Callable[[ArbMarket], None] | None = None) -> None:
        while True:
            try:
                mkt = await asyncio.to_thread(self.run_once)
                if mkt.errors:
                    log.warning("escaneo de arbitraje con faltantes: %s", list(mkt.errors))
                if on_scan is not None:
                    on_scan(mkt)
            except Exception:  # noqa: BLE001 - el escáner nunca tumba la API
                log.exception("escaneo de arbitraje fallido")
            await asyncio.sleep(self.interval_s)
