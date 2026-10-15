"""Contratos de arbitraje (T38): modelo de costos, patas, oportunidad y resultado de escaneo.

Toda oportunidad lleva su desglose de costos y su riesgo; importes en USD(T) para el
nocional evaluado. Convención: `gross_edge` = lo que captura la tesis a precio medio y sin
fricción; `costs` = fricciones; `net_edge = gross_edge − costs.total` (lo valida el contrato).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from eim.core.market import Frozen

MarketKind = Literal["spot", "usdm", "usdcm"]  # spot · futuros USDⓈ-M · futuros USDC-M
Side = Literal["buy", "sell"]
Role = Literal["maker", "taker"]
StrategyId = Literal["funding_carry", "basis", "triangular", "related_perps"]
ScanStatus = Literal["ok", "degraded", "no_data"]
FeeTable = dict[int, tuple[float, float]]  # nivel VIP → (maker, taker) en fracción

# Tablas públicas de Binance. VIP 0 verificado el 2026-10-15 (spot 0,10 %/0,10 %;
# USDⓈ-M 0,02 %/0,05 %); el resto son de referencia y deben confirmarse en la cuenta.
SPOT_FEES: FeeTable = {
    0: (0.0010, 0.0010), 1: (0.0009, 0.0010), 2: (0.0008, 0.0010), 3: (0.00042, 0.0006),
    4: (0.00042, 0.00054), 5: (0.00036, 0.00048), 6: (0.0003, 0.00042),
    7: (0.00024, 0.00036), 8: (0.00018, 0.0003), 9: (0.00012, 0.00024),
}
USDM_FEES: FeeTable = {
    0: (0.0002, 0.0005), 1: (0.00016, 0.0004), 2: (0.00014, 0.00035), 3: (0.00012, 0.00032),
    4: (0.0001, 0.0003), 5: (0.00008, 0.00027), 6: (0.00006, 0.00025),
    7: (0.00004, 0.00022), 8: (0.00002, 0.0002), 9: (0.0, 0.00017),
}
FEE_SOURCE = ("tabla pública Binance (VIP 0 verificado 2026-10-15; otros niveles de referencia; "
              "USDC-M sin verificar → igual que USDⓈ-M) · configurable")


class Fill(Frozen):
    """Resultado de recorrer un lado del libro (VWAP real, no el mejor precio)."""

    base: float  # cantidad base ejecutable con la profundidad visible
    quote: float  # importe en moneda cotizada de esa cantidad
    vwap: float
    best: float
    levels: int  # niveles consumidos
    complete: bool  # el libro visible alcanzó para todo lo pedido


class CostModel(Frozen):
    """Comisiones por mercado/nivel VIP/descuento BNB y deslizamiento por profundidad.

    El arbitraje cruza el libro, por eso `role` por defecto es taker. `delivery_fee` = tasa
    al liquidar un trimestral al vencimiento (None = taker de futuros, conservador).
    """

    spot_vip: int = 0
    futures_vip: int = 0
    bnb_discount: bool = False
    spot_bnb_discount: float = Field(default=0.25, ge=0, lt=1)
    futures_bnb_discount: float = Field(default=0.10, ge=0, lt=1)
    spot_fees: FeeTable = SPOT_FEES
    usdm_fees: FeeTable = USDM_FEES
    usdcm_fees: FeeTable = USDM_FEES
    role: Role = "taker"
    delivery_fee: float | None = None
    source: str = FEE_SOURCE

    @model_validator(mode="after")
    def _check_vip(self) -> CostModel:
        if self.spot_vip not in self.spot_fees:
            raise ValueError(f"nivel VIP spot {self.spot_vip} sin tabla")
        for table in (self.usdm_fees, self.usdcm_fees):
            if self.futures_vip not in table:
                raise ValueError(f"nivel VIP futuros {self.futures_vip} sin tabla")
        return self

    def fee_rate(self, market: MarketKind, role: Role | None = None) -> float:
        """Tasa efectiva (fracción del nocional) tras el descuento BNB si aplica."""
        idx = 0 if (role or self.role) == "maker" else 1
        if market == "spot":
            rate = self.spot_fees[self.spot_vip][idx]
            return rate * (1 - self.spot_bnb_discount) if self.bnb_discount else rate
        table = self.usdm_fees if market == "usdm" else self.usdcm_fees
        rate = table[self.futures_vip][idx]
        return rate * (1 - self.futures_bnb_discount) if self.bnb_discount else rate

    def settle_rate(self) -> float:
        return self.fee_rate("usdm") if self.delivery_fee is None else self.delivery_fee

    @staticmethod
    def fill(levels: list[tuple[float, float]], *, base: float | None = None,
             quote: float | None = None) -> Fill:
        """Recorre `levels` (precio, cantidad) desde el mejor precio hasta cubrir `base`
        unidades o gastar `quote` de moneda cotizada (exactamente uno de los dos)."""
        if (base is None) == (quote is None):
            raise ValueError("indicar base o quote, no ambos")
        if not levels:
            return Fill(base=0.0, quote=0.0, vwap=0.0, best=0.0, levels=0, complete=False)
        want = base if base is not None else quote
        assert want is not None
        got_b = got_q = 0.0
        used = 0
        for price, qty in levels:
            if price <= 0 or qty <= 0:
                continue
            room = want - (got_b if base is not None else got_q)
            if room <= 1e-15:
                break
            take = min(qty, room if base is not None else room / price)
            got_b += take
            got_q += take * price
            used += 1
        done = got_b if base is not None else got_q
        return Fill(base=got_b, quote=got_q, vwap=got_q / got_b if got_b else 0.0,
                    best=levels[0][0], levels=used, complete=done >= want * (1 - 1e-9))


class Leg(Frozen):
    """Una pata ejecutada contra el libro; `fee` y `slippage` en USD.

    `slippage` = |VWAP − precio medio| × cantidad: incluye medio diferencial e impacto de
    profundidad. `action="close"` = salida estimada con el libro actual (forma estable).
    """

    market: MarketKind
    symbol: str
    side: Side
    action: Literal["open", "close"] = "open"
    qty: float = Field(ge=0)  # base pedida
    filled: float = Field(ge=0)  # base ejecutable con la profundidad visible
    vwap: float
    mid: float
    best: float
    fee_rate: float = Field(ge=0)
    fee: float = Field(ge=0)
    slippage: float
    levels: int = Field(ge=0)

    @property
    def complete(self) -> bool:
        return self.filled >= self.qty * (1 - 1e-9) and self.qty > 0


class Costs(Frozen):
    """Desglose obligatorio. `funding` > 0 = se paga, < 0 = se cobra (patas cuyo funding no
    es la tesis); `borrow` = interés del préstamo spot."""

    fees: float = Field(ge=0)
    slippage: float
    funding: float = 0.0
    borrow: float = Field(default=0.0, ge=0)

    @property
    def total(self) -> float:
        return self.fees + self.slippage + self.funding + self.borrow


class Risk(Frozen):
    """Riesgos 0 (bajo) … 1 (alto), heurísticos y explicados en `notes`."""

    legging: float = Field(ge=0, le=1)
    basis: float = Field(ge=0, le=1)
    liquidation: float = Field(ge=0, le=1)
    liquidity: float = Field(ge=0, le=1)
    notes: dict[str, str] = {}

    def penalty(self, weights: dict[str, float]) -> float:
        total = sum(weights.values()) or 1.0
        return sum(getattr(self, k) * w for k, w in weights.items()) / total


class Opportunity(Frozen):
    """Oportunidad valorada neta de costos y con su riesgo declarado."""

    strategy: StrategyId
    variant: str  # p. ej. "largo spot / corto perpetuo"
    asset: str  # activo o ciclo ("BTC", "USDT→BTC→ETH→USDT")
    legs: list[Leg] = Field(min_length=1)
    gross_edge: float
    costs: Costs
    net_edge: float
    capital_required: float = Field(gt=0)
    annualized: float | None  # neto/capital anualizado; None si es instantáneo
    horizon_h: float = Field(ge=0)
    risk: Risk
    asof: int
    valid_until: int
    source: str
    coverage: dict[str, tuple[int, int]]
    executable: bool  # todas las patas caben en el libro visible
    details: dict[str, float | int | str | None] = {}
    warnings: list[str] = []

    @model_validator(mode="after")
    def _check_net(self) -> Opportunity:
        if abs(self.net_edge - (self.gross_edge - self.costs.total)) > 1e-6 * max(
                1.0, abs(self.gross_edge)):
            raise ValueError("net_edge debe ser gross_edge − costs.total")
        if self.valid_until < self.asof:
            raise ValueError("valid_until anterior a asof")
        return self

    @property
    def net_bps(self) -> float:
        return self.net_edge / self.capital_required * 1e4


class ArbScan(Frozen):
    """Resultado de una estrategia sobre los datos cargados (incluye lo que faltó)."""

    strategy: StrategyId
    status: ScanStatus
    asof: int
    opportunities: list[Opportunity] = []
    missing: list[str] = []
    warnings: list[str] = []
