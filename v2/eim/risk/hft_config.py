"""Configuración del riesgo del carril HFT (T83): inmutable, versionada como la de T29/T45.

Un cambio de límites es un archivo nuevo en `eim/risk/versions/` (`hft_risk_vN.json`); la versión
y el SHA-256 del archivo quedan en cada `HftDecision`. Solo SIMULADO o TESTNET (REAL o ANALISIS
se rechazan al cargar). Las tasas propias deben quedar con margen bajo los límites reales de
Binance verificados en T77 (`ORDERS` 300/10 s y 1200/min por cuenta, compartidos REST + WS API):
la validación lo exige. El presupuesto de latencia (310 ms p99) es el de
`PLAN/notas/T77_decisiones.md`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eim.risk.config import VERSIONS_DIR

HFT_VERSION = "hft_risk_v1"


class HftRiskConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    description: str = ""
    sha256: str = ""
    allowed_modes: tuple[str, ...] = ("SIMULADO", "TESTNET")
    symbols: tuple[str, ...]
    capital_usd: float = Field(gt=0)               # capital del carril (sin asignador: T46/T86)
    # inventario, exposición y tamaño
    max_position_qty: float = Field(gt=0)          # |posición| si se llenara todo lo vivo + esta
    max_position_notional: float = Field(gt=0)
    max_net_exposure_notional: float = Field(gt=0)  # |posición + compras − ventas vivas + esta|
    max_order_qty: float = Field(gt=0)
    max_order_notional: float = Field(gt=0)
    min_notional_usd: float = Field(ge=0)          # filtro del símbolo (BTCUSDT 50 USDT, T77)
    max_price_dev_bps: float = Field(gt=0)         # precio lejos del mid = error de operación
    max_live_orders: int = Field(ge=1)
    # pérdidas (fracciones de `capital_usd`; resultado neto de comisiones, a precio medio)
    max_session_loss_frac: float = Field(gt=0, lt=1)
    max_hour_loss_frac: float = Field(gt=0, lt=1)
    max_day_loss_frac: float = Field(gt=0, lt=1)
    max_intraday_drawdown_frac: float = Field(gt=0, lt=1)
    max_consecutive_losses: int = Field(ge=1)
    cooldown_ms: int = Field(ge=0)
    # tasas por ventana (propias) y los límites reales del exchange de los que cuelgan
    max_orders_10s: int = Field(ge=1)
    max_orders_60s: int = Field(ge=1)
    max_cancels_10s: int = Field(ge=1)
    max_cancels_60s: int = Field(ge=1)
    exchange_orders_10s: int = Field(ge=1)
    exchange_orders_60s: int = Field(ge=1)
    rate_margin: float = Field(gt=0, le=0.9)       # propias ≤ esto × las del exchange
    reduce_rate_frac: float = Field(gt=0, le=0.95)  # reduce-only: hasta esto × las del exchange
    # datos, reloj, latido y flujo de usuario
    max_book_age_ms: int = Field(gt=0)             # edad del último evento del libro
    max_clock_skew_ms: int = Field(gt=0)           # |reloj del exchange − local|
    deadman_ms: int = Field(gt=0)                  # sin latido de la estrategia → cancelar todo
    exchange_countdown_ms: int = Field(ge=0)       # `countdownCancelAll` en testnet (0 = no)
    # decisiones y presupuesto de latencia (T77)
    decision_ttl_ms: int = Field(gt=0)
    latency_budget_ms: float = Field(gt=0)
    decision_budget_frac: float = Field(gt=0, lt=0.2)  # p99 de decidir + verificar ≤ esto × budget
    # reconciliación
    recon_qty_tolerance: float = Field(gt=0)       # diferencia de posición que ya es divergencia
    recon_max_silence_ms: int = Field(gt=0)        # sin respuesta del exchange → kill-switch

    @model_validator(mode="after")
    def _coherent(self) -> HftRiskConfig:
        if not self.allowed_modes or set(self.allowed_modes) - {"SIMULADO", "TESTNET"}:
            raise ValueError("el carril HFT solo opera en SIMULADO o TESTNET (nunca REAL)")
        own = (("órdenes/10 s", self.max_orders_10s, self.exchange_orders_10s),
               ("órdenes/min", self.max_orders_60s, self.exchange_orders_60s),
               ("cancelaciones/10 s", self.max_cancels_10s, self.exchange_orders_10s),
               ("cancelaciones/min", self.max_cancels_60s, self.exchange_orders_60s))
        for what, mine, ex in own:
            if mine > self.rate_margin * ex:
                raise ValueError(f"{what}: {mine} supera {self.rate_margin:.0%} del límite "
                                 f"real {ex}")
        if self.max_order_qty > self.max_position_qty:
            raise ValueError("max_order_qty no puede superar max_position_qty")
        if self.max_order_notional < self.min_notional_usd:
            raise ValueError("max_order_notional < min_notional_usd: ninguna orden cabría")
        if self.decision_ttl_ms > 10 * self.latency_budget_ms:
            raise ValueError("decision_ttl_ms demasiado largo frente al presupuesto de latencia")
        return self

    @property
    def decision_budget_ms(self) -> float:
        """p99 máximo admitido para decidir y verificar una orden (fracción del presupuesto)."""
        return self.latency_budget_ms * self.decision_budget_frac


def load_hft_config(path: str | Path | None = None, version: str = HFT_VERSION) -> HftRiskConfig:
    p = Path(path) if path is not None else VERSIONS_DIR / f"{version}.json"
    raw = p.read_bytes()
    data = json.loads(raw)
    if data.get("version") != p.stem:
        raise ValueError(f"versión '{data.get('version')}' no coincide con el archivo {p.name}")
    return HftRiskConfig(**data, sha256=hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest())
