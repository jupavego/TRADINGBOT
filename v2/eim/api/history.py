"""Carga automática de historia: un (símbolo, marco) sin velas se rellena desde el proveedor.

Sin esto, abrir un marco nunca descargado (p. ej. 4h) dejaba todo en 0: sin velas no hay snapshot,
ni reportes de agentes, ni pronóstico. Solo hace red si el almacén tiene pocas velas.
"""

from __future__ import annotations

import threading
import time

from eim.data.providers.base import Provider
from eim.data.store import Store
from eim.data.sync import sync_candles
from eim.data.timeframes import tf_ms


class HistoryLoader:
    def __init__(self, store: Store, provider: Provider, bars: int = 1500,
                 min_bars: int = 600) -> None:
        self._store, self._provider, self._bars, self._min = store, provider, bars, min_bars
        self._lock = threading.Lock()
        self.errors: dict[tuple[str, str], str] = {}

    def ensure(self, symbol: str, timeframe: str) -> bool:
        """True si tras la llamada hay historia suficiente. Nunca lanza (falla de red → False)."""
        with self._lock:
            have = len(self._store.read_candles(symbol, timeframe, last=self._min))
            if have >= self._min:
                return True
            try:
                now = int(time.time() * 1000)
                sync_candles(self._store, self._provider, symbol, timeframe,
                             now - self._bars * tf_ms(timeframe), now)
                self.errors.pop((symbol, timeframe), None)
            except Exception as exc:  # red caída, límite de tasa, etc.
                self.errors[(symbol, timeframe)] = f"{type(exc).__name__}: {exc}"
                return False
            return len(self._store.read_candles(symbol, timeframe, last=self._min)) >= self._min
