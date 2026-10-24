"""Contratos del riesgo del carril HFT (T83): orden pedida, mercado, cuenta y decisión sellada.

Una estrategia (T82, aún sin construir) PIDE una orden concreta con `HftOrder` (sin poder sobre
el tamaño máximo: lo acota el motor); `HftRiskEngine` la aprueba o la veta con una `HftDecision`
sellada (HMAC de proceso, el mismo de T29) que nombra la regla que la causó; solo una decisión
aprobada, sellada y vigente llega al ejecutor por `HftGateway` (`eim/execution/gateway.py`), y
la orden que se envía sale de la decisión (no se puede alterar después).

`HftMarket` y `HftAccount` son fotografías baratas (dataclasses) que se arman en cada decisión:
el coste de decidir cuenta contra el presupuesto de latencia de T77. `HftDecision.as_record()`
la proyecta al contrato único `RiskDecision` (T114) para el registro y el Observatorio.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from eim.core import Mode
from eim.core.authority import RiskDecision
from eim.core.market import Frozen
from eim.execution.broker import HFT_PREFIX
from eim.risk.models import Check

AUTHORITY = "risk.hft_engine"
SOURCE = "hft.micro"                       # fuente registrada en `eim/risk/authority.py`
Purpose = Literal["quote", "take", "exit", "flatten"]


class HftOrder(Frozen):
    """Una orden concreta pedida por la estrategia. `quote` = GTX post-only; `take` = IOC (solo
    desde 60 s de horizonte, T77); `exit` = reduce-only pasiva; `flatten` = reduce-only a mercado
    (la usa el propio carril para cerrar inventario ante un kill-switch)."""

    order_id: str = Field(min_length=1, max_length=120)   # único por estrategia
    source: str = SOURCE
    source_version: str = Field(min_length=1, max_length=120)
    symbol: str
    side: int = Field(ge=-1, le=1)
    qty: float
    kind: Literal["LIMIT", "MARKET"] = "LIMIT"
    price: float | None = None
    tif: Literal["GTX", "IOC", "GTC"] = "GTX"
    reduce_only: bool = False
    purpose: Purpose = "quote"
    mode: Mode = Mode.SIMULADO
    asof: int                              # ms del dato con el que se decidió la orden
    expires_at: int


@dataclass(frozen=True, slots=True)
class HftMarket:
    """Libro y reloj al decidir. `book_E` = hora del exchange del último evento aplicado;
    `book_recv` = hora local de su llegada; `clock_offset_ms` = exchange − local (None = sin
    medir). `book_synced` = libro verificado sin hueco de secuencia (`pu`) pendiente."""

    symbol: str
    best_bid: float | None
    best_ask: float | None
    book_E: int | None
    book_recv: int | None
    book_synced: bool
    clock_offset_ms: float | None
    book_issue: str = ""
    source: str = "desconocida"

    @property
    def mid(self) -> float | None:
        if self.best_bid and self.best_ask and self.best_ask >= self.best_bid > 0:
            return (self.best_bid + self.best_ask) / 2
        return None

    def book_age_ms(self, now: int) -> float:
        """Edad del libro: la peor de la hora local de llegada y la del exchange (corregida)."""
        if self.book_E is None or self.book_recv is None:
            return math.inf
        return max(now - self.book_recv, now + (self.clock_offset_ms or 0.0) - self.book_E)


@dataclass(frozen=True, slots=True)
class HftAccount:
    """Cuenta del carril al decidir (de `HftLedger`): posición, órdenes vivas, resultado neto y
    tasas por ventana. Las pérdidas en USD (negativas = pérdida)."""

    position: float = 0.0
    live_buy_qty: float = 0.0              # resto sin llenar de las compras vivas
    live_sell_qty: float = 0.0
    live_orders: int = 0
    pnl_session: float = 0.0
    pnl_hour: float = 0.0
    pnl_day: float = 0.0
    drawdown_day: float = 0.0              # USD desde el máximo del día (≥ 0)
    consecutive_losses: int = 0
    last_loss_t: int | None = None
    orders_10s: int = 0
    orders_60s: int = 0
    cancels_10s: int = 0
    cancels_60s: int = 0
    rate_limited_until: int | None = None
    banned: bool = False                   # 418: IP bloqueada por el exchange
    heartbeat_t: int | None = None         # último latido de la estrategia
    user_stream_ok: bool = True            # flujo de usuario conectado (fills por evento)
    source: str = "desconocida"


def hft_client_id(order_id: str, symbol: str) -> str:
    """Id de cliente determinista por orden: reenviar la misma decisión nunca crea otra orden.
    Patrón de Binance `^[.A-Z:/a-z0-9_-]{1,36}$` (`eih-` + 24 hex = 28)."""
    return HFT_PREFIX + hashlib.sha256(f"{symbol}|{order_id}".encode()).hexdigest()[:24]


class HftDecision(Frozen):
    approved: bool
    order: HftOrder
    mode: Mode
    decided_at: int
    client_id: str
    notional: float = 0.0
    reducing: bool = False                 # reduce de verdad: pasa con bloqueos y kill-switch
    rule: str = ""                         # regla que la vetó (la primera); "" si aprobada
    reasons: tuple[str, ...] = ()
    checks: tuple[Check, ...] = ()
    config_version: str
    config_sha256: str
    account_source: str
    seal: str = ""

    def as_record(self) -> RiskDecision:
        """Proyección al contrato único (registro y Observatorio); la que se ejecuta es esta."""
        o = self.order
        return RiskDecision(
            approved=self.approved, symbol=o.symbol, timeframe="hft", plan_id=o.order_id,
            side=o.side, mode=self.mode, asof=o.asof, decided_at=self.decided_at,
            size=o.qty if self.approved else 0.0, notional=self.notional, entry=o.price or 0.0,
            reasons=self.reasons, checks=self.checks, config_version=self.config_version,
            config_sha256=self.config_sha256, account_source=self.account_source,
            seal=self.seal, authority=AUTHORITY, exit_mode="hft_rules")
