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
from eim.bots.quarantine import Quarantine
from eim.core import NOT_SAVED, VERSION_CHANGED, BotSignal, MarketSnapshot
from eim.data.bots.store import BotSignalStore
from eim.observability import hooks_service
from eim.synthesis.squad import current_policy

log = logging.getLogger("eim.bots")
FT_PY_ENV = "EIM_BOT_FREQTRADE_PY"          # intérprete del entorno aparte de Freqtrade
FT_ENGINE_ENV = "EIM_BOT_FREQTRADE_ENGINE"  # versión del motor fijada (p. ej. «2026.9»)


def _note(sig: BotSignal, note: str) -> BotSignal:
    q = sig.data_quality.model_copy(update={"notes": [*sig.data_quality.notes, note]})
    return sig.model_copy(update={"data_quality": q})


class BotService:
    def __init__(self, adapters: Sequence[SignalAdapter], store: BotSignalStore | None = None,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000),
                 quarantine: Quarantine | None = None) -> None:
        self.adapters, self.store, self.clock = list(adapters), store, clock
        self.quarantine = quarantine   # T60: un bot que vota y se degrada pierde el voto

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
        self._watch(out)
        return out

    def _watch(self, sigs: Sequence[BotSignal]) -> None:
        """Latido y alerta (T31); cuarentena de los bots que votan y salen degradados (T60)."""
        bad = [s for s in sigs if s.status == "degraded"]
        for s in bad:
            hooks_service.service_error(f"bots.{s.bot_id}", "; ".join(s.evidence) or "degradado")
        hooks_service.beat("bots.service", status="degraded" if bad else "ok",
                           detail={"signals": len(sigs), "degraded": len(bad)})
        pol = current_policy()
        if self.quarantine is None or pol is None:
            return
        for s in bad:
            for b in pol.voters:
                if b.bot_id == s.bot_id and s.strategy in ("*", b.strategy):
                    self.quarantine.trip(b.key, "; ".join(s.evidence) or "degradado", self.clock())

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
    from eim.bots.jesse_examples import JesseExamplesAdapter
    from eim.bots.trendrider import TrendRiderAdapter

    # Jesse y TrendRider piden 1000 y 5400 velas de 1 h: con menos en el snapshot dan `no_data`
    adapters: list[SignalAdapter] = [HummingbotDirectionalAdapter(), JesseExamplesAdapter(),
                                     TrendRiderAdapter()]
    py, engine = os.environ.get(FT_PY_ENV), os.environ.get(FT_ENGINE_ENV)
    checkout = Path(data_dir) / "bots" / "freqtrade-strategies"
    if py and engine and checkout.exists():
        from eim.bots.ft_adapter import FreqtradeAdapter

        adapters.append(FreqtradeAdapter(Path(py), checkout, engine))
    return BotService(adapters, store, quarantine=Quarantine(Path(data_dir) / "bots"))
