"""Parámetros del motor de arbitraje (sin números mágicos en las estrategias)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from eim.core.arbitrage import StrategyId


class ArbParams(BaseModel):
    """Supuestos configurables. Los riesgos son puntuaciones heurísticas 0..1 (ver `risk.py`)."""

    model_config = ConfigDict(frozen=True)

    assets: tuple[str, ...] = ("BTC", "ETH")
    notional_usd: float = Field(default=10_000.0, gt=0)  # nocional por oportunidad
    carry_horizon_h: float = Field(default=24.0, gt=0)  # tenencia del carry de funding
    related_horizon_h: float = Field(default=24.0, gt=0)  # tenencia USDT-M vs USDC-M
    funding_realized_n: int = Field(default=21, ge=1)  # liquidaciones realizadas (7 d a 8 h)
    perp_leverage: float = Field(default=2.0, ge=1)  # apalancamiento de las patas de futuros
    mmr: float = Field(default=0.005, ge=0, lt=1)  # margen de mantenimiento (tramo bajo)
    daily_move: float = Field(default=0.04, gt=0)  # movimiento adverso plausible en 1 día
    basis_floor_bps: float = Field(default=5.0, ge=0)  # cambio de base mínimo considerado
    # Desvío de funding por liquidación al extrapolar tenencias largas (0,01 % = componente
    # de interés base de Binance); se acumula sin diversificar (los regímenes persisten).
    funding_shock_rate: float = Field(default=0.0001, ge=0)
    quote_ttl_s: int = Field(default=15, ge=1)  # vigencia de un precio de libro
    # Selector
    min_net_bps: float = 2.0  # margen neto mínimo sobre el capital
    max_liquidity_risk: float = Field(default=0.5, ge=0, le=1)  # fracción del libro visible
    risk_aversion: float = Field(default=0.5, ge=0, le=1)
    risk_weights: dict[str, float] = {"legging": 1.0, "basis": 1.0, "liquidation": 1.0,
                                      "liquidity": 1.0}
    # T33 (alcance aprobado): solo funding/basis; el triangular se informa pero no se elige.
    selectable: tuple[StrategyId, ...] = ("funding_carry", "basis", "related_perps")


DEFAULT_PARAMS = ArbParams()
