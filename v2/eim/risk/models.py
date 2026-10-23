"""Contratos del motor de riesgo: entrada (plan, cuenta, mercado) y salida (`RiskDecision`).

`Check` y `RiskDecision` viven en `eim/core/authority.py` desde T114 (contrato único de todas
las autoridades); aquí se reexportan para no cambiar ningún import.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from eim.core import Mode
from eim.core.authority import Check, ExitMode, RiskDecision, TradeProposal
from eim.risk.authority import expires_after


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

    def as_proposal(self, source: str, source_version: str, *, max_age_ms: float,
                    exit_mode: ExitMode, confidence: float | None = None, reason: str = "",
                    horizon_ms: int | None = None) -> TradeProposal:
        """El plan como `TradeProposal` de su fuente (T114). Caduca cuando la regla de vigencia
        de la política lo daría por viejo (`max_age_ms`), nunca antes."""
        return TradeProposal(
            proposal_id=self.plan_id, source=source, source_version=source_version,
            symbol=self.symbol, side=self.side, timeframe=self.timeframe,
            horizon_ms=horizon_ms, confidence=confidence, entry=self.entry, stop=self.sl,
            target=self.tp[0] if self.tp else None, reason=reason[:400], data_asof=self.asof,
            expires_at=expires_after(self.asof, max_age_ms), exit_mode=exit_mode,
            mode=self.mode)


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
    event_window: bool = False                   # ventana pre/post-evento sin blackout (T44)
    event_reason: str = ""
    event_pause: bool = False                    # agente `context` (T24): solo añade pausas
    pause_reason: str = ""


__all__ = ["AccountState", "Check", "MarketContext", "PlanRequest", "RiskDecision"]
