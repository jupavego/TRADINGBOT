"""Contrato `Broker`: la misma interfaz para el simulador (`SimBroker`) y la testnet de Binance.

Un `Broker` solo traduce órdenes al exchange; no decide nada. Quién puede abrir posición lo
controla `ExecutionService.place`, al que solo llama `OrderGateway` tras verificar la
`RiskDecision`. SL y TP son órdenes condicionales `close_position` (cierre total, solo reducen
posición): se colocan ANTES de la entrada, así cualquier fill —parcial o total— nace protegido.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from eim.core import Mode

CLIENT_PREFIX = "eim-"
ARB_PREFIX = "eia-"       # T45: patas de arbitraje (la reconciliación T30 no las toca)
HFT_PREFIX = "eih-"       # T83: órdenes del carril HFT (tampoco las toca la reconciliación T30)
# tipos de orden
MARKET, LIMIT, STOP, TAKE_PROFIT = "MARKET", "LIMIT", "STOP", "TAKE_PROFIT"
CONDITIONAL = (STOP, TAKE_PROFIT)
GTX = "GTX"               # T83: post-only (el exchange la rechaza si casaría como taker)
# estados
NEW, PARTIAL, FILLED = "NEW", "PARTIALLY_FILLED", "FILLED"
CANCELED, REJECTED, EXPIRED, TRIGGERED = "CANCELED", "REJECTED", "EXPIRED", "TRIGGERED"
OPEN_STATUSES = (NEW, PARTIAL)


class BrokerError(RuntimeError):
    """Fallo del broker sin ambigüedad (configuración, cuenta, símbolo)."""


class OrderRejected(BrokerError):
    """El exchange rechazó la orden: no existe y reintentarla igual no sirve."""

    def __init__(self, msg: str, code: int | None = None, duplicate: bool = False) -> None:
        super().__init__(f"rechazada ({code}): {msg}" if code is not None else msg)
        self.code, self.duplicate = code, duplicate


class NetworkError(BrokerError):
    """Resultado desconocido (timeout, desconexión, 5xx): la orden pudo llegar o no."""


class RateLimited(NetworkError):
    """T83: límite de tasa del exchange (HTTP 429) o IP bloqueada (418). Hasta `until` (ms) no
    se envía nada: insistir convierte un 429 en un 418 (bloqueo de 2 min a 3 días)."""

    def __init__(self, msg: str, status: int, until: int) -> None:
        super().__init__(msg)
        self.status, self.until = status, until

    @property
    def banned(self) -> bool:
        return self.status == 418


@dataclass(frozen=True)
class OrderSpec:
    client_id: str
    symbol: str
    side: int                        # +1 compra, −1 venta
    kind: str                        # MARKET | LIMIT | STOP | TAKE_PROFIT
    qty: float | None = None         # None con close_position
    price: float | None = None       # LIMIT
    trigger: float | None = None     # STOP / TAKE_PROFIT
    reduce_only: bool = False
    close_position: bool = False
    tif: str = "GTC"                 # LIMIT: GTC | IOC (T45) | GTX post-only (T83)

    @property
    def conditional(self) -> bool:
        return self.kind in CONDITIONAL


@dataclass(frozen=True)
class OrderState:
    client_id: str
    symbol: str
    side: int
    kind: str
    status: str
    qty: float | None
    filled: float = 0.0
    avg_price: float | None = None
    trigger: float | None = None
    close_position: bool = False
    reduce_only: bool = False
    exchange_id: str = ""
    fee: float = 0.0                 # comisión cobrada (spot: puede ir en la moneda base)
    fee_asset: str = ""

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def conditional(self) -> bool:
        return self.kind in CONDITIONAL


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float                       # con signo: + largo, − corto, 0 plano
    entry_price: float | None = None


class Broker(Protocol):
    mode: Mode

    def prepare(self, symbol: str, leverage: int) -> None:
        """Margen aislado, apalancamiento y modo de posición única (one-way)."""

    def round_qty(self, symbol: str, qty: float) -> float:
        """Redondea HACIA ABAJO al paso del símbolo (0 si no llega al mínimo)."""

    def round_price(self, symbol: str, price: float) -> float: ...

    def post_order(self, spec: OrderSpec) -> OrderState: ...

    def get_order(self, symbol: str, client_id: str, conditional: bool) -> OrderState | None:
        """None si el exchange confirma que no existe."""

    def cancel(self, symbol: str, client_id: str, conditional: bool) -> None:
        """Idempotente: cancelar una orden inexistente o ya cerrada no es error."""

    def open_orders(self, symbol: str) -> list[OrderState]:
        """Órdenes abiertas (normales y condicionales) del símbolo."""

    def position(self, symbol: str) -> Position: ...

    def equity(self) -> float: ...


def client_id(plan_id: str, symbol: str, role: str, prefix: str = CLIENT_PREFIX) -> str:
    """Id determinista por (plan, rol): reenviar la misma orden nunca crea otra distinta.

    role: e entrada · s SL · t TP · x cierre · s2.. SL de reparación. Patrón Binance
    `^[.A-Z:/a-z0-9_-]{1,36}$`.
    """
    h = hashlib.sha256(f"{symbol}|{plan_id}".encode()).hexdigest()[:20]
    return f"{prefix}{h}-{role}"


def trade_key(cid: str) -> str:
    """Parte común de los ids de una operación (sin el rol)."""
    return cid.rsplit("-", 1)[0]
