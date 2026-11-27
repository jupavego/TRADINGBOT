"""T213: colector de cadenas de opciones de Deribit con datos sintéticos (sin red).

Lo que se fija aquí: unidades (precios en BTC → USD para la calidad), qué es una fila incompleta,
que una toma está entera o no está, que no se repite la misma hora, la cadencia por presupuesto
y que el proveedor no devuelve nunca una respuesta a medias.
"""

from __future__ import annotations

import json

import httpx
import pytest

from eim.data import options_chain as oc
from eim.data.options_parse import expiry_quality, normalize, parse_name
from eim.data.providers.binance import ProviderError
from eim.data.providers.deribit import BOOK_PATH, DeribitPublic
from eim.data.providers.meta import DERIBIT, lookup
from tests.data.options_helpers import EXPIRY, T0, F, provider_for, raw_chain, smile


# --- nombres y filas ------------------------------------------------------------------------
def test_parse_name_reads_deribit_option_names():
    assert parse_name("BTC-25DEC26-90000-C") == ("BTC", EXPIRY, 90_000.0, "call")
    base, exp, k, kind = parse_name("BTC-5DEC26-95000-P")
    assert (base, k, kind) == ("BTC", 95_000.0, "put") and exp % 86_400_000 == 8 * 3_600_000
    assert parse_name("XRP_USDC-27DEC26-0d625-C")[2] == 0.625      # decimal con «d»
    for bad in ("BTC-PERPETUAL", "BTC-25DEC26", "BTC-25XYZ26-1000-C", "BTC-25DEC26-0-C", ""):
        assert parse_name(bad) is None


def test_incomplete_rows_are_dropped_with_a_reason_and_empty_sides_kept():
    raw = raw_chain()[:4]
    raw[0] = {**raw[0], "bid_price": None}                  # cara vacía: dato real, se guarda
    raw[1] = {**raw[1], "mark_iv": None}                    # incompleta
    raw[2] = {**raw[2], "instrument_name": "BTC-PERPETUAL"}  # no es una opción
    rows, dropped = normalize(raw)
    assert dropped == {"campos": 1, "nombre": 1} and len(rows) == 2
    assert rows[0]["bid"] is None and rows[0]["ask"] > 0
    assert set(rows[0]) >= {"instrument", "expiry", "strike", "kind", "bid", "ask", "mark",
                            "mark_iv", "underlying", "rate", "oi", "ts"}


def test_quality_converts_btc_prices_to_usd_and_recovers_the_smile():
    rows, _ = normalize(raw_chain())
    q = expiry_quality(rows, T0)
    assert q["status"] == "ok" and q["n_crossed"] == 0 and q["n_arbitrage"] == 0
    assert q["underlying"] == F and q["t_years"] > 0
    assert q["atm_iv"] == pytest.approx(smile(F), abs=3e-3)          # IV desde bid/ask en USD
    assert q["mark_atm_iv"] == pytest.approx(smile(F), abs=3e-3)     # IV de marca de Deribit
    assert q["skew_90_110"] == pytest.approx(smile(0.9 * F) - smile(1.1 * F), abs=6e-3)


def test_quality_flags_crossed_quotes_and_expired_series():
    raw = raw_chain()
    raw[5] = {**raw[5], "bid_price": raw[5]["ask_price"] * 2}       # cruzada
    rows, _ = normalize(raw)
    q = expiry_quality(rows, T0)
    assert q["status"] == "degradado" and q["n_crossed"] == 1
    assert expiry_quality(rows, EXPIRY + 1)["status"] == "vencida"


# --- toma y disco ---------------------------------------------------------------------------
def test_snapshot_writes_rows_and_quality_atomically(tmp_path):
    out = oc.take_snapshot(tmp_path, "btc", provider_for(raw_chain()), clock=lambda: T0)
    data, quality = oc.snapshot_paths(tmp_path, "BTC", T0)
    assert data.name == "14.jsonl.gz" and data.parent.name == "2026-11-27"
    assert out["already"] is False and out["rows"] == 26 and out["dropped"] == 0
    rows = oc.read_rows(data)
    assert len(rows) == 26 and rows == sorted(rows, key=lambda r: (r["expiry"], r["strike"],
                                                                  r["kind"]))
    meta = json.loads(quality.read_text(encoding="utf-8"))
    assert meta["source"] == "deribit-options" and meta["level"] == 1
    assert meta["currency"] == "BTC" and meta["n_expiries"] == 1 and "uso personal" in meta["use"]
    assert not list(data.parent.glob("*.tmp"))


