"""Contrato único de la autoridad de ejecución (T114): `TradeProposal` → `RiskDecision`.

Toda fuente de señal (plan de los agentes, estrategias del bróker, copia de líderes, arbitraje,
bots…) PROPONE con `TradeProposal`; solo un motor determinista de riesgo registrado en
`eim/risk/authority.py` DECIDE con `RiskDecision`. Una propuesta no tiene cantidad, apalancamiento
ni claves (`extra="forbid"`): como mucho pide una fracción máxima de riesgo. La cantidad la pone
la autoridad. El objetivo es siempre una estimación, nunca una orden.

`RiskDecision` y `Check` nacieron en T29 (`eim/risk/models.py`, que los reexporta); T114 los
trae aquí y les suma, de forma aditiva, la propuesta decidida, la autoridad que decidió, la
versión de los parámetros del perfil y el modo de salida concedido.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eim.core.market import Frozen
from eim.core.mode import Mode

MarketKind = Literal["perp", "spot", "spot_perp"]   # spot_perp = arbitraje de dos patas (T45)
# Modo de salida. Lo pide la fuente y lo concede la autoridad (puede no coincidir):
#   stop_only     solo cierra el stop, inicial o dinámico (escalera de T109)
#   sl_tp_time    SL, TP, BE+ y tiempo de la sombra del bróker (modo «tp»)
#   bracket       SL y TP condicionales colocados antes de la entrada (T30)
#   follow_leader sale cuando sale el líder, con stop de protección (T42)
#   arb_rules     reglas de gestión del arbitraje: neto agotado, vencimiento, tenencia (T45)
#   policy        la fuente no pide modo: lo decide la política
ExitMode = Literal["stop_only", "sl_tp_time", "bracket", "follow_leader", "arb_rules", "policy"]
EXIT_MODES: tuple[str, ...] = ExitMode.__args__  # type: ignore[attr-defined]
TARGET_LABEL = "estimación"


class TradeProposal(Frozen):
    """Lo único que una fuente puede pedir: abrir en un sentido, con su stop y su caducidad.

    Validación solo estructural: una geometría mala (stop del lado equivocado, sin stop) NO se
    rechaza aquí, la veta la autoridad con su motivo (así queda registrada como rechazo).
    Tiempos en ms epoch UTC; `data_asof` = hasta qué dato se decidió la propuesta.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=40)        # id de `eim/risk/authority.SOURCES`
    source_version: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=40)
    market: MarketKind = "perp"
    side: int = Field(ge=-1, le=1)          # +1 largo, −1 corto (spot_perp: +1 = largo spot)
    timeframe: str = Field(min_length=1, max_length=12)
    horizon_ms: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)  # None si la fuente no la da
    entry: float                            # precio de referencia de la entrada
    stop: float | None = None               # None = la fuente no declara stop
    target: float | None = None             # objetivo: SIEMPRE una estimación
    target_label: Literal["estimación"] = TARGET_LABEL
    # fracción máxima del capital que la fuente pide arriesgar (None = la de la política)
    max_risk_frac: float | None = Field(default=None, gt=0, le=1)
    reason: str = Field(default="", max_length=400)
    data_asof: int
    expires_at: int                         # caducidad de la señal: después ya no se decide
    exit_mode: ExitMode = "policy"
    mode: Mode = Mode.SIMULADO

    @model_validator(mode="after")
    def _times(self) -> TradeProposal:
        if self.expires_at < self.data_asof:
            raise ValueError("la propuesta caduca antes del dato que la originó")
        return self


class Check(Frozen):
    """Una regla de la autoridad: si pasó y por qué."""

    rule: str
    ok: bool
    detail: str


class RiskDecision(Frozen):
    """Resultado de una autoridad; siempre se registra. `seal` lo firma el motor (`engine.verify`).

    `size` = cantidad permitida (moneda base); `reasons` = motivos del veto (o del recorte si
    se aprobó); `config_version`/`config_sha256` = política de riesgo; `profile_version` =
    huella de los parámetros del perfil o de la subcuenta (None si la política no tiene perfil).
    """

    approved: bool
    symbol: str
    timeframe: str
    plan_id: str
    side: int
    mode: Mode
    asof: int                                    # instante del plan / de la propuesta
    decided_at: int                              # `MarketContext.now`
    size: float = 0.0                            # cantidad en moneda base
    notional: float = 0.0
    leverage: float = 0.0
    margin: float = 0.0
    risk_amount: float = 0.0                     # pérdida hasta el SL (sin costos)
    risk_frac: float = 0.0
    liquidation_price: float | None = None
    entry: float = 0.0                           # entrada del plan (precio de una LIMIT)
    sized_at: float = 0.0                        # precio actual con el que se dimensionó
    sl: float = 0.0
    tp: tuple[float, ...] = ()
    reasons: tuple[str, ...] = ()                # motivos de veto (o de recorte si aprobado)
    checks: tuple[Check, ...] = ()
    config_version: str
    config_sha256: str
    account_source: str
    seal: str = ""
    # T114 (aditivos): qué se decidió, quién decidió y con qué perfil y salida
    proposal: TradeProposal | None = None
    authority: str = "risk.engine"               # componente del catálogo que decidió
    profile_version: str | None = None
    exit_mode: ExitMode | None = None            # modo de salida concedido

    @property
    def source(self) -> str | None:
        return self.proposal.source if self.proposal else None


def params_fingerprint(m: BaseModel) -> str:
    """Huella de 12 hex de unos parámetros (perfil, subcuenta): otro valor = otra versión."""
    return hashlib.sha256(m.model_dump_json().encode("utf-8")).hexdigest()[:12]
