"""Descubrimiento de instrumentos (T89): de la respuesta de una plaza a fichas del registro.

Funciones **puras**: entran los datos tal como los devuelve la fuente y salen `Instrument`.
La red vive en `eim/data/providers/` y la escritura en `eim/data/instruments_store.py`, así
que esto se prueba con respuestas simuladas (`tests/fixtures/instruments/`) y sin red.

Binance USDⓈ-M (`/fapi/v1/exchangeInfo`) es la fuente primaria de la fase 17: 705 perpetuos
cripto y 247 TradFi el 2026-11-20. La clase no se adivina, la dice la plaza en
`underlyingType` (COIN, EQUITY, HK_EQUITY, KR_EQUITY, CN_EQUITY, PREMARKET, COMMODITY,
INDEX, FX); lo que no esté en ese mapa entra como `future` y se anota, nunca se supone.

Las demás fuentes aprobadas en T88 **no tienen catálogo que descubrir**, y por eso no hay
mapeo para ellas: FRED/ALFRED, US Treasury y Binance Vision sirven series y archivos
históricos, no universos de instrumentos. La excepción es el FX de referencia del BCE, que sí
tiene una lista de divisas: `from_frankfurter`.

**Los TradFi entran como nivel 1 (investigación), no 2.** Dos razones escritas en T88: sus
comisiones no se pudieron verificar en ninguna fuente y operarlos exigiría firmar
`POST /fapi/v1/stock/contract`, que no se ha firmado. La ◆ de T88 §7 punto 4 fijó por
defecto que se **observan** en T93 y que ninguna tarea publica un veredicto de rentabilidad
sobre ellos. El nivel del registro es ese límite, puesto en el dato.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping

from eim.instruments.calendars import ALWAYS, WEEKDAYS
from eim.instruments.models import (
    AssetClass,
    DataCapability,
    EventKind,
    Instrument,
    InstrumentEvent,
    InstrumentStatus,
    MarketStructure,
    SessionKind,
    TradableLevel,
    make_id,
)

BINANCE_USDM_SOURCE = "binance-futures (fapi/v1/exchangeInfo)"
PERPETUAL_TYPES = frozenset({"PERPETUAL", "TRADIFI_PERPETUAL"})
TRADFI_TYPES = frozenset({"TRADIFI_PERPETUAL"})

#: Clase de activo según `underlyingType` de Binance. Lo que falte entra como `future`.
UNDERLYING_CLASS: dict[str, AssetClass] = {
    "COIN": AssetClass.CRYPTO,
    "EQUITY": AssetClass.EQUITY,
    "HK_EQUITY": AssetClass.EQUITY,
    "KR_EQUITY": AssetClass.EQUITY,
    "CN_EQUITY": AssetClass.EQUITY,
    "PREMARKET": AssetClass.EQUITY,
    "COMMODITY": AssetClass.COMMODITY,
    "INDEX": AssetClass.INDEX,
    "FX": AssetClass.FX,
}

#: Estado del registro según `status` de Binance.
BINANCE_STATUS: dict[str, InstrumentStatus] = {
    "TRADING": InstrumentStatus.ACTIVE,
    "PENDING_TRADING": InstrumentStatus.PENDING,
    "PRE_SETTLE": InstrumentStatus.SUSPENDED,
    "SETTLING": InstrumentStatus.SUSPENDED,
    "PRE_DELIVERING": InstrumentStatus.SUSPENDED,
    "HALT": InstrumentStatus.SUSPENDED,
    "BREAK": InstrumentStatus.SUSPENDED,
    "AUCTION_MATCH": InstrumentStatus.SUSPENDED,
    "DELIVERING": InstrumentStatus.SUSPENDED,
    "DELIVERED": InstrumentStatus.EXPIRED,
    "CLOSE": InstrumentStatus.DELISTED,
}

_CAPS = frozenset({
    DataCapability.CANDLES, DataCapability.QUOTES, DataCapability.DEPTH_L2,
    DataCapability.REAL_VOLUME, DataCapability.FUNDING, DataCapability.OPEN_INTEREST,
})
#: Los campos del contrato que, si cambian, son un hecho fechado (`contract_change`).
CONTRACT_FIELDS = ("tick", "lot", "multiplier", "min_notional", "expiry", "calendar_id",
                   "asset_class", "market_structure", "quote_currency", "currency")
_STATUS_EVENT = {
    InstrumentStatus.ACTIVE: EventKind.RESUMED,
    InstrumentStatus.SUSPENDED: EventKind.SUSPENDED,
    InstrumentStatus.EXPIRED: EventKind.EXPIRED,
    InstrumentStatus.DELISTED: EventKind.DELISTED,
    InstrumentStatus.PENDING: EventKind.LISTED,
}


def _filters(raw: Mapping) -> dict[str, Mapping]:
    return {f.get("filterType"): f for f in raw.get("filters") or ()}


def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def from_binance_usdm(payload: Mapping, *, source: str = BINANCE_USDM_SOURCE) -> list[Instrument]:
    """Fichas de todo lo que lista `exchangeInfo`, en cualquier estado.

    Se incluyen los no vigentes a propósito: sin ellos el catálogo tiene sesgo de
    supervivencia (el aviso que `eim/data/perp_universe.py` ya dejó escrito en T181).
    """
    out: list[Instrument] = []
    for raw in payload.get("symbols") or ():
        inst = _one_binance(raw, source=source)
        if inst is not None:
            out.append(inst)
    return sorted(out, key=lambda i: i.id)


def _one_binance(raw: Mapping, *, source: str) -> Instrument | None:
    symbol, ctype = raw.get("symbol"), raw.get("contractType")
    if not symbol or not ctype:
        return None
    perpetual = ctype in PERPETUAL_TYPES
    tradfi = ctype in TRADFI_TYPES
    utype = str(raw.get("underlyingType") or "")
    asset_class = UNDERLYING_CLASS.get(utype, AssetClass.FUTURE)
    if not perpetual:
        asset_class = AssetClass.FUTURE          # trimestral: el contrato manda sobre el subyacente
    delivery = int(raw.get("deliveryDate") or 0)
    fl = _filters(raw)
    notional = fl.get("MIN_NOTIONAL") or {}
    quote = str(raw.get("quoteAsset") or "")
    sub = tuple(raw.get("underlyingSubType") or ())
    label = f"{raw.get('pair') or symbol} · {ctype.lower()}"
    if sub:
        label += f" ({', '.join(sub)})"
    return Instrument(
        id=make_id(asset_class, "binance", symbol, market="usdm"),
        symbol=symbol, label=label, asset_class=asset_class,
        market_structure=MarketStructure.CONTINUOUS_BOOK, venue="binance",
        status=BINANCE_STATUS.get(str(raw.get("status")), InstrumentStatus.SUSPENDED),
        currency=str(raw.get("marginAsset") or quote), quote_currency=quote,
        calendar_id=ALWAYS, underlying_calendar_id=None,
        session=SessionKind.ALWAYS,
        tick=_num((fl.get("PRICE_FILTER") or {}).get("tickSize")),
        lot=_num((fl.get("LOT_SIZE") or {}).get("stepSize")),
        min_notional=_num(notional.get("notional") or notional.get("minNotional")),
        expiry=None if perpetual else (delivery or None),
        underlying=str(raw.get("pair") or "") or None,
        tradable_level=TradableLevel.RESEARCH if tradfi else TradableLevel.OPERATIONAL,
        data_capabilities=_CAPS, listed_at=int(raw.get("onboardDate") or 0) or None,
        source=source)


def diff_events(previous: Instrument | None, current: Instrument, *,
                t: int | None = None) -> list[InstrumentEvent]:
    """Hechos fechados entre dos versiones de la misma ficha: alta, cambio de estado y cambio
    de contrato. `t` es el instante que se registra (por defecto, ahora)."""
    now = int(time.time() * 1000) if t is None else int(t)
    if previous is not None and previous.id != current.id:
        raise ValueError(f"fichas de instrumentos distintos: {previous.id} y {current.id}")
    events: list[InstrumentEvent] = []
    if previous is None:
        events.append(InstrumentEvent(
            instrument_id=current.id, kind=EventKind.LISTED,
            t=current.listed_at or now, detail=f"estado={current.status.value}",
            source=current.source, observed_at=now))
    elif previous.status is not current.status:
        events.append(InstrumentEvent(
            instrument_id=current.id, kind=_STATUS_EVENT[current.status], t=now,
            detail=f"{previous.status.value} → {current.status.value}",
            source=current.source, observed_at=now))
    if previous is not None:
        changed = [f for f in CONTRACT_FIELDS if getattr(previous, f) != getattr(current, f)]
        if changed:
            detail = "; ".join(
                f"{f}: {getattr(previous, f)!r} → {getattr(current, f)!r}" for f in changed)
            events.append(InstrumentEvent(
                instrument_id=current.id, kind=EventKind.CONTRACT_CHANGE, t=now,
                detail=detail, source=current.source, observed_at=now))
    return events


# --- FX de referencia (Frankfurter / BCE) ---------------------------------
FRANKFURTER_SOURCE = ("frankfurter (api.frankfurter.dev) sobre los tipos de referencia del BCE; "
                      "citar al BCE como fuente")
#: Las mayores, para que `FOCUS` de una clase de FX no sea «las 30 que devuelve el endpoint».
FX_MAJORS = ("EUR", "USD", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD")


def from_frankfurter(currencies: Mapping[str, str], *, base: str = "EUR",
                     majors_only: bool = True,
                     source: str = FRANKFURTER_SOURCE) -> list[Instrument]:
    """Pares de FX contra `base` a partir de `/v1/currencies`.

    Lo que el registro deja escrito de esta clase, y que el código de hoy no sabía decir:

    - **`market_structure` es `quote_driven`**: el FX al contado no tiene libro central, y el
      tipo del BCE es una referencia diaria, no un precio negociado.
    - **No hay volumen de ninguna clase.** No se declara `real_volume` ni `tick_volume`, así
      que la familia de flujo de `technical` y `vwap` quedan fuera por contrato, no por suerte.
    - **Calendario `24/5`**, con su aviso: no conoce festivos (ver `calendars.FX_WARNINGS`).

    Nivel 2 (operativa): la licencia está verificada en la fuente —uso libre citando al BCE— y
    el código de Frankfurter es MIT (T88 §2.1). Es análisis, no ejecución: no hay nivel 3.
    """
    out: list[Instrument] = []
    for code, name in sorted(currencies.items()):
        if code == base or not code.isalpha() or len(code) != 3:
            continue
        if majors_only and (code not in FX_MAJORS or base not in FX_MAJORS):
            continue
        symbol = f"{base}{code}"
        out.append(Instrument(
            id=make_id(AssetClass.FX, "ecb", symbol), symbol=symbol,
            label=f"{base}/{code} ({name}, tipo de referencia del BCE)",
            asset_class=AssetClass.FX, market_structure=MarketStructure.QUOTE_DRIVEN,
            venue="ecb", status=InstrumentStatus.ACTIVE, currency=code, quote_currency=code,
            calendar_id=WEEKDAYS, underlying_calendar_id=WEEKDAYS,
            session=SessionKind.WEEKDAYS, underlying=f"{base}/{code}",
            tradable_level=TradableLevel.OPERATIONAL,
            data_capabilities=frozenset({DataCapability.CANDLES}),
            aliases=(f"{base}/{code}",), source=source))
    return sorted(out, key=lambda i: i.id)


def missing_from(previous: Iterable[Instrument], current: Iterable[Instrument], *,
                 t: int | None = None) -> list[InstrumentEvent]:
    """Bajas: lo que estaba en el catálogo y la plaza ha dejado de listar.

    Se anota como `delisted` con el motivo «desapareció de exchangeInfo»; el estado de la
    ficha no se cambia a ciegas, porque desaparecer de un listado no es lo mismo que una
    retirada anunciada, y esa diferencia tiene que quedar legible.
    """
    now = int(time.time() * 1000) if t is None else int(t)
    live = {i.id for i in current}
    return [InstrumentEvent(instrument_id=p.id, kind=EventKind.DELISTED, t=now,
                            detail="desapareció de exchangeInfo", source=p.source,
                            observed_at=now)
            for p in previous if p.id not in live
            and p.status not in (InstrumentStatus.DELISTED, InstrumentStatus.EXPIRED)]
