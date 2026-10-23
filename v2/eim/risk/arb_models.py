"""Contratos del riesgo de arbitraje (T45): plan de dos patas, cuenta total y decisión sellada.

El plan sale de una oportunidad del motor T38 (`eim/arbitrage/live/plan.py`); el motor de
riesgo lo dimensiona o lo veta (`arb_engine.py`) y solo una `ArbDecision` aprobada y sellada
llega al ejecutor por `ArbGateway` (`eim/execution/gateway.py`).

T114: el plan entra como `TradeProposal` (`ArbPlan.as_proposal`, mercado `spot_perp`, sin stop:
el riesgo de un arbitraje neutro es la pata incompleta y la liquidación, que veta este motor) y
`ArbDecision.as_record()` lo proyecta al contrato único `RiskDecision` para registrarlo.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from eim.core import Mode
from eim.core.arbitrage import StrategyId
from eim.core.authority import RiskDecision, TradeProposal
from eim.core.market import Frozen
from eim.risk.models import Check


class ArbLegPlan(Frozen):
    market: Literal["spot", "usdm"]
    symbol: str
    side: int = Field(ge=-1, le=1)   # +1 compra, −1 venta (al abrir)
    ref_price: float = Field(gt=0)   # VWAP estimado por el escáner (mercado real de Binance)
    depth_frac: float = Field(ge=0)  # fracción del libro visible que consume (orden de envío)


class ArbPlan(Frozen):
    """Dos patas en orden de envío: la menos líquida primero."""

    arb_id: str
    strategy: StrategyId
    variant: str
    asset: str
    legs: tuple[ArbLegPlan, ArbLegPlan]
    qty: float = Field(gt=0)         # cantidad base propuesta (nocional del escáner)
    notional: float = Field(gt=0)    # qty × precio spot de referencia
    leverage: int = Field(ge=1)
    net_edge: float                  # USD para `qty` (neto estimado, no garantizado)
    net_bps: float
    score: float                     # pb/día ajustados por riesgo (selector T38)
    annualized: float | None = None
    horizon_h: float
    funding_rate: float | None = None   # funding esperado por liquidación (carry)
    interval_h: float | None = None
    delivery_t: int | None = None       # vencimiento del trimestral (base)
    exit_cost_bps: float = 0.0          # costo estimado de salida (comisión + deslizamiento)
    asof: int
    valid_until: int
    source: str
    mode: Mode = Mode.TESTNET

    @property
    def key(self) -> str:
        """Una posición a la vez por estrategia y activo."""
        return f"{self.strategy}:{self.asset}"

    @property
    def futures(self) -> ArbLegPlan:
        return next(lg for lg in self.legs if lg.market == "usdm")

    @property
    def spot(self) -> ArbLegPlan:
        return next(lg for lg in self.legs if lg.market == "spot")

    def as_proposal(self, source: str, source_version: str) -> TradeProposal:
        """El plan como `TradeProposal` (largo spot / corto perpetuo = lado +1)."""
        return TradeProposal(
            proposal_id=self.arb_id, source=source, source_version=source_version,
            symbol=self.futures.symbol, market="spot_perp", side=self.spot.side,
            timeframe="arb", horizon_ms=int(self.horizon_h * 3_600_000), entry=self.spot.ref_price,
            reason=f"{self.strategy} · {self.variant}: neto estimado {self.net_bps:.1f} pb "
                   "(no garantizado)", data_asof=self.asof,
            expires_at=max(self.valid_until, self.asof), exit_mode="arb_rules", mode=self.mode)


class ArbAccount(Frozen):
    """Cuenta al decidir. Margen y exposición son los de TODA la cuenta (direccional incluido)."""

    equity: float                    # futuros + USDT spot + spot de arbitrajes a mercado
    day_start_equity: float
    futures_equity: float
    futures_available: float
    spot_quote_free: float
    initial_margin: float            # margen inicial en uso en futuros (todas las posiciones)
    gross_exposure: float            # nocional bruto: futuros + patas spot de arbitrajes
    open_arbs: tuple[str, ...] = ()  # `ArbPlan.key` de los abiertos
    directional_symbols: tuple[str, ...] = ()  # operaciones direccionales activas (T30)
    source: str = "desconocida"


class ArbDecision(Frozen):
    approved: bool
    plan: ArbPlan
    mode: Mode
    decided_at: int
    qty: float = 0.0                 # cantidad aprobada (≤ la propuesta)
    notional: float = 0.0
    margin: float = 0.0              # margen de la pata de futuros
    leverage: int = 0
    max_leg_loss: float = 0.0        # USD: tope de pérdida por pata incompleta
    max_leg_loss_bps: float = 0.0
    reasons: tuple[str, ...] = ()    # motivos de veto (o de recorte si aprobado)
    checks: tuple[Check, ...] = ()
    config_version: str
    config_sha256: str
    account_source: str
    seal: str = ""
    proposal: TradeProposal | None = None      # T114: lo propuesto (ruta registrada)

    def as_record(self) -> RiskDecision:
        """Proyección al contrato único (registro y Observatorio); la que se ejecuta es esta."""
        p = self.plan
        return RiskDecision(
            approved=self.approved, symbol=p.futures.symbol, timeframe="arb", plan_id=p.arb_id,
            side=p.spot.side, mode=self.mode, asof=p.asof, decided_at=self.decided_at,
            size=self.qty, notional=self.notional, leverage=float(self.leverage),
            margin=self.margin, entry=p.spot.ref_price, sized_at=p.spot.ref_price,
            reasons=self.reasons, checks=self.checks, config_version=self.config_version,
            config_sha256=self.config_sha256, account_source=self.account_source,
            seal=self.seal, proposal=self.proposal, authority="risk.arb_engine",
            exit_mode="arb_rules")
