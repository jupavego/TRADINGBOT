"""Semilla del registro de instrumentos (T89) y compatibilidad con lo que ya existe.

Aquí viven las primeras fichas: los dos perpetuos del foco (`BTCUSDT`, `ETHUSDT`) y los cinco
activos del visor (`eim/data/providers/multi_asset.py`). De esta semilla se derivan `SYMBOLS` y
`FOCUS` de `eim/data/timeframes.py` **sin cambiar su valor**, que es el requisito 4 de T89:
ningún endpoint ni servicio cambia de comportamiento.

Este módulo no importa nada de `eim.data`, a propósito: `timeframes.py` lo importan 73 módulos
y no puede arrastrar el almacén ni la red.

Lo que el registro dice y el código de hoy no decía:

- **Los índices de Yahoo son nivel 1 (investigación), no 2.** T88 verificó que los Términos de
  Yahoo prohíben la recolección automatizada y crear bases de datos con su contenido. Siguen
  en el visor como estaban, pero el registro deja escrito que no sostienen una decisión.
- **Ningún índice declara volumen.** El de `^GSPC` es una suma de componentes, no volumen
  negociado del instrumento; declararlo haría correr en silencio a `vwap` y a la familia de
  flujo de `technical` (el «acierto silencioso» de T87 §9, punto 4).
- **El oro de Binance tiene dos calendarios**: el contrato es 24/7 y su subyacente, CME. T88
  midió que el contrato no cierra aunque el subyacente sí.
"""

from __future__ import annotations

from collections.abc import Iterable

from eim.instruments.calendars import ALWAYS
from eim.instruments.models import (
    AssetClass,
    DataCapability,
    Instrument,
    InstrumentStatus,
    MarketStructure,
    SessionKind,
    TradableLevel,
    make_id,
)

BINANCE_USDM = "binance-futures (fapi/v1/exchangeInfo)"
YAHOO = "yahoo finance (yfinance) — sin licencia de datos verificada (T88 §3)"

_PERP_CAPS = frozenset({
    DataCapability.CANDLES, DataCapability.QUOTES, DataCapability.DEPTH_L2,
    DataCapability.REAL_VOLUME, DataCapability.FUNDING, DataCapability.OPEN_INTEREST,
})
_INDEX_CAPS = frozenset({DataCapability.CANDLES})


def _perp(symbol: str, label: str, *, asset_class: AssetClass = AssetClass.CRYPTO,
          underlying_calendar_id: str | None = None, underlying: str | None = None,
          level: TradableLevel = TradableLevel.OPERATIONAL,
          aliases: tuple[str, ...] = ()) -> Instrument:
    """Perpetuo USDⓈ-M de Binance, lineal y liquidado en USDT."""
    return Instrument(
        id=make_id(asset_class, "binance", symbol, market="usdm"), symbol=symbol, label=label,
        asset_class=asset_class, market_structure=MarketStructure.CONTINUOUS_BOOK,
        venue="binance", status=InstrumentStatus.ACTIVE, currency="USDT", quote_currency="USDT",
        calendar_id=ALWAYS, underlying_calendar_id=underlying_calendar_id,
        session=SessionKind.ALWAYS, underlying=underlying,
        tradable_level=level, data_capabilities=_PERP_CAPS,
        aliases=aliases, source=BINANCE_USDM)


def _index(symbol: str, label: str, calendar_id: str, aliases: tuple[str, ...]) -> Instrument:
    """Índice de Yahoo: sintético (se calcula), sin volumen propio y solo para investigación."""
    return Instrument(
        id=make_id(AssetClass.INDEX, "yahoo", symbol), symbol=symbol, label=label,
        asset_class=AssetClass.INDEX, market_structure=MarketStructure.SYNTHETIC,
        venue="yahoo", status=InstrumentStatus.ACTIVE, currency="USD", quote_currency="USD",
        calendar_id=calendar_id, underlying_calendar_id=calendar_id,
        session=SessionKind.EXCHANGE_HOURS, tradable_level=TradableLevel.RESEARCH,
        data_capabilities=_INDEX_CAPS, aliases=aliases, source=YAHOO)


