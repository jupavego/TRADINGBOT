"""DVOL de Deribit: proveedor con recorte grabado, paginación, almacén y cobertura (sin red)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from eim.data.dvol import KIND, TIMEFRAME, coverage, main, sync
from eim.data.providers.binance import ProviderError
from eim.data.providers.deribit import HISTORY_START_MS, PATH, DeribitPublic
from eim.data.store import Store

FIX = Path(__file__).parent.parent / "fixtures" / "dvol" / "btc_2021-03-24_2021-04-01_1h.json"
H = 3_600_000
RECORDED = json.loads(FIX.read_text(encoding="utf-8"))
FIRST_T = HISTORY_START_MS
LAST_T = FIRST_T + 192 * H  # 193 velas horarias en el recorte


def _provider(handler, *, now: int, **kw) -> DeribitPublic:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://deribit.test")
    return DeribitPublic(client, clock=lambda: now, sleep=lambda _s: None, **kw)


def _recorded(request: httpx.Request) -> httpx.Response:
    """Devuelve el recorte real; comprueba que la ventana pedida es la grabada."""
    assert request.url.path == PATH
    return httpx.Response(200, json=RECORDED["pages"][0]["body"])


# --- proveedor --------------------------------------------------------------
def test_recorded_page_parses_into_ordered_closed_candles():
    p = _provider(_recorded, now=LAST_T + H)
    out = p.volatility_index("BTC", FIRST_T, LAST_T + H)
    assert len(out) == 193
    assert [c.t for c in out] == sorted(c.t for c in out)
    assert out[0].t == FIRST_T and out[-1].t == LAST_T
    assert all(c.l <= min(c.o, c.c) <= max(c.o, c.c) <= c.h and c.v == 0.0 for c in out)
    assert 50.0 < out[0].c < 150.0  # DVOL es sigma anualizada en %


def test_candle_still_forming_is_dropped():
    p = _provider(_recorded, now=LAST_T + H // 2)  # la última vela aún no ha cerrado
    out = p.volatility_index("BTC", FIRST_T, LAST_T + H)
    assert [c.t for c in out][-1] == LAST_T - H
    assert len(out) == 192


def test_pagination_walks_backwards_with_continuation():
    """Dos páginas: la API devuelve las 1 000 más recientes y `continuation` para seguir atrás."""
    rows = [[FIRST_T + i * H, 40.0, 41.0, 39.0, 40.5] for i in range(1500)]
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        end = int(request.url.params["end_timestamp"])
        seen.append(end)
        page = [r for r in rows if r[0] <= end][-1000:]
        cont = page[0][0] - H if len(page) == 1000 else None
        return httpx.Response(200, json={"result": {"data": page, "continuation": cont}})

    p = _provider(handler, now=FIRST_T + 1500 * H)
    out = p.volatility_index("BTC", FIRST_T, FIRST_T + 1500 * H)
    assert len(seen) == 2 and seen[1] < seen[0]
    assert len(out) == 1500 and out[0].t == FIRST_T


def test_api_error_and_bad_status_raise_provider_error():
    def broken(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"code": 10001, "message": "nope"}})

    with pytest.raises(ProviderError):
        _provider(broken, now=LAST_T).volatility_index("BTC", FIRST_T, LAST_T)
    with pytest.raises(ProviderError):
        _provider(lambda _r: httpx.Response(400, text="mal"),
                  now=LAST_T).volatility_index("BTC", FIRST_T, LAST_T)


def test_retries_a_transient_status_then_succeeds():
    calls = {"n": 0}

    def flaky(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="luego")
        return httpx.Response(200, json=RECORDED["pages"][0]["body"])

    out = _provider(flaky, now=LAST_T + H).volatility_index("BTC", FIRST_T, LAST_T + H)
    assert calls["n"] == 2 and len(out) == 193


# --- almacén y cobertura ----------------------------------------------------
def test_sync_stores_the_series_and_reports_full_coverage(tmp_path):
    store = Store(tmp_path)
    p = _provider(_recorded, now=LAST_T + H)
    out = sync(store, "btc", FIRST_T, LAST_T + H, provider=p)
    assert out["currency"] == "BTC" and out["fetched"] == 193 and out["rows"] == 193
    assert out["coverage"] == 1.0 and out["first"] == "2021-03-24T00:00:00Z"
    arrays = store.read_arrays("BTC", TIMEFRAME, kind=KIND)
    assert len(arrays["t"]) == 193 and arrays["c"][0] > 0


def test_sync_is_idempotent_and_resumes_from_the_last_candle(tmp_path):
    store = Store(tmp_path)
    p = _provider(_recorded, now=LAST_T + H)
    sync(store, "BTC", FIRST_T, LAST_T + H, provider=p)
    windows: list[tuple[int, int]] = []

    def record(request: httpx.Request) -> httpx.Response:
        windows.append((int(request.url.params["start_timestamp"]),
                        int(request.url.params["end_timestamp"])))
        return _recorded(request)

    again = sync(store, "BTC", provider=_provider(record, now=LAST_T + H))
    assert again["rows"] == 193  # nada duplicado
    assert windows[0][0] == LAST_T - 24 * H  # rehace el borde, no toda la historia


def test_coverage_of_an_empty_store_says_so(tmp_path):
    assert coverage(Store(tmp_path), "BTC") == {
        "source": "deribit-dvol", "first": None, "last": None, "rows": 0, "coverage": None}


def test_cli_writes_the_store_and_prints_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("eim.data.dvol.DeribitPublic",
                        lambda *a, **k: _provider(_recorded, now=LAST_T + H))
    assert main(["--data", str(tmp_path), "--currency", "BTC",
                 "--from", "2021-03-24T00:00:00Z", "--to", "2021-04-01T01:00:00Z"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed[0]["rows"] == 193
    assert Store(tmp_path).count("BTC", TIMEFRAME, kind=KIND) == 193
