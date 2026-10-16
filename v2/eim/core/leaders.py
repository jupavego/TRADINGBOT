"""Copy trading (T40): líderes, sus posiciones, ejecuciones y funding. I/O en `data/`.

Todo tiempo en ms epoch UTC. Se distingue **cuándo ocurrió** (`t`, hora del exchange) de
**cuándo lo vimos** (`observed_at`, reloj local corregido con el desfase medido frente al
servidor del exchange): `observed_at − t` es la latencia real de la señal. Fuente
automatizada: solo la API pública oficial de Hyperliquid (T33); Binance solo como registro
manual (sin scraping ni endpoints `/bapi`).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import model_validator

from eim.core.market import Frozen

Venue = Literal["hyperliquid", "binance"]
LeaderStatus = Literal["candidate", "watch", "approved", "rejected"]
Origin = Literal["manual", "trades_ws", "vault"]
Side = Literal["long", "short"]
FillAction = Literal["open", "increase", "reduce", "close", "flip"]
# ws = evento en vivo; ws_snapshot = historial que el WS reenvía al suscribirse;
# rest_poll = líder sin WS (consulta periódica); rest_backfill = relleno de un hueco.
Channel = Literal["ws", "ws_snapshot", "rest_poll", "rest_backfill"]

_EVM = re.compile(r"^0x[0-9a-f]{40}$")


def leader_id(venue: str, address: str) -> str:
    return f"{venue}:{address.lower() if venue == 'hyperliquid' else address}"


class Leader(Frozen):
    """Trader a seguir. `status`: candidate (descubierto) → watch (se capturan sus datos) →
    approved/rejected (lo decide T41 con el usuario). `evidence` = cifras del descubrimiento."""

    id: str
    venue: Venue
    address: str  # Hyperliquid: 0x… en minúsculas; Binance: identificador manual del perfil
    label: str = ""
    origin: Origin
    status: LeaderStatus = "candidate"
    discovered_at: int
    source: str
    evidence: dict[str, float | str] = {}

    @model_validator(mode="after")
    def _check(self) -> Leader:
        if self.id != leader_id(self.venue, self.address):
            raise ValueError("id debe ser '<venue>:<address>'")
        if self.venue == "hyperliquid" and not _EVM.match(self.address):
            raise ValueError("dirección Hyperliquid inválida (0x + 40 hex en minúsculas)")
        if self.venue == "binance" and self.origin != "manual":
            raise ValueError("Binance solo admite registro manual (T33)")
        return self

    @property
    def tracked(self) -> bool:
        return self.status in ("watch", "approved")


class LeaderPosition(Frozen):
    """Posición abierta de un líder tal como la reporta el exchange (`t` = hora del estado)."""

    leader_id: str
    address: str
    symbol: str  # moneda del exchange ("BTC", "ETH", "xyz:NVDA")
    side: Side
    size: float  # > 0, unidades base
    entry: float
    leverage: float | None = None
    margin_mode: Literal["cross", "isolated"] | None = None
    liquidation_px: float | None = None
    unrealized_pnl: float | None = None
    margin_used: float | None = None
    t: int
    observed_at: int
    source: str

    @model_validator(mode="after")
    def _check(self) -> LeaderPosition:
        if self.size <= 0 or self.entry <= 0:
            raise ValueError("size y entry deben ser > 0")
        return self

    @property
    def notional(self) -> float:
        return self.size * self.entry


class LeaderFill(Frozen):
    """Ejecución del líder. `side` = lado de la posición afectada (la nueva en open/increase/
    flip; la que se cierra en reduce/close). Posiciones firmadas: > 0 long, < 0 short.
    `fee` < 0 = rebate de maker. `liquidated` = el propio líder fue liquidado. `leverage` =
    el último conocido al recibir la ejecución (las ejecuciones no lo traen)."""

    leader_id: str
    address: str
    symbol: str
    side: Side
    action: FillAction
    size: float  # > 0, unidades base de esta ejecución
    price: float
    start_position: float
    end_position: float
    fee: float
    fee_token: str = "USDC"
    closed_pnl: float = 0.0
    crossed: bool = False  # True = tomador (cruzó el libro)
    liquidated: bool = False
    leverage: float | None = None
    tid: int
    oid: int
    t: int
    observed_at: int
    channel: Channel
    source: str

    @model_validator(mode="after")
    def _check(self) -> LeaderFill:
        if self.size <= 0 or self.price <= 0:
            raise ValueError("size y price deben ser > 0")
        return self

    @property
    def latency_ms(self) -> int:
        return self.observed_at - self.t


class LeaderFunding(Frozen):
    """Pago de funding de una posición: `usdc` < 0 = el líder pagó; `size` firmado."""

    leader_id: str
    address: str
    symbol: str
    usdc: float
    rate: float
    size: float
    t: int
    observed_at: int
    source: str
