"""Adaptador de bots (T57): protocolo único y utilidades para construir `BotSignal`.

Modo A = función pura sobre el snapshot (lógica portada). Modo B = proceso aislado
(`eim/data/bots/runner.py`). En ambos casos el adaptador **solo devuelve posturas**: jamás órdenes.
Un adaptador no lanza excepciones hacia el servicio: falla ⇒ señal `degraded` con postura 0.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from eim.bots.card import BotCard
from eim.core import BotQuality, BotSignal, MarketSnapshot
from eim.data.timeframes import tf_ms


@runtime_checkable
class SignalAdapter(Protocol):
    """Convierte lo que un bot opina sobre las velas del snapshot en `BotSignal`s."""

    bot_id: str
    card: BotCard

    def signals(self, snapshot: MarketSnapshot) -> list[BotSignal]: ...


def params_hash(params: Mapping) -> str:
    """12 hex del SHA-256 de los parámetros en JSON canónico (orden de claves irrelevante)."""
    raw = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def version_of(sha: str, params: Mapping) -> str:
    """Versión de un bot = SHA fijado + hash de parámetros: cambiar cualquiera crea otra."""
    return f"{sha}+{params_hash(params)}"


def split_version(version: str) -> tuple[str, str]:
    """(SHA del bot, hash de parámetros) de una versión `<sha>+<hash>`."""
    sha, _, phash = version.partition("+")
    return sha, phash


def quality_of(snapshot: MarketSnapshot, needed: int, *notes: str) -> BotQuality:
    """Cobertura real: velas disponibles frente a las que pide el bot."""
    cs = snapshot.candles
    cov = min(1.0, len(cs) / needed) if needed > 0 else None
    return BotQuality(
        bars=len(cs), last_candle_t=cs[-1].t if cs else None,
        source=snapshot.sources.get("candles", "desconocida"), coverage=cov, notes=list(notes))


def empty_signal(card: BotCard, strategy: str, version: str, snapshot: MarketSnapshot,
                 status: str, reason: str, needed: int = 0, raw: dict | None = None) -> BotSignal:
    """Señal sin postura (`no_data` o `degraded`): stance 0 y sin confianza; dice por qué."""
    return BotSignal(
        bot_id=card.id, strategy=strategy, version=version, asof=snapshot.asof,
        timeframe=snapshot.timeframe, symbol=snapshot.symbol, stance=0.0, confidence=None,
        evidence=[reason], raw=raw or {}, data_quality=quality_of(snapshot, needed, reason),
        status=status)  # type: ignore[arg-type]


def closed_candles_only(snapshot: MarketSnapshot) -> bool:
    """Garantía de punto en el tiempo: la última vela cerrada termina a más tardar en `asof`."""
    cs = snapshot.candles
    return not cs or cs[-1].t + tf_ms(snapshot.timeframe) <= snapshot.asof
