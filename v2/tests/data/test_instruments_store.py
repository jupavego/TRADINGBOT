"""Almacén del catálogo de instrumentos (T89): altas, bajas, historia e idempotencia."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eim.data.instruments_store import DB_NAME, AmbiguousKey, InstrumentsStore, open_store
from eim.instruments import discovery, registry
from eim.instruments.models import (
    AssetClass,
    EventKind,
    InstrumentStatus,
    TradableLevel,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "instruments" / \
    "binance_usdm_exchange_info.json"
T0 = 1_700_000_000_000
HOUR = 3_600_000


@pytest.fixture
def store():
    s = InstrumentsStore(":memory:")
    yield s
    s.close()


@pytest.fixture(scope="module")
def descubiertos() -> list:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return registry.curate_all(discovery.from_binance_usdm(payload))


def test_alta_de_la_semilla(store):
    res = store.upsert(registry.SEED, t=T0)
    assert (res.added, res.changed, res.unchanged) == (5, 0, 0)
    assert store.count() == 5
    assert res.events == 5


def test_el_alta_es_idempotente(store):
    store.upsert(registry.SEED, t=T0)
    otra = store.upsert(registry.SEED, t=T0 + HOUR)
    assert (otra.added, otra.changed, otra.unchanged, otra.events) == (0, 0, 5, 0)
    assert store.count() == 5
    assert len(store.events()) == 5


def test_resolver_por_id_simbolo_y_alias(store):
    store.upsert(registry.SEED, t=T0)
    assert store.resolve("crypto.binance.usdm.BTCUSDT").symbol == "BTCUSDT"
    assert store.resolve("BTCUSDT").id == "crypto.binance.usdm.BTCUSDT"
    assert store.resolve("SP500").id == "index.yahoo.^GSPC"
    assert store.resolve("^IXIC").id == "index.yahoo.^IXIC"
    assert store.get("NO_EXISTE") is None
    with pytest.raises(KeyError, match="no está en el catálogo"):
        store.resolve("NO_EXISTE")


def test_un_simbolo_ambiguo_no_se_resuelve_a_ciegas(store):
    """Dos instrumentos con el mismo símbolo nativo: antes que acertar por azar, levanta."""
    btc = registry.BTCUSDT
    gemelo = btc.model_copy(update={"id": "equity.otraplaza.BTCUSDT", "venue": "otraplaza",
                                    "asset_class": AssetClass.EQUITY})
    store.upsert([btc, gemelo], t=T0)
    assert store.get("crypto.binance.usdm.BTCUSDT") == btc        # por id, nunca hay duda
    with pytest.raises(AmbiguousKey, match="apunta a 2"):
        store.get("BTCUSDT")


def test_la_ficha_vuelve_igual_que_entro(store):
    """Ida y vuelta por DuckDB sin perder capacidades, alias ni niveles."""
    store.upsert(registry.SEED, t=T0)
    for inst in registry.SEED:
        assert store.resolve(inst.id) == inst


def test_filtros_del_catalogo(store, descubiertos):
    store.upsert(descubiertos, t=T0)
    assert store.symbols(asset_class=AssetClass.FX) == ("USDBRLUSDT",)
    assert store.list(status=InstrumentStatus.PENDING)[0].symbol == "GAIBUSDT"
    assert len(store.list(venue="binance")) == len(descubiertos)
    assert len(store.list(calendar_id="24/7")) == len(descubiertos)
    assert len(store.list(limit=3)) == 3
    operativos = {i.symbol for i in store.list(min_level=int(TradableLevel.OPERATIONAL))}
    assert operativos >= {"BTCUSDT", "ETHUSDT"}
    assert operativos.isdisjoint({"TSLAUSDT", "XAUUSDT", "USDBRLUSDT"})   # TradFi: nivel 1


def test_el_sesgo_de_supervivencia_queda_a_la_vista(store, descubiertos):
    store.upsert(descubiertos, t=T0)
    assert store.by_status() == {"active": 7, "pending": 1, "suspended": 2}


def test_cambio_de_estado_se_guarda_con_su_fecha(store, descubiertos):
    store.upsert(descubiertos, t=T0)
    btc = store.resolve("BTCUSDT")
    store.upsert([btc.model_copy(update={"status": InstrumentStatus.SUSPENDED})], t=T0 + HOUR)
    assert store.resolve("BTCUSDT").status is InstrumentStatus.SUSPENDED
    kinds = [(e.kind, e.t) for e in store.events(btc.id)]
    assert (EventKind.SUSPENDED, T0 + HOUR) in kinds


def test_cambio_de_contrato_se_guarda(store, descubiertos):
    store.upsert(descubiertos, t=T0)
    btc = store.resolve("BTCUSDT")
    res = store.upsert([btc.model_copy(update={"tick": 0.5})], t=T0 + HOUR)
    assert (res.added, res.changed) == (0, 1)
    cambios = [e for e in store.events(btc.id) if e.kind is EventKind.CONTRACT_CHANGE]
    assert len(cambios) == 1 and "tick" in cambios[0].detail


def test_repetir_el_mismo_hecho_no_lo_duplica(store, descubiertos):
    store.upsert(descubiertos, t=T0)
    btc = store.resolve("BTCUSDT")
    eventos = discovery.diff_events(None, btc, t=T0)
    assert store.add_events(eventos) == 0          # el alta ya está
    assert store.add_events([]) == 0


def test_sync_anota_la_baja_de_lo_que_la_plaza_deja_de_listar(store, descubiertos):
    store.upsert(descubiertos, t=T0)
    quedan = [i for i in descubiertos if i.symbol != "OMGUSDT"]
    res = store.sync(quedan, t=T0 + HOUR, scope={"venue": "binance"})
    assert res.added == res.changed == 0
    bajas = [e for e in store.events() if e.kind is EventKind.DELISTED]
    assert [e.instrument_id for e in bajas] == ["crypto.binance.usdm.OMGUSDT"]
    # la ficha sigue en el catálogo: desaparecer de un listado no es una retirada anunciada
    assert store.resolve("OMGUSDT").status is InstrumentStatus.SUSPENDED


def test_sin_ambito_no_se_dan_bajas_por_un_listado_parcial(store, descubiertos):
    store.upsert(descubiertos, t=T0)
    store.sync(descubiertos[:1], t=T0 + HOUR)
    assert [e for e in store.events() if e.kind is EventKind.DELISTED] == []


def test_la_baja_no_se_repite_en_cada_pasada(store, descubiertos):
    store.upsert(descubiertos, t=T0)
    quedan = [i for i in descubiertos if i.symbol != "OMGUSDT"]
    store.sync(quedan, t=T0 + HOUR, scope={"venue": "binance"})
    store.sync(quedan, t=T0 + HOUR, scope={"venue": "binance"})
    assert len([e for e in store.events() if e.kind is EventKind.DELISTED]) == 1


def test_el_descubrimiento_enriquece_la_semilla_sin_romperla(store, descubiertos):
    """Primero la semilla, luego la plaza: gana el contrato real y se conserva lo curado."""
    store.upsert(registry.SEED, t=T0)
    store.sync(descubiertos, t=T0 + HOUR, scope={"venue": "binance"})
    btc = store.resolve("BTCUSDT")
    assert btc.tick == 0.1 and btc.lot == 0.001          # lo que dice la plaza
    xau = store.resolve("XAUUSDT")
    assert xau.underlying_calendar_id == "CMES"          # lo verificado en T88, intacto
    assert xau.label == registry.XAUUSDT.label
    assert store.resolve("SP500").id == "index.yahoo.^GSPC"   # el alias legado sigue vivo


def test_version_de_esquema_distinta_no_entra(store):
    mala = registry.BTCUSDT.model_copy(update={"schema_version": "0.9.0"})
    with pytest.raises(ValueError, match="schema_version"):
        store.upsert([mala], t=T0)


def test_en_disco_y_con_su_nombre(tmp_path):
    s = open_store(tmp_path)
    s.upsert(registry.SEED, t=T0)
    s.close()
    assert (tmp_path / DB_NAME).exists()
    otra = open_store(tmp_path)
    assert otra.count() == 5 and otra.resolve("SP500").label == registry.SP500.label
    otra.close()


def test_un_alias_no_puede_ser_de_dos_instrumentos(store):
    """El alias legado es el camino de compatibilidad: si resolviera a dos, no sirve de nada."""
    store.upsert([registry.SP500], t=T0)
    impostor = registry.NASDAQ.model_copy(update={"aliases": ("SP500",)})
    with pytest.raises(AmbiguousKey, match="ya es de"):
        store.upsert([impostor], t=T0 + HOUR)
    assert store.resolve("SP500").id == registry.SP500.id
