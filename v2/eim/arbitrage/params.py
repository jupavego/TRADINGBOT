"""Parámetros del motor de arbitraje (sin números mágicos en las estrategias).

Los marcados «T43» se fijaron con el backtest de `reports/arbitrage_edge.md` (2023-01 →
2026-10, BTC y ETH, VIP 0): no con intuición. Para repetirlo: `python -m eim.arbitrage.sim run`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from eim.core.arbitrage import StrategyId

# T43: la base perpetuo/trimestral perdió en el backtest (−12 pb por operación; el funding
# realizado del perpetuo superó al extrapolado): se informa pero no se elige.
PERP_QUARTERLY_VARIANTS = ("corto perpetuo / largo trimestral",
                           "largo perpetuo / corto trimestral")


class ArbParams(BaseModel):
    """Supuestos configurables. Los riesgos son puntuaciones heurísticas 0..1 (ver `risk.py`)."""

    model_config = ConfigDict(frozen=True)

    assets: tuple[str, ...] = ("BTC", "ETH")
    notional_usd: float = Field(default=10_000.0, gt=0)  # nocional por oportunidad
    # T43: 2160 h (90 d) rinde más que 24/72/168/720 h (a 24 h el carry nunca cubre costos).
    carry_horizon_h: float = Field(default=2160.0, gt=0)  # tenencia del carry de funding
    related_horizon_h: float = Field(default=24.0, gt=0)  # tenencia USDT-M vs USDC-M
    funding_realized_n: int = Field(default=21, ge=1)  # liquidaciones realizadas (7 d a 8 h)
    # T43: ×3 rindió más que ×1/×2 sin liquidaciones, CON rebalanceo horario de margen.
    perp_leverage: float = Field(default=3.0, ge=1)  # apalancamiento de las patas de futuros
    mmr: float = Field(default=0.005, ge=0, lt=1)  # margen de mantenimiento (tramo bajo)
    daily_move: float = Field(default=0.0514, gt=0)  # T43: p90 |rend. 24 h| (ETH; BTC 3,8 %)
    basis_floor_bps: float = Field(default=10.1, ge=0)  # T43: p90 |Δ base perp−spot| en 90 d
    # Desvío de funding por liquidación al extrapolar tenencias largas; se acumula sin
    # diversificar (los regímenes persisten). T43: p90 |media de 90 − media de 21| = 0,0071 %.
    funding_shock_rate: float = Field(default=0.000071, ge=0)
    quote_ttl_s: int = Field(default=15, ge=1)  # vigencia de un precio de libro
    # Selector
    min_net_bps: float = 2.0  # margen neto mínimo sobre el capital (T43: 0–10 pb indistintos)
    max_liquidity_risk: float = Field(default=0.5, ge=0, le=1)  # fracción del libro visible
    risk_aversion: float = Field(default=0.5, ge=0, le=1)
    risk_weights: dict[str, float] = {"legging": 1.0, "basis": 1.0, "liquidation": 1.0,
                                      "liquidity": 1.0}
    # T33 (alcance aprobado): solo funding/basis; el triangular se informa pero no se elige.
    # T43: USDT-M vs USDC-M No viable (el selector no la tomó nunca en 3,8 años) → fuera.
    selectable: tuple[StrategyId, ...] = ("funding_carry", "basis")
    disabled_variants: tuple[str, ...] = PERP_QUARTERLY_VARIANTS  # no se eligen (T43)


DEFAULT_PARAMS = ArbParams()
