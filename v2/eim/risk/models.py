"""Contratos del motor de riesgo: entrada (plan, cuenta, mercado) y salida (`RiskDecision`)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from eim.core import Mode


class PlanRequest(BaseModel):
    """Plan a dimensionar (del agente `plan`, T13). Sin tamaño: lo decide el motor."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    plan_id: str
    side: int = Field(ge=-1, le=1)     # +1 largo, −1 corto (0 se veta)
    entry: float
    sl: float
    tp: tuple[float, ...] = ()
    rr: float | None = None
    mode: Mode = Mode.SIMULADO
    asof: int                          # ms: instante del plan


class AccountState(BaseModel):
    """Estado de la cuenta al decidir. `source` dice de dónde sale (libro simulado, testnet…)."""

    model_config = ConfigDict(frozen=True)

    equity: float
    day_start_equity: float
    week_start_equity: float
    peak_equity: float
    open_symbols: tuple[str, ...] = ()           # una entrada por posición abierta
    consecutive_losses: int = 0
    last_loss_t: int | None = None
    source: str = "desconocida"


class MarketContext(BaseModel):
    """Calidad de datos y ventanas de evento en el instante de decidir."""

    model_config = ConfigDict(frozen=True)

    now: int                                     # ms
    bar_ms: int
    last_close_t: int | None                     # ms de cierre de la última vela cerrada
    last_price: float | None = None              # precio actual: el tamaño se calcula aquí
    agent_status: dict[str, str] = {}            # agent_id → ok | degraded | no_data
    blackout: bool = False                       # agente `calendar` (T36/T37)
    blackout_reason: str = ""
    event_pause: bool = False                    # agente `context` (T24): solo añade pausas
    pause_reason: str = ""


class Check(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule: str
    ok: bool
    detail: str


class RiskDecision(BaseModel):
    """Resultado del motor; siempre se registra. `seal` lo firma el motor (ver `engine.verify`)."""

    model_config = ConfigDict(frozen=True)

    approved: bool
    symbol: str
    timeframe: str
    plan_id: str
    side: int
    mode: Mode
    asof: int                                    # instante del plan
    decided_at: int                              # `MarketContext.now`
    size: float = 0.0                            # cantidad en moneda base
    notional: float = 0.0
    leverage: float = 0.0
    margin: float = 0.0
    risk_amount: float = 0.0                     # pérdida hasta el SL (sin costos)
    risk_frac: float = 0.0
    liquidation_price: float | None = None
    reasons: tuple[str, ...] = ()                # motivos de veto (o de recorte si aprobado)
    checks: tuple[Check, ...] = ()
    config_version: str
    config_sha256: str
    account_source: str
    seal: str = ""
