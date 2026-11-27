"""T93 — el servicio de punta a punta sobre un almacén y un catálogo de prueba (sin red):
embudo con motivos, registro en `scanner.duckdb`, barrido reproducible, caché de la lista corta,
ritmo rápido, reanudación, latido, relleno y la medición del presupuesto."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("duckdb")

from eim.data import scanner_market as market  # noqa: E402
from eim.data.instruments_store import open_store  # noqa: E402
from eim.data.scanner_store import ScannerStore, open_scanner_store  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.instruments.models import InstrumentStatus  # noqa: E402
from eim.scanner import budget  # noqa: E402
from eim.scanner.__main__ import main  # noqa: E402
from eim.scanner.runner import run_loop  # noqa: E402
from eim.scanner.service import ScannerError, ScannerService  # noqa: E402
from tests.scanner._helpers import DAY, T0, candles, perp  # noqa: E402

ASOF = T0 + 101 * DAY + 3_600_000
GOOD = ("AUSDT", "BUSDT", "BTCUSDT", "CUSDT", "DUSDT", "EUSDT")


@pytest.fixture
def world(tmp_path):
    root = market.universe_root(tmp_path)
    st = Store(root)
    for k, s in enumerate(GOOD):
        st.upsert_candles(s, "1d", candles(150, seed=k, drift=0.002 * k), "prueba")
    st.upsert_candles("OLDUSDT", "1d", candles(150, seed=9, end_t=T0 + 80 * DAY), "prueba")
    st.upsert_candles("THINUSDT", "1d", candles(150, seed=8, volume=10.0), "prueba")
    st.upsert_candles("NEWUSDT", "1d", candles(20, seed=7), "prueba")
    cat = open_store(tmp_path)
    cat.upsert([perp(s) for s in (*GOOD, "OLDUSDT", "THINUSDT", "NEWUSDT", "OPENAIUSDT")]
               + [perp("GONEUSDT", status=InstrumentStatus.DELISTED)], t=T0)
    cat.close()
    return tmp_path


def svc_of(path, **kw) -> ScannerService:
    return ScannerService(path, procs=1, **kw)


def test_a_wide_spread_excludes_at_stage_two(world):
    svc = svc_of(world, quotes_fn=lambda: {"BUSDT": (1.0, 2.0, ASOF)})
    s = svc.sweep(ASOF, process_deep=False)
    assert s["n_stage2"] == 5 and s["detail_json"]["exclusions"]["spread"] == 1
    assert s["detail_json"]["notes"] == {"spread_sin_medir": 5}
    svc.close()


def test_sweep_filters_scores_and_records_everything(world):
    svc = svc_of(world)
    s = svc.sweep(ASOF)
    assert (s["n_catalog"], s["n_stage1"], s["n_stage2"]) == (11, 9, 6)
    assert s["detail_json"]["exclusions"] == {"dato_viejo": 1, "estado": 1, "liquidez": 1,
                                              "pocas_velas": 1, "pre_opv": 1}
    assert s["detail_json"]["notes"] == {"spread_sin_medir": 6}
    assert s["ms_per_instrument"] > 0 and s["n_shortlist"] == 6   # el presupuesto: `budget`
    assert s["detail_json"]["queue"]["done"] == 6
    rows = svc.store.scores_of(s["run_id"])
    assert [r["rank"] for r in rows] == list(range(1, 7))
    assert all(r["data_hash"] and r["last_t"] == T0 + 100 * DAY for r in rows)
    assert svc.store.exclusion_counts(s["run_id"])["pre_opv"] == 1
    svc.close()


def test_the_sweep_is_reproducible_and_the_shortlist_hits_the_cache(world):
    svc = svc_of(world)
    a, b = svc.sweep(ASOF), svc.sweep(ASOF)
    assert a["fingerprint"] == b["fingerprint"] and a["run_id"] != b["run_id"]
    assert a["detail_json"]["queue"]["cached"] == 0
    assert b["detail_json"]["queue"]["cached"] == b["n_shortlist"] == 6
    svc.close()


def test_deep_prep_says_which_agents_could_run_without_running_them(world):
    svc = svc_of(world)
    s = svc.sweep(ASOF)
    job = svc.store.by_state("done", s["run_id"])[0]
    r = job.result
    assert r["n_bars"] == 150 and r["volume"] == "real" and r["fields"] == ["candles"]
    assert {"ema", "plan", "technical"} <= set(r["eligible"])
    assert "marco no soportado" in r["ineligible"]["microstructure"]
    assert "aquí no corre ningún agente" in r["note"]
    svc.close()


def test_fast_rhythm_alerts_on_what_was_scored(world):
    quotes: dict = {}
    svc = svc_of(world, quotes_fn=lambda: quotes)
    assert svc.fast(ASOF)["status"] == "sin_barrido"
    svc.sweep(ASOF)                                   # sin cotizaciones: se puntúan los 6
    quotes.update({"AUSDT": (1e6, 1e6 + 1, ASOF), "BUSDT": (1.0, 2.0, ASOF)})
    out = svc.fast(ASOF)
    assert out["detail_json"]["checked"] == 2        # los otros 4: sin cotización (se dice)
    assert out["alerts"] == 3                         # A: precio · B: precio y diferencial
    assert out["detail_json"]["skipped"] == {"sin_cotizacion": 4}
    status = json.loads((world / "scanner" / "status.json").read_text(encoding="utf-8"))
    assert status["last_fast"]["alerts"] == out["alerts"] and "last_sweep" in status
    svc.close()


def test_empty_catalog_is_said_not_guessed(tmp_path):
    svc = svc_of(tmp_path)
    with pytest.raises(ScannerError, match="catálogo vacío"):
        svc.sweep(ASOF)
    svc.close()


def test_queue_survives_a_restart(world):
    svc = svc_of(world)
    s = svc.sweep(ASOF, process_deep=False)
    pending = svc.store.counts(s["run_id"])["pending"]
    svc.close()
    store = open_scanner_store(world)
    job = store.ready(10**15, 1)[0]
    store.update(job.with_(state="running", attempts=1))         # «se cayó» con este en curso
    store.close()
    svc2 = svc_of(world)
    assert svc2.queue.resume() == 1
    st = svc2.queue.run_pending()
    assert st.done == pending and svc2.store.counts(s["run_id"])["done"] == pending
    svc2.close()


def test_runner_beats_resumes_and_refuses_a_second_instance(world):
    from eim.operation.watchdog import instance_lock

    svc = svc_of(world)
    assert run_loop(svc, once=True, sync=False, quotes=False, say=lambda *_: None) == 0
    hb = json.loads((world / "scanner" / "heartbeat.json").read_text(encoding="utf-8"))
    assert hb["state"] == "detenido" and hb["cycles"] == 1
    lock = instance_lock(world / "scanner" / "scanner.lock")
    try:
        assert run_loop(svc_of(world), once=True, sync=False, quotes=False,
                        say=lambda *_: None) == 2
    finally:
        lock.close()


class FakeFutures:
    def __init__(self, cs):
        self.cs, self.calls = cs, 0

    def klines(self, symbol, timeframe, start, end, **_kw):
        self.calls += 1
        return [c for c in self.cs if start <= c.t < end]

    def request(self, path, params=None):
        assert path == "/fapi/v1/exchangeInfo"
        raw = {"contractType": "PERPETUAL", "status": "TRADING", "quoteAsset": "USDT",
               "marginAsset": "USDT", "underlyingType": "COIN", "filters": []}
        return {"symbols": [raw | {"symbol": "AUSDT", "pair": "AUSDT"},
                            raw | {"symbol": "ZUSDT", "pair": "ZUSDT"}]}


def test_sync_symbol_fills_only_what_is_missing(tmp_path):
    root = market.universe_root(tmp_path)
    cs = candles(30, end_t=T0 + 29 * DAY)
    f = FakeFutures(cs)
    now = T0 + 30 * DAY + 5
    got = market.sync_symbol(root, "AUSDT", "1d", now, 520, futures=f)
    assert got["fetched"] == 30 and Store(root).count("AUSDT", "1d") == 30
    assert market.sync_symbol(root, "AUSDT", "1d", now, 520, futures=f)["up_to_date"]
    assert f.calls == 1


def test_refresh_catalog_is_the_t89_discovery(tmp_path):
    out = market.refresh_catalog(tmp_path, futures=FakeFutures([]))
    assert out["found"] == 2 and out["added"] == 2
    insts, _ = market.read_catalog(tmp_path, "binance")
    assert {i.symbol for i in insts} == {"AUSDT", "ZUSDT"}


def test_budget_measures_and_renders(world):
    svc = ScannerService(world, procs=1, store=ScannerStore(":memory:"))
    m = budget.measure(svc, ASOF)
    svc.close()
    assert m["reproducible"] and m["cache_warm"] == 1.0 and m["ms_per_instrument"] > 0
    assert [r["n"] for r in m["projection"]] == [1_000, 10_000]
    md = budget.render(m)
    assert "Proyección" in md and "ms por instrumento" in md and "10,000" in md


def test_cli_sweep_and_status(world, capsys):
    assert main(["--data-dir", str(world), "--procs", "1", "sweep", "--asof", "latest"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["n_stage2"] == 6 and out["fingerprint"]
    assert main(["--data-dir", str(world), "status"]) == 0
    assert "last_sweep" in capsys.readouterr().out