def test_same_hour_is_not_taken_twice(tmp_path):
    oc.take_snapshot(tmp_path, "BTC", provider_for(raw_chain()), clock=lambda: T0)
    data, _ = oc.snapshot_paths(tmp_path, "BTC", T0)
    before = data.read_bytes()

    def must_not_call(_r):
        raise AssertionError("no debía llamar a la API")

    again = oc.take_snapshot(tmp_path, "BTC", provider_for(must_not_call),
                             clock=lambda: T0 + 30 * 60_000)
    assert again["already"] is True and data.read_bytes() == before


def test_a_failed_call_leaves_nothing_on_disk(tmp_path):
    broken = provider_for(lambda _r: httpx.Response(400, text="mal"))
    with pytest.raises(ProviderError):
        oc.take_snapshot(tmp_path, "BTC", broken, clock=lambda: T0)
    with pytest.raises(ValueError):                         # ni una fila completa
        oc.take_snapshot(tmp_path, "BTC", provider_for([{"instrument_name": "x"}]),
                         clock=lambda: T0)
    assert not (tmp_path / "options").exists() or not list((tmp_path / "options").rglob("*.gz"))


def test_coverage_counts_snapshots(tmp_path):
    assert oc.coverage(tmp_path, "BTC")["snapshots"] == 0
    for h in (0, 1):
        oc.take_snapshot(tmp_path, "BTC", provider_for(raw_chain()),
                         clock=lambda h=h: T0 + h * 3_600_000)
    c = oc.coverage(tmp_path, "BTC")
    assert c["snapshots"] == 2 and c["first"] == "2026-11-27T14:00Z" and c["bytes"] > 0


# --- volumen y cadencia ---------------------------------------------------------------------
def test_cadence_reduces_frequency_to_fit_the_budget():
    assert oc.choose_cadence(40_000, 1.0) == 1             # 0,96 MB/día
    assert oc.choose_cadence(50_000, 1.0) == 2             # 1,2 MB/día a la hora → cada 2 h
    assert oc.choose_cadence(2_000_000, 1.0) is None       # ni una toma al día cabe


def test_volume_plan_adds_eth_only_if_it_fits_with_btc():
    p = oc.plan_volume({"BTC": 20_000, "ETH": 15_000}, 1.0)
    assert p["currencies"] == ["BTC", "ETH"] and p["every_hours"] == 1
    assert p["mb_day"] == pytest.approx(0.84) and p["backups_mb_after_one_year"] > p["mb_year"]
    p = oc.plan_volume({"BTC": 30_000, "ETH": 15_000}, 1.0)
    assert p["currencies"] == ["BTC"] and p["every_hours"] == 1
    with pytest.raises(ValueError):
        oc.plan_volume({"ETH": 1}, 1.0)


def test_measure_saves_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = oc.measure(["BTC"], provider_for(raw_chain()), clock=lambda: T0)
    assert m["per_currency"]["BTC"]["rows"] == 26 and m["plan"]["currencies"] == ["BTC"]
    assert not list(tmp_path.rglob("*"))


def test_cli_snapshot_prints_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(oc, "DeribitPublic", lambda *a, **k: provider_for(raw_chain()))
    assert oc.main(["snapshot", "--data", str(tmp_path), "--currency", "BTC"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed[0]["rows"] == 26 and printed[0]["already"] is False


# --- proveedor y ficha ----------------------------------------------------------------------
def test_provider_asks_one_call_per_currency_for_options():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"result": raw_chain()[:2]})

    assert len(provider_for(handler).option_book_summary("btc")) == 2
    assert seen == [(BOOK_PATH, {"currency": "BTC", "kind": "option"})]


def test_provider_never_returns_a_partial_answer():
    calls = {"n": 0}

    def flaky(_r):
        calls["n"] += 1
        return httpx.Response(503 if calls["n"] == 1 else 200, json={"result": raw_chain()[:3]})

    assert len(provider_for(flaky).option_book_summary("BTC")) == 3 and calls["n"] == 2
    with pytest.raises(ProviderError):
        provider_for(lambda _r: httpx.Response(200, json={"result": {"no": "lista"}})
                     ).option_book_summary("BTC")
    with pytest.raises(ProviderError):
        provider_for(lambda _r: httpx.Response(200, json={"error": {"code": 1}})
                     ).option_book_summary("BTC")


def test_deribit_declares_a_level_1_personal_use_source():
    assert DeribitPublic.meta is DERIBIT and DERIBIT.coverage == 1
    assert "uso personal" in DERIBIT.license and "NO VERIFICADOS" in DERIBIT.license
    assert lookup("deribit-dvol") is DERIBIT and lookup("deribit-options") is DERIBIT
