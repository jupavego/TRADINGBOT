"""Compatibilidad hacia atrás del registro (T89, requisito 4).

Lo que estas pruebas fijan: derivar `SYMBOLS` y `FOCUS` del registro **no cambia su valor**, y
el símbolo de hoy (`BTCUSDT`, `SP500`) sigue siendo un identificador válido. Si alguien toca la
semilla y mueve el foco, el gate lo dice aquí, no en producción.
"""

from __future__ import annotations

import pytest

from eim.data import timeframes
from eim.data.providers import multi_asset
from eim.instruments import registry
from eim.instruments.models import AssetClass, DataCapability, MarketStructure, TradableLevel


def test_symbols_y_focus_no_cambian_de_valor():
    assert timeframes.SYMBOLS == ("BTCUSDT", "ETHUSDT")
    assert timeframes.FOCUS == ("BTCUSDT",)


def test_symbols_y_focus_salen_del_registro():
    assert timeframes.SYMBOLS == registry.store_symbols()
    assert timeframes.FOCUS == registry.focus_symbols()
    assert set(registry.FOCUS_IDS) <= set(registry.SYMBOL_IDS)


def test_el_foco_esta_en_la_semilla():
    for i in registry.SYMBOL_IDS:
        assert i in registry.by_id()


@pytest.mark.parametrize("key", ["BTCUSDT", "ETHUSDT", "XAUUSDT", "SP500", "NASDAQ",
                                 "^GSPC", "^IXIC", "crypto.binance.usdm.BTCUSDT"])
def test_los_identificadores_de_hoy_siguen_resolviendo(key):
    assert registry.resolve(key) is not None


def test_los_cinco_del_visor_estan_migrados():
    """Los cinco de `multi_asset.ASSETS` son las primeras entradas del catálogo."""
    assert set(registry.viewer_assets()) == set(multi_asset.ASSETS)
    assert len(registry.SEED) == len(multi_asset.ASSETS) == 5


def test_los_indices_son_nivel_1_porque_yahoo_no_tiene_licencia():
    """T88 §3: los Términos de Yahoo prohíben la recolección automatizada."""
    for inst in (registry.SP500, registry.NASDAQ):
        assert inst.tradable_level is TradableLevel.RESEARCH
        assert "sin licencia" in inst.source


def test_ningun_indice_declara_volumen():
    """El volumen de ^GSPC es suma de componentes: si se declarase, `vwap` correría en silencio."""
    for inst in (registry.SP500, registry.NASDAQ):
        assert inst.market_structure is MarketStructure.SYNTHETIC
        assert DataCapability.REAL_VOLUME not in inst.data_capabilities
        assert DataCapability.TICK_VOLUME not in inst.data_capabilities
        assert inst.data_capabilities == frozenset({DataCapability.CANDLES})


def test_los_perpetuos_declaran_funding_y_libro():
    for inst in (registry.BTCUSDT, registry.ETHUSDT):
        assert inst.has(DataCapability.CANDLES, DataCapability.FUNDING,
                        DataCapability.DEPTH_L2, DataCapability.REAL_VOLUME)
        assert inst.tradable_level is TradableLevel.OPERATIONAL
        assert inst.calendar_id == "24/7" and inst.underlying_calendar_id is None


def test_el_oro_de_binance_tiene_dos_calendarios():
    """T88: el contrato no cierra aunque su subyacente sí."""
    assert registry.XAUUSDT.asset_class is AssetClass.COMMODITY
    assert registry.XAUUSDT.calendar_id == "24/7"
    assert registry.XAUUSDT.underlying_calendar_id == "CMES"
    assert registry.XAUUSDT.tradable_level is TradableLevel.RESEARCH


def test_cada_ficha_de_la_semilla_declara_su_fuente():
    for inst in registry.SEED:
        assert inst.source and inst.label
        assert inst.id.endswith(inst.symbol)


def test_los_ids_de_la_semilla_son_unicos_y_sus_claves_no_chocan():
    ids = [i.id for i in registry.SEED]
    assert len(set(ids)) == len(ids)
    keys: list[str] = []
    for inst in registry.SEED:
        keys += list(inst.keys)
    assert len(set(keys)) == len(keys)
