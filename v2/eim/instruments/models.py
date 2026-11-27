"""Identidad y contrato de un instrumento (T89): el catálogo único de la fase 17.

Por qué existe: hasta T89 cada módulo nuevo codificaba `"BTCUSDT"` a mano (T87 contó 117
archivos de `eim/` con literales de cripto). Un instrumento es ahora un dato del registro,
no una constante del código: `eim/instruments/registry.py` trae la semilla, el descubrimiento
de `discovery.py` trae el resto y `eim/data/instruments_store.py` guarda su historia.

El `id` es estable y legible: `clase.plaza[.mercado].SÍMBOLO`
(`crypto.binance.usdm.BTCUSDT`, `index.yahoo.^GSPC`). El símbolo nativo de la plaza sigue
siendo un identificador válido a través de `aliases`, así que nada de lo que hay hoy cambia
de nombre.

Qué NO vive aquí: descargar series (T90-T91), elegibilidad de agentes (T91), costos por
clase (T92) ni el detalle contractual de opciones y bonos (T100).
"""

from __future__ import annotations

import re
from enum import IntEnum, StrEnum

from pydantic import field_validator, model_validator

from eim.core.market import Frozen

SCHEMA_VERSION = "1.0.0"

#: `clase.plaza.SÍMBOLO` o `clase.plaza.mercado.SÍMBOLO`; el último tramo es el símbolo nativo.
#: El símbolo admite letras y dígitos de cualquier alfabeto —Binance lista `币安人生USDT`, y un
#: catálogo que no lo acepte no es universal— más `_`, `-` y `^` (`^GSPC`). Puntos y espacios
#: quedan fuera a propósito: el punto separa tramos y el id tiene que poder partirse por el
#: último sin ambigüedad (un símbolo como `CL.F` se registra `CL-F`).
ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+(?:\.[a-z0-9_]+)?\.[\w^][\w^-]*$")


class AssetClass(StrEnum):
    """Clase de activo (el orden aprobado en la ◆ de T87 recorre cripto → índices → ...)."""

    CRYPTO = "crypto"          # cripto
    EQUITY = "equity"          # renta variable
    ETF = "etf"                # fondo cotizado
    INDEX = "index"            # índice
    FX = "fx"                  # divisas
    COMMODITY = "commodity"    # materia prima
    FUTURE = "future"          # futuro
    OPTION = "option"          # opción
    BOND = "bond"              # renta fija
    CASH = "cash"              # monetario


class MarketStructure(StrEnum):
    """Cómo se forma el precio. Decide qué puede esperar un agente del volumen y del libro."""

    CONTINUOUS_BOOK = "continuous_book"   # libro continuo (cripto, acciones en sesión)
    QUOTE_DRIVEN = "quote_driven"         # cotización/OTC fragmentado (FX al contado)
    AUCTION = "auction"                   # subasta (apertura/cierre, mercados de corros)
    SYNTHETIC = "synthetic"               # sintético: se calcula, no se negocia (índices)


class SessionKind(StrEnum):
    """Forma de la semana de negociación."""

    ALWAYS = "24/7"
    WEEKDAYS = "24/5"
    EXCHANGE_HOURS = "exchange_hours"


class DataCapability(StrEnum):
    """Qué datos existen para el instrumento. Un agente que necesite uno que no está aquí
    no corre: sale `no_data` con motivo (regla del punto 4 de la lista de T87; la implanta T91).
    """

    CANDLES = "candles"
    QUOTES = "quotes"
    DEPTH_L2 = "depth_l2"
    OPTION_CHAIN = "option_chain"
    CURVE = "curve"
    FUNDAMENTALS = "fundamentals"
    REAL_VOLUME = "real_volume"     # volumen negociado de verdad
    TICK_VOLUME = "tick_volume"     # solo cuenta de ticks (FX): no es volumen
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"


class TradableLevel(IntEnum):
    """Hasta dónde llega el permiso sobre sus datos (niveles de la ◆ de T88 §2).

    1 investigación: estudiar, no publicar ni decidir con ello. 2 operativa: licencia y
    límites escritos. 3 ejecución: autorizada por un intermediario — hoy no hay ninguno,
    y el alcance aprobado (T145 D, T87 ◆1) es solo análisis simulado.
    """

    RESEARCH = 1
    OPERATIONAL = 2
    EXECUTION = 3


class InstrumentStatus(StrEnum):
    """Estado en la plaza."""

    PENDING = "pending"        # anunciado, sin negociar
    ACTIVE = "active"
    SUSPENDED = "suspended"    # parado, liquidando o en subasta de cierre
    EXPIRED = "expired"        # vencido/entregado
    DELISTED = "delisted"      # retirado


