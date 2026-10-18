"""Configuración del riesgo de arbitraje (T45): inmutable, versionada como la de T29.

Un cambio de límites es un archivo nuevo en `eim/risk/versions/` (`risk_arb_vN.json`); la
versión y el SHA-256 del archivo quedan en cada `ArbDecision`. El arbitraje corre en TESTNET
(`risk_arb_v1`) o en el bróker simulado (`risk_arb_sim_v1`); REAL o ANALISIS se rechazan al cargar.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eim.core.arbitrage import StrategyId
from eim.risk.config import VERSIONS_DIR

ARB_VERSION = "risk_arb_v1"


class ArbRiskConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    description: str = ""
    sha256: str = ""
    allowed_modes: tuple[str, ...] = ("TESTNET",)
    strategies: tuple[StrategyId, ...]           # Viable o Marginal en T43
    max_notional_usd: float = Field(gt=0)        # por arbitraje
    max_open_arbs: int = Field(ge=0)
    max_per_asset: int = Field(ge=0)
    max_leverage: int = Field(ge=1, le=5)
    mmr: float = Field(ge=0, lt=0.1)
    min_liq_move: float = Field(gt=0, lt=1)      # movimiento hasta la liquidación del futuro
    max_margin_frac: float = Field(gt=0, le=1)   # margen total en uso ≤ esto × capital futuros
    max_gross_frac: float = Field(gt=0, le=10)   # exposición bruta total ≤ esto × capital
    max_quote_age_ms: int = Field(gt=0)
    min_net_bps: float
    max_leg_loss_bps: float = Field(gt=0, le=500)  # tope por pata incompleta (pb del nocional)
    max_incident_loss_frac: float = Field(gt=0, lt=0.1)
    max_daily_loss: float = Field(gt=0, lt=1)
    spot_cash_buffer: float = Field(ge=1, le=1.2)
    # gestión de posiciones abiertas
    rebalance_frac: float = Field(gt=0, lt=1)    # margen del corto ≤ esto × objetivo → rebalanceo
    close_liq_move: float = Field(gt=0, lt=1)    # tras rebalancear, liquidación más cerca → cierre
    negative_funding_n: int = Field(ge=1)        # lecturas seguidas con funding < 0 → cierre
    exit_before_delivery_ms: int = Field(ge=0)   # base: cerrar antes del vencimiento
    max_hedge_residual_frac: float = Field(gt=0, lt=1)  # descubierto tolerado (polvo)
    kill_max_disconnect_ms: int = Field(gt=0)    # sin respuesta del exchange → kill-switch

    @model_validator(mode="after")
    def _coherent(self) -> ArbRiskConfig:
        if not self.allowed_modes or set(self.allowed_modes) - {"TESTNET", "SIMULADO"}:
            raise ValueError("el arbitraje solo se ejecuta en TESTNET o SIMULADO (nunca REAL)")
        if self.close_liq_move >= self.min_liq_move:
            raise ValueError("close_liq_move debe ser < min_liq_move")
        return self


def load_arb_config(path: str | Path | None = None, version: str = ARB_VERSION) -> ArbRiskConfig:
    p = Path(path) if path is not None else VERSIONS_DIR / f"{version}.json"
    raw = p.read_bytes()
    data = json.loads(raw)
    if data.get("version") != p.stem:
        raise ValueError(f"versión '{data.get('version')}' no coincide con el archivo {p.name}")
    return ArbRiskConfig(**data, sha256=hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest())
