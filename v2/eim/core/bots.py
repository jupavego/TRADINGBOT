"""Contrato del módulo de bots (T57): lo único que un bot puede decir es una postura.

`BotSignal` no tiene campos de orden, tamaño, apalancamiento ni claves, y `extra="forbid"` rechaza
cualquier otro: un bot no puede pedir operar. Lo que se haga con la postura lo decide el motor de
riesgo (código determinista con veto), nunca el bot.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from eim.core.market import Frozen

BotStatus = Literal["ok", "degraded", "no_data"]
# `<SHA completo del bot>+<hash de 12 hex de los parámetros>`: otro SHA o parámetros = otra versión.
VERSION_PATTERN = r"^[0-9a-f]{40}\+[0-9a-f]{12}$"
# Nota que el servicio añade a `data_quality.notes` si la versión difiere de la última guardada.
VERSION_CHANGED = "version_changed"
NOT_SAVED = "no_guardada"  # …o si no se pudo guardar en `bot_signals` (el agente lo avisa)


class BotInvalidation(Frozen):
    """Condición que anula la postura (si el bot la da; no se inventa)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: float | None = None
    condition: str


class BotQuality(Frozen):
    """Cobertura real de los datos con que se calculó la postura."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bars: int = Field(ge=0)
    last_candle_t: int | None = None  # apertura de la última vela usada (nunca posterior a `asof`)
    source: str = "desconocida"
    coverage: float | None = Field(default=None, ge=0, le=1)  # velas usadas / velas que pide el bot
    notes: list[str] = []


class BotSignal(Frozen):
    """Postura deseada de un bot sobre un símbolo y marco, a `asof` (ms epoch UTC).

    `stance` ∈ [−1, +1]: 0 = plano (no «sin información»: eso es `status="no_data"`).
    `confidence` es None si el bot no la da (no se inventa). `raw` conserva lo que el bot emitió.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bot_id: str
    strategy: str
    version: str = Field(pattern=VERSION_PATTERN)
    asof: int
    timeframe: str
    symbol: str
    stance: float = Field(ge=-1, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    horizon_bars: int | None = Field(default=None, ge=1)
    invalidation: BotInvalidation | None = None
    evidence: list[str] = []
    costs_assumed: dict[str, float] | None = None
    raw: dict = {}
    data_quality: BotQuality
    status: BotStatus = "ok"

    @model_validator(mode="after")
    def _point_in_time(self) -> BotSignal:
        t = self.data_quality.last_candle_t
        if t is not None and t > self.asof:
            raise ValueError("la señal usa una vela posterior a su asof")
        if self.status == "no_data" and (self.stance != 0 or self.confidence is not None):
            raise ValueError("sin datos: postura 0 y sin confianza")
        return self