class EventKind(StrEnum):
    """Hechos del ciclo de vida que el almacén fecha (altas, bajas, vencimientos, cambios)."""

    LISTED = "listed"
    DELISTED = "delisted"
    SUSPENDED = "suspended"
    RESUMED = "resumed"
    EXPIRED = "expired"
    CONTRACT_CHANGE = "contract_change"


def make_id(asset_class: AssetClass | str, venue: str, symbol: str,
            market: str | None = None) -> str:
    """`clase.plaza[.mercado].SÍMBOLO`, con los tramos en minúscula y el símbolo tal cual."""
    parts = [str(asset_class).lower(), venue.lower()]
    if market:
        parts.append(market.lower())
    parts.append(symbol)
    out = ".".join(parts)
    if not ID_RE.match(out):
        raise ValueError(f"id de instrumento inválido: {out!r}")
    return out


class Instrument(Frozen):
    """Un instrumento negociable (o calculable, en el caso de un índice).

    `calendar_id` es el calendario del **contrato**; `underlying_calendar_id`, el del
    subyacente, y son distintos a propósito: T88 midió que un perpetuo TradFi de Binance
    **no cierra aunque su subyacente sí** (0 huecos en las 48 h de cierre, liquidez al
    6-28 %). Sin los dos no se puede decir si un hueco de datos es «cerrado» o «sin datos».

    `tick`, `lot`, `multiplier` y `min_notional` son del contrato, no del proveedor.
    `aliases` guarda el símbolo legado (`SP500`, `BTCUSDT`) para que nada de lo que ya
    funciona tenga que cambiar de nombre.
    """

    id: str
    schema_version: str = SCHEMA_VERSION
    symbol: str                       # símbolo nativo de la plaza
    label: str                        # nombre para la interfaz (español)
    asset_class: AssetClass
    market_structure: MarketStructure
    venue: str
    status: InstrumentStatus = InstrumentStatus.ACTIVE
    currency: str                     # moneda de liquidación/margen
    quote_currency: str               # moneda en la que cotiza el precio
    calendar_id: str
    underlying_calendar_id: str | None = None
    session: SessionKind
    tick: float | None = None
    lot: float | None = None
    multiplier: float = 1.0
    min_notional: float | None = None
    expiry: int | None = None         # ms epoch UTC; None = perpetuo o sin vencimiento
    underlying: str | None = None
    tradable_level: TradableLevel = TradableLevel.RESEARCH
    data_capabilities: frozenset[DataCapability] = frozenset()
    aliases: tuple[str, ...] = ()
    listed_at: int | None = None      # ms epoch UTC del alta en la plaza
    source: str                       # de dónde sale esta ficha (regla de `source` de CLAUDE.md)

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError(f"id de instrumento inválido: {v!r}")
        return v

    @field_validator("tick", "lot", "min_notional")
    @classmethod
    def _positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("tick, lot y min_notional, si están, deben ser > 0")
        return v

    @field_validator("multiplier")
    @classmethod
    def _multiplier(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("multiplier debe ser > 0")
        return v

    @model_validator(mode="after")
    def _coherent(self) -> Instrument:
        if self.id.rsplit(".", 1)[1] != self.symbol:
            raise ValueError(f"el id {self.id!r} no termina en su símbolo {self.symbol!r}")
        if not self.id.startswith(f"{self.asset_class.value}."):
            raise ValueError(f"el id {self.id!r} no empieza por su clase {self.asset_class!r}")
        if self.symbol in self.aliases:
            raise ValueError("el símbolo nativo no se repite en `aliases`")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("`aliases` con repetidos")
        if self.expiry is not None and self.expiry <= 0:
            raise ValueError("expiry en ms epoch UTC o None")
        has_volume = DataCapability.REAL_VOLUME in self.data_capabilities
        if has_volume and DataCapability.TICK_VOLUME in self.data_capabilities:
            raise ValueError("un instrumento no tiene a la vez volumen real y de ticks")
        if self.market_structure is MarketStructure.SYNTHETIC and has_volume:
            raise ValueError("un sintético no tiene volumen negociado propio")
        return self

    @property
    def keys(self) -> tuple[str, ...]:
        """Todo lo que resuelve a este instrumento: su id, su símbolo y sus alias."""
        return (self.id, self.symbol, *self.aliases)

    def has(self, *caps: DataCapability) -> bool:
        """¿Están todas esas capacidades de datos? (lo que T91 usará para la elegibilidad)."""
        return all(c in self.data_capabilities for c in caps)


class InstrumentEvent(Frozen):
    """Un hecho fechado del ciclo de vida: alta, baja, vencimiento, suspensión o cambio."""

    instrument_id: str
    kind: EventKind
    t: int                      # ms epoch UTC del hecho (o de cuando se observó, si no hay otro)
    detail: str = ""
    source: str = ""
    observed_at: int | None = None

    @field_validator("t")
    @classmethod
    def _t(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("t en ms epoch UTC")
        return v
