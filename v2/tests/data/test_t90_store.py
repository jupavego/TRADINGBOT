"""T90 sobre el almacén: por instrumento, crudo y ajustado separados, procedencia, huecos con
calendario, marcos de sesión en el snapshot y regresión de BTC/ETH. Sin red."""

from __future__ import annotations

import pytest

from eim.core import Candle
from eim.data import Store, adjust, build_snapshot
from eim.data.instrument_snapshot import build_instrument_snapshot
from eim.data.providers.meta import SourceMeta
from eim.data.quality_io import series_quality
from eim.data.series import InstrumentData, storage_key
from eim.data.timeframes import tf_offset
from eim.instruments import registry
from tests.data.t90_helpers import ACME, ACME_247, DAY, EURUSD, HOUR, load, ms, needs_xcals

FIXMETA = SourceMeta(name="fixture-t90", coverage=1, license="sintética, solo pruebas",
                     delay_ms=0)
WEEK = 7 * DAY


def _acme(tmp_path, inst=ACME) -> tuple[InstrumentData, dict]:
    d = load("equity_split_dividend")
    data = InstrumentData(Store(tmp_path), resolver=lambda k: inst)
    data.upsert_candles(inst, "1d", d["candles"], FIXMETA)
    data.upsert_actions(inst, d["events"], FIXMETA)
    return data, d


def _cs(start: int, step: int, n: int, p: float = 100.0) -> list[Candle]:
    return [Candle(t=start + k * step, o=p, h=p + 1, l=p - 1, c=p + 0.5, v=2.0)
            for k in range(n)]


# --- por instrumento ------------------------------------------------------------------------------
def test_clave_de_almacen_legada_en_la_semilla_y_por_id_en_el_resto():
    assert storage_key(registry.BTCUSDT) == "BTCUSDT"
    assert storage_key(registry.SP500) == "SP500"          # el alias legado, como el visor
    assert storage_key(ACME) == "equity.test.ACME"
    data = InstrumentData(Store("unused"))
    for key in ("BTCUSDT", "crypto.binance.usdm.BTCUSDT"):
        assert data.key(key) == "BTCUSDT"


def test_crudo_y_ajustado_nunca_se_mezclan(tmp_path):
    data, d = _acme(tmp_path)
    raw, evs = data.read_raw(ACME, "1d"), d["events"]
    assert raw == d["candles"]
    adj = data.read_candles(ACME, "1d")
    assert adj == adjust.adjust_candles(raw, evs) and adj != raw
    assert data.read_both(ACME, "1d") == (raw, adj)
    assert Store(tmp_path).read_candles("equity.test.ACME", "1d") == raw   # en disco, cruda
    # point-in-time: antes de la fecha ex del dividendo solo cuenta el split
    pit = data.read_candles(ACME, "1d", asof=evs[1].t - 1)
    assert pit == adjust.adjust_candles(raw, evs[:1])
    # ventana anterior al dividendo pero ajustada a hoy: su cierre previo se trae aparte
    cut = ms("2026-02-10")
    old = data.read_candles(ACME, "1d", end=cut, asof=ms("2026-03-10"))
    assert old == [c for c in adj if c.t < cut]
    assert data.read_candles(ACME, "1d", adjusted=False) == raw


def test_eventos_factores_y_procedencia(tmp_path):
    data, d = _acme(tmp_path)
    got = data.read_actions(ACME)
    assert [(e.t, e.split, e.dividend, e.roll) for e in got] == [
        (e.t, e.split, e.dividend, e.roll) for e in d["events"]]
    assert {e.source for e in got} == {"fixture-t90"}
    fs = data.write_adj_factor(ACME, "1d")
    assert len(fs) == 2 and data.read_adj_factor(ACME, "1d") == fs
    assert data.provenance(ACME, "candles", "1d") == FIXMETA
    assert data.provenance(ACME, "corporate_actions") == FIXMETA
    assert data.provenance(ACME, "quotes") is None              # serie inexistente


def test_series_anteriores_a_t90_sacan_su_ficha_del_catalogo(tmp_path):
    store = Store(tmp_path)
    store.upsert_candles("BTCUSDT", "1h", _cs(0, HOUR, 3), "binance-futures")
    meta = InstrumentData(store).provenance("BTCUSDT", "candles", "1h")
    assert meta.name == "binance-futures" and meta.coverage == 2


