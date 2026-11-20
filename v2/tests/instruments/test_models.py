"""Esquema del registro de instrumentos (T89)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from eim.instruments.models import (
    SCHEMA_VERSION,
    AssetClass,
    DataCapability,
    EventKind,
    Instrument,
    InstrumentEvent,
    MarketStructure,
    SessionKind,
    TradableLevel,
    make_id,
)

BASE = {
    "symbol": "BTCUSDT", "label": "Bitcoin", "asset_class": AssetClass.CRYPTO,
    "market_structure": MarketStructure.CONTINUOUS_BOOK, "venue": "binance",
    "currency": "USDT", "quote_currency": "USDT", "calendar_id": "24/7",
    "session": SessionKind.ALWAYS, "source": "prueba",
}


def inst(**over) -> Instrument:
    d = {**BASE, **over}
    d.setdefault("id", make_id(d["asset_class"], d["venue"], d["symbol"], market="usdm"))
    return Instrument(**d)


def test_id_estable_y_legible():
    assert make_id(AssetClass.CRYPTO, "Binance", "BTCUSDT", market="USDM") == \
        "crypto.binance.usdm.BTCUSDT"
    assert make_id(AssetClass.EQUITY, "nyse", "SPY") == "equity.nyse.SPY"
    assert make_id(AssetClass.INDEX, "yahoo", "^GSPC") == "index.yahoo.^GSPC"


@pytest.mark.parametrize("bad", ["BTCUSDT", "crypto.BTCUSDT", "Crypto.binance.usdm.BTCUSDT",
                                 "crypto.binance.usdm.btc usdt", "crypto..usdm.BTCUSDT",
                                 "crypto.binance.usdm.BTCUSDT.", ""])
def test_id_invalido_no_pasa(bad):
    with pytest.raises(ValidationError):
        inst(id=bad)


@pytest.mark.parametrize("symbol", ["btc usdt", "BTC/USDT", "", "BTC,USDT", "CL.F"])
def test_make_id_rechaza_simbolos_que_romperian_el_id(symbol):
    with pytest.raises(ValueError, match="inválido"):
        make_id(AssetClass.CRYPTO, "binance", symbol, market="usdm")


@pytest.mark.parametrize("symbol", ["BTCUSDT", "^GSPC", "BTCUSDT_261225", "1000PEPEUSDT",
                                    "币安人生USDT"])
def test_los_simbolos_reales_de_las_plazas_se_aceptan(symbol):
    """`币安人生USDT` existe en Binance: un catálogo que no lo acepte no es universal."""
    i = inst(symbol=symbol)
    assert i.id.rsplit(".", 1)[1] == symbol


def test_el_id_tiene_que_cuadrar_con_su_clase_y_su_simbolo():
    with pytest.raises(ValidationError, match="no termina en su símbolo"):
        inst(id="crypto.binance.usdm.ETHUSDT")
    with pytest.raises(ValidationError, match="no empieza por su clase"):
        inst(id="equity.binance.usdm.BTCUSDT")


def test_frozen_y_version_de_esquema():
    i = inst()
    assert i.schema_version == SCHEMA_VERSION
    with pytest.raises(ValidationError):
        i.symbol = "ETHUSDT"


def test_claves_resuelven_id_simbolo_y_alias():
    i = inst(symbol="^GSPC", asset_class=AssetClass.INDEX,
             market_structure=MarketStructure.SYNTHETIC, venue="yahoo",
             id="index.yahoo.^GSPC", aliases=("SP500",))
    assert i.keys == ("index.yahoo.^GSPC", "^GSPC", "SP500")


def test_alias_no_repite_el_simbolo_ni_se_duplica():
    with pytest.raises(ValidationError, match="no se repite"):
        inst(aliases=("BTCUSDT",))
    with pytest.raises(ValidationError, match="repetidos"):
        inst(aliases=("XBT", "XBT"))


@pytest.mark.parametrize("field", ["tick", "lot", "min_notional", "multiplier"])
def test_numeros_de_contrato_positivos(field):
    with pytest.raises(ValidationError):
        inst(**{field: 0.0})


def test_un_sintetico_no_tiene_volumen_negociado():
    """El volumen de ^GSPC es suma de componentes: declararlo haría correr a `vwap` en silencio."""
    with pytest.raises(ValidationError, match="sintético"):
        inst(id="index.yahoo.^GSPC", symbol="^GSPC", asset_class=AssetClass.INDEX,
             market_structure=MarketStructure.SYNTHETIC,
             data_capabilities=frozenset({DataCapability.REAL_VOLUME}))


def test_volumen_real_y_de_ticks_son_excluyentes():
    with pytest.raises(ValidationError, match="a la vez"):
        inst(data_capabilities=frozenset({DataCapability.REAL_VOLUME,
                                          DataCapability.TICK_VOLUME}))


def test_has_declara_capacidades():
    i = inst(data_capabilities=frozenset({DataCapability.CANDLES, DataCapability.FUNDING}))
    assert i.has(DataCapability.CANDLES, DataCapability.FUNDING)
    assert not i.has(DataCapability.DEPTH_L2)


def test_niveles_son_los_de_t88():
    assert (int(TradableLevel.RESEARCH), int(TradableLevel.OPERATIONAL),
            int(TradableLevel.EXECUTION)) == (1, 2, 3)


def test_evento_exige_t_utc():
    e = InstrumentEvent(instrument_id="crypto.binance.usdm.BTCUSDT", kind=EventKind.LISTED,
                        t=1_700_000_000_000)
    assert e.kind is EventKind.LISTED
    with pytest.raises(ValidationError):
        InstrumentEvent(instrument_id="x.y.Z", kind=EventKind.LISTED, t=0)
