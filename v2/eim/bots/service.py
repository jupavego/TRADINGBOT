"""Servicio de bots (T57): produce las `BotSignal` de un snapshot, las guarda y las adjunta.

Es el único que lanza adaptadores (y, con ellos, procesos de modo B); el agente `bots` solo lee
`snapshot.bot_signals`. Solo participan fichas **utilizables** (seguridad habilitada y aprobadas
por el usuario). Un adaptador que falla no rompe el ciclo: queda una señal `degraded`.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from eim.bots.adapter import (
    SignalAdapter,
    closed_candles_only,
    empty_signal,
    params_hash,
    split_version,
)
from eim.core import NOT_SAVED, VERSION_CHANGED, BotSignal, MarketSnapshot
from eim.data.bots.store import BotSignalStore

log = logging.getLogger("eim.bots")
FT_PY_ENV = "EIM_BOT_FREQTRADE_PY"          # intérprete del entorno aparte de Freqtrade
FT_ENGINE_ENV = "EIM_BOT_FREQTRADE_ENGINE"  # versión del motor fijada (p. ej. «2026.9»)


def _note(sig: BotSignal, note: str) -> BotSignal:
    q = sig.data_quality.model_copy(update={"notes": [*sig.data_quality.notes, note]})
    return sig.model_copy(update={"data_quality": q})


class BotService:
    def __init__(self, adapters: Sequence[SignalAdapter], store: BotSignalStore | None = None,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.adapters, self.store, self.clock = list(adapters), store, clock

    def produce(self, snapshot: MarketSnapshot) -> list[BotSignal]:
        if not closed_candles_only(snapshot):   # point-in-time: nunca con una vela sin cerrar
            log.warning("snapshot con vela sin cerrar a %s: no se calculan señales de bots",
                        snapshot.asof)
            return []
        out: list[BotSignal] = []
        for ad in self.adapters:
            if not ad.card.usable:
                continue
            tfs = getattr(ad, "timeframes", None)   # marcos para los que el bot está definido
            if tfs and snapshot.timeframe not in tfs:
                continue
            try:
                sigs = ad.signals(snapshot)
            except Exception as exc:  # noqa: BLE001 - un bot roto no tumba el ciclo
                ver = f"{ad.card.commit_sha}+{params_hash({})}"
                sigs = [empty_signal(ad.card, "*", ver, snapshot, "degraded",
                                     f"error del adaptador: {type(exc).__name__}: {exc}")]
            out.extend(self._seal(s) for s in sigs)
        return out

    def _seal(self, sig: BotSignal) -> BotSignal:
        """Marca el cambio de versión y guarda (solo añadir). Nunca lanza."""
        if self.store is None:
            return sig
        try:
            prev = self.store.last_version(sig.bot_id, sig.strategy, sig.symbol, sig.timeframe,
                                           sig.asof)
            if prev is not None and prev != sig.version:
                (psha, ph), (nsha, nh) = split_version(prev), split_version(sig.version)
                sig = _note(sig, f"{VERSION_CHANGED}: {psha[:12]}+{ph} → {nsha[:12]}+{nh}")
            self.store.append(sig, self.clock())
        except Exception as exc:  # noqa: BLE001
            log.warning("no se pudo guardar la señal de %s/%s: %s", sig.bot_id, sig.strategy, exc)
            sig = _note(sig, f"{NOT_SAVED}: {type(exc).__name__}: {exc}")
        return sig

    def attach(self, snapshot: MarketSnapshot) -> MarketSnapshot:
        """Snapshot con `bot_signals` (None si no hay ningún bot utilizable)."""
        sigs = self.produce(snapshot)
        return snapshot.model_copy(update={"bot_signals": sigs or None})


def default_service(data_dir: Path, store: BotSignalStore | None) -> BotService:
    """Modo A siempre; modo B (Freqtrade) solo si el entorno aparte está configurado y fijado."""
    from eim.bots.hb_directional import HummingbotDirectionalAdapter

    adapters: list[SignalAdapter] = [HummingbotDirectionalAdapter()]
    py, engine = os.environ.get(FT_PY_ENV), os.environ.get(FT_ENGINE_ENV)
    checkout = Path(data_dir) / "bots" / "freqtrade-strategies"
    if py and engine and checkout.exists():
        from eim.bots.ft_adapter import FreqtradeAdapter

        adapters.append(FreqtradeAdapter(Path(py), checkout, engine))
    return BotService(adapters, store)