def test_cotizaciones_fundamentales_y_curva(tmp_path):
    data = InstrumentData(Store(tmp_path), resolver=lambda k: ACME)
    data.upsert_quotes(ACME, [(1, 99.5, 100.5, 10.0, None), (2, 99.6, 100.4, None, None)],
                       FIXMETA)
    assert data.read_quotes(ACME) == [(1, 99.5, 100.5, 10.0, None), (2, 99.6, 100.4, None, None)]
    data.upsert_fundamentals(ACME, "eps", [(ms("2026-02-01"), 1.25)], FIXMETA)
    assert data.read_fundamentals(ACME, "eps") == [(ms("2026-02-01"), 1.25)]
    data.upsert_curve("US-TREASURY-PAR", "10Y", [(ms("2026-02-02"), 4.21)], FIXMETA)
    assert data.read_curve("US-TREASURY-PAR", "10Y") == [(ms("2026-02-02"), 4.21)]
    assert data.provenance("US-TREASURY-PAR", "curve", "10Y") == FIXMETA
    with pytest.raises(ValueError):
        data.upsert_fundamentals(ACME, "../fuera", [], FIXMETA)


# --- huecos y calidad -----------------------------------------------------------------------------
def test_cripto_hueco_real_igual_que_antes(tmp_path):
    d = load("crypto_gap")
    store = Store(tmp_path)
    store.upsert_candles("BTCUSDT", "1h", d["candles"], "fixture")
    legacy = store.find_gaps("BTCUSDT", "1h")
    assert legacy == [tuple(d["gap"])]
    assert store.find_gaps("BTCUSDT", "1h", calendar="24/7") == legacy
    assert store.find_gaps("BTCUSDT", "1h", calendar=registry.BTCUSDT) == legacy
    q = series_quality(store, "BTCUSDT", "1h", asof=d["candles"][-1].t + HOUR,
                       instrument=registry.BTCUSDT)
    assert q.status == "rota" and q.missing_bars == 5 and q.closed_gaps == 0
    assert q.zero_volume == 0 and q.duplicates == 0 and q.stale is False


@needs_xcals
def test_accion_fin_de_semana_y_festivos_son_cierre_y_el_dia_que_falta_es_hueco(tmp_path):
    data, d = _acme(tmp_path)
    assert data.find_gaps(ACME, "1d") == [(d["missing_day"], d["missing_day"])]
    assert len(data.store.find_gaps("equity.test.ACME", "1d")) > 9   # la regla 24/7 de antes
    q = data.quality(ACME, "1d", asof=ms("2026-03-07T15:00"))
    assert q.status == "rota" and q.missing_bars == 1 and q.closed_gaps >= 9
    assert q.expected == len(d["candles"]) + 1 and q.off_session == 0 and q.stale is False


@needs_xcals
def test_fx_el_fin_de_semana_no_es_hueco(tmp_path):
    d = load("fx_weekend")
    data = InstrumentData(Store(tmp_path), resolver=lambda k: EURUSD)
    data.upsert_candles(EURUSD, "1h", d["candles"], FIXMETA)
    assert data.find_gaps(EURUSD, "1h") == [tuple(d["missing"])]
    q = data.quality(EURUSD, "1h", asof=d["candles"][-1].t + HOUR)
    assert q.status == "rota" and q.closed_gaps == 1 and q.zero_volume is None