BTCUSDT = _perp("BTCUSDT", "Bitcoin (BTCUSDT)")
ETHUSDT = _perp("ETHUSDT", "Ethereum (ETHUSDT)")
# Nivel 1 y no 2, aunque esté en el visor: T88 no pudo verificar las comisiones de los
# perpetuos TradFi en ninguna fuente, y operarlos exigiría firmar `POST /fapi/v1/stock/contract`.
XAUUSDT = _perp("XAUUSDT", "Oro (XAUUSDT — perpetuo TradFi de Binance)",
                asset_class=AssetClass.COMMODITY, underlying_calendar_id="CMES",
                underlying="XAU/USD", level=TradableLevel.RESEARCH)
SP500 = _index("^GSPC", "S&P 500 (^GSPC, Yahoo Finance)", "XNYS", ("SP500",))
NASDAQ = _index("^IXIC", "Nasdaq Composite (^IXIC, Yahoo Finance)", "XNAS", ("NASDAQ",))

#: Las primeras entradas del catálogo (requisito 2 de T89): el foco y los cinco del visor.
SEED: tuple[Instrument, ...] = (BTCUSDT, ETHUSDT, XAUUSDT, SP500, NASDAQ)

#: Lo que el almacén y la API conservan y sirven, en su orden de siempre.
SYMBOL_IDS: tuple[str, ...] = (BTCUSDT.id, ETHUSDT.id)
#: Lo que los servicios en vivo analizan y la interfaz pide (T122, decisión del usuario).
FOCUS_IDS: tuple[str, ...] = (BTCUSDT.id,)


#: Lo que el descubrimiento NO puede saber y por tanto no debe borrar. `exchangeInfo` no sabe
#: que el subyacente del oro es CME, ni que `SP500` es el nombre legado del índice, ni cómo se
#: llama el instrumento en español. La capa curada gana sobre la de la fuente en estos campos;
#: en todo lo demás (tick, lote, estado, nocional mínimo, nivel) manda la fuente.
CURATED_FIELDS = ("label", "aliases", "underlying_calendar_id", "underlying")


def curate(inst: Instrument) -> Instrument:
    """Devuelve la ficha con lo curado de la semilla puesto encima, si es uno de la semilla."""
    seed = by_id().get(inst.id)
    if seed is None:
        return inst
    patch = {f: getattr(seed, f) for f in CURATED_FIELDS if getattr(seed, f)}
    return inst.model_copy(update=patch) if patch else inst


def curate_all(instruments: Iterable[Instrument]) -> list[Instrument]:
    """`curate` sobre una lista descubierta (lo que hace el descubrimiento antes de guardar)."""
    return [curate(i) for i in instruments]


def by_id() -> dict[str, Instrument]:
    return {i.id: i for i in SEED}


def resolve(key: str) -> Instrument:
    """Instrumento de la semilla por id, símbolo nativo o alias legado (`SP500`)."""
    for inst in SEED:
        if key in inst.keys:
            return inst
    raise KeyError(f"instrumento {key!r} no está en la semilla del registro")


def _symbols_of(ids: tuple[str, ...]) -> tuple[str, ...]:
    index = by_id()
    return tuple(index[i].symbol for i in ids)


def store_symbols() -> tuple[str, ...]:
    """`SYMBOLS` de `eim/data/timeframes.py`, derivado del registro."""
    return _symbols_of(SYMBOL_IDS)


def focus_symbols() -> tuple[str, ...]:
    """`FOCUS` de `eim/data/timeframes.py`, derivado del registro."""
    return _symbols_of(FOCUS_IDS)


def viewer_assets() -> dict[str, Instrument]:
    """Los cinco activos del visor por su clave legada (`ASSETS` de `multi_asset.py`)."""
    out: dict[str, Instrument] = {}
    for inst in SEED:
        key = inst.aliases[0] if inst.aliases else inst.symbol
        out[key] = inst
    return out
