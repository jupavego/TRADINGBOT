"""Datos de mercado: vela y snapshot (entrada de todos los agentes)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class Frozen(BaseModel):
    """Base inmutable para todos los contratos."""

    model_config = ConfigDict(frozen=True)


class Candle(Frozen):
    """Vela OHLCV; `t` en ms epoch UTC."""

    t: int
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    v: float

    @model_validator(mode="after")
    def _check_ohlc(self) -> Candle:
        if self.h < max(self.o, self.c, self.l) or self.l > min(self.o, self.c, self.h):
            raise ValueError("OHLC inconsistente: h debe ser el máximo y l el mínimo")
        return self


class Book(Frozen):
    """Libro de órdenes: listas (precio, cantidad)."""

    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    source: str


class LiquidationDay(Frozen):
    """Liquidaciones forzadas de un día (UTC): notional USD por lado de la POSICIÓN liquidada."""

    t: int  # inicio del día, ms epoch UTC
    longs_usd: float
    shorts_usd: float


class LiquidationLevel(Frozen):
    """Notional liquidado acumulado en un nivel de precio (centro del bin)."""

    price: float
    longs_usd: float
    shorts_usd: float


class Liquidations(Frozen):
    """Liquidaciones ya descargadas (I/O en `data/providers/liquidations.py`).

    `liquidation_symbol` es el contrato coin-margined real (ETHUSD_PERP), distinto del
    `requested_symbol` (ETHUSDT). Binance dejó de publicar el dataset en octubre de 2024.
    """

    requested_symbol: str
    liquidation_symbol: str
    most_recent_date: str  # YYYY-MM-DD del último archivo publicado
    stale: bool
    stale_age_days: int
    days_with_data: int
    source: str
    daily: list[LiquidationDay]
    levels: list[LiquidationLevel] = []


class NewsItem(Frozen):
    """Titular ya cargado (I/O en `data/providers/news.py`). Texto externo = solo datos."""

    id: str  # identificador estable (hash de url/título); las citas del LLM lo referencian
    t: int  # publicación, ms epoch UTC
    title: str
    source: str
    url: str = ""


class MarketSnapshot(Frozen):
    """Estado de mercado inmutable que consume `Agent.run`."""

    symbol: str
    timeframe: str
    candles: list[Candle]  # más antiguo → reciente; la última está cerrada
    forming: Candle | None = None
    funding: list[tuple[int, float]] | None = None
    open_interest: list[tuple[int, float]] | None = None
    long_short_ratio: list[tuple[int, float]] | None = None  # cuentas long/short (global)
    basis: list[tuple[int, float]] | None = None  # (futuro−índice)/índice del perpetuo
    orderbook: Book | None = None
    liquidations: Liquidations | None = None
    headlines: list[NewsItem] | None = None
    asof: int
    sources: dict[str, str] = {}
    coverage: dict[str, tuple[int, int]] = {}

    @model_validator(mode="after")
    def _check_order(self) -> MarketSnapshot:
        ts = [c.t for c in self.candles]
        if any(b <= a for a, b in zip(ts, ts[1:], strict=False)):
            raise ValueError("las velas deben estar ordenadas estrictamente por tiempo")
        if self.forming is not None and ts and self.forming.t <= ts[-1]:
            raise ValueError("la vela en curso debe ser posterior a la última cerrada")
        return self