# --- marcos de sesión en el snapshot y regresión de BTC/ETH ------------------------------------
def _legacy(store: Store) -> None:
    base = ms("2026-01-05")
    store.upsert_candles("BTCUSDT", "15m", _cs(base, HOUR // 4, 800), "s15m")
    store.upsert_candles("BTCUSDT", "1h", _cs(base, HOUR, 200), "s1h")
    store.upsert_candles("BTCUSDT", "4h", _cs(base, 4 * HOUR, 50), "s4h")
    store.upsert_candles("ETHUSDT", "1h", _cs(base, HOUR, 200, 3000.0), "s1h")
    store.upsert_series("funding", "BTCUSDT", "-", [(base + 8 * HOUR * k, 1e-4)
                                                    for k in range(20)], "bf")
    store.upsert_series("open_interest", "BTCUSDT", "1h", [(base + HOUR * k, 5.0 + k)
                                                           for k in range(200)], "boi")


def test_guardar_velas_diarias_no_cambia_los_snapshots_de_siempre(tmp_path):
    before, after = Store(tmp_path / "antes"), Store(tmp_path / "despues")
    _legacy(before)
    _legacy(after)
    after.upsert_candles("BTCUSDT", "1d", _cs(ms("2026-01-05"), DAY, 9), "s1d")
    after.upsert_candles("BTCUSDT", "1w", _cs(ms("2026-01-05"), WEEK, 2), "s1w")
    asof = ms("2026-01-12T05:00")
    for sym, tf in (("BTCUSDT", "15m"), ("BTCUSDT", "1h"), ("BTCUSDT", "4h"), ("ETHUSDT", "1h")):
        a = build_snapshot(before, sym, tf, 100, asof=asof)
        b = build_snapshot(after, sym, tf, 100, asof=asof)
        assert a.model_dump() == b.model_dump(), (sym, tf)
        assert not any(k.startswith(("quality:", "provenance:", "adjustment:"))
                       for k in b.sources)
    assert set(build_snapshot(after, "BTCUSDT", "4h", 10, asof=asof).candles_tf) == {"1h"}


def test_build_snapshot_admite_1d_y_1w(tmp_path):
    store = Store(tmp_path)
    _legacy(store)
    store.upsert_candles("BTCUSDT", "1d", _cs(ms("2026-01-05"), DAY, 9), "s1d")
    store.upsert_candles("BTCUSDT", "1w", _cs(ms("2026-01-05"), WEEK, 2), "s1w")
    snap = build_snapshot(store, "BTCUSDT", "1d", 30, asof=ms("2026-01-12T05:00"))
    assert [c.t for c in snap.candles][-1] == ms("2026-01-11")     # la del 12 sigue abierta
    assert set(snap.candles_tf) == {"4h", "1w"}       # vecinos intradía y semanal
    assert snap.candles_tf["1w"][-1].t == ms("2026-01-05")          # la del 12 sigue abierta
    assert snap.open_interest and all(t % DAY == 0 for t, _ in snap.open_interest)
    wk = build_snapshot(store, "BTCUSDT", "1w", 5, asof=ms("2026-01-19T01:00"))
    assert [c.t for c in wk.candles] == [ms("2026-01-05"), ms("2026-01-12")]
    assert all((t - tf_offset("1w")) % WEEK == 0 for t, _ in wk.open_interest)


# --- snapshot por instrumento ---------------------------------------------------------------------
def test_snapshot_de_instrumento_ajustado_y_con_marcas(tmp_path):
    data, d = _acme(tmp_path, ACME_247)
    asof = ms("2026-03-08")
    snap = build_instrument_snapshot(data.store, ACME_247, "1d", 100, asof,
                                     resolver=lambda k: ACME_247)
    raw = data.read_raw(ACME_247, "1d")
    assert snap.candles == adjust.adjust_candles(raw, d["events"])
    s = snap.sources
    assert s["instrument"] == "equity.test.ACME" and s["candles"] == "fixture-t90"
    assert "cobertura=1" in s["provenance:candles"] and "licencia=" in s["provenance:candles"]
    assert s["adjustment:candles"].startswith("ajustada (1 split, 1 dividendo)")
    assert "quality:candles" in s and "quality:candles" in snap.coverage


@needs_xcals
def test_la_vela_diaria_de_una_accion_cierra_con_su_sesion(tmp_path):
    data, d = _acme(tmp_path)
    late = build_instrument_snapshot(data.store, ACME, "1d", 100, ms("2026-03-06T22:00"),
                                     resolver=lambda k: ACME)
    assert late.candles[-1].t == ms("2026-03-06T14:30")       # cerró a las 21:00
    early = build_instrument_snapshot(data.store, ACME, "1d", 100, ms("2026-03-06T15:00"),
                                      resolver=lambda k: ACME)
    assert early.candles[-1].t == ms("2026-03-05T14:30")      # la del viernes sigue abierta
    assert late.sources["quality:candles"].startswith("rota: 1 huecos con mercado abierto")
