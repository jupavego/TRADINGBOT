"""Descubrimiento con respuestas simuladas (T89, requisito 6). Sin red.

La respuesta de `/fapi/v1/exchangeInfo` de `tests/fixtures/instruments/` es real, recortada a
diez símbolos el 2026-11-20: trae un caso de cada cosa que el mapeo tiene que resolver
(perpetuo cripto, TradFi de materia prima, de acción y de divisa, trimestral, en liquidación,
pendiente de alta, cotizado en USDC y un índice).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eim.instruments import discovery, registry
from eim.instruments.models import (
    AssetClass,
    DataCapability,
    EventKind,
    InstrumentStatus,
    TradableLevel,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "instruments" / \
    "binance_usdm_exchange_info.json"
T0 = 1_700_000_000_000


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def found(payload) -> dict:
    return {i.id: i for i in discovery.from_binance_usdm(payload)}


def test_descubre_todos_los_simbolos_en_cualquier_estado(payload, found):
    """Incluir los no vigentes es a propósito: sin ellos el catálogo tiene sesgo de
    supervivencia (el aviso que T181 ya dejó escrito)."""
    assert len(found) == len(payload["symbols"])
    estados = {i.status for i in found.values()}
    assert InstrumentStatus.SUSPENDED in estados and InstrumentStatus.PENDING in estados


def test_la_clase_la_dice_la_plaza_no_el_nombre(found):
    assert found["crypto.binance.usdm.BTCUSDT"].asset_class is AssetClass.CRYPTO
    assert found["commodity.binance.usdm.XAUUSDT"].asset_class is AssetClass.COMMODITY
    assert found["equity.binance.usdm.TSLAUSDT"].asset_class is AssetClass.EQUITY
    assert found["fx.binance.usdm.USDBRLUSDT"].asset_class is AssetClass.FX
    assert found["index.binance.usdm.DEFIUSDT"].asset_class is AssetClass.INDEX


def test_un_underlying_type_desconocido_entra_como_futuro_no_como_cripto():
    raro = {"symbols": [{"symbol": "ZZZUSDT", "contractType": "PERPETUAL", "status": "TRADING",
                         "quoteAsset": "USDT", "marginAsset": "USDT",
                         "underlyingType": "ALGO_NUEVO", "filters": []}]}
    (inst,) = discovery.from_binance_usdm(raro)
    assert inst.asset_class is AssetClass.FUTURE and inst.id.startswith("future.")


def test_el_trimestral_lleva_vencimiento_y_el_perpetuo_no(found):
    q = found["future.binance.usdm.BTCUSDT_261225"]
    assert q.expiry == 1_798_185_600_000 and q.asset_class is AssetClass.FUTURE
    assert found["crypto.binance.usdm.BTCUSDT"].expiry is None


def test_el_contrato_sale_de_los_filtros_reales(found):
    btc = found["crypto.binance.usdm.BTCUSDT"]
    assert (btc.tick, btc.lot, btc.min_notional) == (0.1, 0.001, 50.0)
    assert btc.multiplier == 1.0 and btc.currency == "USDT" and btc.quote_currency == "USDT"


def test_los_tradfi_entran_como_nivel_1(found):
    """T88: sus comisiones no se verificaron y operarlos exige firmar un contrato aparte."""
    for i in ("commodity.binance.usdm.XAUUSDT", "equity.binance.usdm.TSLAUSDT",
              "fx.binance.usdm.USDBRLUSDT"):
        assert found[i].tradable_level is TradableLevel.RESEARCH
    assert found["crypto.binance.usdm.BTCUSDT"].tradable_level is TradableLevel.OPERATIONAL


def test_el_cotizado_en_usdc_conserva_su_moneda(found):
    assert found["crypto.binance.usdm.BTCUSDC"].quote_currency == "USDC"


def test_todo_lo_descubierto_es_24_7_y_declara_su_fuente(found):
    for inst in found.values():
        assert inst.calendar_id == "24/7"
        assert inst.source == discovery.BINANCE_USDM_SOURCE
        assert inst.has(DataCapability.CANDLES, DataCapability.FUNDING)


def test_descubrir_dos_veces_da_lo_mismo(payload):
    assert discovery.from_binance_usdm(payload) == discovery.from_binance_usdm(payload)


def test_un_simbolo_sin_tipo_de_contrato_se_ignora():
    assert discovery.from_binance_usdm({"symbols": [{"symbol": "X"}, {"contractType": "P"}]}) == []
    assert discovery.from_binance_usdm({}) == []


# --- hechos fechados ------------------------------------------------------
def test_alta_se_fecha_con_el_onboard_de_la_plaza(found):
    btc = found["crypto.binance.usdm.BTCUSDT"]
    (ev,) = discovery.diff_events(None, btc, t=T0)
    assert ev.kind is EventKind.LISTED and ev.t == btc.listed_at and ev.observed_at == T0


def test_cambio_de_estado_se_fecha_al_observarlo(found):
    btc = found["crypto.binance.usdm.BTCUSDT"]
    parado = btc.model_copy(update={"status": InstrumentStatus.SUSPENDED})
    (ev,) = discovery.diff_events(btc, parado, t=T0)
    assert ev.kind is EventKind.SUSPENDED and ev.t == T0 and "active → suspended" in ev.detail
    (vuelta,) = discovery.diff_events(parado, btc, t=T0 + 1)
    assert vuelta.kind is EventKind.RESUMED


def test_cambio_de_contrato_dice_que_campo_cambio(found):
    btc = found["crypto.binance.usdm.BTCUSDT"]
    (ev,) = discovery.diff_events(btc, btc.model_copy(update={"tick": 0.5}), t=T0)
    assert ev.kind is EventKind.CONTRACT_CHANGE and "tick" in ev.detail and "0.5" in ev.detail


def test_sin_cambios_no_hay_hechos(found):
    btc = found["crypto.binance.usdm.BTCUSDT"]
    assert discovery.diff_events(btc, btc, t=T0) == []


def test_no_se_comparan_fichas_de_instrumentos_distintos(found):
    with pytest.raises(ValueError, match="distintos"):
        discovery.diff_events(found["crypto.binance.usdm.BTCUSDT"],
                              found["crypto.binance.usdm.ETHUSDT"], t=T0)


def test_la_baja_se_anota_pero_no_cambia_el_estado_a_ciegas(found):
    btc, eth = (found["crypto.binance.usdm.BTCUSDT"], found["crypto.binance.usdm.ETHUSDT"])
    (ev,) = discovery.missing_from([btc, eth], [btc], t=T0)
    assert ev.instrument_id == eth.id and ev.kind is EventKind.DELISTED
    assert "exchangeInfo" in ev.detail
    ya_fuera = eth.model_copy(update={"status": InstrumentStatus.DELISTED})
    assert discovery.missing_from([btc, ya_fuera], [btc], t=T0) == []


# --- capa curada ----------------------------------------------------------
def test_la_fuente_enriquece_pero_no_borra_lo_verificado(found):
    """`exchangeInfo` no sabe que el subyacente del oro es CME ni que `SP500` es un alias."""
    bruto = found["commodity.binance.usdm.XAUUSDT"]
    assert bruto.underlying_calendar_id is None
    curado = registry.curate(bruto)
    assert curado.underlying_calendar_id == "CMES"
    assert curado.label == registry.XAUUSDT.label
    assert curado.tick == bruto.tick                      # el contrato lo sigue diciendo la plaza
    assert curado.tradable_level is bruto.tradable_level


def test_curar_no_toca_lo_que_no_esta_en_la_semilla(found):
    tsla = found["equity.binance.usdm.TSLAUSDT"]
    assert registry.curate(tsla) == tsla


# --- FX de referencia (Frankfurter / BCE) ---------------------------------
CURRENCIES = Path(__file__).parent.parent / "fixtures" / "instruments" / \
    "frankfurter_currencies.json"


@pytest.fixture(scope="module")
def fx() -> dict:
    cur = json.loads(CURRENCIES.read_text(encoding="utf-8"))
    return {i.id: i for i in discovery.from_frankfurter(cur)}


def test_los_pares_mayores_contra_el_euro(fx):
    assert set(fx) == {f"fx.ecb.EUR{c}" for c in ("USD", "JPY", "GBP", "CHF", "AUD", "CAD",
                                                  "NZD")}
    assert fx["fx.ecb.EURUSD"].aliases == ("EUR/USD",)


def test_el_fx_no_declara_volumen_de_ninguna_clase(fx):
    """Sin volumen declarado, la familia de flujo de `technical` y `vwap` quedan fuera por
    contrato: es el punto 4 de la lista de T87, puesto en el dato."""
    for inst in fx.values():
        assert inst.data_capabilities == frozenset({DataCapability.CANDLES})
        assert inst.market_structure.value == "quote_driven"


def test_el_fx_va_al_calendario_de_dias_habiles(fx):
    for inst in fx.values():
        assert inst.calendar_id == "24/5" and inst.underlying_calendar_id == "24/5"
        assert inst.tradable_level is TradableLevel.OPERATIONAL
        assert "BCE" in inst.source


def test_todas_las_divisas_si_se_piden():
    cur = json.loads(CURRENCIES.read_text(encoding="utf-8"))
    todas = discovery.from_frankfurter(cur, majors_only=False)
    assert len(todas) == len(cur) - 1          # todas menos la base
    assert all(i.asset_class is AssetClass.FX for i in todas)


def test_otra_base_y_sin_pares_degenerados():
    cur = {"EUR": "Euro", "USD": "US Dollar", "XX": "no es un código", "1USD": "tampoco"}
    (par,) = discovery.from_frankfurter(cur, base="USD")
    assert par.id == "fx.ecb.USDEUR" and par.currency == "EUR"
