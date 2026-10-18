"""Libro de posiciones de arbitraje (T45): patas, órdenes y resultado. Serializable a JSON.

Cada orden se anota ANTES de enviarse (estado `ENVIANDO`): si el proceso cae o la red se corta a
mitad, la reconciliación sabe qué ids consultar. Los fills se aplican por diferencia
(`applied`), así releer una orden nunca cuenta dos veces lo mismo. Cantidades en moneda base,
con signo (+ largo, − corto); `cash` = flujo en USDT de la pata (− al comprar, + al vender), de
modo que el resultado de una pata es `cash + held × precio`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from eim.execution.broker import ARB_PREFIX, OrderState, client_id, trade_key

PENDING, OPEN, CLOSING, CLOSED, FAILED = "PENDIENTE", "ABIERTA", "CERRANDO", "CERRADA", "FALLIDA"
UNHEDGED = "DESCUBIERTA"           # una pata sin su cobertura: la reconciliación la corrige
ACTIVE = (PENDING, OPEN, CLOSING, UNHEDGED)
SENDING, UNKNOWN, GONE = "ENVIANDO", "DESCONOCIDO", "NO_EXISTE"
UNSETTLED = (SENDING, UNKNOWN, "NEW", "PARTIALLY_FILLED")


@dataclass
class ArbLeg:
    market: str                       # spot | usdm
    symbol: str
    side: int                         # lado al abrir
    held: float = 0.0                 # cantidad actual con signo
    cash: float = 0.0
    fee_quote: float = 0.0

    def pnl(self, price: float | None) -> float | None:
        return None if price is None else self.cash + self.held * price


@dataclass
class ArbOrder:
    cid: str
    market: str
    symbol: str
    side: int
    qty: float
    price: float | None
    role: str                         # abrir | cubrir | deshacer | cerrar | rebalanceo …
    status: str = SENDING
    filled: float = 0.0
    avg: float | None = None
    fee: float = 0.0
    fee_asset: str = ""
    applied: float = 0.0              # fill ya aplicado a la pata
    fee_applied: float = 0.0          # comisión en moneda base ya aplicada
    fee_quote_applied: float = 0.0    # comisión en USDT ya aplicada
    t: int = 0


@dataclass
class ArbPosition:
    key: str
    arb_id: str
    strategy: str
    variant: str
    asset: str
    leverage: int
    legs: dict[str, ArbLeg]           # por mercado
    order: list[str]                  # mercados en orden de envío (menos líquida primero)
    plan: dict[str, Any]              # `ArbPlan` aprobado (JSON)
    approved_qty: float
    max_leg_loss: float               # USD
    max_leg_loss_bps: float
    status: str = PENDING
    created_at: int = 0
    opened_at: int | None = None
    closed_at: int | None = None
    exit_reason: str = ""
    seq: int = 0
    orders: list[ArbOrder] = field(default_factory=list)
    funding_expected: float = 0.0
    funding_received: float = 0.0
    funding_n: int = 0
    mark: float | None = None         # marca del futuro (testnet)
    spot_px: float | None = None      # precio medio spot (testnet)
    margin_equity: float | None = None
    liq_price: float | None = None
    liq_move: float | None = None
    rebalances: int = 0
    margin_added: float = 0.0
    negative_funding_streak: int = 0
    funding_seen_t: int = 0           # última fotografía del escáner leída (lecturas distintas)
    incident_loss: float = 0.0        # pérdidas por patas incompletas (USD)
    events: list[str] = field(default_factory=list)

    @staticmethod
    def key_of(arb_id: str, fut_symbol: str) -> str:
        return trade_key(client_id(arb_id, fut_symbol, "x", ARB_PREFIX))

    def next_cid(self, tag: str) -> str:
        self.seq += 1
        return f"{self.key}-{tag}{self.seq}"

    @property
    def spot(self) -> ArbLeg:
        return self.legs["spot"]

    @property
    def fut(self) -> ArbLeg:
        return self.legs["usdm"]

    @property
    def hedged(self) -> float:
        """Cantidad cubierta (la menor de las dos patas en sentido opuesto)."""
        s, f = self.spot.held, -self.fut.held
        return max(0.0, min(s, f)) if s * f > 0 else 0.0

    @property
    def residual(self) -> float:
        """Exposición neta (+ sobra spot, − sobra corto)."""
        return round(self.spot.held + self.fut.held, 12)

    @property
    def flat(self) -> bool:
        return abs(self.spot.held) < 1e-12 and abs(self.fut.held) < 1e-12

    def pnl(self, spot_px: float | None, fut_px: float | None) -> float | None:
        a, b = self.spot.pnl(spot_px), self.fut.pnl(fut_px)
        return None if a is None or b is None else a + b + self.funding_received

    def apply(self, rec: ArbOrder, st: OrderState, base_asset: str) -> float:
        """Aplica a la pata lo nuevo de `st`; devuelve la cantidad base neta movida.

        Una comisión en la moneda base (compra spot) reduce lo recibido; una en USDT va a
        `cash`. Otras monedas (BNB) solo quedan anotadas en la orden."""
        leg = self.legs[rec.market]
        rec.status, rec.avg = st.status, st.avg_price or rec.avg
        rec.fee, rec.fee_asset = st.fee, st.fee_asset
        fee_base = st.fee if base_asset and st.fee_asset == base_asset else 0.0
        fee_quote = st.fee if st.fee_asset == "USDT" else 0.0
        delta = round(st.filled - rec.applied, 12)
        d_base = round(fee_base - rec.fee_applied, 12)
        d_quote = round(fee_quote - rec.fee_quote_applied, 12)
        rec.filled = max(rec.filled, st.filled)
        if delta <= 0 and d_base <= 0 and d_quote <= 0:
            return 0.0
        px = st.avg_price or rec.price or 0.0
        leg.held = round(leg.held + rec.side * max(delta, 0.0) - max(d_base, 0.0), 12)
        leg.cash -= rec.side * max(delta, 0.0) * px + max(d_quote, 0.0)
        leg.fee_quote += max(d_quote, 0.0)
        rec.applied, rec.fee_applied, rec.fee_quote_applied = st.filled, fee_base, fee_quote
        return max(delta, 0.0) - (max(d_base, 0.0) if rec.side > 0 else 0.0)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> ArbPosition:
        d = dict(d)
        d["legs"] = {k: ArbLeg(**v) for k, v in d["legs"].items()}
        d["orders"] = [ArbOrder(**o) for o in d.get("orders", [])]
        return cls(**d)


def position_row(p: ArbPosition) -> dict[str, Any]:
    """Fila para la API y la UI (ejecución en testnet y bróker simulado)."""
    return {
        "key": p.key, "arb": p.arb_id, "strategy": p.strategy, "variant": p.variant,
        "asset": p.asset, "status": p.status, "leverage": p.leverage,
        "created_at": p.created_at, "opened_at": p.opened_at, "closed_at": p.closed_at,
        "exit_reason": p.exit_reason, "spot": p.spot.held, "futures": p.fut.held,
        "spot_symbol": p.spot.symbol, "futures_symbol": p.fut.symbol,
        "hedged": p.hedged, "residual": p.residual, "mark": p.mark, "spot_px": p.spot_px,
        "liq_price": p.liq_price, "liq_move": p.liq_move, "margin_equity": p.margin_equity,
        "funding_expected": p.funding_expected, "funding_received": p.funding_received,
        "funding_n": p.funding_n, "rebalances": p.rebalances, "margin_added": p.margin_added,
        "incident_loss": p.incident_loss, "pnl": p.pnl(p.spot_px, p.mark),
        "net_bps": p.plan.get("net_bps"), "horizon_h": p.plan.get("horizon_h"),
        "orders": len(p.orders), "events": p.events[-12:],
    }
