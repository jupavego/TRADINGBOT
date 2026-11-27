"""T94 — la pasada de agentes de punta a punta sobre DuckDB (sin red, agentes de prueba):
lista corta → cola `deep_run` → `deep_results`/`opportunities` → vista publicada → `verify`."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("duckdb")

from eim.data import scanner_market as market  # noqa: E402
from eim.data.instruments_store import open_store  # noqa: E402
from eim.data.scanner_view import read_view  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.scanner import deep  # noqa: E402
from eim.scanner.__main__ import main  # noqa: E402
from eim.scanner.deep_service import deep_pass  # noqa: E402
from eim.scanner.service import ScannerError, ScannerService  # noqa: E402
from tests.scanner._helpers import DAY, T0, candles, perp  # noqa: E402
from tests.scanner.test_deep import FakeAgent  # noqa: E402

ASOF = T0 + 101 * DAY + 3_600_000
GOOD = ("AUSDT", "BUSDT", "CUSDT")


@pytest.fixture
def world(tmp_path, monkeypatch):
    st = Store(market.universe_root(tmp_path))
    for k, s in enumerate(GOOD):
        st.upsert_candles(s, "1d", candles(150, seed=k, drift=0.002 * k), "prueba")
    cat = open_store(tmp_path)
    cat.upsert([perp(s) for s in GOOD], t=T0)
    cat.close()
    fakes = [FakeAgent("ema", 0.6), FakeAgent("structure", 0.5),
             FakeAgent("microstructure", 1.0)]
    monkeypatch.setattr(deep, "_AGENTS", fakes)      # lo que corre el manejador `deep_run`
    return tmp_path


def test_without_a_sweep_it_says_so(world):
    svc = ScannerService(world, procs=1)
    with pytest.raises(ScannerError, match="sin barrido"):
        deep_pass(svc)
    svc.close()


def test_deep_pass_records_publishes_and_caches(world):
    svc = ScannerService(world, procs=1)
    s = svc.sweep(ASOF)
    d = deep_pass(svc)
    assert d["detail_json"]["base_run"] == s["run_id"] and d["n_shortlist"] == 3
    assert len(d["opportunities"]) == 3 and not d["detail_json"]["failed"]
    assert all(o["side"] == "largo" and o["run_id"] == s["run_id"] for o in d["opportunities"])
    stored = svc.store.opportunities_of(d["run_id"])
    assert {o["opportunity_id"] for o in stored} == {o["opportunity_id"]
                                                     for o in d["opportunities"]}
    res = svc.store.deep_results_of(d["run_id"])
    assert all("marco no soportado" in r["skipped"][0]["reason"] for r in res)
    v = read_view(world)
    assert v["mode"] == "ANALISIS" and v["status_label"] == "candidata, no validada"
    assert v["deep"]["n_opportunities"] == 3 and len(v["universe"]["rows"]) == 3
    assert v["universe"]["markets"][0]["abierto"] == 3            # perpetuos 24/7
    one = v["instruments"][stored[0]["instrument_id"]]
    assert [a["agent_id"] for a in one["ran"]] == ["ema", "structure"]
    again = deep_pass(svc)                                       # mismos datos: caché
    assert again["detail_json"]["queue"]["cached"] == 3
    assert [o["opportunity_id"] for o in again["opportunities"]] == \
        [o["opportunity_id"] for o in d["opportunities"]]
    status = json.loads((world / "scanner" / "status.json").read_text(encoding="utf-8"))
    assert status["last_deep"]["opportunities"] == 3
    svc.close()


def test_cli_deep_and_verify(world, capsys):
    assert main(["--data-dir", str(world), "--procs", "1", "sweep", "--asof", "latest"]) == 0
    capsys.readouterr()
    assert main(["--data-dir", str(world), "--procs", "1", "deep", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    oid = out["opportunities"][0]["opportunity_id"]
    assert main(["--data-dir", str(world), "--procs", "1", "verify", oid]) == 0
    assert "reproducida: sí" in capsys.readouterr().out
    assert main(["--data-dir", str(world), "--procs", "1", "verify", "op-nada"]) == 5


def test_runner_runs_the_agents_after_each_sweep(world):
    from eim.scanner.runner import run_loop

    said: list[str] = []
    svc = ScannerService(world, procs=1, clock=lambda: ASOF)
    assert run_loop(svc, once=True, sync=False, quotes=False, agents=True, say=said.append) == 0
    assert any(s.startswith("agentes ") and "3 candidatas" in s for s in said)
    assert read_view(world)["deep"]["n_opportunities"] == 3
